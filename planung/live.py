"""Live-Aktualisierung per Server-Sent Events.

Änderungen an Einteilungen, Abwesenheiten und Tagesinfos werden per ``pg_notify`` gemeldet
(``planung.dienste``). Je Worker-Prozess hält ein ``Verteiler`` genau eine PostgreSQL-Verbindung mit
``LISTEN planung`` und reicht die Ereignisse an alle offenen Teamplaner-Seiten des Prozesses weiter –
nicht eine Verbindung je Seite, die sonst die Datenbankverbindungen aufbrauchen könnte. Jede
Seite bekommt nur Ereignisse zu Personen, die das Konto sehen darf (Tagesinfos an alle); der Client lädt
daraufhin den betroffenen Ausschnitt neu. Ist die Sitzung abgelaufen oder das Konto deaktiviert, endet
der Stream beim nächsten Neuladen der Rechte.
"""

import asyncio
import json
import logging
import time
from collections import defaultdict
from importlib import import_module

import psycopg
from asgiref.sync import sync_to_async
from django.conf import settings
from django.contrib.auth import HASH_SESSION_KEY, SESSION_KEY
from django.http import HttpResponse, StreamingHttpResponse
from django.utils.crypto import constant_time_compare

from kern import rechte as kern_rechte
from kern import zwei_faktor
from kern.models import Konto

from . import rechte
from .dienste import KANAL

log = logging.getLogger(__name__)

PING_SEKUNDEN = 20
RECHTE_NEU_LADEN_SEKUNDEN = 60
MAX_STREAMS_JE_KONTO = 5  # je Worker-Prozess
WARTESCHLANGE = 200
# Nach einer Unterbrechung der LISTEN-Verbindung: Clients sollen alles neu laden
NEU_LADEN = json.dumps({"art": "neu_laden", "alle": True, "person_ids": [], "client": ""})
_PING = object()


def _conninfo():
    db = settings.DATABASES["default"]
    return psycopg.conninfo.make_conninfo(
        host=db["HOST"], port=db["PORT"], dbname=db["NAME"], user=db["USER"], password=db["PASSWORD"]
    )


class Verteiler:
    """Eine LISTEN-Verbindung je Prozess; jede offene Seite hat eine eigene Warteschlange."""

    def __init__(self):
        self.warteschlangen = set()
        self.aufgabe = None
        self.schleife = None

    def anmelden(self):
        schleife = asyncio.get_running_loop()
        if self.schleife is not schleife:  # anderer Event-Loop (z. B. in Tests): neu beginnen
            self.warteschlangen, self.aufgabe, self.schleife = set(), None, schleife
        warteschlange = asyncio.Queue(maxsize=WARTESCHLANGE)
        self.warteschlangen.add(warteschlange)
        if self.aufgabe is None or self.aufgabe.done():
            self.aufgabe = schleife.create_task(self._lauschen())
        return warteschlange

    def abmelden(self, warteschlange):
        self.warteschlangen.discard(warteschlange)

    def verteilen(self, nutzlast):
        for warteschlange in list(self.warteschlangen):
            try:
                warteschlange.put_nowait(nutzlast)
            except asyncio.QueueFull:
                # Seite kommt nicht nach: Rückstand verwerfen, stattdessen alles neu laden lassen
                while not warteschlange.empty():
                    warteschlange.get_nowait()
                warteschlange.put_nowait(NEU_LADEN)

    async def _lauschen(self):
        # Endet nur über die Prüfung der Schleife – ohne await dazwischen, damit eine gerade
        # angemeldete Seite nicht ohne Verbindung bleibt.
        nach_fehler = False
        while self.warteschlangen:
            try:
                async with await psycopg.AsyncConnection.connect(_conninfo(), autocommit=True) as verbindung:
                    await verbindung.execute(f"LISTEN {KANAL}")
                    if nach_fehler:
                        self.verteilen(NEU_LADEN)
                        nach_fehler = False
                    while self.warteschlangen:
                        async for meldung in verbindung.notifies(timeout=PING_SEKUNDEN):
                            self.verteilen(meldung.payload)
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 – Datenbank weg (Neustart, Update): später erneut versuchen
                log.exception("SSE: LISTEN-Verbindung unterbrochen")
                nach_fehler = True
                await asyncio.sleep(5)


verteiler = Verteiler()
_offen = defaultdict(int)  # offene Streams je Konto in diesem Prozess


def _noch_gueltig(konto_pk, sitzungsschluessel):
    """Frisch geladenes Konto, wenn Sitzung und Konto noch gelten – sonst None (abgemeldet, abgelaufen,
    deaktiviert, Passwort geändert, zweiter Faktor fehlt, Admin zu lange inaktiv)."""
    from kern.middleware import LETZTE_AKTIVITAET

    sitzung = import_module(settings.SESSION_ENGINE).SessionStore(sitzungsschluessel)
    if str(sitzung.get(SESSION_KEY)) != str(konto_pk):
        return None
    konto = Konto.objects.select_related("person").filter(pk=konto_pk).first()
    if konto is None or not konto.is_active:
        return None
    if not constant_time_compare(sitzung.get(HASH_SESSION_KEY, ""), konto.get_session_auth_hash()):
        return None
    if zwei_faktor.aktiv(konto):
        if sitzung.get(zwei_faktor.SITZUNG) != zwei_faktor.marke(konto):
            return None
    elif zwei_faktor.pflicht(konto):
        return None
    if kern_rechte.ist_admin(konto):
        letzte = sitzung.get(LETZTE_AKTIVITAET)
        if letzte is None or time.time() - letzte > settings.TEAMPLANER_ADMIN_INAKTIV_MINUTEN * 60:
            return None
    return konto


def _fuer_konto(nutzlast, sichtbar):
    """Ereignis für dieses Konto: nur sichtbare Personen-IDs, sonst gar nicht (None)."""
    daten = json.loads(nutzlast)
    daten.pop("akteur_id", None)
    if sichtbar is not None and not daten.get("alle"):
        ids = [p for p in daten.get("person_ids", []) if p in sichtbar]
        if not ids:
            return None
        daten["person_ids"] = ids
    return json.dumps(daten)


async def stream(request):
    konto = await request.auser()
    if not konto.is_authenticated:
        return HttpResponse(status=401)
    if _offen[konto.pk] >= MAX_STREAMS_JE_KONTO:
        return HttpResponse(status=429)
    sitzungsschluessel = request.session.session_key

    async def ereignisse():
        _offen[konto.pk] += 1
        warteschlange = verteiler.anmelden()
        try:
            sichtbar = await sync_to_async(rechte.sichtbare_personen_ids)(konto)
            geprueft = time.monotonic()
            yield "retry: 3000\n: verbunden\n\n"
            while True:
                try:
                    nutzlast = await asyncio.wait_for(warteschlange.get(), timeout=PING_SEKUNDEN)
                except TimeoutError:
                    nutzlast = _PING
                if time.monotonic() - geprueft > RECHTE_NEU_LADEN_SEKUNDEN:
                    aktuell = await sync_to_async(_noch_gueltig)(konto.pk, sitzungsschluessel)
                    if aktuell is None:
                        return
                    sichtbar = await sync_to_async(rechte.sichtbare_personen_ids)(aktuell)
                    geprueft = time.monotonic()
                if nutzlast is _PING:
                    yield ": ping\n\n"
                    continue
                ausgabe = _fuer_konto(nutzlast, sichtbar)
                if ausgabe is not None:
                    yield f"event: planung\ndata: {ausgabe}\n\n"
        finally:
            verteiler.abmelden(warteschlange)
            _offen[konto.pk] -= 1

    antwort = StreamingHttpResponse(ereignisse(), content_type="text/event-stream")
    antwort["Cache-Control"] = "no-cache"
    antwort["X-Accel-Buffering"] = "no"
    return antwort
