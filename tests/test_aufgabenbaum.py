"""Projektliste als Baum: Ziehen innerhalb und zwischen Abschnitten, eine Ebene höher und
tiefer, Grenzen und Rechte; neue Projekte ohne Abschnitte; Pfad im Teamplaner; Abmelden während HTMX."""

import pytest

from kern.models import Protokolleintrag, Rolle
from planung.raster import palette
from projekte.models import Abschnitt, Aufgabe, Projekt, Status

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def neu(projekt, abschnitt, titel, eltern=None, sortierung=0, erledigt=False):
    status = Status.standard_erledigt() if erledigt else Status.standard_offen()
    return Aufgabe.objects.create(projekt=projekt, abschnitt=eltern.abschnitt if eltern else abschnitt, eltern=eltern,
                                  titel=titel, status=status, sortierung=sortierung)


def verschieben(client, projekt, aufgabe, eltern=None, abschnitt=None, vor=None):
    return client.post(f"/projekte/{projekt.pk}/aufgaben/verschieben/", {
        "id": aufgabe.pk, "eltern": eltern.pk if eltern else None,
        "abschnitt": abschnitt.pk if abschnitt else None, "vor": vor.pk if vor else None,
    }, format="json")


def reihe(projekt, **filter_):
    return list(Aufgabe.objects.filter(projekt=projekt, **filter_).order_by("sortierung", "id").values_list("titel", flat=True))


@pytest.fixture
def liste(projekt, abschnitt):
    """Abschnitt „Fertigung“ mit a, b (erledigt), c; „Montage“ mit d."""
    montage = Abschnitt.objects.create(projekt=projekt, name="Montage", sortierung=10)
    a = neu(projekt, abschnitt, "a", sortierung=10)
    b = neu(projekt, abschnitt, "b", sortierung=20, erledigt=True)
    c = neu(projekt, abschnitt, "c", sortierung=30)
    d = neu(projekt, montage, "d", sortierung=10)
    return {"a": a, "b": b, "c": c, "d": d, "montage": montage}


def test_reihenfolge_mit_ausgeblendeter_aufgabe(client_fuer, konten, projekt, abschnitt, liste):
    # Im Filter „Offen“ sieht man nur a und c; c vor a ziehen lässt die erledigte b an ihrem Platz
    assert verschieben(client_fuer(konten[P]), projekt, liste["c"], abschnitt=abschnitt, vor=liste["a"]).status_code == 204
    assert reihe(projekt, abschnitt=abschnitt) == ["c", "a", "b"]


def test_in_anderen_abschnitt_mit_unteraufgaben(client_fuer, konten, projekt, liste):
    kind = neu(projekt, None, "a1", eltern=liste["a"])
    verschieben(client_fuer(konten[P]), projekt, liste["a"], abschnitt=liste["montage"])
    kind.refresh_from_db()
    assert reihe(projekt, abschnitt=liste["montage"], eltern=None) == ["d", "a"]
    assert kind.abschnitt == liste["montage"]


def test_eine_ebene_tiefer_und_wieder_hoeher(client_fuer, konten, projekt, abschnitt, liste):
    c = client_fuer(konten[P])
    # c in a hineinziehen: c wird Unteraufgabe von a (samt eigener Unteraufgabe)
    c1 = neu(projekt, None, "c1", eltern=liste["c"])
    assert verschieben(c, projekt, liste["c"], eltern=liste["a"]).status_code == 204
    liste["c"].refresh_from_db()
    assert liste["c"].eltern == liste["a"] and liste["c"].tiefe == 1
    c1.refresh_from_db()
    assert c1.tiefe == 2
    assert Protokolleintrag.objects.filter(objekt_typ="unteraufgabe", aktion="hierher", aufgabe_id=liste["a"].pk).exists()
    # wieder heraus in den Abschnitt „Montage“, vor d
    assert verschieben(c, projekt, liste["c"], abschnitt=liste["montage"], vor=liste["d"]).status_code == 204
    liste["c"].refresh_from_db()
    assert liste["c"].eltern is None and liste["c"].abschnitt == liste["montage"]
    assert reihe(projekt, abschnitt=liste["montage"], eltern=None) == ["c", "d"]
    assert Protokolleintrag.objects.filter(objekt_typ="unteraufgabe", aktion="weg", aufgabe_id=liste["a"].pk).exists()
    assert Protokolleintrag.objects.filter(objekt_typ="aufgabe", objekt_id=liste["c"].pk, aktion="geaendert",
                                           daten__has_key="eltern").count() == 2


def test_nicht_zu_tief_und_nicht_in_sich_selbst(client_fuer, konten, projekt, abschnitt, liste):
    c = client_fuer(konten[P])
    a1 = neu(projekt, None, "a1", eltern=liste["a"])
    a2 = neu(projekt, None, "a2", eltern=a1)
    a3 = neu(projekt, None, "a3", eltern=a2)
    # in die eigene Unteraufgabe
    assert verschieben(c, projekt, liste["a"], eltern=a2).status_code == 400
    # c auf Ebene 4 wäre zu tief, c mit Unteraufgabe unter a2 ebenso
    assert verschieben(c, projekt, liste["c"], eltern=a3).status_code == 400
    neu(projekt, None, "c1", eltern=liste["c"])
    assert verschieben(c, projekt, liste["c"], eltern=a2).status_code == 400
    assert verschieben(c, projekt, liste["c"], eltern=a1).status_code == 204
    # Aufgaben anderer Projekte gibt es hier nicht
    fremd = Projekt.objects.create(name="Anderes Projekt")
    fremde = Aufgabe.objects.create(projekt=fremd, titel="x", status=Status.standard_offen())
    assert verschieben(c, projekt, liste["d"], eltern=fremde).status_code == 404


@pytest.mark.parametrize("rolle, status", [(A, 204), (BL, 204), (P, 204), (M, 403), (L, 403)])
def test_verschieben_rechte(client_fuer, konten, projekt, liste, rolle, status):
    assert verschieben(client_fuer(konten[rolle]), projekt, liste["c"], eltern=liste["a"]).status_code == status


def test_projektmitglied_darf_verschieben(client_fuer, konten, projekt, liste):
    projekt.mitglieder.add(konten[M].person)
    assert verschieben(client_fuer(konten[M]), projekt, liste["c"], eltern=liste["a"]).status_code == 204


def test_liste_ist_auch_mit_filter_ziehbar(client_fuer, konten, projekt, liste):
    c = client_fuer(konten[P])
    standard = c.get(f"/projekte/{projekt.pk}/").content.decode()  # Filter „Offen“
    assert "data-aufgaben-baum" in standard and 'class="ziehgriff aufgabe-griff"' in standard
    assert "data-aufgaben-baum" not in c.get(f"/projekte/{projekt.pk}/?sort=faellig").content.decode()
    assert "data-aufgaben-baum" not in client_fuer(konten[L]).get(f"/projekte/{projekt.pk}/").content.decode()


# --- Neue Projekte ohne Abschnitte ---

def test_neues_projekt_ist_leer(client_fuer, konten):
    c = client_fuer(konten[P])
    c.post("/projekte/neu/", {"name": "Halle 3", "farbe": "blau"})
    projekt = Projekt.objects.get(name="Halle 3")
    assert not projekt.abschnitte.exists()
    seite = c.get(f"/projekte/{projekt.pk}/").content.decode()
    assert f'hx-post="/projekte/{projekt.pk}/aufgaben/"' in seite
    antwort = c.post(f"/projekte/{projekt.pk}/aufgaben/", {"titel": "Erste Aufgabe"}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200 and "Erste Aufgabe" in antwort.content.decode()
    aufgabe = projekt.aufgaben.get()
    assert aufgabe.abschnitt is None
    assert "Erste Aufgabe" in c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()


def test_letzter_abschnitt_darf_weg(client_fuer, konten, projekt, abschnitt):
    client_fuer(konten[P]).post(f"/abschnitte/{abschnitt.pk}/", {"loeschen": "1"})
    assert not projekt.abschnitte.exists()


def test_aufgabe_ohne_abschnitt_in_einen_abschnitt_ziehen(client_fuer, konten, projekt, abschnitt):
    lose = neu(projekt, None, "lose")
    assert verschieben(client_fuer(konten[P]), projekt, lose, abschnitt=abschnitt).status_code == 204
    lose.refresh_from_db()
    assert lose.abschnitt == abschnitt
    seite = client_fuer(konten[P]).get(f"/projekte/{projekt.pk}/").content.decode()
    assert "abschnitt--ohne" not in seite  # keine losen Aufgaben mehr, Abschnitte vorhanden


# --- Teamplaner: Pfad der Zugehörigkeit ---

def test_palette_zeigt_pfad_tieferer_ebenen(konten, projekt, abschnitt, aufgabe):
    eins = neu(projekt, None, "Boden", eltern=aufgabe)
    zwei = neu(projekt, None, "Platten", eltern=eins)
    daten = palette(konten[P], modus="projekt", projekt_id=projekt.pk)
    pfade = {a["titel"]: a["eltern"] for a in daten["aufgaben"]}
    assert pfade == {"Hallenboden Nord": None, "Boden": "Hallenboden Nord", "Platten": "Hallenboden Nord › Boden"}
    assert [a["titel"] for a in palette(konten[P], modus="projekt", suche="Boden")["aufgaben"]] != []
    assert zwei.tiefe == 2


# --- Abmelden: Seite nicht weiter anzeigen ---

def test_htmx_abfrage_ohne_anmeldung_laedt_seite_neu(client_fuer):
    antwort = client_fuer(None).get("/posteingang/zahl/", HTTP_HX_REQUEST="true", HTTP_X_HINTERGRUND="1")
    assert antwort.status_code == 204 and antwort["HX-Refresh"] == "true"
    # ohne HTMX weiterhin normale Weiterleitung zur Anmeldung
    assert client_fuer(None).get("/posteingang/zahl/").status_code == 302


def test_admin_nach_inaktivitaet_abgemeldet_api_meldet_401(client_fuer, konten, settings):
    import time

    from kern.middleware import LETZTE_AKTIVITAET

    c = client_fuer(konten[A])
    sitzung = c.session
    sitzung[LETZTE_AKTIVITAET] = time.time() - (settings.TEAMPLANER_ADMIN_INAKTIV_MINUTEN + 1) * 60
    sitzung.save()
    antwort = c.get("/posteingang/zahl/", HTTP_HX_REQUEST="true", HTTP_X_HINTERGRUND="1")
    assert antwort["HX-Redirect"] == "/anmelden/"
    # danach: weitere Abfragen laden die Seite neu, die API antwortet mit 401 statt 403
    assert c.get("/posteingang/zahl/", HTTP_HX_REQUEST="true")["HX-Refresh"] == "true"
    assert c.get("/api/planung/ansichten").status_code == 401
