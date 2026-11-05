"""Termine nachziehen: Hauptaufgaben umfassen ihre Unteraufgaben, Nachfolger rücken
nach hinten, Sammelaufgaben verschieben sich als Ganzes; Gantt-Daten mit zwei Ebenen und Projekt-Überzug."""

from datetime import date

import pytest
from django.test import Client

from gantt.models import GanttAnsicht
from planung.models import Einteilung
from projekte import dienste, termine
from projekte.models import Abhaengigkeit, Aufgabe, Status

from .conftest import DI, DI2, DO, FR, MI, MI2, MO, ROLLEN

pytestmark = pytest.mark.django_db
A, BL, P, M, L = ROLLEN
MO2 = date(2026, 11, 2)
DI3 = date(2026, 11, 3)


def neu(projekt, titel, beginn=None, ende=None, eltern=None, erledigt=False):
    status = Status.standard_erledigt() if erledigt else Status.standard_offen()
    return Aufgabe.objects.create(projekt=projekt, abschnitt=eltern.abschnitt if eltern else None, eltern=eltern,
                                  titel=titel, status=status, beginn_am=beginn, faellig_am=ende)


def frisch(*aufgaben):
    for a in aufgaben:
        a.refresh_from_db()


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


# --- Hauptaufgaben umfassen ihre Unteraufgaben ---

def test_hauptaufgabe_reicht_ueber_alle_unteraufgaben(konten, projekt):
    haupt = neu(projekt, "Halle")
    eins = dienste.aufgabe_anlegen(konten[P], projekt, None, "Boden", eltern=haupt, beginn_am=MI, faellig_am=FR)
    frisch(haupt)
    assert (haupt.beginn_am, haupt.faellig_am) == (MI, FR)
    zwei = dienste.aufgabe_anlegen(konten[P], projekt, None, "Wände", eltern=haupt, faellig_am=DI2)  # nur Fälligkeit
    tiefer = dienste.aufgabe_anlegen(konten[P], projekt, None, "Vorbereitung", eltern=eins, beginn_am=MO, faellig_am=DI)
    frisch(haupt, eins)
    assert (eins.beginn_am, eins.faellig_am) == (MO, DI)  # die Unteraufgabe umfasst ihre eigene Unteraufgabe
    assert (haupt.beginn_am, haupt.faellig_am) == (MO, DI2)
    # Löschen und Herausziehen rechnen neu
    dienste.aufgabe_loeschen(konten[P], zwei)
    frisch(haupt)
    assert haupt.faellig_am == DI
    dienste.aufgabe_verschieben(konten[P], eins, eltern=None, abschnitt=None)
    frisch(haupt, tiefer)
    assert (haupt.beginn_am, haupt.faellig_am) == (MO, DI)  # ohne terminierte Unteraufgaben bleibt der letzte Stand


def test_termine_der_sammelaufgabe_nicht_von_hand(konten, projekt):
    haupt = neu(projekt, "Halle")
    dienste.aufgabe_anlegen(konten[P], projekt, None, "Boden", eltern=haupt, beginn_am=MI, faellig_am=FR)
    frisch(haupt)
    for ansicht in ("", "detail"):
        for feld in ("faellig_am", "beginn_am"):
            antwort = client_fuer(konten[P]).post(f"/aufgaben/{haupt.pk}/feld/", {
                "feld": feld, "wert": "2026-12-01", "version": haupt.version, "ansicht": ansicht})
            assert antwort.status_code == 400
    # Auf der Detailseite nur als Anzeige, ohne Datumsfeld
    seite = client_fuer(konten[P]).get(f"/aufgaben/{haupt.pk}/").content.decode()
    assert 'id="eingabe-faellig_am"' not in seite and 'id="eingabe-beginn_am"' not in seite


# --- Nachfolger rücken nach ---

def test_nachfolger_ruecken_nach_hinten(konten, projekt):
    a = neu(projekt, "A", MO, DI)
    b = neu(projekt, "B", MI, FR)    # drei Werktage
    c = neu(projekt, "C", MO2, DI3)
    Abhaengigkeit.objects.create(vorher=a, nachher=b)
    Abhaengigkeit.objects.create(vorher=b, nachher=c)
    # A endet jetzt Do: B beginnt Fr und behält drei Werktage (Mo 26.10. ist Feiertag) → Fr, Di, Mi
    dienste.aufgabe_speichern(konten[P], a, {"faellig_am": DO}, None)
    frisch(b, c)
    assert (b.beginn_am, b.faellig_am) == (FR, MI2)
    assert (c.beginn_am, c.faellig_am) == (MO2, DI3)  # C beginnt ohnehin erst danach
    # weiter nach hinten: C wird mitgeschoben
    dienste.aufgabe_speichern(konten[P], a, {"faellig_am": DI2}, None)
    frisch(b, c)
    assert (b.beginn_am, b.faellig_am) == (MI2, date(2026, 10, 30))
    assert (c.beginn_am, c.faellig_am) == (MO2, DI3)
    # nach vorne wird nichts gezogen
    dienste.aufgabe_speichern(konten[P], a, {"faellig_am": MO}, None)
    frisch(b)
    assert b.beginn_am == MI2
    # Verlauf und Benachrichtigung wie bei einer Änderung von Hand
    from kern.models import Protokolleintrag
    assert Protokolleintrag.objects.filter(objekt_typ="aufgabe", objekt_id=b.pk, aktion="geaendert").count() == 2


def test_erledigte_nachfolger_bleiben(konten, projekt):
    a = neu(projekt, "A", MO, DI)
    b = neu(projekt, "B", MI, FR, erledigt=True)
    Abhaengigkeit.objects.create(vorher=a, nachher=b)
    dienste.aufgabe_speichern(konten[P], a, {"faellig_am": FR}, None)
    frisch(b)
    assert (b.beginn_am, b.faellig_am) == (MI, FR)


def test_nachfolger_als_sammelaufgabe_wandert_mit_unteraufgaben(konten, projekt):
    a = neu(projekt, "A", MO, DI)
    b = neu(projekt, "B")
    b1 = dienste.aufgabe_anlegen(konten[P], projekt, None, "B1", eltern=b, beginn_am=MI, faellig_am=DO)
    Abhaengigkeit.objects.create(vorher=a, nachher=b)
    dienste.aufgabe_speichern(konten[P], a, {"faellig_am": MI}, None)
    frisch(b, b1)
    assert (b1.beginn_am, b1.faellig_am) == (DO, FR)
    assert (b.beginn_am, b.faellig_am) == (DO, FR)


def test_neue_abhaengigkeit_schiebt_sofort(konten, projekt):
    ansicht = GanttAnsicht.objects.create(name="Gesamt")
    ansicht.projekte.add(projekt)
    a, b = neu(projekt, "A", MO, DO), neu(projekt, "B", MI, FR)
    antwort = client_fuer(konten[BL]).post(f"/api/gantt/{ansicht.pk}/abhaengigkeiten", {"vorher": a.pk, "nachher": b.pk},
                                           content_type="application/json")
    assert antwort.status_code == 201
    frisch(b)
    assert b.beginn_am == FR


def test_keine_abhaengigkeit_zwischen_haupt_und_unteraufgabe(konten, projekt):
    ansicht = GanttAnsicht.objects.create(name="Gesamt")
    ansicht.projekte.add(projekt)
    haupt = neu(projekt, "Halle")
    kind = neu(projekt, "Boden", eltern=haupt)
    enkel = neu(projekt, "Platten", eltern=kind)
    c = client_fuer(konten[BL])
    for vorher, nachher in [(haupt, enkel), (enkel, haupt)]:
        antwort = c.post(f"/api/gantt/{ansicht.pk}/abhaengigkeiten", {"vorher": vorher.pk, "nachher": nachher.pk},
                         content_type="application/json")
        assert antwort.status_code == 400
    assert not Abhaengigkeit.objects.exists()


# --- Gantt: Sammelaufgaben ziehen, zwei Ebenen, Überzug ---

def test_sammelaufgabe_im_gantt_verschieben(konten, projekt):
    ansicht = GanttAnsicht.objects.create(name="Gesamt")
    ansicht.projekte.add(projekt)
    haupt = neu(projekt, "Halle")
    eins = dienste.aufgabe_anlegen(konten[P], projekt, None, "Boden", eltern=haupt, beginn_am=MO, faellig_am=DI)
    zwei = dienste.aufgabe_anlegen(konten[P], projekt, None, "Wände", eltern=haupt, beginn_am=MI, faellig_am=DO)
    tiefer = dienste.aufgabe_anlegen(konten[P], projekt, None, "Platten", eltern=eins, beginn_am=MO, faellig_am=DI)
    frisch(haupt)
    assert (haupt.beginn_am, haupt.faellig_am) == (MO, DO)
    antwort = client_fuer(konten[BL]).patch(f"/api/gantt/{ansicht.pk}/aufgaben/{haupt.pk}",
                                            {"beginn": DI.isoformat(), "ende": FR.isoformat(), "version": haupt.version},
                                            content_type="application/json")
    assert antwort.status_code == 200
    frisch(haupt, eins, zwei, tiefer)
    assert (eins.beginn_am, eins.faellig_am, zwei.beginn_am, zwei.faellig_am) == (DI, MI, DO, FR)
    assert tiefer.beginn_am == DI
    assert (haupt.beginn_am, haupt.faellig_am) == (DI, FR)
    assert antwort.json()["version"] == haupt.version


def test_gantt_zeigt_zwei_ebenen_und_ueberzug(konten, projekt, person_a):
    projekt.beginn, projekt.ende = MO, DO
    projekt.save()
    ansicht = GanttAnsicht.objects.create(name="Gesamt")
    ansicht.projekte.add(projekt)
    haupt = neu(projekt, "Halle")
    eins = dienste.aufgabe_anlegen(konten[P], projekt, None, "Boden", eltern=haupt, beginn_am=MI, faellig_am=FR)
    tiefer = dienste.aufgabe_anlegen(konten[P], projekt, None, "Platten", eltern=eins, beginn_am=MI, faellig_am=FR)
    Einteilung.objects.create(aufgabe=tiefer, person=person_a, von=DO, bis=FR)
    daten = client_fuer(konten[BL]).get(f"/api/gantt/{ansicht.pk}").json()
    assert set(daten["aufgaben"]) == {str(haupt.pk), str(eins.pk)}  # dritte Ebene nicht im Gantt
    assert daten["aufgaben"][str(haupt.pk)]["kinder"] == [eins.pk]
    assert daten["aufgaben"][str(haupt.pk)]["sammel"] is True
    assert daten["aufgaben"][str(eins.pk)]["sammel"] is True  # Termine aus der (unsichtbaren) dritten Ebene
    # die Einteilung der dritten Ebene zählt bei ihrer Unteraufgabe der ersten Ebene
    assert (daten["aufgaben"][str(eins.pk)]["ist_von"], daten["aufgaben"][str(eins.pk)]["ist_bis"]) == (DO.isoformat(), FR.isoformat())
    p = daten["projekte"][0]
    assert (p["beginn"], p["ende"], p["plan_von"], p["plan_bis"]) == (MO.isoformat(), DO.isoformat(), MI.isoformat(), FR.isoformat())


def test_abhaengigkeit_tieferer_ebene_zeigt_auf_erste_ebene(konten, projekt):
    ansicht = GanttAnsicht.objects.create(name="Gesamt")
    ansicht.projekte.add(projekt)
    haupt = neu(projekt, "Halle")
    eins = neu(projekt, "Boden", eltern=haupt)
    tiefer = neu(projekt, "Platten", MO, DI, eltern=eins)
    andere = neu(projekt, "Dichtheit", MI, DO)
    Abhaengigkeit.objects.create(vorher=tiefer, nachher=andere)
    daten = client_fuer(konten[BL]).get(f"/api/gantt/{ansicht.pk}").json()
    assert [(d["vorher"], d["nachher"]) for d in daten["abhaengigkeiten"]] == [(eins.pk, andere.pk)]


def test_verletzung_nach_tatsaechlichen_einteilungen(konten, projekt, person_a):
    from gantt.daten import ist_zeitraeume, verletzt

    a, b = neu(projekt, "A", MO, DI), neu(projekt, "B", MI, DO)
    assert not verletzt(a, b, {})
    Einteilung.objects.create(aufgabe=a, person=person_a, von=MO, bis=DO)
    Einteilung.objects.create(aufgabe=b, person=person_a, von=MI, bis=DO)
    assert verletzt(a, b, ist_zeitraeume(Einteilung.objects.all()))


def test_naechster_werktag_und_dauer():
    assert termine.naechster_werktag(FR) == DI2  # Wochenende und Nationalfeiertag
    assert termine.mit_gleicher_dauer(MO, MI, FR) == MI2  # drei Werktage ab Fr: Fr, Di, Mi
