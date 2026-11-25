"""Räume: Liste unter Einstellungen → Listen, Auswahl im Aufgabendetail, Filter in der Projektliste,
Übernahme in die Folgeaufgabe wiederkehrender Aufgaben."""

import re

import pytest

from kern.models import Protokolleintrag, Raum
from projekte.models import Aufgabe, Status
from projekte.wiederholung import regel_bauen
from zusammenarbeit.verlauf import verlauf_eintraege

from .conftest import BL, MO, A, L, M, P

pytestmark = pytest.mark.django_db


def htmx(client, url, daten=None):
    return client.post(url, daten or {}, HTTP_HX_REQUEST="true")


def feld(client, aufgabe, wert, version=None):
    return client.post(f"/aufgaben/{aufgabe.pk}/feld/", {
        "ansicht": "detail", "feld": "raum", "wert": wert,
        "version": aufgabe.version if version is None else version,
    }, HTTP_HX_REQUEST="true")


@pytest.fixture
def raeume(db):
    return {n: Raum.objects.create(name=n, sortierung=(i + 1) * 10) for i, n in enumerate(["Halle 1", "Werkstatt", "Lager"])}


def neue_aufgabe(projekt, titel, **felder):
    return Aufgabe.objects.create(projekt=projekt, titel=titel, **{"status": Status.standard_offen(), **felder})


# --- Einstellungen → Listen ---

def test_liste_raeume_in_den_einstellungen(client_fuer, konten, raeume, aufgabe):
    aufgabe.raum = raeume["Werkstatt"]
    aufgabe.save()
    seite = client_fuer(konten[A]).get("/einstellungen/listen/").content.decode()
    assert 'id="liste-raum"' in seite and ">Räume</h2>" in seite
    abschnitt = seite[seite.index('id="liste-raum"'):]
    abschnitt = abschnitt[:abschnitt.index("</section>")]
    assert "data-reihenfolge=" in abschnitt  # ziehbar
    assert [n for n in re.findall(r"<span>([^<]+)</span>", abschnitt)] == ["Halle 1", "Werkstatt", "Lager"]
    zeile = abschnitt[abschnitt.index(f'id="eintrag-raum-{raeume["Werkstatt"].pk}"'):]
    zeile = zeile[:zeile.index("</li>")]
    assert "1 Aufgabe" in zeile and "disabled" not in zeile  # verwendet, trotzdem löschbar


def test_raum_anlegen_umbenennen_und_doppelter_name(client_fuer, konten, raeume):
    c = client_fuer(konten[A])
    antwort = htmx(c, "/einstellungen/listen/raum/neu/", {"neu-name": "Büro"})
    assert antwort.status_code == 200 and "Büro" in antwort.content.decode()
    neu = Raum.objects.get(name="Büro")
    assert neu.sortierung > max(r.sortierung for r in raeume.values())  # ans Ende
    assert Protokolleintrag.objects.filter(objekt_typ="raum", objekt_id=neu.pk, aktion="angelegt").exists()
    assert htmx(c, "/einstellungen/listen/raum/neu/", {"neu-name": "Lager"})["X-Fehler"] == "1"
    assert htmx(c, f"/einstellungen/listen/raum/{neu.pk}/", {f"e{neu.pk}-name": "Besprechung"}).status_code == 204
    neu.refresh_from_db()
    assert neu.name == "Besprechung"
    eintrag = Protokolleintrag.objects.filter(objekt_typ="raum", objekt_id=neu.pk, aktion="geaendert").get()
    assert eintrag.daten == {"name": "Besprechung", "vorher": "Büro"}
    antwort = htmx(c, f"/einstellungen/listen/raum/{neu.pk}/", {f"e{neu.pk}-name": "Lager"})
    assert antwort["X-Fehler"] == "1" and antwort["HX-Retarget"] == f"#eintrag-raum-{neu.pk}"
    assert Raum.objects.get(pk=neu.pk).name == "Besprechung"


def test_raeume_sortieren(client_fuer, konten, raeume):
    c = client_fuer(konten[A])
    neu = [raeume["Lager"].pk, raeume["Halle 1"].pk, raeume["Werkstatt"].pk]
    assert c.post("/einstellungen/listen/raum/reihenfolge/", {"ids": neu}, content_type="application/json").status_code == 204
    assert list(Raum.objects.values_list("pk", flat=True)) == neu
    assert Protokolleintrag.objects.get(objekt_typ="raum", aktion="sortiert").daten == {
        "reihenfolge": ["Lager", "Halle 1", "Werkstatt"]}
    assert c.post("/einstellungen/listen/raum/reihenfolge/", {"ids": neu[:2]}, content_type="application/json").status_code == 400


def test_unbenutzten_raum_loeschen(client_fuer, konten, raeume):
    c = client_fuer(konten[A])
    frage = c.get(f"/einstellungen/listen/raum/{raeume['Lager'].pk}/?ansicht=frage").content.decode()
    assert "Raum „Lager“ löschen?" in frage and "keinen Raum mehr" not in frage
    antwort = htmx(c, f"/einstellungen/listen/raum/{raeume['Lager'].pk}/loeschen/")
    assert antwort.status_code == 200 and not Raum.objects.filter(name="Lager").exists()
    assert Protokolleintrag.objects.filter(objekt_typ="raum", aktion="geloescht").exists()


def test_verwendeten_raum_loeschen_aufgaben_ohne_raum(client_fuer, konten, raeume, projekt, aufgabe):
    c = client_fuer(konten[A])
    halle = raeume["Halle 1"]
    zweite = neue_aufgabe(projekt, "Zweite", raum=halle)
    aufgabe.raum = halle
    aufgabe.save()
    andere = neue_aufgabe(projekt, "Andere", raum=raeume["Werkstatt"])
    frage = c.get(f"/einstellungen/listen/raum/{halle.pk}/?ansicht=frage").content.decode()
    assert "Raum „Halle 1“ löschen? 2 Aufgaben haben danach keinen Raum mehr." in frage
    htmx(c, f"/einstellungen/listen/raum/{halle.pk}/loeschen/")
    assert not Raum.objects.filter(pk=halle.pk).exists()
    assert Aufgabe.objects.get(pk=aufgabe.pk).raum is None and Aufgabe.objects.get(pk=zweite.pk).raum is None
    assert Aufgabe.objects.get(pk=andere.pk).raum == raeume["Werkstatt"]
    # Einzahl
    frage = c.get(f"/einstellungen/listen/raum/{raeume['Werkstatt'].pk}/?ansicht=frage").content.decode()
    assert "1 Aufgabe hat danach keinen Raum mehr." in frage


@pytest.mark.parametrize("rolle", [BL, P, M, L])
def test_raeume_pflegen_nur_admin(client_fuer, konten, raeume, rolle):
    """Wie die übrigen Listen: nur mit dem Recht auf Systemeinstellungen."""
    from kern import rechte
    c = client_fuer(konten[rolle])
    erwartet = 200 if rechte.darf_systemeinstellungen(konten[rolle]) else 403
    assert c.get("/einstellungen/listen/").status_code == erwartet
    if erwartet == 403:
        assert htmx(c, "/einstellungen/listen/raum/neu/", {"neu-name": "Büro"}).status_code == 403
        assert htmx(c, f"/einstellungen/listen/raum/{raeume['Lager'].pk}/loeschen/").status_code == 403
        assert Raum.objects.count() == 3


# --- Aufgabendetail ---

def test_raum_setzen_und_entfernen_mit_verlauf(client_fuer, konten, raeume, aufgabe):
    c = client_fuer(konten[P])
    antwort = feld(c, aufgabe, raeume["Werkstatt"].pk)
    assert antwort.status_code == 200
    inhalt = antwort.content.decode()
    assert 'id="feld-raum"' in inhalt and f'<option value="{raeume["Werkstatt"].pk}" selected>Werkstatt</option>' in inhalt
    aufgabe.refresh_from_db()
    assert aufgabe.raum == raeume["Werkstatt"] and aufgabe.version == 2
    eintrag = Protokolleintrag.objects.filter(objekt_typ="aufgabe", aktion="geaendert", aufgabe_id=aufgabe.pk).latest("id")
    assert eintrag.daten == {"raum": [None, {"id": raeume["Werkstatt"].pk, "name": "Werkstatt"}]}
    antwort = feld(c, aufgabe, "")
    assert antwort.status_code == 200
    aufgabe.refresh_from_db()
    assert aufgabe.raum is None and aufgabe.version == 3
    texte = [e["text"] for e in verlauf_eintraege(konten[P], aufgabe) if e["art"] != "kommentar"]
    assert "hat geändert: Raum: – → Werkstatt" in texte and "hat geändert: Raum: Werkstatt → –" in texte


def test_ungueltiger_raum_am_feld(client_fuer, konten, raeume, aufgabe):
    c = client_fuer(konten[P])
    for wert in ("999999", "99999999999999999999", "abc"):
        antwort = feld(c, aufgabe, wert)
        assert antwort.status_code == 200 and "Ungültige Eingabe." in antwort.content.decode()
    assert Aufgabe.objects.get(pk=aufgabe.pk).version == aufgabe.version


def test_raum_nicht_in_der_zeile(client_fuer, konten, raeume, aufgabe):
    """Nur im Detail: die Inline-Bearbeitung der Liste nimmt das Feld nicht an, die Zeile zeigt es nicht."""
    c = client_fuer(konten[P])
    antwort = c.post(f"/aufgaben/{aufgabe.pk}/feld/", {"feld": "raum", "wert": raeume["Lager"].pk,
                                                      "version": aufgabe.version}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 400 and Aufgabe.objects.get(pk=aufgabe.pk).raum is None
    aufgabe.raum = raeume["Lager"]
    aufgabe.save()
    seite = c.get(f"/projekte/{aufgabe.projekt_id}/").content.decode()
    zeile = seite[seite.index(f'id="aufgabe-block-{aufgabe.pk}"'):]
    zeile = zeile[:zeile.index('class="unter-liste"')]
    assert "Lager" not in zeile


def test_detail_zeigt_raum_seite_und_seitenleiste(client_fuer, konten, raeume, aufgabe):
    c = client_fuer(konten[P])
    for url in (f"/aufgaben/{aufgabe.pk}/", f"/projekte/{aufgabe.projekt_id}/?aufgabe={aufgabe.pk}"):
        seite = c.get(url).content.decode()
        assert 'id="eingabe-raum"' in seite and '<option value="">– kein Raum –</option>' in seite
        assert seite.index("Halle 1") < seite.index("Werkstatt") < seite.index("Lager", seite.index("Werkstatt"))
    seite = c.get(f"/aufgaben/{aufgabe.pk}/?seitenleiste=1", HTTP_HX_REQUEST="true").content.decode()
    assert 'id="eingabe-raum"' in seite


def test_ohne_raeume_kein_feld(client_fuer, konten, aufgabe):
    assert 'id="feld-raum"' not in client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()


@pytest.mark.parametrize("rolle", [M, L])
def test_raum_nur_mit_bearbeitungsrecht(client_fuer, konten, raeume, aufgabe, rolle):
    aufgabe.raum = raeume["Halle 1"]
    aufgabe.save()
    c = client_fuer(konten[rolle])
    assert feld(c, aufgabe, raeume["Lager"].pk).status_code == 403
    assert Aufgabe.objects.get(pk=aufgabe.pk).raum == raeume["Halle 1"]
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    feldhtml = seite[seite.index('id="feld-raum"'):]
    feldhtml = feldhtml[:feldhtml.index("</dd>")]
    assert 'id="eingabe-raum"' not in seite and "Halle 1" in feldhtml


def test_projektmitglied_darf_raum_setzen(client_fuer, konten, raeume, aufgabe):
    aufgabe.projekt.mitglieder.add(konten[M].person)
    assert feld(client_fuer(konten[M]), aufgabe, raeume["Lager"].pk).status_code == 200
    assert Aufgabe.objects.get(pk=aufgabe.pk).raum == raeume["Lager"]


def test_wiederholung_uebernimmt_raum(client_fuer, konten, raeume, aufgabe):
    aufgabe.wiederholung = regel_bauen("woechentlich", 1, (), None, MO)
    aufgabe.faellig_am = MO
    aufgabe.raum = raeume["Werkstatt"]
    aufgabe.save()
    unter = neue_aufgabe(aufgabe.projekt, "Unteraufgabe", eltern=aufgabe, abschnitt=aufgabe.abschnitt, raum=raeume["Lager"])
    client_fuer(konten[M]).post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "1"})
    folge = Aufgabe.objects.get(wiederholt_von=aufgabe)
    assert folge.raum == raeume["Werkstatt"]
    assert folge.unteraufgaben.get().raum == raeume["Lager"] and unter.pk != folge.unteraufgaben.get().pk


# --- Filter in der Projektansicht ---

@pytest.fixture
def liste(projekt, raeume, konten):
    return {
        "halle": neue_aufgabe(projekt, "Boden Halle", raum=raeume["Halle 1"]),
        "halle_mir": neue_aufgabe(projekt, "Licht Halle", raum=raeume["Halle 1"], verantwortlich=konten[P].person),
        "werkstatt": neue_aufgabe(projekt, "Werkbank", raum=raeume["Werkstatt"], verantwortlich=konten[P].person),
        "ohne": neue_aufgabe(projekt, "Ohne Raum"),
        "halle_erledigt": neue_aufgabe(projekt, "Tor Halle", raum=raeume["Halle 1"],
                                       status=Status.standard_erledigt()),
    }


def sichtbar(seite, liste):
    return {k for k, a in liste.items() if f'id="aufgabe-block-{a.pk}"' in seite}


def filter_anzahl(seite):
    treffer = re.search(r'<span class="tp-filter-anzahl">(\d+)</span>', seite)
    return int(treffer[1]) if treffer else 0


def test_filter_nach_raum(client_fuer, konten, projekt, raeume, liste):
    c = client_fuer(konten[P])
    seite = c.get(f"/projekte/{projekt.pk}/?raum={raeume['Halle 1'].pk}").content.decode()
    assert sichtbar(seite, liste) == {"halle", "halle_mir"}
    assert filter_anzahl(seite) == 1 and "Filter zurücksetzen" in seite
    assert f'<option value="{raeume["Halle 1"].pk}" selected>Halle 1</option>' in seite
    # Per HTMX wie die übrigen Filter
    seite = c.get(f"/projekte/{projekt.pk}/?raum={raeume['Werkstatt'].pk}", HTTP_HX_REQUEST="true").content.decode()
    assert sichtbar(seite, liste) == {"werkstatt"}


def test_filter_raum_kombiniert(client_fuer, konten, projekt, raeume, liste):
    c = client_fuer(konten[P])
    halle = raeume["Halle 1"].pk
    seite = c.get(f"/projekte/{projekt.pk}/?raum={halle}&verantwortlich=ich").content.decode()
    assert sichtbar(seite, liste) == {"halle_mir"} and filter_anzahl(seite) == 2
    seite = c.get(f"/projekte/{projekt.pk}/?raum={halle}&status=alle").content.decode()
    assert sichtbar(seite, liste) == {"halle", "halle_mir", "halle_erledigt"} and filter_anzahl(seite) == 2
    seite = c.get(f"/projekte/{projekt.pk}/?raum={halle}&status=erledigt&q=tor").content.decode()
    assert sichtbar(seite, liste) == {"halle_erledigt"} and filter_anzahl(seite) == 3
    seite = c.get(f"/projekte/{projekt.pk}/?raum={halle}&q=licht&sort=titel").content.decode()
    assert sichtbar(seite, liste) == {"halle_mir"} and filter_anzahl(seite) == 2


@pytest.mark.parametrize("wert", ["abc", "-1", "0", "999999", "99999999999999999999", "1.5", ""])
def test_ungueltiger_raum_wird_ignoriert(client_fuer, konten, projekt, raeume, liste, wert):
    antwort = client_fuer(konten[P]).get(f"/projekte/{projekt.pk}/?raum={wert}")
    assert antwort.status_code == 200
    seite = antwort.content.decode()
    assert sichtbar(seite, liste) == {"halle", "halle_mir", "werkstatt", "ohne"}
    assert filter_anzahl(seite) == 0 and "Filter zurücksetzen" not in seite


def test_raumauswahl_nur_mit_raeumen_im_projekt(client_fuer, konten, projekt, raeume, liste, aufgabe):
    c = client_fuer(konten[P])
    seite = c.get(f"/projekte/{projekt.pk}/").content.decode()
    assert '<select name="raum"' in seite and "Alle Räume" in seite
    auswahl = seite[seite.index('<select name="raum"'):]
    auswahl = auswahl[:auswahl.index("</select>")]
    assert "Halle 1" in auswahl and "Werkstatt" in auswahl and "Lager" not in auswahl
    # Projekt ohne Räume: keine Auswahl
    anderes = aufgabe.projekt.__class__.objects.create(name="Anderes Projekt", farbe="blau")
    neue_aufgabe(anderes, "Etwas")
    assert '<select name="raum"' not in c.get(f"/projekte/{anderes.pk}/").content.decode()
    # Ein gewählter Raum bleibt in der Auswahl, auch wenn er im Projekt nicht vorkommt
    seite = c.get(f"/projekte/{anderes.pk}/?raum={raeume['Lager'].pk}").content.decode()
    assert f'<option value="{raeume["Lager"].pk}" selected>Lager</option>' in seite and filter_anzahl(seite) == 1


def test_filter_zuruecksetzen_ohne_raum(client_fuer, konten, projekt, raeume, liste):
    seite = client_fuer(konten[P]).get(f"/projekte/{projekt.pk}/?raum={raeume['Halle 1'].pk}").content.decode()
    assert f'<a class="knopf knopf--text klein" href="/projekte/{projekt.pk}/">Filter zurücksetzen</a>' in seite
