"""Übersetzung: englische Texte vollständig, .mo aktuell, Sprachwahl wirkt."""

import importlib.util
from pathlib import Path

import pytest
from django.conf import settings
from django.test import Client
from django.utils import translation

from kern.models import Rolle

from .conftest import FEIERTAG, ROLLEN

PO = Path(settings.BASE_DIR) / "locale" / "en" / "LC_MESSAGES" / "django.po"


def _po_werkzeug():
    spec = importlib.util.spec_from_file_location("po_werkzeug", Path(settings.BASE_DIR) / "werkzeuge" / "po_werkzeug.py")
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    return modul


def _eintraege():
    werkzeug = _po_werkzeug()
    for e in werkzeug.eintraege(PO.read_text(encoding="utf-8")):
        d = e["daten"]
        msgid = werkzeug._str(d["msgid"])
        if msgid:
            yield msgid, {k: werkzeug._str(v) for k, v in d.items() if k.startswith("msgstr")}, e["kommentare"]


def test_englische_uebersetzung_vollstaendig():
    fehlend = [m for m, werte, kommentare in _eintraege()
               if not all(werte.values()) or any(k.startswith("#, fuzzy") for k in kommentare)]
    assert fehlend == [], "Fehlende englische Übersetzungen – bitte locale/en/LC_MESSAGES/django.po ergänzen"


def test_kompilierte_datei_passt_zur_quelle():
    """Schlägt fehl, wenn nach dem Bearbeiten der .po-Datei compilemessages vergessen wurde."""
    with translation.override("en"):
        veraltet = [m for m, werte, _k in _eintraege()
                    if "msgstr" in werte and translation.gettext(m) != werte["msgstr"]]
    assert veraltet == [], "django.mo ist veraltet: python manage.py compilemessages ausführen"


@pytest.mark.django_db
def test_konto_sprache_englisch(konten):
    konto = konten[Rolle.MITARBEITER]
    konto.sprache = "en"
    konto.save(update_fields=["sprache"])
    c = Client()
    c.force_login(konto)
    seite = c.get("/meine-aufgaben/").content.decode()
    assert "My tasks" in seite and 'lang="en"' in seite
    # Deutsch bleibt für andere Konten
    andere = Client()
    andere.force_login(konten[Rolle.PLANER])
    assert "Meine Aufgaben" in andere.get("/meine-aufgaben/").content.decode()


@pytest.mark.django_db
def test_api_meldungen_und_feiertage_englisch(konten, aufgabe, person_a):
    konto = konten[Rolle.BEREICHSLEITUNG]
    konto.sprache = "en"
    konto.save(update_fields=["sprache"])
    c = Client()
    c.force_login(konto)
    antwort = c.post("/api/planung/einteilungen", {"aufgabe_id": aufgabe.pk, "person_id": person_a.pk,
                                                   "von": FEIERTAG.isoformat(), "bis": FEIERTAG.isoformat()},
                     content_type="application/json")
    assert antwort.json()["feiertag"] == "National Day"
    assert "Schedule anyway?" in antwort.json()["nachricht"]


@pytest.mark.django_db
def test_sprache_im_konto_umstellen(konten):
    konto = konten[ROLLEN[3]]
    c = Client()
    c.force_login(konto)
    antwort = c.post("/einstellungen/darstellung/speichern/", {"feld": "sprache", "wert": "en"}, HTTP_HX_REQUEST="true")
    konto.refresh_from_db()
    assert konto.sprache == "en" and antwort["HX-Refresh"] == "true"
    assert "Appearance" in c.get("/einstellungen/darstellung/").content.decode()


@pytest.mark.django_db
def test_anmeldeseite_sprachwahl():
    c = Client()
    assert "Anmelden" in c.get("/anmelden/").content.decode()
    c.post("/i18n/setlang/", {"language": "en", "next": "/anmelden/"})
    assert "Sign in" in c.get("/anmelden/").content.decode()
