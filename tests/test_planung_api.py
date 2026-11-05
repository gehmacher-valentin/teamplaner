"""Teamplaner-API: Einteilungslogik und serverseitige Rechteprüfung."""

import pytest

from kern.models import Protokolleintrag, Rolle
from planung.models import Abwesenheit, Einteilung, FreierTag, Recht
from projekte.models import Aufgabe, Status
from zusammenarbeit.models import Benachrichtigung

from .conftest import DI, DO, FEIERTAG, FR, MI, MI2, MO, SA, freigeben

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND
URL = "/api/planung/einteilungen"


def anlegen(client, aufgabe, person, von, bis, **extra):
    return client.post(URL, {"aufgabe_id": aufgabe.pk, "person_id": person.pk,
                             "von": von.isoformat(), "bis": bis.isoformat(), **extra}, format="json")


def einteilung(aufgabe, person, von, bis):
    return Einteilung.objects.create(aufgabe=aufgabe, person=person, von=von, bis=bis)


# --- Rechte: wer darf einteilen? ---

@pytest.mark.parametrize("rolle, status", [(A, 201), (BL, 201), (P, 403), (M, 403), (L, 403)])
def test_einteilen_ohne_freigabe(client_fuer, konten, aufgabe, person_a, rolle, status):
    antwort = anlegen(client_fuer(konten[rolle]), aufgabe, person_a, MO, MI)
    assert antwort.status_code == status
    assert Einteilung.objects.count() == (1 if status == 201 else 0)


@pytest.mark.parametrize("rolle, status", [(P, 201), (M, 403), (L, 403)])
def test_einteilen_mit_bearbeiten_freigabe(client_fuer, konten, aufgabe, person_a, ansicht_a, rolle, status):
    freigeben(ansicht_a, konten[rolle], Recht.BEARBEITEN)
    assert anlegen(client_fuer(konten[rolle]), aufgabe, person_a, MO, MI).status_code == status


def test_planer_darf_fremden_bereich_nicht_einteilen(client_fuer, konten, aufgabe, person_b, ansicht_a):
    freigeben(ansicht_a, konten[P])
    antwort = anlegen(client_fuer(konten[P]), aufgabe, person_b, MO, MI)
    assert antwort.status_code == 403
    assert antwort.json()["code"] == "keine_berechtigung"


def test_nicht_angemeldet(client_fuer, aufgabe, person_a):
    antwort = anlegen(client_fuer(None), aufgabe, person_a, MO, MI)
    assert antwort.status_code == 401 and antwort.json()["code"] == "abgemeldet"  # Oberfläche geht zur Anmeldung


def test_verschieben_auf_person_ohne_recht_wird_abgewiesen(client_fuer, konten, aufgabe, person_a, person_b, ansicht_a):
    freigeben(ansicht_a, konten[P])
    e = einteilung(aufgabe, person_a, MO, MI)
    antwort = client_fuer(konten[P]).patch(f"{URL}/{e.pk}", {"person_id": person_b.pk, "version": 1}, format="json")
    assert antwort.status_code == 403
    e.refresh_from_db()
    assert e.person == person_a


def test_aendern_fremder_einteilung_ohne_recht(client_fuer, konten, aufgabe, person_b, ansicht_a):
    freigeben(ansicht_a, konten[P])
    e = einteilung(aufgabe, person_b, MO, MI)
    client = client_fuer(konten[P])
    assert client.patch(f"{URL}/{e.pk}", {"bis": FR.isoformat(), "version": 1}, format="json").status_code == 403
    assert client.delete(f"{URL}/{e.pk}?version=1").status_code == 403
    assert Einteilung.objects.filter(pk=e.pk).exists()


# --- Einteilungslogik ---

def test_mehrfach_und_parallel_einteilen(client_fuer, konten, aufgabe, person_a, platzhalter):
    client = client_fuer(konten[BL])
    assert anlegen(client, aufgabe, person_a, MO, DI).status_code == 201
    assert anlegen(client, aufgabe, person_a, DO, FR).status_code == 201  # Unterbrechung
    assert anlegen(client, aufgabe, platzhalter, MO, FR).status_code == 201       # parallel, Platzhalter
    assert aufgabe.einteilungen.count() == 3


def test_doppelbelegung_wird_nicht_verhindert(client_fuer, konten, aufgabe, projekt, abschnitt, person_a):
    zweite = Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel="Gehäuse Band",
                                    status=Status.standard_offen())
    client = client_fuer(konten[BL])
    assert anlegen(client, aufgabe, person_a, MO, MI).status_code == 201
    assert anlegen(client, zweite, person_a, MI, FR).status_code == 201


def test_feiertag_eintaegig_braucht_bestaetigung(client_fuer, konten, aufgabe, person_a):
    client = client_fuer(konten[BL])
    antwort = anlegen(client, aufgabe, person_a, FEIERTAG, FEIERTAG)
    assert antwort.status_code == 409
    assert antwort.json()["code"] == "feiertag_bestaetigung"
    assert antwort.json()["feiertag"] == "Nationalfeiertag"
    assert anlegen(client, aufgabe, person_a, FEIERTAG, FEIERTAG, feiertag_bestaetigt=True).status_code == 201


def test_freier_tag_wird_wie_feiertag_behandelt(client_fuer, konten, aufgabe, person_a):
    FreierTag.objects.create(datum=MI, bezeichnung="Betriebsurlaub")
    antwort = anlegen(client_fuer(konten[BL]), aufgabe, person_a, MI, MI)
    assert antwort.json()["code"] == "feiertag_bestaetigung"


def test_mehrtaegig_ueber_feiertag_ohne_bestaetigung(client_fuer, konten, aufgabe, person_a):
    assert anlegen(client_fuer(konten[BL]), aufgabe, person_a, FR, MI2).status_code == 201


def test_wochenende_wie_feiertag(client_fuer, konten, aufgabe, person_a):
    client = client_fuer(konten[BL])
    assert anlegen(client, aufgabe, person_a, SA, MI2).status_code == 201  # mehrtägig: ohne Rückfrage
    antwort = anlegen(client, aufgabe, person_a, SA, SA)
    assert antwort.status_code == 409 and antwort.json()["feiertag"] == "Wochenende"
    assert anlegen(client, aufgabe, person_a, SA, SA, feiertag_bestaetigt=True).status_code == 201


def test_ende_vor_beginn(client_fuer, konten, aufgabe, person_a):
    assert anlegen(client_fuer(konten[BL]), aufgabe, person_a, MI, MO).json()["code"] == "zeitraum"


def test_archivierte_person_kann_nicht_eingeteilt_werden(client_fuer, konten, aufgabe, platzhalter):
    platzhalter.archivieren()
    antwort = anlegen(client_fuer(konten[BL]), aufgabe, platzhalter, MO, MI)
    assert antwort.status_code == 400
    assert antwort.json()["code"] == "archiviert"


def test_archivierte_einteilung_darf_geloescht_aber_nicht_verlaengert_werden(client_fuer, konten, aufgabe, platzhalter):
    e = einteilung(aufgabe, platzhalter, MO, MI)
    platzhalter.archivieren()
    client = client_fuer(konten[BL])
    assert client.patch(f"{URL}/{e.pk}", {"bis": FR.isoformat(), "version": 1}, format="json").status_code == 400
    assert client.delete(f"{URL}/{e.pk}?version=1").status_code == 204


def test_verschieben_verlaengern_umhaengen(client_fuer, konten, aufgabe, person_a, platzhalter):
    e = einteilung(aufgabe, person_a, MO, DI)
    client = client_fuer(konten[BL])
    antwort = client.patch(f"{URL}/{e.pk}", {"von": MI.isoformat(), "bis": FR.isoformat(), "version": 1}, format="json")
    assert antwort.status_code == 200
    assert antwort.json()["version"] == 2
    antwort = client.patch(f"{URL}/{e.pk}", {"person_id": platzhalter.pk, "version": 2}, format="json")
    assert antwort.status_code == 200
    e.refresh_from_db()
    assert (e.person, e.von, e.bis, e.version) == (platzhalter, MI, FR, 3)


def test_gleichzeitige_aenderung_ergibt_konflikt_statt_ueberschreiben(client_fuer, konten, aufgabe, person_a):
    e = einteilung(aufgabe, person_a, MO, DI)
    client = client_fuer(konten[BL])
    assert client.patch(f"{URL}/{e.pk}", {"bis": MI.isoformat(), "version": 1}, format="json").status_code == 200
    veraltet = client.patch(f"{URL}/{e.pk}", {"bis": FR.isoformat(), "version": 1}, format="json")
    assert veraltet.status_code == 409
    assert veraltet.json()["code"] == "konflikt"
    assert veraltet.json()["aktuell"]["bis"] == MI.isoformat()
    assert client.delete(f"{URL}/{e.pk}?version=1").status_code == 409


def test_geloeschte_einteilung_aendern(client_fuer, konten, aufgabe, person_a):
    e = einteilung(aufgabe, person_a, MO, DI)
    pk = e.pk
    e.delete()
    antwort = client_fuer(konten[BL]).patch(f"{URL}/{pk}", {"bis": MI.isoformat(), "version": 1}, format="json")
    assert antwort.json()["code"] == "geloescht"


def test_aenderungen_werden_protokolliert(client_fuer, konten, aufgabe, person_a):
    client = client_fuer(konten[BL])
    pk = anlegen(client, aufgabe, person_a, MO, DI).json()["id"]
    client.patch(f"{URL}/{pk}", {"bis": MI.isoformat(), "version": 1}, format="json")
    client.delete(f"{URL}/{pk}?version=2")
    eintraege = list(Protokolleintrag.objects.filter(objekt_typ="einteilung", objekt_id=pk).order_by("id"))
    assert [e.aktion for e in eintraege] == ["angelegt", "geaendert", "geloescht"]
    assert all(e.akteur == konten[BL].person for e in eintraege)
    assert eintraege[1].daten == {"bis": [DI.isoformat(), MI.isoformat()]}
    assert eintraege[0].aufgabe_id == aufgabe.pk


def test_protokoll_ist_unveraenderlich(client_fuer, konten, aufgabe, person_a):
    from django.db import DatabaseError, transaction

    anlegen(client_fuer(konten[BL]), aufgabe, person_a, MO, DI)
    eintrag = Protokolleintrag.objects.first()
    with pytest.raises(DatabaseError), transaction.atomic():
        Protokolleintrag.objects.filter(pk=eintrag.pk).update(aktion="manipuliert")
    with pytest.raises(DatabaseError), transaction.atomic():
        Protokolleintrag.objects.filter(pk=eintrag.pk).delete()


def test_benachrichtigung_an_eingeteilte_person_nicht_an_platzhalter(client_fuer, konten, aufgabe, platzhalter):
    client = client_fuer(konten[BL])
    anlegen(client, aufgabe, konten[M].person, MO, DI)
    anlegen(client, aufgabe, platzhalter, MO, DI)
    anlegen(client, aufgabe, konten[BL].person, MO, DI)  # sich selbst: keine
    assert list(Benachrichtigung.objects.values_list("empfaenger_id", flat=True)) == [konten[M].person_id]


# --- Abwesenheiten ---

ABW = "/api/planung/abwesenheiten"


@pytest.mark.parametrize("rolle, status", [(A, 201), (BL, 201), (P, 403), (M, 403), (L, 403)])
def test_abwesenheit_rechte(client_fuer, konten, person_a, rolle, status):
    antwort = client_fuer(konten[rolle]).post(
        ABW, {"person_id": person_a.pk, "von": MO.isoformat(), "bis": FR.isoformat()}, format="json")
    assert antwort.status_code == status


def test_abwesenheit_auf_feiertag_ohne_bestaetigung_und_protokoll_ohne_grund(client_fuer, konten, person_a):
    client = client_fuer(konten[BL])
    antwort = client.post(ABW, {"person_id": person_a.pk, "von": FEIERTAG.isoformat(),
                                "bis": FEIERTAG.isoformat()}, format="json")
    assert antwort.status_code == 201
    pk = antwort.json()["id"]
    assert client.patch(f"{ABW}/{pk}", {"bis": MI2.isoformat(), "version": 1}, format="json").status_code == 200
    assert client.delete(f"{ABW}/{pk}?version=2").status_code == 204
    eintrag = Protokolleintrag.objects.filter(objekt_typ="abwesenheit").order_by("id").first()
    assert set(eintrag.daten) == {"person", "von", "bis"}
    assert not Abwesenheit.objects.exists()


# --- Raster und Palette ---

def raster(client, ansicht, von=MO, bis=FR + (MI2 - MI), **params):
    return client.get("/api/planung/raster", {"ansicht": ansicht, "von": von.isoformat(),
                                              "bis": bis.isoformat(), **params})


def test_raster_inhalt(client_fuer, konten, aufgabe, person_a, person_b, ansicht_a):
    einteilung(aufgabe, person_a, MO, MI)
    einteilung(aufgabe, person_a, MI, DO)
    einteilung(aufgabe, person_b, MO, DI)
    Abwesenheit.objects.create(person=person_a, von=DO, bis=FR)
    daten = raster(client_fuer(konten[BL]), ansicht_a.pk).json()

    assert [t["datum"] for t in daten["tage"]][:5] == [d.isoformat() for d in (MO, DI, MI, DO, FR)]
    assert len(daten["tage"]) == 12  # Mo 19.10. bis Fr 30.10. mit Wochenende
    assert {t["frei"] for t in daten["tage"] if t["datum"] in (SA.isoformat(), "2026-10-25")} == {"Wochenende"}
    assert next(t for t in daten["tage"] if t["datum"] == FEIERTAG.isoformat())["frei"] == "Nationalfeiertag"
    person_ids = {p["id"] for p in daten["personen"]}
    assert person_a.pk in person_ids and person_b.pk not in person_ids
    assert len(daten["einteilungen"]) == 2 and "teil" not in daten["einteilungen"][0]  # keine Teil-Nummern mehr
    assert daten["aufgaben"][str(aufgabe.pk)]["eingeteilt"] == 3 + 2 + 2
    konflikte = {(d["person_id"], d["datum"]) for d in daten["doppelbelegungen"]}
    assert konflikte == {(person_a.pk, MI.isoformat()), (person_a.pk, DO.isoformat())}


def test_raster_fremde_ansicht_verboten(client_fuer, konten, ansicht_a, ansicht_b):
    freigeben(ansicht_a, konten[P], Recht.SEHEN)
    client = client_fuer(konten[P])
    assert raster(client, ansicht_a.pk).status_code == 200
    assert raster(client, ansicht_b.pk).status_code == 403
    assert raster(client, "alle").status_code == 403


def test_raster_nur_sehen_ist_nicht_einteilbar(client_fuer, konten, person_a, ansicht_a):
    freigeben(ansicht_a, konten[P], Recht.SEHEN)
    daten = raster(client_fuer(konten[P]), ansicht_a.pk).json()
    assert daten["personen"] and not any(p["einteilbar"] for p in daten["personen"])


def test_raster_nur_ich_zeigt_eigene_einteilung_immer(client_fuer, konten, aufgabe):
    einteilung(aufgabe, konten[L].person, MO, MI)
    daten = raster(client_fuer(konten[L]), "ich").json()
    assert [p["id"] for p in daten["personen"]] == [konten[L].person_id]
    assert len(daten["einteilungen"]) == 1


def test_raster_archivierte_nur_mit_filter(client_fuer, konten, aufgabe, platzhalter, ansicht_a):
    einteilung(aufgabe, platzhalter, MO, MI)
    platzhalter.archivieren()
    client = client_fuer(konten[BL])
    assert platzhalter.pk not in {p["id"] for p in raster(client, ansicht_a.pk).json()["personen"]}
    daten = raster(client, ansicht_a.pk, archivierte="1").json()
    eintrag = next(p for p in daten["personen"] if p["id"] == platzhalter.pk)
    assert eintrag["archiviert"] and not eintrag["einteilbar"]


def test_palette_zeigt_nur_nicht_voll_eingeteilte(client_fuer, konten, aufgabe, projekt, abschnitt, person_a):
    voll = Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel="Regal Lager",
                                  status=Status.standard_offen(), schaetzung_personentage=2)
    einteilung(voll, person_a, MO, DI)
    einteilung(aufgabe, person_a, MO, DI)  # 2 von 4
    erledigt = Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel="Alt",
                                      status=Status.standard_erledigt())
    client = client_fuer(konten[BL])
    titel = {a["titel"] for a in client.get("/api/planung/palette").json()["aufgaben"]}
    assert titel == {"Hallenboden Nord"}
    titel = {a["titel"] for a in client.get("/api/planung/palette", {"modus": "projekt", "projekt": projekt.pk}).json()["aufgaben"]}
    assert titel == {"Hallenboden Nord", "Regal Lager"}
    assert erledigt.titel not in titel


@pytest.mark.parametrize("rolle, status", [(BL, 200), (P, 200), (M, 403), (L, 403)])
def test_palette_rechte(client_fuer, konten, rolle, status):
    assert client_fuer(konten[rolle]).get("/api/planung/palette").status_code == status


def test_ansichten_liste(client_fuer, konten, ansicht_a, ansicht_b):
    freigeben(ansicht_a, konten[M], Recht.BEARBEITEN)
    ids = [a["id"] for a in client_fuer(konten[M]).get("/api/planung/ansichten").json()["ansichten"]]
    assert ids == [str(ansicht_a.pk), "ich"]
    eintraege = client_fuer(konten[M]).get("/api/planung/ansichten").json()["ansichten"]
    assert eintraege[0]["recht"] == "sehen"  # Mitarbeiter:in: bearbeiten wirkt nicht
    ids = [a["id"] for a in client_fuer(konten[BL]).get("/api/planung/ansichten").json()["ansichten"]]
    assert ids[0] == "alle" and str(ansicht_b.pk) in ids


def test_karten_zeigen_anzahl_anhaenge(client_fuer, konten, aufgabe, person_a, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    from django.core.files.uploadedfile import SimpleUploadedFile

    from zusammenarbeit.models import Anhang

    Einteilung.objects.create(aufgabe=aufgabe, person=person_a, von=MO, bis=DI)
    c = client_fuer(konten[BL])
    url = f"/api/planung/raster?ansicht=alle&von={MO.isoformat()}&bis={FR.isoformat()}"
    assert c.get(url).json()["aufgaben"][str(aufgabe.pk)]["anhaenge"] == 0
    for name in ("a.pdf", "b.pdf"):
        Anhang.objects.create(aufgabe=aufgabe, datei=SimpleUploadedFile(name, b"%PDF"), dateiname=name, groesse=4,
                              hochgeladen_von=konten[BL].person)
    assert c.get(url).json()["aufgaben"][str(aufgabe.pk)]["anhaenge"] == 2
