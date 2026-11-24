"""Anhänge: welcher Inhaltstyp gespeichert und was im Browser angezeigt statt heruntergeladen wird;
Ausliefern und Entfernen der Dateien (gemeinsam für ``Anhang`` und ``notizen.NotizAnhang``)."""

import logging

from django.db import transaction
from django.http import FileResponse, Http404

log = logging.getLogger(__name__)

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


def ausliefern(feld, content_type, dateiname=None):
    """Datei eines Anhangs (oder seine Vorschau) mit den Kopfzeilen für fremde Inhalte. Im Browser angezeigt
    werden nur ``INLINE_TYPEN``, alles andere wird heruntergeladen."""
    if not feld:
        raise Http404
    try:
        datei = feld.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    inline = content_type in INLINE_TYPEN
    antwort = FileResponse(datei, as_attachment=not inline, filename=dateiname or "",
                           content_type=content_type if inline else "application/octet-stream")
    antwort["X-Content-Type-Options"] = "nosniff"
    antwort["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    antwort["Cache-Control"] = "private"
    return antwort


def dateien_entfernen(sender, instance, **kwargs):
    """``post_delete`` von ``Anhang`` und ``NotizAnhang``: Datei und Vorschau löschen, sobald das Löschen
    feststeht. Gilt auch, wenn der Anhang mit seiner Aufgabe, Notiz oder seinem Ordner oder beim Aufräumen
    nach Fristen verschwindet; wird die Transaktion zurückgerollt, bleiben die Dateien."""
    dateien = [(feld.storage, feld.name) for feld in (instance.datei, instance.vorschau) if feld]

    def entfernen():
        for speicher, name in dateien:
            try:
                speicher.delete(name)
            except OSError:
                log.warning("Datei %s ließ sich nicht löschen", name, exc_info=True)

    if dateien:
        transaction.on_commit(entfernen)
