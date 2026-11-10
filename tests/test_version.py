"""Versionsanzeige auf der Seite „Über“."""

import pytest

from kern.models import Rolle


@pytest.mark.django_db
def test_version_fuer_alle_sichtbar(konten, client_fuer, settings):
    settings.TEAMPLANER_VERSION = "1.0.0"
    for rolle in (Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND):
        seite = client_fuer(konten[rolle]).get("/einstellungen/ueber/").content.decode()
        assert '<span class="mono">1.0.0</span>' in seite


@pytest.mark.django_db
def test_entwicklungsstand_ohne_versionsnummer(konten, client_fuer, settings):
    settings.TEAMPLANER_VERSION = ""
    seite = client_fuer(konten[Rolle.ADMIN]).get("/einstellungen/ueber/").content.decode()
    assert "Aus dem Quellcode gestartet" in seite
