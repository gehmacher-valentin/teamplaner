"""Gemeinsames Bearbeiten von Notizen.

Der Browser führt gleichzeitige Änderungen mit Yjs zusammen (frontend/src/editor/gemeinsam.ts). Der
Server wertet den Yjs-Zustand nicht aus: Er speichert jede Änderung (``NotizAenderung``), verteilt sie
per Server-Sent Events und übernimmt Titel und Markdown, die der Browser mitschickt. Gemeldet wird wie
im Teamplaner über PostgreSQL ``NOTIFY`` (eigener Kanal), damit es über alle Worker-Prozesse hinweg
wirkt; der Stream liegt unter ``/api/planung/stream/``, für den die Webserver-Vorlagen das Puffern
schon abschalten.

Änderungen einer Notiz werden unter der Sperre der Notiz angelegt. Ihre IDs steigen deshalb in der
Reihenfolge der Commits, und ein Browser, der bis zur ID n alles hat, verpasst nichts, wenn er nur
spätere nachlädt.
"""

import asyncio
import base64
import binascii
import json
import time
from collections import defaultdict

from asgiref.sync import sync_to_async
from django.db import connection, transaction
from django.db.models import F, Max
from django.http import HttpResponse, JsonResponse, StreamingHttpResponse
from django.views.decorators.http import require_POST

from kern import rechte as kern_rechte
from kern.hilfen import TEXT_MAX_ZEICHEN, als_zahl, erfordert
from planung.live import (
    NEU_LADEN,
    PING_SEKUNDEN,
    RECHTE_NEU_LADEN_SEKUNDEN,
    Verteiler,
    _noch_gueltig,
)

from . import rechte
from .models import Notiz, NotizAenderung

KANAL = "notizen"
MAX_AENDERUNG_BYTES = 2_000_000
MAX_STREAMS_JE_KONTO = 10  # je Worker-Prozess
_PING = object()

verteiler = Verteiler(KANAL)
_offen = defaultdict(int)


def _b64(daten):
    return base64.b64encode(bytes(daten)).decode("ascii")


def _bytes(wert):
    """Base64 aus der Anfrage; None bei ungültigen oder zu großen Daten."""
    if not isinstance(wert, str) or len(wert) > MAX_AENDERUNG_BYTES * 4 // 3 + 4:
        return None
    try:
        return base64.b64decode(wert, validate=True)
    except (binascii.Error, ValueError):
        return None


def _melden(notiz_id, typ, **extra):
    nutzlast = json.dumps({"notiz": notiz_id, "typ": typ, **extra})

    def senden():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_notify(%s, %s)", [KANAL, nutzlast])

    transaction.on_commit(senden)


def startdaten(notiz):
    """Stand für den Browser beim Öffnen: zusammengefasster Zustand und alle Änderungen danach."""
    if notiz.pk is None:
        return {"notiz": None, "zustand": "", "aenderungen": [], "ab": 0}
    with transaction.atomic():
        gesperrt = Notiz.objects.select_for_update().only("yjs", "yjs_bis").get(pk=notiz.pk)
        aenderungen = list(NotizAenderung.objects.filter(notiz_id=notiz.pk).values_list("id", "daten"))
    return {
        "notiz": notiz.pk,
        "zustand": _b64(gesperrt.yjs) if gesperrt.yjs else "",
        "aenderungen": [_b64(d) for _i, d in aenderungen],
        "ab": aenderungen[-1][0] if aenderungen else gesperrt.yjs_bis,
    }


def _json(request):
    try:
        daten = json.loads(request.body)
    except (ValueError, UnicodeDecodeError):
        return None
    return daten if isinstance(daten, dict) else None


def _notiz_zum_schreiben(konto, pk):
    """Gesperrte Notiz, wenn das Konto sie bearbeiten darf; sonst eine Fehlerantwort."""
    notiz = Notiz.objects.select_for_update(of=("self",)).select_related("ordner").filter(pk=pk).first()
    if notiz is None:
        return None, HttpResponse(status=404)
    if not rechte.darf_notiz_schreiben(konto, notiz):
        return None, HttpResponse(status=403)
    return notiz, None


def _titel_und_text(notiz, daten):
    """Titel und Markdown aus der Anfrage übernehmen; gibt die geänderten Felder zurück (oder None bei
    ungültigen Angaben). Ein leerer Titel bleibt ungespeichert, der bisherige gilt weiter."""
    text, titel = daten.get("text"), daten.get("titel")
    if text is not None and (not isinstance(text, str) or len(text) > TEXT_MAX_ZEICHEN):
        return None
    if titel is not None and not isinstance(titel, str):
        return None
    felder = []
    if text is not None and text != notiz.text:
        notiz.text = text
        felder.append("text")
    titel = " ".join((titel or "").split())
    if titel and len(titel) <= 200 and titel != notiz.titel:
        notiz.titel = titel
        felder.append("titel")
    return felder


def _speichern(konto, notiz, felder, eigen):
    if not felder:
        return
    if eigen:
        notiz.geaendert_von = konto.person
        felder.append("geaendert_von")
    notiz.version = F("version") + 1
    notiz.save(update_fields=[*felder, "version", "geaendert_am"])


@require_POST
@erfordert(kern_rechte.darf_lesen)
def aenderung(request, pk):
    """Eine Yjs-Änderung speichern und verteilen; dazu Titel und Markdown, wie der Browser sie jetzt sieht.
    Ohne ``update`` nur Titel und Text abgleichen (nach Änderungen anderer)."""
    daten = _json(request)
    if daten is None:
        return HttpResponse(status=400)
    update = None
    if daten.get("update"):
        update = _bytes(daten["update"])
        if update is None:
            return HttpResponse(status=400)
    with transaction.atomic():
        notiz, fehler = _notiz_zum_schreiben(request.user, pk)
        if fehler:
            return fehler
        felder = _titel_und_text(notiz, daten)
        if felder is None:
            return HttpResponse(status=400)
        neu = NotizAenderung.objects.create(notiz=notiz, daten=update) if update else None
        _speichern(request.user, notiz, felder, eigen=bool(daten.get("eigen")))
        if neu:
            _melden(notiz.pk, "aenderung")
    return JsonResponse({"id": neu.pk if neu else None})


@require_POST
@erfordert(kern_rechte.darf_lesen)
def start(request, pk):
    """Erster Yjs-Stand einer Notiz, die es schon als Markdown gibt (oder gerade angelegt wurde). Wer
    zuerst kommt, legt ihn an; alle anderen bekommen 409 und laden den Stand neu."""
    daten = _json(request)
    zustand = _bytes(daten.get("zustand")) if daten else None
    if not zustand:
        return HttpResponse(status=400)
    with transaction.atomic():
        notiz, fehler = _notiz_zum_schreiben(request.user, pk)
        if fehler:
            return fehler
        if notiz.yjs or notiz.yjs_bis or NotizAenderung.objects.filter(notiz=notiz).exists():
            return HttpResponse(status=409)
        felder = _titel_und_text(notiz, daten)
        if felder is None:
            return HttpResponse(status=400)
        neu = NotizAenderung.objects.create(notiz=notiz, daten=zustand)
        _speichern(request.user, notiz, felder, eigen=True)
        _melden(notiz.pk, "aenderung")
    return JsonResponse({"id": neu.pk})


@require_POST
@erfordert(kern_rechte.darf_lesen)
def zusammenfassen(request, pk):
    """Der Browser schickt seinen Gesamtstand, der alle Änderungen bis ``bis`` enthält: Die einzelnen
    Änderungen werden durch ihn ersetzt, damit sie nicht endlos anwachsen."""
    daten = _json(request)
    zustand = _bytes(daten.get("zustand")) if daten else None
    bis = als_zahl(daten.get("bis")) if daten else None
    if not zustand or not bis:
        return HttpResponse(status=400)
    with transaction.atomic():
        notiz, fehler = _notiz_zum_schreiben(request.user, pk)
        if fehler:
            return fehler
        letzte = NotizAenderung.objects.filter(notiz=notiz).aggregate(m=Max("id"))["m"] or 0
        if bis <= notiz.yjs_bis or bis > letzte:
            return HttpResponse(status=204)
        notiz.yjs, notiz.yjs_bis = zustand, bis
        notiz.save(update_fields=["yjs", "yjs_bis"])
        NotizAenderung.objects.filter(notiz=notiz, id__lte=bis).delete()
    return HttpResponse(status=204)


@require_POST
@erfordert(kern_rechte.darf_lesen)
def anwesend(request, pk):
    """Wer die Notiz gerade bearbeitet: regelmäßig „da“, beim Verlassen „weg“."""
    daten = _json(request)
    client = daten.get("client") if daten else None
    if not isinstance(client, str) or not client or len(client) > 64:
        return HttpResponse(status=400)
    notiz = Notiz.objects.select_related("ordner").filter(pk=pk).first()
    if notiz is None:
        return HttpResponse(status=404)
    if not rechte.darf_notiz_schreiben(request.user, notiz):
        return HttpResponse(status=403)
    person = request.user.person
    _melden(notiz.pk, "da", client=client, person=person.pk, name=person.anzeigename, initialen=person.initialen,
            foto=person.foto_url, weg=bool(daten.get("weg")))
    return HttpResponse(status=204)


def _darf_lesen(konto_pk, sitzungsschluessel, pk):
    konto = _noch_gueltig(konto_pk, sitzungsschluessel)
    notiz = Notiz.objects.select_related("ordner").filter(pk=pk).first()
    return konto is not None and notiz is not None and rechte.darf_notiz_lesen(konto, notiz)


def _nachholen(pk, gesendet):
    """Ereignis mit allem nach ``gesendet``; (Text oder None, neue Position)."""
    with transaction.atomic():
        notiz = Notiz.objects.select_for_update().only("yjs", "yjs_bis").filter(pk=pk).first()
        if notiz is None:
            return None, gesendet
        teile = []
        if gesendet < notiz.yjs_bis and notiz.yjs:
            teile.append(_b64(notiz.yjs))
            gesendet = notiz.yjs_bis
        for i, daten in NotizAenderung.objects.filter(notiz_id=pk, id__gt=gesendet).values_list("id", "daten"):
            teile.append(_b64(daten))
            gesendet = i
    if not teile:
        return None, gesendet
    return f"id: {gesendet}\nevent: aenderung\ndata: {json.dumps({'daten': teile})}\n\n", gesendet


async def stream(request, pk):
    konto = await request.auser()
    if not konto.is_authenticated:
        return HttpResponse(status=401)
    sitzungsschluessel = request.session.session_key
    if not await sync_to_async(_darf_lesen)(konto.pk, sitzungsschluessel, pk):
        return HttpResponse(status=403)
    if _offen[konto.pk] >= MAX_STREAMS_JE_KONTO:
        return HttpResponse(status=429)
    # Nach einer Unterbrechung schickt der Browser die letzte ID selbst mit (Last-Event-ID)
    ab = als_zahl(request.headers.get("Last-Event-ID") or request.GET.get("ab")) or 0

    async def ereignisse():
        _offen[konto.pk] += 1
        warteschlange = verteiler.anmelden()
        try:
            yield "retry: 3000\n: verbunden\n\n"
            paket, gesendet = await sync_to_async(_nachholen)(pk, ab)
            if paket:
                yield paket
            geprueft = time.monotonic()
            while True:
                try:
                    nutzlast = await asyncio.wait_for(warteschlange.get(), timeout=PING_SEKUNDEN)
                except TimeoutError:
                    nutzlast = _PING
                if time.monotonic() - geprueft > RECHTE_NEU_LADEN_SEKUNDEN:
                    if not await sync_to_async(_darf_lesen)(konto.pk, sitzungsschluessel, pk):
                        return
                    geprueft = time.monotonic()
                if nutzlast is _PING:
                    yield ": ping\n\n"
                    continue
                daten = json.loads(nutzlast)
                if nutzlast == NEU_LADEN or (daten.get("notiz") == pk and daten.get("typ") == "aenderung"):
                    paket, gesendet = await sync_to_async(_nachholen)(pk, gesendet)
                    if paket:
                        yield paket
                elif daten.get("notiz") == pk and daten.get("typ") == "da":
                    daten.pop("notiz", None)
                    yield f"event: da\ndata: {json.dumps(daten)}\n\n"
        finally:
            verteiler.abmelden(warteschlange)
            _offen[konto.pk] -= 1

    antwort = StreamingHttpResponse(ereignisse(), content_type="text/event-stream")
    antwort["Cache-Control"] = "no-cache"
    antwort["X-Accel-Buffering"] = "no"
    return antwort
