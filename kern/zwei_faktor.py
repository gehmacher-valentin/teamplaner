"""Zwei-Faktor-Anmeldung mit Einmalcodes aus einer Authenticator-App (TOTP, RFC 6238).

Pflicht für Admin und Bereichsleitung, freiwillig für alle anderen. Das Geheimnis liegt am Konto;
benutzte Zeitschritte werden gemerkt, damit ein Code nicht zweimal gilt. Für den Fall eines verlorenen
Telefons gibt es zehn Ersatzcodes, gespeichert nur als Hash.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

import segno
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.safestring import mark_safe

from .models import Rolle, Systemeinstellungen

SCHRITT = 30  # Sekunden je Code
STELLEN = 6
TOLERANZ = 1  # Schritte davor und danach (Uhrabweichung des Telefons)
ERSATZ_ANZAHL = 10
ERSATZ_ZEICHEN = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # ohne leicht verwechselbare Zeichen
# Sitzungsschlüssel: Zeitpunkt der Einrichtung, mit dem die Sitzung den zweiten Faktor bestanden hat
SITZUNG = "zwei_faktor"


def pflicht(konto):
    return settings.TEAMPLANER_ZWEI_FAKTOR_PFLICHT and konto.hat_mindestens(Rolle.BEREICHSLEITUNG)


def aktiv(konto):
    return bool(konto.totp_geheimnis and konto.totp_seit)


def marke(konto):
    """Wert in der Sitzung nach bestandenem zweiten Faktor; neu einrichten macht alte Sitzungen ungültig."""
    return konto.totp_seit.isoformat() if aktiv(konto) else None


def bestanden(request, konto):
    request.session[SITZUNG] = marke(konto)


def neues_geheimnis():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code(geheimnis, schritt):
    schluessel = base64.b32decode(geheimnis + "=" * (-len(geheimnis) % 8))
    mac = hmac.new(schluessel, struct.pack(">Q", schritt), hashlib.sha1).digest()
    versatz = mac[-1] & 0x0F
    zahl = (struct.unpack(">I", mac[versatz:versatz + 4])[0] & 0x7FFFFFFF) % 10**STELLEN
    return f"{zahl:0{STELLEN}d}"


def passender_schritt(geheimnis, eingabe, nach_schritt=None, jetzt=None):
    """Zeitschritt, zu dem ``eingabe`` passt, sonst None. Schritte bis ``nach_schritt`` sind verbraucht."""
    eingabe = "".join(eingabe.split())
    if len(eingabe) != STELLEN or not eingabe.isdigit():
        return None
    aktuell = int((time.time() if jetzt is None else jetzt) // SCHRITT)
    for schritt in range(aktuell - TOLERANZ, aktuell + TOLERANZ + 1):
        if nach_schritt is not None and schritt <= nach_schritt:
            continue
        if hmac.compare_digest(code(geheimnis, schritt), eingabe):
            return schritt
    return None


def qr_svg(konto, geheimnis):
    """QR-Code zum Einscannen in die Authenticator-App (SVG zum direkten Einbetten)."""
    aussteller = f"Teamplaner {Systemeinstellungen.laden().organisation}".strip()
    adresse = "otpauth://totp/{}?{}".format(
        quote(f"{aussteller}:{konto.email}", safe=""),
        urlencode({"secret": geheimnis, "issuer": aussteller, "digits": STELLEN, "period": SCHRITT}),
    )
    return mark_safe(segno.make(adresse, error="m").svg_inline(scale=5, border=2, omitsize=True))  # nur viewBox: skaliert mit dem CSS


def geheimnis_anzeigen(geheimnis):
    """In Vierergruppen, zum Abtippen, falls der QR-Code nicht geht."""
    return " ".join(geheimnis[i:i + 4] for i in range(0, len(geheimnis), 4))


# --- Ersatzcodes ---

def _ersatz_hash(text):
    normal = "".join(z for z in text.upper() if z.isalnum())
    return hashlib.sha256(normal.encode()).hexdigest()


def ersatzcodes_erzeugen(konto):
    """Neue Ersatzcodes (ersetzen die alten); gibt sie im Klartext zurück – nur einmal anzeigen."""
    codes = []
    for _ in range(ERSATZ_ANZAHL):
        roh = "".join(secrets.choice(ERSATZ_ZEICHEN) for _ in range(10))
        codes.append(f"{roh[:5]}-{roh[5:]}")
    konto.totp_ersatzcodes = [_ersatz_hash(c) for c in codes]
    return codes


def einrichten(konto, geheimnis, schritt):
    """Gibt die Ersatzcodes zurück; speichert das Konto."""
    konto.totp_geheimnis = geheimnis
    konto.totp_seit = timezone.now()
    konto.totp_letzter_schritt = schritt
    codes = ersatzcodes_erzeugen(konto)
    konto.save(update_fields=["totp_geheimnis", "totp_seit", "totp_letzter_schritt", "totp_ersatzcodes"])
    return codes


def zuruecksetzen(konto):
    konto.totp_geheimnis = ""
    konto.totp_seit = None
    konto.totp_letzter_schritt = None
    konto.totp_ersatzcodes = []
    konto.save(update_fields=["totp_geheimnis", "totp_seit", "totp_letzter_schritt", "totp_ersatzcodes"])


def pruefen(konto, eingabe):
    """Code aus der App oder Ersatzcode prüfen und verbrauchen. Rückgabe: 'app', 'ersatz' oder None.

    Das Konto wird dabei gesperrt, damit derselbe Code bei zwei gleichzeitigen Anfragen nur einmal gilt.
    """
    with transaction.atomic():
        k = type(konto).objects.select_for_update().get(pk=konto.pk)
        if not aktiv(k):
            return None
        schritt = passender_schritt(k.totp_geheimnis, eingabe, k.totp_letzter_schritt)
        if schritt is not None:
            k.totp_letzter_schritt = schritt
            k.save(update_fields=["totp_letzter_schritt"])
            return "app"
        if len("".join(z for z in eingabe if z.isalnum())) != 10:
            return None
        gesucht = _ersatz_hash(eingabe)
        if any(hmac.compare_digest(gesucht, h) for h in k.totp_ersatzcodes):
            k.totp_ersatzcodes = [h for h in k.totp_ersatzcodes if h != gesucht]
            k.save(update_fields=["totp_ersatzcodes"])
            return "ersatz"
    return None


def ersatzcodes_uebrig(konto):
    return len(konto.totp_ersatzcodes or [])
