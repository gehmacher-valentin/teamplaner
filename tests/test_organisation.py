"""Organisationsname in den Einstellungen."""

import pytest
from django.core import mail
from django.test import Client

from kern import zwei_faktor
from kern.models import Protokolleintrag, Rolle, Systemeinstellungen
from zusammenarbeit.mail import _fusszeile

pytestmark = pytest.mark.django_db
A, BL = Rolle.ADMIN, Rolle.BEREICHSLEITUNG
URL = "/einstellungen/allgemein/"


def setzen(name):
    Systemeinstellungen.objects.update_or_create(pk=1, defaults={"organisation": name})


def angemeldet(konto):
    c = Client()
    c.force_login(konto)
    return c


def test_nur_admin_darf_den_namen_aendern(konten):
    assert angemeldet(konten[BL]).post(URL, {"feld": "organisation", "wert": "Firma 01"}).status_code == 403
    assert Systemeinstellungen.laden().organisation == ""


def test_admin_speichert_sofort_und_ins_protokoll(konten):
    assert angemeldet(konten[A]).post(URL, {"feld": "organisation", "wert": "  Firma   01 "}).status_code == 204
    assert Systemeinstellungen.laden().organisation == "Firma 01"
    eintrag = Protokolleintrag.objects.get(objekt_typ="einstellungen", aktion="geaendert")
    assert eintrag.daten == {"organisation": ["", "Firma 01"]}


def test_zu_langer_name_wird_abgelehnt(konten):
    assert angemeldet(konten[A]).post(URL, {"feld": "organisation", "wert": "x" * 101}).status_code == 400
    assert Systemeinstellungen.laden().organisation == ""


def test_unbekanntes_feld_wird_abgelehnt(konten):
    assert angemeldet(konten[A]).post(URL, {"feld": "id", "wert": "2"}).status_code == 400


def test_leer_kein_element_in_kopfzeile_und_anmeldeseite(konten):
    seite = angemeldet(konten[A]).get("/einstellungen/profil/").content.decode()
    assert 'class="kopf__org"' not in seite
    assert '<div class="gedaempft klein">' not in Client().get("/anmelden/").content.decode()


def test_gesetzt_in_kopfzeile_und_anmeldeseite(konten):
    setzen("Firma <01>")
    assert '<div class="kopf__org">Firma &lt;01&gt;</div>' in angemeldet(konten[A]).get("/einstellungen/profil/").content.decode()
    assert '<div class="gedaempft klein">Firma &lt;01&gt;</div>' in Client().get("/anmelden/").content.decode()


def test_mail_fusszeile(settings):
    settings.TEAMPLANER_ADRESSE = "https://teamplaner.example.test"
    assert "\nTeamplaner\n" in _fusszeile() and " · " not in _fusszeile()
    setzen("Firma 01")
    assert "\nTeamplaner · Firma 01\n" in _fusszeile()
    assert mail.outbox == []


def aussteller_im_qr(konto, monkeypatch):
    inhalte = []
    echt = zwei_faktor.segno.make
    monkeypatch.setattr(zwei_faktor.segno, "make", lambda inhalt, **kw: inhalte.append(inhalt) or echt(inhalt, **kw))
    zwei_faktor.qr_svg(konto, "GEHEIM")
    return inhalte[0]


def test_zwei_faktor_qr_skaliert_mit_dem_css(konten):
    kopf = str(zwei_faktor.qr_svg(konten[A], "GEHEIM")).split(">")[0]
    assert "viewBox=" in kopf and "width=" not in kopf


def test_zwei_faktor_aussteller(konten, monkeypatch):
    assert "issuer=Teamplaner&" in aussteller_im_qr(konten[A], monkeypatch)
    setzen("Firma/01")
    adresse = aussteller_im_qr(konten[A], monkeypatch)
    assert "issuer=Teamplaner+Firma%2F01&" in adresse and "Firma%2F01%3A" in adresse
