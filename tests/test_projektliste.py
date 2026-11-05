"""Projektliste: Priorität, Navigation, Mitgliederauswahl; Protokoll „erledigte Aufgaben“; Posteingang im Kopf;
Gantt-Gesamtansicht nimmt neue Projekte auf."""

import pytest
from django.test import Client

from gantt.models import GanttAnsicht
from kern.models import Protokolleintrag, Rolle
from projekte import dienste
from projekte.models import Projekt
from zusammenarbeit.models import Benachrichtigung

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


@pytest.mark.parametrize("rolle, erlaubt", [(A, True), (BL, True), (P, True), (M, False), (L, False)])
def test_prioritaet_setzen(konten, projekt, rolle, erlaubt):
    antwort = client_fuer(konten[rolle]).post(f"/projekte/{projekt.pk}/prioritaet/", {"prioritaet": "2", "weiter": "/projekte/?tag="})
    projekt.refresh_from_db()
    assert antwort.status_code == (302 if erlaubt else 403)
    assert projekt.prioritaet == (2 if erlaubt else None)
    if erlaubt:
        assert antwort.url == "/projekte/?tag="


def test_liste_nach_prioritaet_sortiert(konten):
    for name, prio in [("Ohne", None), ("Zwei", 2), ("Eins", 1), ("Auch ohne", None)]:
        Projekt.objects.create(name=name, prioritaet=prio)
    assert list(Projekt.objects.values_list("name", flat=True)) == ["Eins", "Zwei", "Auch ohne", "Ohne"]
    seite = client_fuer(konten[M]).get("/projekte/").content.decode()
    assert seite.index(">Eins<") < seite.index(">Zwei<") < seite.index(">Auch ohne<")


def test_navigation_projekte_ueberschrift_und_neu_knopf(konten):
    planer = client_fuer(konten[P]).get("/meine-aufgaben/").content.decode()
    assert 'href="/projekte/neu/"' in planer and "Alle Projekte</span>" not in planer
    assert 'href="/projekte/neu/"' not in client_fuer(konten[M]).get("/meine-aufgaben/").content.decode()


def test_mitglieder_als_kaestchen_mit_suche(konten, person_a):
    seite = client_fuer(konten[P]).get("/projekte/neu/").content.decode()
    assert "data-personenauswahl" in seite and 'type="checkbox" name="mitglieder"' in seite
    antwort = client_fuer(konten[P]).post("/projekte/neu/", {
        "name": "Neues Projekt", "farbe": "blau", "mitglieder": [person_a.pk, konten[M].pk],
    })
    assert antwort.status_code == 302
    assert set(Projekt.objects.get(name="Neues Projekt").mitglieder.all()) == {person_a, konten[M].person}


def test_neues_projekt_kommt_in_gesamtansicht(konten):
    gesamt = GanttAnsicht.objects.create(name="Gesamt", neue_projekte_automatisch=True)
    andere = GanttAnsicht.objects.create(name="Bereich A")
    client_fuer(konten[P]).post("/projekte/neu/", {"name": "Halle 3", "farbe": "blau"})
    neu = Projekt.objects.get(name="Halle 3")
    assert neu in gesamt.projekte.all() and neu not in andere.projekte.all()


def test_protokoll_erledigte_aufgaben(konten, aufgabe):
    dienste.erledigt_setzen(konten[M], aufgabe, True)
    dienste.aufgabe_speichern(konten[M], aufgabe, {"titel": "Hallenboden Nord 2"}, None)
    planer = client_fuer(konten[P]).get("/protokoll/").content.decode()
    assert "Erledigte Aufgaben" in planer and "Hallenboden Nord 2" in planer and "Person 01" in planer
    # Planer:innen sehen nur Erledigt-Einträge, auch wenn sie anderes anfordern
    assert "hat geändert" not in client_fuer(konten[P]).get("/protokoll/?ansicht=").content.decode()
    voll = client_fuer(konten[BL]).get("/protokoll/").content.decode()
    assert "Änderungsprotokoll" in voll
    assert Protokolleintrag.objects.filter(objekt_typ="aufgabe", aktion="geaendert").count() == 2
    nur_erledigt = client_fuer(konten[BL]).get("/protokoll/?ansicht=erledigt").content.decode()
    assert nur_erledigt.count('class="liste__zeile"') == 1


def test_posteingang_im_kopf(konten, aufgabe):
    Benachrichtigung.objects.create(empfaenger=konten[M].person, ausloeser=konten[P].person, aufgabe=aufgabe,
                                    art="zuweisung", text="Ihnen wurde eine Aufgabe zugewiesen")
    c = client_fuer(konten[M])
    seite = c.get("/meine-aufgaben/").content.decode()
    assert "mitteilungen__knopf" in seite and "1 ungelesen" in seite
    feld = c.get("/posteingang/feld/").content.decode()
    assert "Ihnen wurde eine Aufgabe zugewiesen" in feld and "mitteilung--neu" in feld
    feld = c.post("/posteingang/feld/").content.decode()
    assert "mitteilung--neu" not in feld and 'hx-swap-oob="true"' in feld
    assert not Benachrichtigung.objects.filter(gelesen_am__isnull=True).exists()
