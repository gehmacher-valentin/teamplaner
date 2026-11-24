"""Vorschau der ersten Seite von PDF-Anhängen (Aufgaben und Notizen).

PDFs sind fremde Dateien, PDFium (``pypdfium2``) ist ein großer C++-Parser. Deshalb rendert ein eigener
Prozess (``pdf_vorschau_prozess.py``, ``python -I`` ohne Django und ohne Umgebungsvariablen) mit Grenzen für
Rechenzeit, Speicher und Bildgröße; die Anwendung wartet höchstens ``ZEIT_SEKUNDEN``. Bei jedem Fehler
(beschädigt, verschlüsselt, zu aufwendig, Grenze überschritten) gibt es keine Vorschau, der Anhang wird
trotzdem gespeichert und zeigt wie bisher das Dateisymbol.

Die Vorschau entsteht beim Hochladen (ein normales PDF braucht rund 0,1 s); für ältere Anhänge trägt sie
der Befehl ``pdf_vorschauen`` nach.
"""

import logging
import subprocess
import sys
from pathlib import Path

from django.core.files.base import ContentFile

log = logging.getLogger(__name__)

PDF = "application/pdf"
PROZESS = Path(__file__).with_name("pdf_vorschau_prozess.py")
ZEIT_SEKUNDEN = 4  # Wartezeit insgesamt, mit Start des Prozesses
CPU_SEKUNDEN = 3
SPEICHER_MB = 512
BREITE = 480  # Pixel; Kachel 172 px breit, scharf auch bei doppelter Pixeldichte
MAX_HOEHE = 720  # nur der obere Teil der Seite
MAX_BYTES = 2 * 1024 * 1024
DATEINAME = "vorschau.webp"


def _befehl():
    return [sys.executable, "-I", str(PROZESS), str(CPU_SEKUNDEN), str(SPEICHER_MB), str(BREITE), str(MAX_HOEHE)]


def erzeugen(daten):
    """WebP-Bytes der ersten Seite oder ``None``. Wirft nie."""
    try:
        ergebnis = subprocess.run(  # fester Befehl, das PDF kommt über stdin
            _befehl(), input=daten, capture_output=True, timeout=ZEIT_SEKUNDEN, env={}, cwd="/", check=False)
    except subprocess.TimeoutExpired:
        log.warning("PDF-Vorschau: Zeitgrenze von %s s überschritten", ZEIT_SEKUNDEN)
        return None
    except Exception:  # noqa: BLE001 – z. B. Prozess lässt sich nicht starten
        log.warning("PDF-Vorschau: Prozess ließ sich nicht starten", exc_info=True)
        return None
    bild = ergebnis.stdout
    if ergebnis.returncode != 0:
        grund = ergebnis.stderr.decode("utf-8", "replace").strip()[:200]
        log.info("PDF-Vorschau nicht möglich (Rückgabewert %s): %s", ergebnis.returncode, grund)
        return None
    if not (12 < len(bild) <= MAX_BYTES and bild[:4] == b"RIFF" and bild[8:12] == b"WEBP"):
        log.warning("PDF-Vorschau: unerwartete Ausgabe (%s Bytes)", len(bild))
        return None
    return bild


def fuer_upload(datei, content_type):
    """Vorschau zu einer hochgeladenen Datei, die der Server als PDF erkannt hat (``dateityp``), als
    ``ContentFile`` für das Feld ``vorschau``; sonst oder bei einem Fehler ``None``."""
    if content_type != PDF:
        return None
    try:
        daten = datei.read()
    finally:
        datei.seek(0)
    bild = erzeugen(daten)
    return ContentFile(bild, name=DATEINAME) if bild else None


def nachtragen(anhang):
    """Vorschau für einen gespeicherten PDF-Anhang erzeugen (``Anhang`` oder ``NotizAnhang``).
    Gibt zurück, ob jetzt eine Vorschau da ist."""
    if anhang.content_type != PDF:
        return False
    try:
        with anhang.datei.open("rb") as datei:
            daten = datei.read()
    except OSError:
        log.warning("PDF-Vorschau: Datei von Anhang %s fehlt", anhang.pk)
        return False
    bild = erzeugen(daten)
    if not bild:
        return False
    alt = anhang.vorschau.name if anhang.vorschau else None
    anhang.vorschau.save(DATEINAME, ContentFile(bild), save=False)
    anhang.save(update_fields=["vorschau"])
    if alt:
        anhang.vorschau.storage.delete(alt)
    return True
