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


def test_stufen_stehen_bei_der_einstellung_nicht_bei_den_listen(client_fuer, konten, stufen):
    c = client_fuer(konten[A])
    assert 'id="liste-freigabestufe"' in c.get(URL).content.decode()
    assert 'id="liste-freigabestufe"' not in c.get("/einstellungen/listen/").content.decode()
