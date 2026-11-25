"""Fälligkeiten: „Gestern“, „Heute“, „Morgen“ statt des Datums, überschrittene Termine rot –
in der Anzeige und in den Datumsfeldern zum Bearbeiten (Projektliste, Aufgabendetail)."""

import re
from datetime import date, timedelta

import pytest
from django.template import Context, Template
from django.utils import timezone, translation

from projekte.models import Status

from .conftest import P

pytestmark = pytest.mark.django_db


def heute_plus(tage):
    return timezone.localdate() + timedelta(days=tage)


def rendern(text, **kontext):
    return Template("{% load teamplaner %}" + text).render(Context(kontext))


@pytest.mark.parametrize(("tage", "wort"), [(-1, "Gestern"), (0, "Heute"), (1, "Morgen")])
def test_filter_gestern_heute_morgen(tage, wort):
    assert rendern("{{ d|tag_relativ }}", d=heute_plus(tage)) == wort
    assert rendern("{{ d|relativer_tag }}", d=heute_plus(tage)) == wort


def test_filter_andere_daten_und_leer():
    assert rendern("{{ d|tag_relativ }}", d=date(2030, 3, 7)) == "07.03."
    assert rendern('{{ d|tag_relativ:"D d.m.Y" }}', d=date(2030, 3, 7)) == "Do 07.03.2030"
    assert rendern("{{ d|tag_relativ }}", d=heute_plus(2)) == heute_plus(2).strftime("%d.%m.")
    assert rendern("{{ d|tag_relativ }}|{{ d|relativer_tag }}", d=None) == "|"
    assert rendern("{{ d|relativer_tag }}", d=heute_plus(-2)) == ""


def test_filter_englisch():
    with translation.override("en"):
        woerter = [rendern("{{ d|tag_relativ }}", d=heute_plus(t)) for t in (-1, 0, 1)]
    assert woerter == ["Yesterday", "Today", "Tomorrow"]


def test_faellig_mit_genauem_datum_als_tooltip():
    d = heute_plus(0)
    html = rendern("{% faellig d %}", d=d)
    assert f'datetime="{d.isoformat()}"' in html and ">Heute</time>" in html
    assert rendern("{% faellig d %}", d=None) == "–"


def datumsfeld(seite, aufgabe_pk=None):
    """Der <span class="datumswahl …">…</span>-Block einer Aufgabe (Projektliste) bzw. der Detailseite."""
    if aufgabe_pk is not None:
        seite = seite[seite.index(f'id="aufgabe-{aufgabe_pk}"'):]
    treffer = re.search(r'<span class="datumswahl[^"]*">.*?</span>\s*</span>|<span class="datumswahl[^"]*">.*?</span>',
                        seite, re.S)
    assert treffer, "kein Datumsfeld gefunden"
    return treffer.group(0)


def test_projektliste_datumsfeld_mit_wort_und_rot(client, konten, projekt, aufgabe):
    aufgabe.faellig_am = heute_plus(-1)
    aufgabe.save()
    client.force_login(konten[P])
    feld = datumsfeld(client.get(f"/projekte/{projekt.pk}/").content.decode(), aufgabe.pk)
    assert 'class="datumswahl faellig--ueberfaellig"' in feld
    assert 'type="date"' in feld and f'value="{aufgabe.faellig_am:%Y-%m-%d}"' in feld
    assert "datumswahl__feld--wort" in feld and ">Gestern</span>" in feld


def test_projektliste_datumsfeld_ohne_wort_und_erledigt_nicht_rot(client, konten, projekt, aufgabe):
    aufgabe.faellig_am = heute_plus(-5)
    aufgabe.save()
    client.force_login(konten[P])
    feld = datumsfeld(client.get(f"/projekte/{projekt.pk}/").content.decode(), aufgabe.pk)
    assert "faellig--ueberfaellig" in feld and "datumswahl__wort" not in feld
    aufgabe.faellig_am, aufgabe.status = heute_plus(-1), Status.standard_erledigt()
    aufgabe.save()
    feld = datumsfeld(client.get(f"/projekte/{projekt.pk}/?status=alle").content.decode(), aufgabe.pk)
    assert "faellig--ueberfaellig" not in feld and ">Gestern</span>" in feld


def test_detailseite_datumsfeld_mit_wort(client, konten, aufgabe):
    aufgabe.faellig_am = heute_plus(1)
    aufgabe.save()
    client.force_login(konten[P])
    seite = client.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    feld = datumsfeld(seite[seite.index('id="feld-faellig_am"'):])
    assert 'id="eingabe-faellig_am"' in feld and ">Morgen</span>" in feld and "faellig--ueberfaellig" not in feld
    aufgabe.faellig_am = heute_plus(-1)
    aufgabe.save()
    seite = client.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    feld = datumsfeld(seite[seite.index('id="feld-faellig_am"'):])
    assert "faellig--ueberfaellig" in feld and ">Gestern</span>" in feld


def test_detailseite_nach_aenderung_neues_wort(client, konten, aufgabe):
    client.force_login(konten[P])
    antwort = client.post(f"/aufgaben/{aufgabe.pk}/feld/", {
        "feld": "faellig_am", "wert": heute_plus(0).isoformat(), "version": aufgabe.version, "ansicht": "detail"},
        HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200
    assert ">Heute</span>" in datumsfeld(antwort.content.decode())
