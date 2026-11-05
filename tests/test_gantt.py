"""Gantt-Diagramm: Freigaben, Termine, Abhängigkeiten, Abgleich."""

from datetime import date

import pytest
from django.test import Client

from gantt.models import GanttAnsicht, GanttFreigabe
from kern.models import Protokolleintrag
from planung.models import Einteilung, Recht
from projekte.models import Abhaengigkeit, Abschnitt, Aufgabe, Projekt, Status

from .conftest import DI, DO, FR, MI, MO, ROLLEN

pytestmark = pytest.mark.django_db
A, BL, P, M, L = ROLLEN


@pytest.fixture
def zweites_projekt():
    projekt = Projekt.objects.create(name="Prototyp Förderband", farbe="blau")
    abschnitt = Abschnitt.objects.create(projekt=projekt, name="Fertigung")
    return projekt, Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel="Gehäuse Band",
                                           status=Status.standard_offen(), beginn_am=MI, faellig_am=FR)


@pytest.fixture
def ansicht(projekt, zweites_projekt):
    a = GanttAnsicht.objects.create(name="Gesamt 2026")
    a.projekte.add(projekt, zweites_projekt[0])
    return a


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


def freigeben(ansicht, konto, recht):
    GanttFreigabe.objects.create(ansicht=ansicht, konto=konto, recht=recht)


# --- Freigaben ---

@pytest.mark.parametrize("rolle, erwartet", [(A, 200), (BL, 200), (P, 403), (M, 403), (L, 403)])
def test_ansicht_ohne_freigabe(konten, ansicht, rolle, erwartet):
    assert client_fuer(konten[rolle]).get(f"/api/gantt/{ansicht.pk}").status_code == erwartet


@pytest.mark.parametrize("rolle", [P, M, L])
def test_ansicht_mit_freigabe_sehen(konten, ansicht, rolle):
    freigeben(ansicht, konten[rolle], Recht.SEHEN)
    daten = client_fuer(konten[rolle]).get(f"/api/gantt/{ansicht.pk}").json()
    assert daten["ansicht"]["recht"] == "sehen"
    assert {p["name"] for p in daten["projekte"]} == {"Neubau Lagerhalle", "Prototyp Förderband"}


@pytest.mark.parametrize("rolle, erwartet", [(P, 200), (M, 403), (L, 403)])
def test_bearbeiten_wirkt_erst_ab_planer(konten, ansicht, aufgabe, rolle, erwartet):
    freigeben(ansicht, konten[rolle], Recht.BEARBEITEN)
    antwort = client_fuer(konten[rolle]).patch(f"/api/gantt/{ansicht.pk}/aufgaben/{aufgabe.pk}",
                                               {"beginn": MO.isoformat(), "ende": MI.isoformat(), "version": aufgabe.version},
                                               content_type="application/json")
    assert antwort.status_code == erwartet


def test_gantt_seite_und_navigation(konten, ansicht):
    assert client_fuer(konten[L]).get("/gantt/").status_code == 403
    freigeben(ansicht, konten[L], Recht.SEHEN)
    c = client_fuer(konten[L])
    assert c.get("/gantt/").status_code == 200
    assert "Gantt-Diagramm" in c.get("/meine-aufgaben/").content.decode()
    assert c.get("/einstellungen/ansichten/?art=gantt").status_code == 403
    assert client_fuer(konten[BL]).get("/einstellungen/ansichten/?art=gantt").status_code == 200


def test_ansicht_verwalten_mit_freigaben(konten, projekt):
    client_fuer(konten[BL]).post("/einstellungen/ansichten/gantt/neu/", {
        "name": "Bereich A 2026", "projekte": [projekt.pk],
        f"freigabe-{konten[P].pk}": "bearbeiten", f"freigabe-{konten[M].pk}": "bearbeiten",
    })
    ansicht = GanttAnsicht.objects.get(name="Bereich A 2026")
    assert list(ansicht.projekte.all()) == [projekt]
    assert dict(GanttFreigabe.objects.values_list("konto_id", "recht")) == {
        konten[P].pk: Recht.BEARBEITEN, konten[M].pk: Recht.SEHEN}


def test_projekt_nachtraeglich_hinzufuegen_nur_verwaltung(konten, ansicht):
    neues = Projekt.objects.create(name="Kundendienst Süd", farbe="gruen")
    freigeben(ansicht, konten[P], Recht.BEARBEITEN)
    url = f"/api/gantt/{ansicht.pk}/projekte/{neues.pk}/zuordnung"
    assert client_fuer(konten[P]).post(url).status_code == 403
    assert client_fuer(konten[BL]).post(url).status_code == 204
    assert neues in ansicht.projekte.all()
    assert client_fuer(konten[BL]).delete(url).status_code == 204
    assert neues not in ansicht.projekte.all()


# --- Termine ---

def test_aufgabe_verschieben_mit_versionspruefung(konten, ansicht, aufgabe):
    c = client_fuer(konten[BL])
    url = f"/api/gantt/{ansicht.pk}/aufgaben/{aufgabe.pk}"
    antwort = c.patch(url, {"beginn": MO.isoformat(), "ende": MI.isoformat(), "version": 1}, content_type="application/json")
    assert antwort.status_code == 200
    aufgabe.refresh_from_db()
    assert (aufgabe.beginn_am, aufgabe.faellig_am, aufgabe.version) == (MO, MI, 2)
    veraltet = c.patch(url, {"beginn": DI.isoformat(), "ende": DO.isoformat(), "version": 1}, content_type="application/json")
    assert veraltet.status_code == 409
    assert Protokolleintrag.objects.filter(objekt_typ="aufgabe", objekt_id=aufgabe.pk, aktion="geaendert").exists()


def test_ende_vor_beginn_abgewiesen(konten, ansicht, aufgabe):
    antwort = client_fuer(konten[BL]).patch(f"/api/gantt/{ansicht.pk}/aufgaben/{aufgabe.pk}",
                                            {"beginn": FR.isoformat(), "ende": MO.isoformat(), "version": 1},
                                            content_type="application/json")
    assert antwort.status_code == 400


def test_aufgabe_ausserhalb_der_ansicht_nicht_aenderbar(konten, ansicht):
    fremd = Projekt.objects.create(name="Anderes Projekt")
    a = Aufgabe.objects.create(projekt=fremd, abschnitt=Abschnitt.objects.create(projekt=fremd, name="x"),
                               titel="Fremd", status=Status.standard_offen())
    antwort = client_fuer(konten[BL]).patch(f"/api/gantt/{ansicht.pk}/aufgaben/{a.pk}",
                                            {"beginn": MO.isoformat(), "version": 1}, content_type="application/json")
    assert antwort.status_code == 403


def test_projekt_termine(konten, ansicht, projekt):
    antwort = client_fuer(konten[BL]).patch(f"/api/gantt/{ansicht.pk}/projekte/{projekt.pk}",
                                            {"beginn": "2026-10-01", "ende": "2026-12-18"}, content_type="application/json")
    assert antwort.status_code == 200
    projekt.refresh_from_db()
    assert (projekt.beginn, projekt.ende) == (date(2026, 10, 1), date(2026, 12, 18))


# --- Abhängigkeiten ---

def test_abhaengigkeit_projektuebergreifend_schiebt_nach(konten, ansicht, aufgabe, zweites_projekt):
    _p2, gehaeuse = zweites_projekt  # Mi–Fr
    aufgabe.beginn_am, aufgabe.faellig_am = MO, DO
    aufgabe.save()
    c = client_fuer(konten[BL])
    antwort = c.post(f"/api/gantt/{ansicht.pk}/abhaengigkeiten", {"vorher": aufgabe.pk, "nachher": gehaeuse.pk},
                     content_type="application/json")
    assert antwort.status_code == 201
    gehaeuse.refresh_from_db()
    assert gehaeuse.beginn_am == FR  # rückt hinter den Hallenboden (endet Do), statt nur markiert zu werden
    assert c.get(f"/api/gantt/{ansicht.pk}").json()["abhaengigkeiten"][0]["verletzt"] is False
    # Erledigte Nachfolger bleiben stehen – dann wird die Abhängigkeit als verletzt markiert
    gehaeuse.status, gehaeuse.beginn_am = Status.standard_erledigt(), MI
    gehaeuse.save()
    assert c.get(f"/api/gantt/{ansicht.pk}").json()["abhaengigkeiten"][0]["verletzt"] is True
    # im Verlauf beider Aufgaben
    assert Protokolleintrag.objects.filter(objekt_typ="abhaengigkeit", aufgabe_id=gehaeuse.pk).exists()
    assert Protokolleintrag.objects.filter(objekt_typ="abhaengigkeit", aufgabe_id=aufgabe.pk).exists()


def test_ringschluss_und_doppelte_abgewiesen(konten, ansicht, aufgabe, zweites_projekt):
    _p2, gehaeuse = zweites_projekt
    c = client_fuer(konten[BL])
    url = f"/api/gantt/{ansicht.pk}/abhaengigkeiten"
    assert c.post(url, {"vorher": aufgabe.pk, "nachher": gehaeuse.pk}, content_type="application/json").status_code == 201
    assert c.post(url, {"vorher": aufgabe.pk, "nachher": gehaeuse.pk}, content_type="application/json").json()["code"] == "besteht"
    assert c.post(url, {"vorher": gehaeuse.pk, "nachher": aufgabe.pk}, content_type="application/json").json()["code"] == "ringschluss"
    assert c.post(url, {"vorher": aufgabe.pk, "nachher": aufgabe.pk}, content_type="application/json").status_code == 400
    assert Abhaengigkeit.objects.count() == 1


def test_abhaengigkeit_loeschen_nur_mit_bearbeiten(konten, ansicht, aufgabe, zweites_projekt):
    abh = Abhaengigkeit.objects.create(vorher=aufgabe, nachher=zweites_projekt[1])
    freigeben(ansicht, konten[P], Recht.SEHEN)
    url = f"/api/gantt/{ansicht.pk}/abhaengigkeiten/{abh.pk}"
    assert client_fuer(konten[P]).delete(url).status_code == 403
    assert client_fuer(konten[BL]).delete(url).status_code == 204
    assert not Abhaengigkeit.objects.exists()


def test_externe_aufgabe_ueber_abhaengigkeit_sichtbar(konten, projekt, aufgabe, zweites_projekt):
    nur_eins = GanttAnsicht.objects.create(name="Nur Lagerhalle")
    nur_eins.projekte.add(projekt)
    Abhaengigkeit.objects.create(vorher=zweites_projekt[1], nachher=aufgabe)
    daten = client_fuer(konten[BL]).get(f"/api/gantt/{nur_eins.pk}").json()
    extern = daten["aufgaben"][str(zweites_projekt[1].pk)]
    assert extern["extern"] is True and str(zweites_projekt[0].pk) in daten["externe_projekte"]


# --- Abgleich und Doppelbelegung ---

def test_ist_zeitraum_ohne_namen_und_ohne_doppelbelegung(konten, ansicht, aufgabe, zweites_projekt, person_a):
    Einteilung.objects.create(aufgabe=aufgabe, person=person_a, von=MO, bis=MI)
    Einteilung.objects.create(aufgabe=zweites_projekt[1], person=person_a, von=MI, bis=FR)  # Mi doppelt
    daten = client_fuer(konten[BL]).get(f"/api/gantt/{ansicht.pk}").json()
    a = daten["aufgaben"][str(aufgabe.pk)]
    assert (a["ist_von"], a["ist_bis"]) == (MO.isoformat(), MI.isoformat())
    assert "konflikt" not in a  # Doppelbelegung wird im Gantt nicht markiert
    assert "Person 02" not in str(daten)


def test_aufgabendetail_zeigt_abhaengigkeiten(konten, aufgabe, zweites_projekt):
    Abhaengigkeit.objects.create(vorher=aufgabe, nachher=zweites_projekt[1])
    seite = client_fuer(konten[L]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert "Gehäuse Band" in seite and "Danach erst möglich" in seite
