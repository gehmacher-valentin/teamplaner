"""Systemkonto nicht als Person auswählbar, Bestellungen „Eingetragen von“ / „Bestellt von“,
Personenauswahl mit Tippsuche und Spalte „Eingeteilt“ zweizeilig."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.test import Client

from bestellungen.models import Bestellung
from kern.models import Bereich, Konto, Person, Protokolleintrag, Rolle
from planung.models import Einteilung
from projekte.forms import ProjektForm
from projekte.models import Projekt

from .conftest import DI, FR, MI, MO

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


@pytest.fixture
def systemkonto(konten):
    konto = konten[A]
    konto.systemkonto = True
    konto.save()
    return konto


# --- Systemkonto ---

def test_auswaehlbar_ohne_systemkonto_mit_platzhalter(konten, systemkonto, platzhalter):
    auswahl = set(Person.objects.auswaehlbar())
    assert systemkonto.person not in auswahl
    assert platzhalter in auswahl and konten[M].person in auswahl
    assert not systemkonto.person.auswaehlbar and platzhalter.auswaehlbar
    # Die Kontenverwaltung zeigt das Systemkonto weiterhin, mit Hinweis
    seite = client_fuer(konten[BL]).get("/einstellungen/personen/").content.decode()
    assert systemkonto.person.anzeigename in seite and "Systemkonto" in seite


def test_formulare_bieten_systemkonto_nicht_an(konten, systemkonto, projekt, aufgabe):
    projektform = ProjektForm(instance=projekt)
    assert systemkonto.person not in projektform.fields["projektleitung"].queryset
    assert systemkonto.person not in projektform.fields["mitglieder"].queryset
    # schon eingetragen: bleibt sichtbar und lässt sich umhängen
    aufgabe.verantwortlich = systemkonto.person
    aufgabe.save()
    detail = client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert f'<option value="{systemkonto.pk}" selected>' in detail
    seite = client_fuer(konten[P]).get(f"/projekte/{projekt.pk}/").content.decode()
    assert seite.count(f'<option value="{systemkonto.pk}"') == 1  # nur in der Zeile mit dieser Aufgabe, nicht im Filter
    vorschlaege = client_fuer(konten[M]).get("/personen/vorschlaege/?q=Person").json()["personen"]
    assert systemkonto.pk not in {p["id"] for p in vorschlaege}


def test_teamplaner_zeigt_systemkonto_nur_mit_bestehenden_eintraegen(client_fuer, konten, systemkonto, aufgabe,
                                                                       person_a):
    api = client_fuer(konten[BL])

    def zeilen():
        daten = api.get("/api/planung/raster", {"ansicht": "alle", "von": MO.isoformat(), "bis": FR.isoformat()}).json()
        return {p["id"]: p for p in daten["personen"]}

    assert systemkonto.pk not in zeilen()
    antwort = api.post("/api/planung/einteilungen", {"aufgabe_id": aufgabe.pk, "person_id": systemkonto.pk,
                                                      "von": MO.isoformat(), "bis": DI.isoformat()}, format="json")
    assert antwort.status_code == 400 and antwort.json()["code"] == "systemkonto"
    # Eine alte Einteilung bleibt sichtbar und lässt sich auf jemand anderen ziehen – nicht zurück
    alt = Einteilung.objects.create(aufgabe=aufgabe, person=systemkonto.person, von=MO, bis=DI)
    zeile = zeilen()[systemkonto.pk]
    assert zeile["auswaehlbar"] is False and zeile["einteilbar"] is True
    antwort = api.patch(f"/api/planung/einteilungen/{alt.pk}", {"version": alt.version, "person_id": person_a.pk},
                        format="json")
    assert antwort.status_code == 200
    alt.refresh_from_db()
    antwort = api.patch(f"/api/planung/einteilungen/{alt.pk}", {"version": alt.version, "person_id": systemkonto.pk},
                        format="json")
    assert antwort.status_code == 400
    assert systemkonto.pk not in zeilen()
    assert api.post("/api/planung/abwesenheiten", {"person_id": systemkonto.pk, "von": MI.isoformat(),
                                                   "bis": MI.isoformat()}, format="json").status_code == 400


def test_systemkonto_setzen_nur_fuer_niedrigere_rollen(konten):
    ziel = konten[P]
    daten = {"anzeigename": "Person 05", "email": ziel.email, "rolle": ziel.rolle, "systemkonto": "on"}
    assert client_fuer(konten[BL]).post(f"/einstellungen/personen/{ziel.pk}/", daten).status_code == 302
    ziel.refresh_from_db()
    assert ziel.systemkonto
    assert Protokolleintrag.objects.filter(objekt_typ="konto", objekt_id=ziel.pk, daten__systemkonto=[False, True]).exists()
    assert client_fuer(konten[BL]).post(f"/einstellungen/personen/{konten[A].pk}/", {**daten, "email": konten[A].email}).status_code == 403


# --- Bestellungen ---

def test_bestellung_eingetragen_und_bestellt_von(konten, person_a, platzhalter):
    c = client_fuer(konten[M])
    seite = c.get("/bestellungen/").content.decode()
    assert "Eingetragen von" in seite and "Bestellt von" in seite and "data-personenwahl" in seite
    c.post("/bestellungen/neu/", {"neu-bedarf": "Kleber", "neu-aufnahmedatum": "2026-10-23", "neu-status": "offen",
                                  "neu-eingetragen_von": konten[M].person.pk, "neu-bestellt_von": ""})
    b = Bestellung.objects.get()
    assert (b.eingetragen_von, b.bestellt_von, b.erstellt_von) == (konten[M].person, None, konten[M].person)
    antwort = c.post(f"/bestellungen/{b.pk}/", {"bestellt_von": platzhalter.pk, "eingetragen_von": person_a.pk,
                                                "status": "bestellt"}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200 and "X-Fehler" not in antwort
    b.refresh_from_db()
    assert (b.eingetragen_von, b.bestellt_von, b.bedarf) == (person_a, platzhalter, "Kleber")
    eintrag = Protokolleintrag.objects.get(objekt_typ="bestellung", aktion="geaendert")
    assert eintrag.daten["bestellt_von"][1]["name"] == platzhalter.anzeigename
    # Löschen hängt weiter an der Person, die die Zeile angelegt hat
    assert client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/loeschen/").status_code == 302


def test_bestellung_ohne_personen_aendern_laesst_sie_stehen(konten):
    b = Bestellung.objects.create(bedarf="Schrauben", eingetragen_von=konten[M].person, bestellt_von=konten[P].person)
    client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/", {"status": "bestellt"}, HTTP_HX_REQUEST="true")
    b.refresh_from_db()
    assert (b.status, b.eingetragen_von, b.bestellt_von) == ("bestellt", konten[M].person, konten[P].person)


# --- Projektliste ---

def test_projektliste_personen_in_zweiter_zeile_und_tippsuche(konten, projekt, aufgabe, person_a):
    Einteilung.objects.create(aufgabe=aufgabe, person=person_a, von=MO, bis=DI)
    seite = client_fuer(konten[P]).get(f"/projekte/{projekt.pk}/").content.decode()
    assert "<span>2 / 4 Tage</span><span>1 Pers.</span>" in seite
    assert 'name="verantwortlich" data-auto-absenden data-personenwahl' in seite
    assert Projekt.objects.count() == 1


def test_frische_installation_startet_mit_bereich_allgemein():
    assert list(Bereich.objects.values_list("name", flat=True)) == ["Allgemein"]
    call_command("konto_anlegen", email="admin@example.test", name="Person 90", bereich="Allgemein", stdout=StringIO())
    assert Konto.objects.get(email="admin@example.test").person.bereich.name == "Allgemein"
