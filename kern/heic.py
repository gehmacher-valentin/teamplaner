"""HEIC/HEIF-Fotos (iPhone) beim Hochladen in JPEG umwandeln.

Pillow liest HEIC erst mit einem Zusatzpaket; ``pi-heif`` kann nur lesen (keine Encoder), die mitgelieferten
Bibliotheken libheif und libde265 stehen unter LGPLv3. Die Ausrichtung aus dem HEIF-Container wendet libheif
beim Lesen an (pi-heif setzt die EXIF-Ausrichtung danach auf 1); ``exif_transpose`` bleibt für den Fall,
dass nur die EXIF-Angabe gesetzt ist. Das JPEG wird ohne EXIF-Daten (z. B. GPS-Position) gespeichert, in
Originalauflösung mit Qualität 85. Lässt sich eine Datei nicht umwandeln, bleibt sie, wie sie ist.
"""

import logging
from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

log = logging.getLogger(__name__)
QUALITAET = 85

try:
    import pi_heif

    pi_heif.register_heif_opener()
    VERFUEGBAR = True
except ImportError:  # pragma: no cover – ohne Zusatzpaket werden HEIC-Dateien unverändert gespeichert
    VERFUEGBAR = False


def ist_heif(datei):
    """Beginnt die Datei wie ein HEIF-Container (ISO-BMFF ``ftyp`` mit HEIC/HEIF-Marke)?"""
    kopf = datei.read(12)
    datei.seek(0)
    return len(kopf) == 12 and kopf[4:8] == b"ftyp" and kopf[8:12] in {
        b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"hevm", b"hevs", b"mif1", b"msf1"}


def heic_umwandeln(datei):
    """Gibt für ein HEIC/HEIF-Bild eine neue JPEG-Datei (``name.jpg``, ``content_type`` gesetzt) zurück,
    sonst ``None`` – auch wenn die Umwandlung scheitert (beschädigt, unbekannte Variante)."""
    if not VERFUEGBAR or not ist_heif(datei):
        return None
    try:
        with Image.open(datei) as bild:
            if bild.format != "HEIF":
                return None
            bild = ImageOps.exif_transpose(bild)
            if bild.mode not in ("RGB", "L"):
                hintergrund = Image.new("RGB", bild.size, (255, 255, 255))  # Transparenz auf Weiß
                bild = bild.convert("RGBA")
                hintergrund.paste(bild, mask=bild.getchannel("A"))
                bild = hintergrund
            puffer = BytesIO()
            bild.save(puffer, "JPEG", quality=QUALITAET, optimize=True)  # ohne exif=…: keine Metadaten
    except Exception:  # noqa: BLE001 – dann eben unverändert speichern
        log.warning("HEIC-Datei %r ließ sich nicht umwandeln", getattr(datei, "name", ""), exc_info=True)
        return None
    finally:
        datei.seek(0)
    name = (Path(datei.name or "foto").stem or "foto")[:250] + ".jpg"
    neu = ContentFile(puffer.getvalue(), name=name)
    neu.content_type = "image/jpeg"
    return neu
