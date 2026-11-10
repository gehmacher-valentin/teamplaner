"""Anhänge: welcher Inhaltstyp gespeichert und was im Browser angezeigt statt heruntergeladen wird."""

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
