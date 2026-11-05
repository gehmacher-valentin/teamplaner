"""Profilfotos: prüfen, quadratisch zuschneiden, verkleinern, Metadaten entfernen."""

import uuid
from io import BytesIO

from django.core.files.base import ContentFile
from django.utils.translation import gettext as _
from PIL import Image, ImageOps, UnidentifiedImageError

from . import heic  # noqa: F401 – macht HEIC/HEIF für Pillow lesbar

GROESSE = 256
MAX_MB = 8
FORMATE = {"JPEG", "PNG", "WEBP", "GIF", "HEIF"}
Image.MAX_IMAGE_PIXELS = 40_000_000  # Schutz vor „Dekompressionsbomben“


class FotoFehler(Exception):
    pass


def verarbeiten(datei):
    """Gibt ein 256×256-JPEG ohne EXIF-Daten (z. B. GPS) zurück."""
    if datei.size > MAX_MB * 1024 * 1024:
        raise FotoFehler(_("Das Foto ist zu groß (höchstens %(mb)s MB).") % {"mb": MAX_MB})
    try:
        bild = Image.open(datei)
        format_ = bild.format
        bild.verify()
        datei.seek(0)
        bild = Image.open(datei)
        bild = ImageOps.exif_transpose(bild)
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise FotoFehler(_("Die Datei ist kein unterstütztes Bild (JPEG, PNG, WebP, HEIC).")) from None
    if format_ not in FORMATE:
        raise FotoFehler(_("Die Datei ist kein unterstütztes Bild (JPEG, PNG, WebP, HEIC)."))
    bild = ImageOps.fit(bild.convert("RGB"), (GROESSE, GROESSE), Image.Resampling.LANCZOS)
    puffer = BytesIO()
    bild.save(puffer, "JPEG", quality=85, optimize=True)
    return ContentFile(puffer.getvalue(), name=f"{uuid.uuid4().hex}.jpg")


def setzen(person, datei):
    if person.ist_platzhalter:
        raise FotoFehler(_("Platzhalter haben kein Foto."))
    neu = verarbeiten(datei)
    alt = person.foto.name if person.foto else None
    person.foto.save(neu.name, neu, save=True)
    if alt:
        person.foto.storage.delete(alt)


def entfernen(person):
    if person.foto:
        person.foto.delete(save=True)
