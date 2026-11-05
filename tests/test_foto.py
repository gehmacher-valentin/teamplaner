"""Profilfoto: Upload, Zuschnitt, Zugriff nur angemeldet, Entfernen."""

from io import BytesIO

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from PIL import Image

from kern.models import Rolle

pytestmark = pytest.mark.django_db


def bild(breite=600, hoehe=400):
    puffer = BytesIO()
    Image.new("RGB", (breite, hoehe), "orange").save(puffer, "PNG")
    return SimpleUploadedFile("foto.png", puffer.getvalue(), content_type="image/png")


def test_foto_hochladen_anzeigen_entfernen(konten, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    konto = konten[Rolle.MITARBEITER]
    c = Client()
    c.force_login(konto)
    c.post("/konto/foto/", {"foto": bild()})
    konto.person.refresh_from_db()
    assert konto.person.foto
    with Image.open(konto.person.foto.path) as gespeichert:
        assert gespeichert.size == (256, 256) and gespeichert.format == "JPEG"
    assert "avatar--foto" in c.get("/einstellungen/profil/").content.decode()
    assert Client().get(konto.person.foto_url).status_code == 302  # nicht angemeldet
    andere = Client()
    andere.force_login(konten[Rolle.LESEND])
    assert andere.get(konto.person.foto_url).status_code == 200
    c.post("/konto/foto/", {"entfernen": "1"})
    konto.person.refresh_from_db()
    assert not konto.person.foto


def test_kein_bild_wird_abgewiesen(konten, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    c = Client()
    c.force_login(konten[Rolle.MITARBEITER])
    c.post("/konto/foto/", {"foto": SimpleUploadedFile("x.png", b"kein bild", content_type="image/png")})
    konten[Rolle.MITARBEITER].person.refresh_from_db()
    assert not konten[Rolle.MITARBEITER].person.foto
