"""Einstellungsbereich: sofort speichernde Schalter, Listen-Editor, Kalender mit Zeiträumen,
Personenliste, Freigaben je Person und Ansichten mit Reihenfolge."""

import json
from datetime import date

import pytest

from gantt.models import GanttAnsicht, GanttFreigabe
from kern.models import Bereich, Gewerk, Protokolleintrag, Rolle
from planung.kalender import neue_freie_tage, zeitraeume
from planung.models import AnsichtFreigabe, FreierTag, Recht, TeamplanerAnsicht
from projekte.models import Aufgabe, Status, Tag

from .conftest import ROLLEN, freigeben

pytestmark = pytest.mark.django_db
A, BL, P, M, L = ROLLEN


def htmx(client, url, daten=None):
    return client.post(url, daten or {}, HTTP_HX_REQUEST="true")


# --- Schalter speichern sofort, nur das eigene Konto ---

def test_darstellung_speichert_sofort_nur_eigenes_konto(client_fuer, konten):
    c = client_fuer(konten[M])
    for feld in ("feier_animation", "gantt_unteraufgaben_offen"):
        antwort = htmx(c, "/einstellungen/darstellung/speichern/", {"feld": feld, "an": "1"})
        assert antwort.status_code == 204 and json.loads(antwort["HX-Trigger"])["toasts"][0]["art"] == "erfolg"
    konten[M].refresh_from_db()
    konten[P].refresh_from_db()
    assert konten[M].feier_animation and konten[M].gantt_unteraufgaben_offen
    assert not konten[P].feier_animation and not konten[P].gantt_unteraufgaben_offen
    htmx(c, "/einstellungen/darstellung/speichern/", {"feld": "feier_animation"})  # Schalter aus: kein „an“
    konten[M].refresh_from_db()
    assert not konten[M].feier_animation
    assert htmx(c, "/einstellungen/darstellung/speichern/", {"feld": "rolle", "an": "1"}).status_code == 400
    assert htmx(c, "/einstellungen/darstellung/speichern/", {"feld": "sprache", "wert": "xx"}).status_code == 400


def _mit_zwei_faktor(client_fuer, konto):
    from kern import zwei_faktor

    zwei_faktor.einrichten(konto, zwei_faktor.neues_geheimnis(), 1)
    c = client_fuer(konto)
    sitzung = c.session
    sitzung[zwei_faktor.SITZUNG] = zwei_faktor.marke(konto)  # Code in dieser Sitzung schon eingegeben
    sitzung.save()
    return c


def test_sicherheit_fragt_passwort_erst_in_der_rueckfrage(client_fuer, konten, settings):
    seite = _mit_zwei_faktor(client_fuer, konten[M]).get("/einstellungen/sicherheit/").content.decode()
    assert 'id="dlg-ersatzcodes"' in seite and 'id="dlg-ausschalten"' in seite
    vor_dialog = seite[:seite.index('<dialog')]
    assert 'name="passwort"' not in vor_dialog and 'name="old_password"' in vor_dialog
    assert "Abmelden" not in seite[seite.index('class="einst"'):]  # nur im Kopfmenü
    # Pflicht für Bereichsleitung: kein Ausschalten
    settings.TEAMPLANER_ZWEI_FAKTOR_PFLICHT = True
    seite = _mit_zwei_faktor(client_fuer, konten[BL]).get("/einstellungen/sicherheit/").content.decode()
    assert 'id="dlg-ausschalten"' not in seite and "Pflicht" in seite


def test_profil_zeigt_bild_einmal(client_fuer, konten):
    seite = client_fuer(konten[M]).get("/einstellungen/profil/").content.decode()
    inhalt = seite[seite.index('class="einst__inhalt'):]
    assert inhalt.count('class="avatar') == 1 and 'data-auto-absenden' in inhalt
    assert "Installiert" not in seite  # Version nur unter „Über“


# --- Listen-Editor ---

@pytest.mark.parametrize("rolle", [BL, P, M])
def test_listen_nur_admin(client_fuer, konten, rolle):
    status = Status.objects.first()
    c = client_fuer(konten[rolle])
    assert c.get("/einstellungen/listen/").status_code == 403
    assert htmx(c, f"/einstellungen/listen/status/{status.pk}/", {f"e{status.pk}-name": "x"}).status_code == 403
    assert htmx(c, f"/einstellungen/listen/status/{status.pk}/loeschen/").status_code == 403
    assert c.post("/einstellungen/listen/status/reihenfolge/", {"ids": []}, content_type="application/json").status_code == 403


def test_eintrag_umbenennen_und_doppelter_name_am_feld(client_fuer, konten):
    c = client_fuer(konten[A])
    gewerk, anderes = Gewerk.objects.create(name="Elektrik"), Gewerk.objects.create(name="Montage")
    antwort = htmx(c, f"/einstellungen/listen/gewerk/{gewerk.pk}/", {f"e{gewerk.pk}-name": "Fertigung"})
    assert antwort.status_code == 204
    gewerk.refresh_from_db()
    assert gewerk.name == "Fertigung"
    assert Protokolleintrag.objects.filter(objekt_typ="gewerk", objekt_id=gewerk.pk, aktion="geaendert").exists()
    antwort = htmx(c, f"/einstellungen/listen/gewerk/{gewerk.pk}/", {f"e{gewerk.pk}-name": anderes.name})
    assert antwort["X-Fehler"] == "1" and antwort["HX-Retarget"] == f"#eintrag-gewerk-{gewerk.pk}"
    assert 'class="fehlerliste einst-zeile__fehler"' in antwort.content.decode()
    gewerk.refresh_from_db()
    assert gewerk.name == "Fertigung"


def test_status_farbe_und_erledigt(client_fuer, konten):
    status = Status.objects.create(name="Abgenommen", farbe="grau", sortierung=50)
    htmx(client_fuer(konten[A]), f"/einstellungen/listen/status/{status.pk}/",
         {f"e{status.pk}-name": "Abgenommen", f"e{status.pk}-farbe": "orange", f"e{status.pk}-ist_erledigt": "on"})
    status.refresh_from_db()
    assert (status.farbe, status.ist_erledigt) == ("orange", True)


def test_hinzufuegen_ans_ende(client_fuer, konten):
    c = client_fuer(konten[A])
    antwort = htmx(c, "/einstellungen/listen/bereich/neu/", {"neu-name": "Bereich A Süd"})
    assert antwort.status_code == 200 and "autofocus" in antwort.content.decode()  # Fokus bleibt für den nächsten
    neu = Bereich.objects.get(name="Bereich A Süd")
    assert neu.sortierung > max(b.sortierung for b in Bereich.objects.exclude(pk=neu.pk))
    assert htmx(c, "/einstellungen/listen/tag/neu/", {"neu-name": ""})["X-Fehler"] == "1"


def test_loeschen_mit_rueckfrage_und_verwendung(client_fuer, konten, projekt):
    c = client_fuer(konten[A])
    gewerk = Gewerk.objects.create(name="Gewerk 03")
    gewerk.personen.add(konten[M].person, konten[P].person)
    frage = c.get(f"/einstellungen/listen/gewerk/{gewerk.pk}/?ansicht=frage").content.decode()
    assert "Gewerk „Gewerk 03“ löschen? Es ist 2 Personen zugeordnet." in frage
    tag = Tag.objects.create(name="Tag 02")
    projekt.tags.add(tag)
    frage = c.get(f"/einstellungen/listen/tag/{tag.pk}/?ansicht=frage").content.decode()
    assert "Tag „Tag 02“ löschen? Er hängt an 1 Projekt." in frage
    htmx(c, f"/einstellungen/listen/gewerk/{gewerk.pk}/loeschen/")
    assert not Gewerk.objects.filter(pk=gewerk.pk).exists()
    assert Protokolleintrag.objects.filter(objekt_typ="gewerk", aktion="geloescht").exists()


def test_verwendeter_status_und_bereich_nicht_loeschbar(client_fuer, konten, aufgabe, bereich_a):
    c = client_fuer(konten[A])
    seite = c.get("/einstellungen/listen/").content.decode()
    zeile = seite[seite.index(f'id="eintrag-status-{aufgabe.status_id}"'):]
    zeile = zeile[:zeile.index("</li>")]
    assert "1 Aufgabe" in zeile and "disabled" in zeile  # Mülleimer gesperrt
    assert "löschen?" not in c.get(f"/einstellungen/listen/status/{aufgabe.status_id}/?ansicht=frage").content.decode()
    htmx(c, f"/einstellungen/listen/status/{aufgabe.status_id}/loeschen/")
    htmx(c, f"/einstellungen/listen/bereich/{bereich_a.pk}/loeschen/")
    assert Status.objects.filter(pk=aufgabe.status_id).exists() and Bereich.objects.filter(pk=bereich_a.pk).exists()


def test_reihenfolge_ziehen(client_fuer, konten):
    c = client_fuer(konten[A])
    ids = list(Status.objects.values_list("pk", flat=True))
    neu = list(reversed(ids))
    antwort = c.post("/einstellungen/listen/status/reihenfolge/", {"ids": neu}, content_type="application/json")
    assert antwort.status_code == 204
    assert list(Status.objects.values_list("pk", flat=True)) == neu
    assert Protokolleintrag.objects.filter(objekt_typ="status", aktion="sortiert").exists()
    # unvollständig oder nicht ziehbar (Gewerke sind alphabetisch)
    assert c.post("/einstellungen/listen/status/reihenfolge/", {"ids": neu[:1]}, content_type="application/json").status_code == 400
    assert c.post("/einstellungen/listen/gewerk/reihenfolge/", {"ids": []}, content_type="application/json").status_code == 400


# --- Kalender ---

def test_zeitraum_ueberspringt_wochenende_feiertage_und_vorhandene():
    # 22.12.2026 (Di) bis 08.01.2027 (Fr): 24.–26.12., 1.1. und 6.1. sind schon frei bzw. Feiertag
    neu = neue_freie_tage(date(2026, 12, 22), date(2027, 1, 8), vorhanden={date(2026, 12, 23)})
    assert date(2026, 12, 25) not in neu and date(2026, 12, 26) not in neu and date(2027, 1, 1) not in neu
    assert date(2027, 1, 6) not in neu and date(2026, 12, 23) not in neu
    assert all(d.weekday() < 5 for d in neu)
    assert neu[:3] == [date(2026, 12, 22), date(2026, 12, 24), date(2026, 12, 28)]


def test_zeitraeume_zusammenfassen():
    tage = [FreierTag(datum=d, bezeichnung="Betriebsurlaub") for d in
            (date(2026, 12, 24), date(2026, 12, 28), date(2026, 12, 29), date(2026, 12, 30), date(2026, 12, 31))]
    tage.append(FreierTag(datum=date(2027, 1, 4), bezeichnung="Betriebsurlaub"))  # 1.1. Feiertag, 2./3.1. Wochenende
    tage.append(FreierTag(datum=date(2027, 1, 7), bezeichnung="Betriebsurlaub"))  # 5.1. Werktag dazwischen: neu
    ergebnis = zeitraeume(tage)
    assert [(z["von"], z["bis"], len(z["tage"])) for z in ergebnis] == [
        (date(2026, 12, 24), date(2027, 1, 4), 6), (date(2027, 1, 7), date(2027, 1, 7), 1)]


@pytest.mark.parametrize("rolle", [BL, P])
def test_kalender_nur_admin(client_fuer, konten, rolle):
    c = client_fuer(konten[rolle])
    assert c.get("/einstellungen/kalender/").status_code == 403
    assert c.post("/einstellungen/kalender/", {"von": "2026-12-24", "bezeichnung": "x"}).status_code == 403


def test_kalender_eintragen_umbenennen_loeschen(client_fuer, konten):
    c = client_fuer(konten[A])
    c.post("/einstellungen/kalender/", {"von": "2026-12-24", "bis": "2026-12-31", "bezeichnung": "Betriebsurlaub"})
    assert sorted(FreierTag.objects.values_list("datum", flat=True)) == [
        date(2026, 12, 24), date(2026, 12, 28), date(2026, 12, 29), date(2026, 12, 30), date(2026, 12, 31)]
    assert Protokolleintrag.objects.filter(objekt_typ="freiertag", aktion="angelegt").get().daten["tage"] == 5
    seite = c.get("/einstellungen/kalender/").content.decode()
    assert "Betriebsurlaub" in seite and "5 Tage" in seite and "automatisch" in seite
    # nochmal derselbe Zeitraum: nichts Neues
    c.post("/einstellungen/kalender/", {"von": "2026-12-24", "bis": "2026-12-31", "bezeichnung": "Betriebsurlaub"})
    assert FreierTag.objects.count() == 5
    zeitraum = {"von": "2026-12-24", "bis": "2026-12-31", "alt": "Betriebsurlaub"}
    c.post("/einstellungen/kalender/zeitraum/", {**zeitraum, "bezeichnung": "Weihnachtsferien"})
    assert set(FreierTag.objects.values_list("bezeichnung", flat=True)) == {"Weihnachtsferien"}
    einzel = FreierTag.objects.get(datum=date(2026, 12, 28))
    c.post(f"/einstellungen/kalender/{einzel.pk}/")
    assert FreierTag.objects.count() == 4
    c.post("/einstellungen/kalender/zeitraum/", {**zeitraum, "alt": "Weihnachtsferien", "aktion": "loeschen"})
    assert not FreierTag.objects.exists()
    seite = c.post("/einstellungen/kalender/", {"von": "2026-12-31", "bis": "2026-12-24", "bezeichnung": "x"}).content.decode()
    assert "„Bis“ liegt vor „Von“." in seite


def test_freie_tage_im_teamplaner(client_fuer, konten):
    from planung.kalender import freie_tage

    client_fuer(konten[A]).post("/einstellungen/kalender/", {"von": "2026-11-02", "bezeichnung": "Fenstertag"})
    assert freie_tage(date(2026, 11, 2), date(2026, 11, 2)) == {date(2026, 11, 2): "Fenstertag"}


# --- Personen ---

def test_planer_sieht_nur_platzhalter(client_fuer, konten, platzhalter):
    seite = client_fuer(konten[P]).get("/einstellungen/personen/").content.decode()
    assert platzhalter.anzeigename in seite and konten[M].person.anzeigename not in seite
    assert "Person einladen" not in seite
    assert client_fuer(konten[P]).get(f"/einstellungen/personen/{konten[M].pk}/").status_code == 403
    assert client_fuer(konten[P]).get(f"/einstellungen/personen/{platzhalter.pk}/").status_code == 200
    for rolle in (M, L):
        assert client_fuer(konten[rolle]).get("/einstellungen/personen/").status_code == 403


def test_personen_suche_und_filter(client_fuer, konten, platzhalter, bereich_b):
    c = client_fuer(konten[A])
    seite = c.get("/einstellungen/personen/?art=platzhalter").content.decode()
    assert platzhalter.anzeigename in seite and konten[M].email not in seite
    seite = c.get(f"/einstellungen/personen/?q={konten[M].email}").content.decode()
    assert konten[M].person.anzeigename in seite and platzhalter.anzeigename not in seite
    konten[L].person.archivieren()
    assert konten[L].person.anzeigename not in c.get("/einstellungen/personen/").content.decode()
    assert konten[L].person.anzeigename in c.get("/einstellungen/personen/?zustand=inaktiv").content.decode()
    seite = c.get(f"/einstellungen/personen/?bereich={bereich_b.pk}").content.decode()
    assert konten[M].person.anzeigename not in seite or konten[M].person.bereich_id == bereich_b.pk


# --- Freigaben auf der Personenseite ---

def test_freigabe_auf_der_personenseite(client_fuer, konten, ansicht_a):
    gantt = GanttAnsicht.objects.create(name="Gesamt")
    c = client_fuer(konten[BL])
    seite = c.get(f"/einstellungen/personen/{konten[P].pk}/").content.decode()
    assert "Bereich A" in seite and "Gesamt" in seite and "Gantt-Diagramm" in seite
    url = f"/einstellungen/personen/{konten[P].pk}/freigabe/"
    assert htmx(c, url, {"art": "teamplaner", "ansicht": ansicht_a.pk, "recht": "bearbeiten"}).status_code == 204
    assert htmx(c, url, {"art": "gantt", "ansicht": gantt.pk, "recht": "sehen"}).status_code == 204
    assert AnsichtFreigabe.objects.get(konto=konten[P]).recht == Recht.BEARBEITEN
    assert GanttFreigabe.objects.get(konto=konten[P]).recht == Recht.SEHEN
    eintrag = Protokolleintrag.objects.filter(objekt_typ="ansicht", objekt_id=ansicht_a.pk).latest("id")
    assert eintrag.daten["freigaben"] == {str(konten[P].pk): [None, "bearbeiten"]}
    htmx(c, url, {"art": "teamplaner", "ansicht": ansicht_a.pk, "recht": ""})
    assert not AnsichtFreigabe.objects.filter(konto=konten[P]).exists()


def test_freigabe_bearbeiten_erst_ab_planer(client_fuer, konten, ansicht_a):
    url = f"/einstellungen/personen/{konten[M].pk}/freigabe/"
    antwort = htmx(client_fuer(konten[BL]), url, {"art": "teamplaner", "ansicht": ansicht_a.pk, "recht": "bearbeiten"})
    assert antwort.status_code == 400
    assert AnsichtFreigabe.objects.get(konto=konten[M]).recht == Recht.SEHEN  # höchstens „Sehen“
    # ohne Verwaltungsrecht: 403
    assert htmx(client_fuer(konten[P]), url, {"art": "teamplaner", "ansicht": ansicht_a.pk,
                                              "recht": "sehen"}).status_code == 403


def test_rolle_unter_planer_stuft_bearbeiten_herab(client_fuer, konten, ansicht_a):
    freigeben(ansicht_a, konten[P], Recht.BEARBEITEN)
    ziel = konten[P]
    client_fuer(konten[BL]).post(f"/einstellungen/personen/{ziel.pk}/", {
        "anzeigename": ziel.person.anzeigename, "email": ziel.email, "rolle": Rolle.MITARBEITER})
    assert AnsichtFreigabe.objects.get(konto=ziel).recht == Recht.SEHEN


# --- Ansichten & Freigaben ---

def test_ansichten_mit_reitern_und_reihenfolge(client_fuer, konten, ansicht_a, ansicht_b):
    GanttAnsicht.objects.create(name="Gesamt")
    c = client_fuer(konten[BL])
    seite = c.get("/einstellungen/ansichten/").content.decode()
    assert "Bereich A" in seite and "?art=gantt" in seite
    assert "Gesamt" in c.get("/einstellungen/ansichten/?art=gantt").content.decode()
    ids = [ansicht_b.pk, ansicht_a.pk]
    assert c.post("/einstellungen/ansichten/teamplaner/reihenfolge/", {"ids": ids},
                  content_type="application/json").status_code == 204
    assert list(TeamplanerAnsicht.objects.values_list("pk", flat=True)) == ids
    assert client_fuer(konten[P]).post("/einstellungen/ansichten/teamplaner/reihenfolge/", {"ids": ids},
                                       content_type="application/json").status_code == 403


def test_ansicht_bearbeiten_mit_freigaben_bauteil(client_fuer, konten, bereich_a, ansicht_a):
    c = client_fuer(konten[BL])
    seite = c.get(f"/einstellungen/ansichten/teamplaner/{ansicht_a.pk}/").content.decode()
    assert "data-freigaben" in seite and "data-freigaben-suche" in seite and "Nur Freigegebene" in seite
    assert f'name="freigabe-{konten[A].pk}"' not in seite  # Admin fest „Bearbeiten“
    c.post(f"/einstellungen/ansichten/teamplaner/{ansicht_a.pk}/", {
        "name": "Bereich A", "bereiche": [bereich_a.pk], "wochen": 2,
        f"freigabe-{konten[P].pk}": "bearbeiten", f"freigabe-{konten[M].pk}": "bearbeiten",
    })
    assert dict(AnsichtFreigabe.objects.filter(ansicht=ansicht_a).values_list("konto_id", "recht")) == {
        konten[P].pk: Recht.BEARBEITEN, konten[M].pk: Recht.SEHEN}


def test_aufgaben_status_reihenfolge_wirkt_in_auswahl(client_fuer, konten, aufgabe):
    ids = list(reversed(Status.objects.values_list("pk", flat=True)))
    client_fuer(konten[A]).post("/einstellungen/listen/status/reihenfolge/", {"ids": ids}, content_type="application/json")
    seite = client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    auswahl = seite[seite.index('id="eingabe-status"'):]
    positionen = [auswahl.index(f'<option value="{pk}"') for pk in ids]
    assert positionen == sorted(positionen)
    assert Aufgabe.objects.filter(pk=aufgabe.pk).exists()
