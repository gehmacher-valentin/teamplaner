"""Laufende Version und Hinweis auf neuere Versionen.

Die Versionsnummer steht in der Datei VERSION im Paket (aus dem Git-Tag gebaut). Neuere Versionen
sucht die Anwendung in der Paketquelle, aus der auch ./teamplaner update lädt – über die
Registry-API (Tag-Liste). Zugang optional aus .env (REGISTRY_BENUTZER/REGISTRY_TOKEN). Fehler
werden nur protokolliert: ohne Internet oder Zugang entfällt der Hinweis einfach.
"""

import base64
import json
import logging
import re
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

MUSTER = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
CACHE_SCHLUESSEL = "teamplaner:neueste_version"
GUELTIG = 6 * 3600
GUELTIG_NACH_FEHLER = 3600


def zerlegen(text):
    """'1.2.3' → (1, 2, 3); alles andere (latest, 1.2, Entwicklungsstand) → None."""
    treffer = MUSTER.match(text or "")
    return tuple(int(teil) for teil in treffer.groups()) if treffer else None


def _json(url, kopf):
    with urllib.request.urlopen(urllib.request.Request(url, headers=kopf), timeout=3) as antwort:
        return json.load(antwort)


def _tags(image):
    """Alle Tags eines Images, z. B. ghcr.io/besitzer/name → ['1.0.0', 'latest', …]."""
    host, _, repo = image.partition("/")
    url = f"https://{host}/v2/{repo}/tags/list?n=1000"
    try:
        return _json(url, {})["tags"] or []
    except urllib.error.HTTPError as fehler:
        if fehler.code != 401:
            raise
        angaben = dict(re.findall(r'(\w+)="([^"]*)"', fehler.headers.get("WWW-Authenticate", "")))
    # Token-Verfahren der Registry; Zugangsdaten nur an die Registry selbst schicken
    realm = urllib.parse.urlsplit(angaben.get("realm", ""))
    if realm.scheme != "https":
        raise ValueError("Registry verlangt eine unbekannte Anmeldung")
    kopf = {}
    if settings.REGISTRY_TOKEN and realm.hostname == host:
        zugang = f"{settings.REGISTRY_BENUTZER}:{settings.REGISTRY_TOKEN}".encode()
        kopf["Authorization"] = "Basic " + base64.b64encode(zugang).decode()
    abfrage = urllib.parse.urlencode({k: angaben[k] for k in ("service", "scope") if k in angaben})
    token = _json(f"{angaben['realm']}?{abfrage}", kopf)["token"]
    return _json(url, {"Authorization": f"Bearer {token}"})["tags"] or []


def neueste_version():
    """Höchste Versionsnummer in der Paketquelle, None wenn nicht abrufbar (6 h zwischengespeichert)."""
    ergebnis = cache.get(CACHE_SCHLUESSEL)
    if ergebnis is None:
        try:
            versionen = [v for v in map(zerlegen, _tags(settings.TEAMPLANER_IMAGE)) if v]
            ergebnis = ".".join(map(str, max(versionen))) if versionen else ""
            cache.set(CACHE_SCHLUESSEL, ergebnis, GUELTIG)
        except (OSError, ValueError, KeyError, TypeError) as fehler:
            logger.info("Neueste Version nicht abrufbar (%s): %s", settings.TEAMPLANER_IMAGE, fehler)
            ergebnis = ""
            cache.set(CACHE_SCHLUESSEL, ergebnis, GUELTIG_NACH_FEHLER)
    return ergebnis or None


def pruefung_moeglich():
    """Nur ein veröffentlichtes Paket (mit Versionsnummer) sucht nach Updates."""
    return bool(zerlegen(settings.TEAMPLANER_VERSION) and settings.TEAMPLANER_IMAGE)


def update_stand():
    """('neu', '1.3.0') | ('aktuell', None) | ('unbekannt', None)."""
    if not pruefung_moeglich():
        return "unbekannt", None
    neueste = neueste_version()
    if neueste is None:
        return "unbekannt", None
    if zerlegen(neueste) > zerlegen(settings.TEAMPLANER_VERSION):
        return "neu", neueste
    return "aktuell", None
