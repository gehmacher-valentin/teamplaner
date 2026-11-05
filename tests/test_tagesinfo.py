"""Info-Zeile im Teamplaner: Freitext je Tag für alle, bearbeitbar nur mit Planungsansicht."""

import pytest

from kern.models import Protokolleintrag, Rolle
from planung.models import Recht, TagesInfo

from .conftest import DI, MO, SA, freigeben

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def setzen(client, datum, text):
    return client.put(f"/api/planung/tagesinfo/{datum.isoformat()}", {"text": text}, format="json")


def raster_tage(client):
    antwort = client.get(f"/api/planung/raster?ansicht=ich&von={MO.isoformat()}&bis={DI.isoformat()}")
    assert antwort.status_code == 200
    return antwort.json()


@pytest.mark.parametrize("rolle, status", [(A, 200), (BL, 200), (P, 403), (M, 403), (L, 403)])
def test_rechte_ohne_freigabe(client_fuer, konten, rolle, status):
    assert setzen(client_fuer(konten[rolle]), MO, "Wartungsarbeiten Kran").status_code == status
    assert TagesInfo.objects.count() == (1 if status == 200 else 0)


@pytest.mark.parametrize("rolle, recht, status", [
    (P, Recht.BEARBEITEN, 200), (P, Recht.SEHEN, 403), (M, Recht.BEARBEITEN, 403),
])
def test_rechte_mit_freigabe(client_fuer, konten, ansicht_a, rolle, recht, status):
    freigeben(ansicht_a, konten[rolle], recht)
    assert setzen(client_fuer(konten[rolle]), MO, "Betriebsausflug").status_code == status


def test_alle_sehen_die_info(client_fuer, konten):
    setzen(client_fuer(konten[A]), MO, "Betriebsausflug")
    daten = raster_tage(client_fuer(konten[L]))
    assert [t["info"] for t in daten["tage"]] == ["Betriebsausflug", ""]
    assert daten["info_bearbeitbar"] is False
    assert raster_tage(client_fuer(konten[A]))["info_bearbeitbar"] is True


def test_aendern_leeren_und_protokoll(client_fuer, konten):
    c = client_fuer(konten[BL])
    assert setzen(c, MO, "  Wartungsarbeiten   Kran ").json()["text"] == "Wartungsarbeiten Kran"
    setzen(c, MO, "Betriebsausflug")
    assert TagesInfo.objects.get(datum=MO).text == "Betriebsausflug"
    assert setzen(c, MO, "").status_code == 200
    assert not TagesInfo.objects.exists()
    aktionen = list(Protokolleintrag.objects.filter(objekt_typ="tagesinfo").order_by("zeitpunkt", "id")
                    .values_list("aktion", flat=True))
    assert aktionen == ["angelegt", "geaendert", "geloescht"]


def test_ungueltige_eingaben(client_fuer, konten):
    c = client_fuer(konten[A])
    assert setzen(c, SA, "Wochenendeinsatz").status_code == 200  # Wochenende ist sichtbar
    assert setzen(c, MO, "x" * 121).json()["code"] == "zu_lang"
    assert c.put("/api/planung/tagesinfo/kein-datum", {"text": "x"}, format="json").status_code == 400
    assert list(TagesInfo.objects.values_list("text", flat=True)) == ["Wochenendeinsatz"]


def test_nicht_angemeldet(client_fuer):
    assert setzen(client_fuer(None), MO, "x").status_code == 401
