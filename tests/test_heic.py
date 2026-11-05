"""HEIC/HEIF-Fotos (iPhone) werden beim Hochladen zu JPEG: Vorschau, richtige Ausrichtung, ohne EXIF.

``tests/daten/hochformat.heic`` ist 48×24 (links rot, rechts blau) mit Ausrichtung „90° im Uhrzeigersinn“
und GPS-Angabe gespeichert – richtig gedreht also 24×48, oben rot, unten blau.
"""

from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from kern.models import Rolle
from notizen.models import Notiz, NotizAnhang, Ordner
from zusammenarbeit.models import Anhang

pytestmark = pytest.mark.django_db
HEIC = (Path(__file__).parent / "daten" / "hochformat.heic").read_bytes()


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


def heic(name="IMG_1234.HEIC"):
    return SimpleUploadedFile(name, HEIC, content_type="image/heic")


def pruefe_jpeg(pfad):
    with Image.open(pfad) as bild:
        assert bild.format == "JPEG" and bild.size == (24, 48)  # Hochformat steht richtig herum
        rot, _g, blau = bild.convert("RGB").getpixel((12, 6))
        assert rot > 180 and blau < 80  # oben rot
        rot, _g, blau = bild.convert("RGB").getpixel((12, 42))
        assert blau > 180 and rot < 80  # unten blau
        assert not bild.getexif()  # keine Metadaten, auch keine GPS-Position


def test_anhang_an_aufgabe_wird_jpeg_mit_vorschau(konten, aufgabe, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    c = client_fuer(konten[Rolle.MITARBEITER])
    assert c.post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": heic()}).status_code == 302
    anhang = Anhang.objects.get()
    assert anhang.dateiname == "IMG_1234.jpg" and anhang.content_type == "image/jpeg" and anhang.hat_vorschau
    assert anhang.datei.name.endswith(".jpg") and anhang.groesse == anhang.datei.size
    pruefe_jpeg(anhang.datei.path)
    antwort = c.get(f"/anhaenge/{anhang.pk}/")
    assert antwort["Content-Type"] == "image/jpeg" and "attachment" not in antwort.get("Content-Disposition", "")


def test_anhang_an_notiz_wird_jpeg(konten, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    ordner = Ordner.objects.create(name="Fotos", erstellt_von=konten[Rolle.PLANER].person)
    ordner.mitglieder.add(konten[Rolle.MITARBEITER])
    notiz = Notiz.objects.create(ordner=ordner, titel="Halle", text="")
    client_fuer(konten[Rolle.MITARBEITER]).post(f"/notizen/{notiz.pk}/anhaenge/", {"datei": heic("foto.heif")})
    anhang = NotizAnhang.objects.get()
    assert anhang.dateiname == "foto.jpg" and anhang.content_type == "image/jpeg"
    pruefe_jpeg(anhang.datei.path)


def test_heic_als_profilfoto(konten, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    konto = konten[Rolle.MITARBEITER]
    client_fuer(konto).post("/konto/foto/", {"foto": heic()})
    konto.person.refresh_from_db()
    with Image.open(konto.person.foto.path) as bild:
        assert bild.format == "JPEG" and bild.size == (256, 256)
    assert "image/heic" in client_fuer(konto).get("/einstellungen/profil/").content.decode()  # in der Dateiauswahl


def test_nicht_umwandelbare_datei_bleibt_unveraendert(konten, aufgabe, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    kaputt = HEIC[:40] + b"\0" * 200  # beginnt wie HEIC, ist aber beschädigt
    datei = SimpleUploadedFile("kaputt.heic", kaputt, content_type="image/heic")
    assert client_fuer(konten[Rolle.MITARBEITER]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": datei}).status_code == 302
    anhang = Anhang.objects.get()
    assert anhang.dateiname == "kaputt.heic" and anhang.groesse == len(kaputt) and not anhang.hat_vorschau
    assert anhang.datei.read() == kaputt


def test_andere_dateien_bleiben_wie_sie_sind(konten, aufgabe, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    datei = SimpleUploadedFile("bericht.txt", b"ftypheic? nein", content_type="text/plain")
    client_fuer(konten[Rolle.MITARBEITER]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": datei})
    anhang = Anhang.objects.get()
    assert anhang.dateiname == "bericht.txt" and anhang.datei.read() == b"ftypheic? nein"
