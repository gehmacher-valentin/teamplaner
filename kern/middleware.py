import json
import time
from urllib.parse import urlparse

from django.conf import settings
from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _

from . import rechte, zwei_faktor
from .hilfen import abmelden_und_weiter

# Zeitpunkt der letzten eigenen Aktivität in der Sitzung (Admin-Abmeldung nach Inaktivität)
LETZTE_AKTIVITAET = "letzte_aktivitaet"


class KontoSpracheMiddleware:
    """Aktiviert die im Konto gewählte Sprache. Steht nach der AuthenticationMiddleware;
    ohne Anmeldung gilt die Auswahl der Anmeldeseite bzw. die Browsersprache (LocaleMiddleware)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        konto = getattr(request, "user", None)
        if konto is not None and konto.is_authenticated and getattr(konto, "sprache", ""):
            request.LANGUAGE_CODE = konto.sprache
            with translation.override(konto.sprache):
                return self.get_response(request)
        return self.get_response(request)


def ist_hintergrund(request):
    """Abfragen, die ohne Zutun der Person laufen (Glocke, Live-Verbindung, Nachladen nach Live-Ereignis)."""
    return request.headers.get("X-Hintergrund") == "1" or request.path == "/api/planung/stream"


class SitzungMiddleware:
    """Admins werden nach TEAMPLANER_ADMIN_INAKTIV_MINUTEN ohne eigene Aktivität abgemeldet.

    Hintergrundabfragen verlängern die Frist nicht, prüfen sie aber – so springt eine liegen gelassene
    Seite spätestens mit der nächsten Abfrage der Glocke zur Anmeldung. Alle anderen Rollen bleiben bis
    TEAMPLANER_SITZUNG_TAGE nach der Anmeldung angemeldet (kern.signale).

    Für die Restzeit in der Kopfzeile (``lib/sitzungsfrist.ts``) steht das Fristende als
    ``request.sitzung_ablauf`` bereit und geht mit jeder Antwort an Admins als ``X-Sitzung-Ablauf`` mit
    (Unix-Zeit in Sekunden, dazu ``X-Sitzung-Jetzt`` für eine falsch gehende Uhr am Rechner).
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        konto = request.user
        if konto.is_authenticated and rechte.ist_admin(konto):
            jetzt = time.time()
            letzte = request.session.get(LETZTE_AKTIVITAET)
            frist = settings.TEAMPLANER_ADMIN_INAKTIV_MINUTEN * 60
            if letzte is not None and jetzt - letzte > frist:
                return abmelden_und_weiter(request, _(
                    "Sie wurden nach %(n)s Minuten ohne Aktivität abgemeldet.") % {"n": settings.TEAMPLANER_ADMIN_INAKTIV_MINUTEN})
            if letzte is None or not ist_hintergrund(request):
                request.session[LETZTE_AKTIVITAET] = letzte = jetzt
            request.sitzung_ablauf, request.sitzung_jetzt = int(letzte + frist), int(jetzt)
            antwort = self.get_response(request)
            letzte = request.session.get(LETZTE_AKTIVITAET)  # nach dem Abmelden leer
            if letzte is not None:
                antwort["X-Sitzung-Ablauf"] = str(int(letzte + frist))
                antwort["X-Sitzung-Jetzt"] = str(int(time.time()))
            return antwort
        return self.get_response(request)


class AbgemeldetMiddleware:
    """Nicht (mehr) angemeldet, z. B. Admin nach Inaktivität: HTMX-Anfragen wie die Glocke
    bekommen statt der Weiterleitung zur Anmeldeseite die Anweisung, die ganze Seite neu zu laden.
    Sonst setzt HTMX das Anmeldeformular in das kleine Feld ein, das die Antwort ersetzen sollte, und
    die übrige Seite bleibt sichtbar. Steht nach der HtmxMiddleware."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        antwort = self.get_response(request)
        if (getattr(request, "htmx", False) and antwort.status_code in (301, 302)
                and urlparse(antwort.get("Location", "")).path == reverse("login")):
            antwort = HttpResponse(status=204)
            antwort["HX-Refresh"] = "true"
        return antwort


TOAST_ART = {messages.SUCCESS: "erfolg", messages.WARNING: "fehler", messages.ERROR: "fehler"}


class HtmxMeldungenMiddleware:
    """Meldungen (``django.contrib.messages``) aus HTMX-Anfragen als Toast: Sie gehen als Ereignis
    „toasts“ im Header ``HX-Trigger`` mit, statt bis zum nächsten Seitenaufruf liegen zu bleiben.
    Lädt die Antwort die Seite neu oder leitet weiter, zeigt die neue Seite sie wie gewohnt."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        antwort = self.get_response(request)
        if (not getattr(request, "htmx", False) or antwort.status_code in (301, 302)
                or any(k in antwort for k in ("HX-Refresh", "HX-Redirect", "HX-Location"))):
            return antwort
        liste = [{"text": str(m), "art": TOAST_ART.get(m.level, "info")} for m in messages.get_messages(request)]
        if liste:
            ausloeser = antwort.get("HX-Trigger", "")
            try:
                ereignisse = json.loads(ausloeser) if ausloeser else {}
            except ValueError:
                ereignisse = {name.strip(): "" for name in ausloeser.split(",") if name.strip()}
            ereignisse["toasts"] = liste
            antwort["HX-Trigger"] = json.dumps(ereignisse)
        return antwort


# Seiten, die ohne eingerichteten zweiten Faktor erreichbar bleiben, solange er Pflicht ist
OHNE_ZWEI_FAKTOR = {"zwei_faktor_einrichten", "logout", "set_language", "gesund"}


class ZweiFaktorMiddleware:
    """Zweiter Faktor: Sitzungen ohne bestandenen Code werden beendet; wer ihn braucht, aber
    noch nicht eingerichtet hat, kommt nur auf die Einrichtungsseite."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        konto = request.user
        if not konto.is_authenticated:
            return None
        if zwei_faktor.aktiv(konto):
            if request.session.get(zwei_faktor.SITZUNG) != zwei_faktor.marke(konto):
                return abmelden_und_weiter(request, _("Bitte melden Sie sich erneut an."))
            return None
        if not zwei_faktor.pflicht(konto) or request.resolver_match.url_name in OHNE_ZWEI_FAKTOR:
            return None
        ziel = reverse("zwei_faktor_einrichten")
        if request.path.startswith("/api/"):
            return JsonResponse({"code": "zwei_faktor", "nachricht": _(
                "Bitte richten Sie zuerst die Zwei-Faktor-Anmeldung ein.")}, status=403)
        if getattr(request, "htmx", False):
            antwort = HttpResponse()
            antwort["HX-Redirect"] = ziel
            return antwort
        return redirect(ziel)


# Content-Security-Policy: Skripte nur aus eigenen Dateien (kein Inline-Code, kein eval), keine
# fremden Quellen, nicht einbettbar. Inline-Styles bleiben erlaubt (style-Attribute in Templates und
# React); Bilder und Schriften auch als data:-Adresse, weil Vite kleine Dateien so einbettet.
CSP = "; ".join([
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data:",
    "font-src 'self' data:",
    "connect-src 'self'",
    "object-src 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "frame-ancestors 'none'",
])


class SicherheitskopfMiddleware:
    """Setzt die CSP für alle Antworten, die keine eigene haben (Anhänge setzen eine strengere)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        antwort = self.get_response(request)
        antwort.setdefault("Content-Security-Policy", CSP)
        return antwort
