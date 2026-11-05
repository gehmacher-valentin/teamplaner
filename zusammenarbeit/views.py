import json
import re

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils.formats import date_format
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from kern import rechte
from kern.heic import heic_umwandeln
from kern.models import Person, Protokolleintrag
from kern.protokoll import protokollieren
from planung import rechte as planungsrechte
from projekte.models import Aufgabe

from .dienste import erwaehnung_benachrichtigen, kommentar_benachrichtigen
from .models import Anhang, Erwaehnung, Kommentar

ERWAEHNUNG = re.compile(r"@\[(\d+)\]")
INLINE_TYPEN = {"image/png", "image/jpeg", "image/gif", "image/webp", "application/pdf"}
BILDFORMATE = {"PNG": "image/png", "JPEG": "image/jpeg", "GIF": "image/gif", "WEBP": "image/webp"}


def dateityp(datei):
    """Inhaltstyp für Vorschau und Anzeige im Browser – bei Bildern und PDF aus den Dateibytes, nicht
    aus der Angabe des Browsers. Was sich als Bild oder PDF ausgibt, aber keins ist, wird
    zum Download; alle anderen Typen liefert der Teamplaner ohnehin nur als Download aus."""
    from PIL import Image

    angabe = (datei.content_type or "")[:120]
    kopf = datei.read(5)
    datei.seek(0)
    if kopf == b"%PDF-":
        return "application/pdf"
    try:
        with Image.open(datei) as bild:
            format_ = bild.format
    except Exception:  # noqa: BLE001 – kein (unterstütztes) Bild
        format_ = None
    finally:
        datei.seek(0)
    if format_ in BILDFORMATE:
        return BILDFORMATE[format_]
    return "application/octet-stream" if angabe in INLINE_TYPEN else angabe

FELDNAMEN = {
    "titel": gettext_lazy("Titel"), "abschnitt": gettext_lazy("Abschnitt"), "verantwortlich": gettext_lazy("Verantwortlich"),
    "gewerk": gettext_lazy("Gewerk"), "beginn_am": gettext_lazy("Beginn"), "faellig_am": gettext_lazy("Fällig"),
    "status": gettext_lazy("Status"),
    "schaetzung_personentage": gettext_lazy("Schätzung"), "eltern": gettext_lazy("Hauptaufgabe"),
}


def _wert(wert):
    if wert in (None, ""):
        return "–"
    if isinstance(wert, dict):
        return wert.get("name", "")
    if isinstance(wert, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", wert):
        return f"{wert[8:10]}.{wert[5:7]}.{wert[:4]}"
    return str(wert)


def _zeitraum(daten):
    von, bis = _wert(daten.get("von")), _wert(daten.get("bis"))
    return von if von == bis else f"{von[:6]}–{bis}"


def verlauf_text(eintrag):
    d = eintrag.daten
    if eintrag.objekt_typ == "aufgabe":
        if eintrag.aktion == "angelegt":
            return _("hat die Aufgabe angelegt.")
        if eintrag.aktion == "geaendert":
            teile = []
            for feld, (alt, neu) in d.items():
                if feld == "beschreibung":
                    teile.append(_("Beschreibung bearbeitet"))
                elif feld in FELDNAMEN:
                    teile.append(f"{FELDNAMEN[feld]}: {_wert(alt)} → {_wert(neu)}")
            return _("hat geändert: %(teile)s") % {"teile": "; ".join(teile)}
    if eintrag.objekt_typ == "einteilung":
        person = _wert(d.get("person"))
        if eintrag.aktion == "angelegt":
            return _("hat die Aufgabe auf %(person)s, %(zeitraum)s eingeplant.") % {"person": person, "zeitraum": _zeitraum(d)}
        if eintrag.aktion == "geloescht":
            return _("hat die Einteilung von %(person)s (%(zeitraum)s) entfernt.") % {"person": person, "zeitraum": _zeitraum(d)}
        teile = [f"{_wert(a)} → {_wert(n)}" for _feld, (a, n) in d.items()]
        return _("hat eine Einteilung geändert: %(teile)s") % {"teile": "; ".join(teile)}
    if eintrag.objekt_typ == "unteraufgabe":
        texte = {"angelegt": _("hat die Unteraufgabe „%(t)s“ angelegt."), "erledigt": _("hat „%(t)s“ erledigt."),
                 "wieder_offen": _("hat „%(t)s“ wieder geöffnet."), "geloescht": _("hat die Unteraufgabe „%(t)s“ gelöscht."),
                 "hierher": _("hat „%(t)s“ hierher als Unteraufgabe verschoben."),
                 "weg": _("hat die Unteraufgabe „%(t)s“ woandershin verschoben.")}
        return texte.get(eintrag.aktion, eintrag.aktion) % {"t": d.get("titel", "")}
    if eintrag.objekt_typ == "abhaengigkeit":
        werte = {"vorher": _wert(d.get("vorher")), "nachher": _wert(d.get("nachher"))}
        if eintrag.aktion == "angelegt":
            return _("hat festgelegt: „%(vorher)s“ vor „%(nachher)s“.") % werte
        return _("hat die Abhängigkeit „%(vorher)s“ vor „%(nachher)s“ entfernt.") % werte
    if eintrag.objekt_typ == "anhang":
        if eintrag.aktion == "angelegt":
            return _("hat „%(name)s“ angehängt.") % {"name": d.get("name", "")}
        return _("hat den Anhang „%(name)s“ entfernt.") % {"name": d.get("name", "")}
    return f"{eintrag.objekt_typ} {eintrag.aktion}"


def _einteilung_sichtbar(konto, eintrag, sichtbar):
    if eintrag.objekt_typ != "einteilung":
        return True
    if sichtbar is None:
        return True
    person = eintrag.daten.get("person") or {}
    return isinstance(person, dict) and person.get("id") in sichtbar


def verlauf_eintraege(konto, aufgabe):
    """Kommentare und Änderungen chronologisch. Einteilungen von Personen,
    die das Konto im Teamplaner nicht sehen darf, werden ausgelassen."""
    sichtbar = planungsrechte.sichtbare_personen_ids(konto)
    kommentare = list(aufgabe.kommentare.select_related("autor__konto"))
    erwaehnte_ids = {int(i) for k in kommentare for i in ERWAEHNUNG.findall(k.text)}
    personen = {p.pk: p for p in Person.objects.filter(pk__in=erwaehnte_ids).select_related("konto", "erstellt_von")}
    eintraege = []
    for k in kommentare:
        platzhalter = [personen[int(i)] for i in dict.fromkeys(ERWAEHNUNG.findall(k.text))
                       if int(i) in personen and personen[int(i)].ist_platzhalter]
        eintraege.append({"art": "kommentar", "zeit": k.erstellt_am, "kommentar": k, "personen": personen,
                          "platzhalter": platzhalter,
                          "darf_loeschen": k.autor_id == konto.person_id or rechte.ist_admin(konto)})
    for p in Protokolleintrag.objects.filter(aufgabe_id=aufgabe.pk).select_related("akteur"):
        if _einteilung_sichtbar(konto, p, sichtbar):
            eintraege.append({"art": "verlauf", "zeit": p.zeitpunkt, "akteur": p.akteur, "text": verlauf_text(p)})
    return sorted(eintraege, key=lambda e: e["zeit"])


def _zurueck(request, aufgabe, anker):
    """Zurück zum Aufgabendetail: auf die Seite oder, von dort abgeschickt, in die Seitenleiste."""
    from projekte.views import offene_seitenleiste, seitenleiste_antwort

    if offene_seitenleiste(request):
        return seitenleiste_antwort(request, aufgabe.pk)
    return redirect(reverse("aufgabe", args=[aufgabe.pk]) + f"#{anker}")


@require_POST
@login_required
def kommentar_anlegen(request, pk):
    aufgabe = get_object_or_404(Aufgabe, pk=pk)
    if not rechte.darf_abschliessen_und_kommentieren(request.user):
        raise PermissionDenied
    text = (request.POST.get("text") or "").strip()[:5000]
    if not text:
        return _zurueck(request, aufgabe, "kommentare")
    text = ERWAEHNUNG.sub(lambda m: f"@ [{m.group(1)}]", text)  # keine gefälschten Erwähnungen
    try:
        zuordnung = json.loads(request.POST.get("erwaehnungen") or "{}")
    except ValueError:
        zuordnung = {}
    kandidaten = {p.pk: p for p in Person.objects.filter(pk__in=[v for v in zuordnung.values() if isinstance(v, int)]).select_related("konto", "erstellt_von__konto")}
    erwaehnt = []
    for name, pid in sorted(zuordnung.items(), key=lambda kv: -len(str(kv[0]))):
        person = kandidaten.get(pid)
        if person and f"@{name}" in text:
            text = text.replace(f"@{name}", f"@[{pid}]")
            erwaehnt.append(person)
    with transaction.atomic():
        kommentar = Kommentar.objects.create(aufgabe=aufgabe, autor=request.user.person, text=text)
        Erwaehnung.objects.bulk_create([Erwaehnung(kommentar=kommentar, person=p) for p in erwaehnt])
        erwaehnung_benachrichtigen(request.user, kommentar, erwaehnt)
        kommentar_benachrichtigen(request.user, kommentar, erwaehnt)
    return _zurueck(request, aufgabe, f"kommentar-{kommentar.pk}")


@require_POST
@login_required
def kommentar_loeschen(request, pk):
    kommentar = get_object_or_404(Kommentar.objects.select_related("aufgabe"), pk=pk)
    if kommentar.autor_id != request.user.person_id and not rechte.ist_admin(request.user):
        raise PermissionDenied
    aufgabe = kommentar.aufgabe
    kommentar.delete()
    messages.success(request, _("Kommentar gelöscht."))
    return _zurueck(request, aufgabe, "kommentare")


@require_POST
@login_required
def anhang_hochladen(request, pk):
    aufgabe = get_object_or_404(Aufgabe, pk=pk)
    if not rechte.darf_abschliessen_und_kommentieren(request.user):
        raise PermissionDenied
    datei = request.FILES.get("datei")
    if datei is None:
        return _zurueck(request, aufgabe, "anhaenge")
    max_mb = settings.TEAMPLANER_ANHANG_MAX_MB
    if datei.size > max_mb * 1024 * 1024:
        messages.error(request, _("Die Datei ist zu groß (höchstens %(mb)s MB).") % {"mb": max_mb})
        return _zurueck(request, aufgabe, "anhaenge")
    datei = heic_umwandeln(datei) or datei  # iPhone-Fotos als JPEG, damit jeder Browser sie zeigt
    anhang = Anhang.objects.create(
        aufgabe=aufgabe, datei=datei, dateiname=datei.name[:255], groesse=datei.size,
        content_type=dateityp(datei), hochgeladen_von=request.user.person,
    )
    protokollieren(request.user, "anhang", anhang.pk, "angelegt", {"name": anhang.dateiname}, aufgabe_id=aufgabe.pk)
    return _zurueck(request, aufgabe, "anhaenge")


@login_required
def anhang_herunterladen(request, pk):
    anhang = get_object_or_404(Anhang, pk=pk)
    if not rechte.darf_lesen(request.user):
        raise PermissionDenied
    try:
        datei = anhang.datei.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    inline = anhang.content_type in INLINE_TYPEN
    antwort = FileResponse(datei, as_attachment=not inline, filename=anhang.dateiname,
                           content_type=anhang.content_type if inline else "application/octet-stream")
    antwort["X-Content-Type-Options"] = "nosniff"
    antwort["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    return antwort


@require_POST
@login_required
def anhang_loeschen(request, pk):
    anhang = get_object_or_404(Anhang.objects.select_related("aufgabe__projekt"), pk=pk)
    aufgabe = anhang.aufgabe
    if anhang.hochgeladen_von_id != request.user.person_id and not rechte.darf_aufgaben_bearbeiten(request.user, aufgabe.projekt):
        raise PermissionDenied
    protokollieren(request.user, "anhang", anhang.pk, "geloescht", {"name": anhang.dateiname}, aufgabe_id=aufgabe.pk)
    anhang.datei.delete(save=False)
    anhang.delete()
    return _zurueck(request, aufgabe, "anhaenge")


def zeitpunkt(wert):
    return date_format(wert, "d.m.Y H:i")
