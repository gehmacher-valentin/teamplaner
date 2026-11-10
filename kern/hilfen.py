"""Hilfen für Views: Rechteprüfung als Decorator, Links für Einladung/Reset."""

from functools import wraps
from urllib.parse import urlencode

import segno
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.core.exceptions import PermissionDenied
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import base36_to_int, urlsafe_base64_encode
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from rest_framework.exceptions import NotAuthenticated
from rest_framework.response import Response
from rest_framework.views import exception_handler


def erfordert(pruefung):
    """View nur für angemeldete Konten, für die ``pruefung(konto)`` wahr ist (sonst 403)."""

    def dekorator(view):
        @login_required
        @wraps(view)
        def huelle(request, *args, **kwargs):
            if not pruefung(request.user):
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return huelle

    return dekorator


class PasswortLinks(PasswordResetTokenGenerator):
    """Wie Djangos Generator (Frist PASSWORD_RESET_TIMEOUT für Einladungen). Links für Konten, die
    schon ein Passwort haben (Zurücksetzen), gelten nur TEAMPLANER_RESET_GUELTIG_STUNDEN."""

    def check_token(self, user, token):
        if not super().check_token(user, token):
            return False
        if user.has_usable_password():
            erzeugt = base36_to_int(token.partition("-")[0])
            return self._num_seconds(self._now()) - erzeugt <= settings.TEAMPLANER_RESET_GUELTIG_STUNDEN * 3600
        return True


passwort_links = PasswortLinks()


def passwort_link(konto):
    """Link zum Setzen des Passworts – für Einladung und Reset.

    Ohne E-Mail-Versand kopieren Admin/Bereichsleitung den Link einer Einladung. Er wird ungültig,
    sobald das Passwort gesetzt wurde oder die Frist abläuft. Die Adresse kommt aus
    TEAMPLANER_ADRESSE, nicht aus der Anfrage (Host-Kopfzeile).
    """
    uid = urlsafe_base64_encode(force_bytes(konto.pk))
    pfad = reverse("passwort_setzen", args=[uid, passwort_links.make_token(konto)])
    return settings.TEAMPLANER_ADRESSE.rstrip("/") + pfad


def abmelden_und_weiter(request, nachricht):
    """Sitzung beenden und passend antworten: HTMX lädt die Anmeldeseite, die API meldet 401."""
    logout(request)
    if request.path.startswith("/api/"):
        return JsonResponse({"code": "abgemeldet", "nachricht": str(nachricht)}, status=401)
    messages.info(request, nachricht)
    ziel = reverse("login")
    if getattr(request, "htmx", False):
        antwort = HttpResponse()
        antwort["HX-Redirect"] = ziel
        return antwort
    if request.method == "GET":
        ziel += "?" + urlencode({"next": request.get_full_path()})
    return redirect(ziel)


def api_ausnahme(exc, context):
    """Fehlerantworten der JSON-API: abgelaufene Sitzung als 401 mit ``code`` „abgemeldet“ (statt
    Djangos 403 ohne Code), damit Teamplaner und Gantt-Diagramm zur Anmeldung wechseln können."""
    if isinstance(exc, NotAuthenticated):
        return Response({"code": "abgemeldet", "nachricht": _("Sitzung abgelaufen – bitte neu anmelden.")}, status=401)
    return exception_handler(exc, context)


# Obergrenze für lange Freitexte (Notiz, Beschreibung). Ohne sie deckelt nur
# DATA_UPLOAD_MAX_MEMORY_SIZE die Größe, und sehr lange Texte machen jede Anzeige teuer.
TEXT_MAX_ZEICHEN = 100_000


def als_zahl(wert):
    """Ganze Zahl aus einer Anfrage (ID, Version) oder None – statt mit Fehler 500 abzubrechen."""
    if isinstance(wert, bool):
        return None
    try:
        return int(wert)
    except (TypeError, ValueError):
        return None


def einstellungsseite(request, vorlage, aktiv, verwaltung=True, **kontext):
    """Seite im Einstellungsrahmen (templates/kern/einstellungen_basis.html). ``aktiv`` ist die Kennung
    in der Unternavigation; Team- und System-Seiten (``verwaltung``) markieren im Hauptmenü
    „Einstellungen“ unter „Verwaltung“, persönliche Seiten das Konto."""
    return render(request, vorlage, {
        "einst_aktiv": aktiv, "aktiv": "einstellungen" if verwaltung else "konto", **kontext,
    })


def link_qr_svg(link):
    """QR-Code eines Passwort-Links zum Einbetten: volle Ruhezone und heller Grund im SVG selbst,
    damit er auch im dunklen Design vom Bildschirm scannbar ist. ``omitsize``: nur viewBox, sonst
    schneidet die Breite aus dem CSS die Grafik ab, statt sie zu skalieren."""
    return mark_safe(segno.make(link, error="m").svg_inline(scale=5, border=4, light="#fff", omitsize=True))
