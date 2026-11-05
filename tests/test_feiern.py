"""Feieranimation: nur wenn eingeschaltet und nur beim Erledigen; sichere Weiterleitung."""

import pytest
from django.test import Client

from kern.models import Rolle

pytestmark = pytest.mark.django_db


def angemeldet(konto, feiern):
    konto.feier_animation = feiern
    konto.save(update_fields=["feier_animation"])
    c = Client()
    c.force_login(konto)
    return c


def test_standard_ist_aus(konten):
    assert konten[Rolle.MITARBEITER].feier_animation is False


def test_htmx_ausloeser_nur_wenn_eingeschaltet(konten, aufgabe):
    c = angemeldet(konten[Rolle.MITARBEITER], True)
    antwort = c.post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "1", "zeile": "1"}, HTTP_HX_REQUEST="true")
    assert antwort["HX-Trigger"] == "feiern"
    # Wieder öffnen feiert nicht
    antwort = c.post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "0", "zeile": "1"}, HTTP_HX_REQUEST="true")
    assert "HX-Trigger" not in antwort


def test_ausgeschaltet_kein_ausloeser(konten, aufgabe):
    c = angemeldet(konten[Rolle.MITARBEITER], False)
    antwort = c.post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "1", "zeile": "1"}, HTTP_HX_REQUEST="true")
    assert "HX-Trigger" not in antwort


def test_nach_weiterleitung_einmal_abgespielt(konten, aufgabe):
    c = angemeldet(konten[Rolle.MITARBEITER], True)
    seite = c.post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "1"}, follow=True).content.decode()
    assert 'data-feiern="1"' in seite
    assert 'data-feiern="1"' not in c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()


def test_keine_weiterleitung_auf_fremde_seiten(konten, aufgabe):
    c = angemeldet(konten[Rolle.MITARBEITER], False)
    antwort = c.post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "1", "weiter": "https://boese.example/"})
    assert antwort.url == f"/aufgaben/{aufgabe.pk}/"
    antwort = c.post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "0", "weiter": "/meine-aufgaben/"})
    assert antwort.url == "/meine-aufgaben/"
