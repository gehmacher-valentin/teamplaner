"""Projektliste: Priorität, Navigation, Mitgliederauswahl; Protokoll „erledigte Aufgaben“; Posteingang im Kopf;
Gantt-Gesamtansicht nimmt neue Projekte auf."""

import re

import pytest
from django.utils import timezone

from gantt.models import GanttAnsicht
from kern.models import Protokolleintrag
from projekte import dienste
from projekte.forms import ProjektForm
from projekte.models import Abschnitt, Aufgabe, Projekt, Projektfarbe, Tag
from zusammenarbeit.models import Benachrichtigung

from .conftest import BL, A, L, M, P, angemeldet

pytestmark = pytest.mark.django_db



@pytest.mark.parametrize("rolle, erlaubt", [(A, True), (BL, True), (P, True), (M, False), (L, False)])
def test_prioritaet_setzen(konten, projekt, rolle, erlaubt):
    antwort = angemeldet(konten[rolle]).post(f"/projekte/{projekt.pk}/prioritaet/", {"prioritaet": "2", "weiter": "/projekte/?archiv=1"})
    projekt.refresh_from_db()
    assert antwort.status_code == (302 if erlaubt else 403)
    assert projekt.prioritaet == (2 if erlaubt else None)
    if erlaubt:
        assert antwort.url == "/projekte/?archiv=1"


@pytest.mark.parametrize("wert, erwartet", [("10", 10), ("11", None), ("0", None)])
def test_prioritaet_bis_10(konten, projekt, wert, erwartet):
    projekt.prioritaet = 3
    projekt.save()
    angemeldet(konten[P]).post(f"/projekte/{projekt.pk}/prioritaet/", {"prioritaet": wert})
    projekt.refresh_from_db()
    assert projekt.prioritaet == erwartet
    seite = angemeldet(konten[P]).get("/projekte/").content.decode()
    assert '<option value="10"' in seite and '<option value="11"' not in seite


def test_projektformular_prioritaet_bis_10():
    werte = [w for w, _ in ProjektForm().fields["prioritaet"].choices if w != ""]
    assert werte == list(range(1, 11))


def test_liste_nach_prioritaet_sortiert(konten):
    for name, prio in [("Ohne", None), ("Zehn", 10), ("Zwei", 2), ("Eins", 1), ("Auch ohne", None)]:
        Projekt.objects.create(name=name, prioritaet=prio)
    assert list(Projekt.objects.values_list("name", flat=True)) == ["Eins", "Zwei", "Zehn", "Auch ohne", "Ohne"]
    seite = angemeldet(konten[M]).get("/projekte/").content.decode()
    assert seite.index(">Eins<") < seite.index(">Zwei<") < seite.index(">Auch ohne<")


def test_navigation_projekte_ueberschrift_und_neu_knopf(konten):
    planer = angemeldet(konten[P]).get("/meine-aufgaben/").content.decode()
    assert 'href="/projekte/neu/"' in planer and "Alle Projekte</span>" not in planer
    assert 'href="/projekte/neu/"' not in angemeldet(konten[M]).get("/meine-aufgaben/").content.decode()


def test_mitglieder_als_kaestchen_mit_suche(konten, person_a):
    seite = angemeldet(konten[P]).get("/projekte/neu/").content.decode()
    assert "data-personenauswahl" in seite and 'type="checkbox" name="mitglieder"' in seite
    antwort = angemeldet(konten[P]).post("/projekte/neu/", {
        "name": "Neues Projekt", "farbe": "blau", "mitglieder": [person_a.pk, konten[M].pk],
    })
    assert antwort.status_code == 302
    assert set(Projekt.objects.get(name="Neues Projekt").mitglieder.all()) == {person_a, konten[M].person}


def test_neues_projekt_kommt_in_gesamtansicht(konten):
    gesamt = GanttAnsicht.objects.create(name="Gesamt", neue_projekte_automatisch=True)
    andere = GanttAnsicht.objects.create(name="Bereich A")
    angemeldet(konten[P]).post("/projekte/neu/", {"name": "Halle 3", "farbe": "blau"})
    neu = Projekt.objects.get(name="Halle 3")
    assert neu in gesamt.projekte.all() and neu not in andere.projekte.all()


def test_protokoll_erledigte_aufgaben(konten, aufgabe):
    dienste.erledigt_setzen(konten[M], aufgabe, True)
    dienste.aufgabe_speichern(konten[M], aufgabe, {"titel": "Hallenboden Nord 2"}, None)
    planer = angemeldet(konten[P]).get("/protokoll/").content.decode()
    assert "Erledigte Aufgaben" in planer and "Hallenboden Nord 2" in planer and "Person 01" in planer
    # Planer:innen sehen nur Erledigt-Einträge, auch wenn sie anderes anfordern
    assert "hat geändert" not in angemeldet(konten[P]).get("/protokoll/?ansicht=").content.decode()
    voll = angemeldet(konten[BL]).get("/protokoll/").content.decode()
    assert "Änderungsprotokoll" in voll
    assert Protokolleintrag.objects.filter(objekt_typ="aufgabe", aktion="geaendert").count() == 2
    nur_erledigt = angemeldet(konten[BL]).get("/protokoll/?ansicht=erledigt").content.decode()
    assert nur_erledigt.count('class="liste__zeile"') == 1


def test_posteingang_im_kopf(konten, aufgabe):
    Benachrichtigung.objects.create(empfaenger=konten[M].person, ausloeser=konten[P].person, aufgabe=aufgabe,
                                    art="zuweisung", text="Ihnen wurde eine Aufgabe zugewiesen")
    c = angemeldet(konten[M])
    seite = c.get("/meine-aufgaben/").content.decode()
    assert "mitteilungen__knopf" in seite and "1 ungelesen" in seite
    feld = c.get("/posteingang/feld/").content.decode()
    assert "Ihnen wurde eine Aufgabe zugewiesen" in feld and "mitteilung--neu" in feld
    feld = c.post("/posteingang/feld/").content.decode()
    assert "mitteilung--neu" not in feld and 'hx-swap-oob="true"' in feld
    assert not Benachrichtigung.objects.filter(gelesen_am__isnull=True).exists()


def test_projekt_tags_ausgeblendet(konten, projekt, aufgabe):
    """Tags bleiben im Datenmodell, erscheinen aber nirgends mehr; Bearbeiten lässt sie unverändert."""
    tag = Tag.objects.create(name="Tagname-Unsichtbar")
    projekt.tags.add(tag)
    c = angemeldet(konten[A])
    for url in ["/projekte/", f"/projekte/{projekt.pk}/", f"/projekte/{projekt.pk}/bearbeiten/", "/projekte/neu/",
                f"/aufgaben/{aufgabe.pk}/", "/suche/?q=Lagerhalle", "/einstellungen/listen/"]:
        seite = c.get(url).content.decode()
        assert "Tagname-Unsichtbar" not in seite and "tags_text" not in seite and "Projekt-Tags" not in seite, url
    assert c.get(f"/einstellungen/listen/tag/{tag.pk}/?ansicht=frage").status_code == 404
    antwort = c.post(f"/projekte/{projekt.pk}/bearbeiten/", {"name": projekt.name, "farbe": projekt.farbe})
    assert antwort.status_code == 302
    assert list(projekt.tags.all()) == [tag]


# --- Projektfarbe: Vorschau und Vorauswahl ---

def test_farbe_als_farbpunkte_mit_namen(konten, projekt):
    seite = angemeldet(konten[P]).get(f"/projekte/{projekt.pk}/bearbeiten/").content.decode()
    assert 'role="radiogroup"' in seite and "<select name=\"farbe\"" not in seite
    for farbe in Projektfarbe:
        assert f'pf-{farbe.value}" title="{farbe.label}"' in seite
    # Bearbeiten: die gespeicherte Farbe bleibt ausgewählt
    assert f'value="{projekt.farbe}" checked' in seite


def test_neues_projekt_bekommt_seltenste_farbe(konten):
    for farbe in Projektfarbe.values:
        if farbe != Projektfarbe.OLIV:
            Projekt.objects.create(name=f"P {farbe}", farbe=farbe)
    Projekt.objects.create(name="Archiviert", farbe=Projektfarbe.OLIV, archiviert_am=timezone.now())
    assert ProjektForm().initial["farbe"] == Projektfarbe.OLIV  # archivierte zählen nicht
    seite = angemeldet(konten[P]).get("/projekte/neu/").content.decode()
    assert 'value="oliv" checked' in seite


def test_vorauswahl_zufaellig_aus_allen_farben_inklusive_grau(konten, projekt):
    assert projekt.farbe == "bernstein"
    gesehen = {ProjektForm().initial["farbe"] for _ in range(200)}
    assert gesehen == set(Projektfarbe.values) - {"bernstein"}
    assert ProjektForm(instance=projekt).initial["farbe"] == "bernstein"


# ---------- Aufgabe anlegen: Knopf neben dem Eingabefeld (#86) ----------

def neue_aufgabe_formulare(seite):
    """Die Formulare „+ Aufgabe hinzufügen“ der Projektseite."""
    return re.findall(r'<form class="liste__zeile neue-aufgabe" hx-post="([^"]+)".*?</form>', seite, re.S)


def test_aufgabe_anlegen_mit_knopf_ohne_und_mit_abschnitt(konten, projekt):
    c = angemeldet(konten[P])
    # Ohne Abschnitte: ein Formular für Aufgaben ohne Abschnitt, mit Knopf
    seite = c.get(f"/projekte/{projekt.pk}/").content.decode()
    assert neue_aufgabe_formulare(seite) == [f"/projekte/{projekt.pk}/aufgaben/"]
    assert 'class="knopf knopf--klein neue-aufgabe__knopf">Hinzufügen</button>' in seite
    antwort = c.post(f"/projekte/{projekt.pk}/aufgaben/", {"titel": "Fundament"}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200 and "Fundament" in antwort.content.decode()
    assert Aufgabe.objects.get(titel="Fundament").abschnitt is None
    # Mit Abschnitt: je Abschnitt ein Formular mit Knopf
    abschnitt = Abschnitt.objects.create(projekt=projekt, name="Montage")
    seite = c.get(f"/projekte/{projekt.pk}/").content.decode()
    assert neue_aufgabe_formulare(seite) == [f"/projekte/{projekt.pk}/abschnitte/{abschnitt.pk}/aufgaben/"]
    assert seite.count("neue-aufgabe__knopf") == 1
    c.post(f"/projekte/{projekt.pk}/abschnitte/{abschnitt.pk}/aufgaben/", {"titel": "Stützen"}, HTTP_HX_REQUEST="true")
    assert Aufgabe.objects.get(titel="Stützen").abschnitt == abschnitt
    # Leerer Titel: nichts angelegt
    assert c.post(f"/projekte/{projekt.pk}/aufgaben/", {"titel": "  "}, HTTP_HX_REQUEST="true").status_code == 400
    assert Aufgabe.objects.count() == 2


def test_ohne_bearbeitungsrecht_kein_formular(konten, projekt):
    seite = angemeldet(konten[M]).get(f"/projekte/{projekt.pk}/").content.decode()
    assert "neue-aufgabe__knopf" not in seite
