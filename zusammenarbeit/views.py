import json

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
from django.views.decorators.http import require_POST

from kern import rechte
from kern.heic import heic_umwandeln
from kern.models import Person
from kern.protokoll import protokollieren
from projekte.models import Aufgabe
from projekte.seitenleiste import offene_seitenleiste, seitenleiste_antwort

from .anhaenge import INLINE_TYPEN, dateityp
from .dienste import erwaehnung_benachrichtigen, kommentar_benachrichtigen
from .models import Anhang, Erwaehnung, Kommentar
from .verlauf import ERWAEHNUNG


def _zurueck(request, aufgabe, anker):
    """Zurück zum Aufgabendetail: auf die Seite oder, von dort abgeschickt, in die Seitenleiste."""
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
