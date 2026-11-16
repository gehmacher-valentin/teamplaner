"""Zeile „Tagesfreigabe“: Stufen und Name stellt der Admin ein, Bearbeiten wie die Info-Zeile, global schaltbar."""

import pytest

from kern.models import Protokolleintrag, Rolle, Systemeinstellungen
from planung.models import FreigabeStufe, Tagesfreigabe

from .conftest import DI, MO, SA

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND
URL = "/einstellungen/allgemein/"


@pytest.fixture
def stufen(db):
    Systemeinstellungen.objects.update_or_create(pk=1, defaults={"freigabe_zeile": True})
    return [FreigabeStufe.objects.create(name=name, sortierung=i * 10) for i, name in enumerate(["Komplett", "Halle A"])]


def setzen(client, datum, stufe):
    wert = str(stufe.pk) if isinstance(stufe, FreigabeStufe) else stufe
    return client.put(f"/api/planung/tagesfreigabe/{datum.isoformat()}", {"stufe": wert}, format="json")


def raster(client):
    antwort = client.get(f"/api/planung/raster?ansicht=ich&von={MO.isoformat()}&bis={DI.isoformat()}")
    assert antwort.status_code == 200
    return antwort.json()


def test_standard_ausgeschaltet_ohne_stufen(client_fuer, konten):
    daten = raster(client_fuer(konten[L]))
    assert daten["freigabe_zeile"] is False
    assert daten["freigabe_stufen"] == []
    assert daten["freigabe_name"] == "Tagesfreigabe"


def test_eingeschaltet_zeigt_stufen_in_reihenfolge(client_fuer, konten, stufen):
    daten = raster(client_fuer(konten[L]))
    assert daten["freigabe_zeile"] is True
    assert [t["freigabe"] for t in daten["tage"]] == ["", ""]
    assert [s["name"] for s in daten["freigabe_stufen"]] == ["Komplett", "Halle A"]


@pytest.mark.parametrize("rolle, status", [(A, 200), (BL, 200), (P, 403), (M, 403), (L, 403)])
def test_rechte(client_fuer, konten, stufen, rolle, status):
    assert setzen(client_fuer(konten[rolle]), MO, stufen[0]).status_code == status


def test_setzen_leeren_protokoll_und_alle_sehen_es(client_fuer, konten, stufen):
    komplett, halle = stufen
    c = client_fuer(konten[BL])
    assert setzen(c, MO, halle).json()["stufe"] == str(halle.pk)
    tage = raster(client_fuer(konten[L]))["tage"]
    assert [t["freigabe"] for t in tage] == [str(halle.pk), ""]
    assert tage[0]["freigabe_von"] == konten[BL].person.anzeigename
    setzen(c, MO, komplett)
    assert setzen(c, MO, "").status_code == 200
    assert not Tagesfreigabe.objects.exists()
    aktionen = list(Protokolleintrag.objects.filter(objekt_typ="tagesfreigabe").order_by("id").values_list("aktion", flat=True))
    assert aktionen == ["angelegt", "geaendert", "geloescht"]


@pytest.mark.parametrize("wert", ["irgendwas", "999999"])
def test_ungueltig(client_fuer, konten, stufen, wert):
    c = client_fuer(konten[A])
    assert setzen(c, SA, stufen[0]).status_code == 200  # auch am Wochenende
    assert setzen(c, MO, wert).json()["code"] == "ungueltig"
    assert list(Tagesfreigabe.objects.values_list("stufe", flat=True)) == [stufen[0].pk]


def test_admin_schaltet_zeile(client_fuer, konten, stufen):
    setzen(client_fuer(konten[A]), MO, stufen[0])
    assert client_fuer(konten[BL]).post(URL, {"feld": "freigabe_zeile"}).status_code == 403
    assert client_fuer(konten[A]).post(URL, {"feld": "freigabe_zeile"}).status_code == 204  # Schalter aus
    assert Systemeinstellungen.laden().freigabe_zeile is False
    assert Protokolleintrag.objects.filter(objekt_typ="einstellungen", aktion="geaendert").exists()
    daten = raster(client_fuer(konten[L]))
    assert daten["freigabe_zeile"] is False and [t["freigabe"] for t in daten["tage"]] == ["", ""]


def test_admin_benennt_zeile(client_fuer, konten):
    assert client_fuer(konten[BL]).post(URL, {"feld": "freigabe_name", "wert": "Hallenfreigabe"}).status_code == 403
    c = client_fuer(konten[A])
    assert c.post(URL, {"feld": "freigabe_name", "wert": "  Hallen   freigabe "}).status_code == 204
    assert raster(client_fuer(konten[L]))["freigabe_name"] == "Hallen freigabe"
    assert c.post(URL, {"feld": "freigabe_name", "wert": "x" * 41}).status_code == 400
    assert c.post(URL, {"feld": "freigabe_name", "wert": ""}).status_code == 204
    assert raster(client_fuer(konten[L]))["freigabe_name"] == "Tagesfreigabe"


def test_stufen_nur_durch_admin_pflegbar(client_fuer, konten):
    neu = "/einstellungen/listen/freigabestufe/neu/"
    assert client_fuer(konten[BL]).post(neu, {"neu-name": "Halle B"}).status_code == 403
    assert client_fuer(konten[A]).post(neu, {"neu-name": "Halle B"}, HTTP_HX_REQUEST="true").status_code == 200
    assert list(FreigabeStufe.objects.values_list("name", flat=True)) == ["Halle B"]
    assert Protokolleintrag.objects.filter(objekt_typ="freigabestufe", aktion="angelegt").exists()


def test_benutzte_stufe_bleibt_erhalten(client_fuer, konten, stufen):
    komplett, halle = stufen
    c = client_fuer(konten[A])
    setzen(c, MO, komplett)
    c.post(f"/einstellungen/listen/freigabestufe/{komplett.pk}/loeschen/", HTTP_HX_REQUEST="true")
    c.post(f"/einstellungen/listen/freigabestufe/{halle.pk}/loeschen/", HTTP_HX_REQUEST="true")
    assert list(FreigabeStufe.objects.values_list("name", flat=True)) == ["Komplett"]


def test_stufen_stehen_bei_den_listen_nicht_bei_der_einstellung(client_fuer, konten, stufen):
    c = client_fuer(konten[A])
    assert 'id="liste-freigabestufe"' not in c.get(URL).content.decode()
    listen = c.get("/einstellungen/listen/").content.decode()
    assert 'id="liste-freigabestufe"' in listen
    assert listen.index('id="liste-bereich"') < listen.index('id="liste-freigabestufe"')


# --- Zeitraum auf einmal setzen ---

def zeitraum(client, von, bis, stufe):
    wert = str(stufe.pk) if isinstance(stufe, FreigabeStufe) else stufe
    return client.put("/api/planung/tagesfreigabe", {"von": von.isoformat(), "bis": bis.isoformat(), "stufe": wert},
                      format="json")


@pytest.mark.parametrize("rolle, status", [(A, 200), (BL, 200), (P, 403), (M, 403), (L, 403)])
def test_zeitraum_rechte(client_fuer, konten, stufen, rolle, status):
    assert zeitraum(client_fuer(konten[rolle]), MO, DI, stufen[0]).status_code == status


def test_zeitraum_setzen_mit_wochenende_und_wieder_entfernen(client_fuer, konten, stufen):
    from datetime import timedelta

    komplett, halle = stufen
    c = client_fuer(konten[BL])
    setzen(c, MO, halle)
    so = SA + timedelta(days=1)
    antwort = zeitraum(c, MO, so, komplett)
    assert antwort.status_code == 200 and antwort.json()["geaendert"] == 7
    tage = dict(Tagesfreigabe.objects.values_list("datum", "stufe"))
    assert tage == {MO + timedelta(days=i): komplett.pk for i in range(7)}  # Wochenende inbegriffen
    assert zeitraum(c, MO, so, komplett).json()["geaendert"] == 0  # unverändert: nichts protokolliert
    assert Protokolleintrag.objects.filter(objekt_typ="tagesfreigabe", aktion="geaendert").count() == 1
    assert zeitraum(c, DI, SA, "").json()["geaendert"] == 5
    assert sorted(Tagesfreigabe.objects.values_list("datum", flat=True)) == [MO, so]


@pytest.mark.parametrize("daten", [
    {"von": "2026-03-10", "bis": "2026-03-09"},
    {"von": "2026-01-01", "bis": "2027-06-01"},
    {"von": "kein Datum", "bis": "2026-03-09"},
    {"bis": "2026-03-09"},
])
def test_zeitraum_ungueltig(client_fuer, konten, stufen, daten):
    antwort = client_fuer(konten[A]).put("/api/planung/tagesfreigabe", {**daten, "stufe": str(stufen[0].pk)}, format="json")
    assert antwort.status_code == 400
    assert not Tagesfreigabe.objects.exists()


def test_zeitraum_unbekannte_stufe(client_fuer, konten, stufen):
    assert zeitraum(client_fuer(konten[A]), MO, DI, "999999").json()["code"] == "ungueltig"
    assert not Tagesfreigabe.objects.exists()
