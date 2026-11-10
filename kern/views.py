"""Views der Basis, die nur kern brauchen: Erreichbarkeit, Profilfotos, Personenvorschläge,
Restzeit der Sitzung. Anmeldung, Einstellungen und Personenverwaltung liegen in verwaltung."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext as _
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from . import fotos
from .models import Person


def gesund(request):
    """Für teamplaner status/update und Monitoring: Anwendung und Datenbank erreichbar?"""
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "fehler"}, status=503)


@require_POST
@login_required
def konto_foto(request):
    """Eigenes Foto hochladen oder entfernen; ohne Foto zeigt der Avatar die Initialen."""
    person = request.user.person
    if "entfernen" in request.POST:
        fotos.entfernen(person)
        messages.success(request, _("Foto entfernt."))
    elif request.FILES.get("foto"):
        try:
            fotos.setzen(person, request.FILES["foto"])
            messages.success(request, _("Foto gespeichert."))
        except fotos.FotoFehler as fehler:
            messages.error(request, str(fehler))
    return redirect("einst_profil")


@login_required
def person_foto(request, pk):
    """Fotos sind personenbezogen und nur für angemeldete Personen abrufbar."""
    person = get_object_or_404(Person, pk=pk)
    if not person.foto:
        raise Http404
    try:
        datei = person.foto.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    antwort = FileResponse(datei, content_type="image/jpeg")
    antwort["Cache-Control"] = "private, max-age=604800"
    antwort["X-Content-Type-Options"] = "nosniff"
    return antwort


@login_required
def personen_vorschlaege(request):
    """Vorschläge für @-Erwähnung und Auswahllisten: nur auswählbare Personen (ohne Systemkonten)."""
    suche = request.GET.get("q", "").strip()
    personen = Person.objects.auswaehlbar().select_related("konto")
    if suche:
        personen = personen.filter(anzeigename__icontains=suche)
    return JsonResponse({"personen": [
        {"id": p.pk, "name": p.anzeigename, "initialen": p.initialen, "platzhalter": p.ist_platzhalter,
         "foto": p.foto_url}
        for p in personen[:8]
    ]})


@never_cache
@login_required
def sitzung_frist(request):
    """Restzeit der Admin-Sitzung: GET als Hintergrundabfrage prüft nur (die Frist steht in der Kopfzeile
    ``X-Sitzung-Ablauf``, kern.middleware.SitzungMiddleware), POST zählt als Aktivität und setzt sie zurück."""
    if request.method not in ("GET", "POST"):
        return HttpResponse(status=405)
    return HttpResponse(status=204)
