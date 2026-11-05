"""Versionsanzeige und Hinweis auf neuere Versionen."""

import io
import json
import urllib.error
from email.message import Message

import pytest
from django.core.cache import cache

from kern import version
from kern.models import Rolle

IMAGE = "ghcr.io/beispiel/teamplaner"


@pytest.fixture(autouse=True)
def cache_leeren():
    cache.clear()
    yield
    cache.clear()


class Registry:
    """Nachbildung der Registry-API mit Token-Verfahren (wie ghcr.io)."""

    def __init__(self, tags, realm="https://ghcr.io/token"):
        self.tags = tags
        self.realm = realm
        self.anfragen = []

    def __call__(self, anfrage, timeout):
        self.anfragen.append((anfrage.full_url, anfrage.get_header("Authorization")))
        if anfrage.full_url.startswith(self.realm):
            return io.BytesIO(json.dumps({"token": "kurzlebig"}).encode())
        if anfrage.get_header("Authorization") != "Bearer kurzlebig":
            kopf = Message()
            kopf["WWW-Authenticate"] = (
                f'Bearer realm="{self.realm}",service="ghcr.io",scope="repository:beispiel/teamplaner:pull"'
            )
            raise urllib.error.HTTPError(anfrage.full_url, 401, "Unauthorized", kopf, None)
        return io.BytesIO(json.dumps({"name": "beispiel/teamplaner", "tags": self.tags}).encode())


@pytest.fixture
def registry(monkeypatch, settings):
    settings.TEAMPLANER_IMAGE = IMAGE
    settings.REGISTRY_BENUTZER = "leser"
    settings.REGISTRY_TOKEN = "lesetoken"

    def erzeugen(tags, **kwargs):
        nachbildung = Registry(tags, **kwargs)
        monkeypatch.setattr(version.urllib.request, "urlopen", nachbildung)
        return nachbildung

    return erzeugen


def test_versionsnummern_zerlegen():
    assert version.zerlegen("1.2.3") == (1, 2, 3)
    assert version.zerlegen("v10.0.1") == (10, 0, 1)
    for text in ("latest", "1.2", "", None, "1.2.3-rc1", "sha-abc123"):
        assert version.zerlegen(text) is None


def test_neueste_version_aus_der_registry(registry):
    nachbildung = registry(["0.9.0", "1.0.0", "1.0", "latest", "1.10.0", "1.2.0"])
    assert version.neueste_version() == "1.10.0"  # numerisch, nicht alphabetisch
    (erste, _), (token_url, token_auth), (zweite, zweite_auth) = nachbildung.anfragen
    assert erste == zweite == "https://ghcr.io/v2/beispiel/teamplaner/tags/list?n=1000"
    assert "scope=repository%3Abeispiel%2Fteamplaner%3Apull" in token_url
    assert token_auth.startswith("Basic ")
    assert zweite_auth == "Bearer kurzlebig"


def test_zugangsdaten_nur_an_die_registry_selbst(registry):
    nachbildung = registry(["1.0.0"], realm="https://anmeldung.example.org/token")
    assert version.neueste_version() == "1.0.0"
    assert nachbildung.anfragen[1][1] is None


def test_fehler_ergibt_keinen_hinweis_und_wird_gemerkt(monkeypatch, settings):
    settings.TEAMPLANER_IMAGE = IMAGE
    aufrufe = []

    def offline(anfrage, timeout):
        aufrufe.append(anfrage)
        raise urllib.error.URLError("keine Verbindung")

    monkeypatch.setattr(version.urllib.request, "urlopen", offline)
    assert version.neueste_version() is None
    assert version.neueste_version() is None
    assert len(aufrufe) == 1  # nicht bei jedem Seitenaufruf erneut versuchen


@pytest.mark.parametrize(("laufend", "neueste", "erwartet"), [
    ("1.0.0", "1.1.0", ("neu", "1.1.0")),
    ("1.0.0", "1.0.0", ("aktuell", None)),
    ("1.2.0", "1.1.9", ("aktuell", None)),
    ("1.0.0", None, ("unbekannt", None)),
])
def test_update_stand(monkeypatch, settings, laufend, neueste, erwartet):
    settings.TEAMPLANER_VERSION = laufend
    monkeypatch.setattr(version, "neueste_version", lambda: neueste)
    assert version.update_stand() == erwartet


def test_quellcode_sucht_nicht_nach_updates(monkeypatch, settings):
    settings.TEAMPLANER_VERSION = ""
    monkeypatch.setattr(version, "neueste_version", lambda: pytest.fail("keine Abfrage erwartet"))
    assert version.update_stand() == ("unbekannt", None)


@pytest.mark.django_db
def test_version_nur_fuer_admin(konten, client_fuer, monkeypatch, settings):
    settings.TEAMPLANER_VERSION = "1.0.0"
    monkeypatch.setattr(version, "neueste_version", lambda: "1.1.0")
    admin = client_fuer(konten[Rolle.ADMIN])
    seite = admin.get("/einstellungen/ueber/").content.decode()
    assert '<span class="mono">1.0.0</span>' in seite and 'hx-get="/einstellungen/version/"' in seite
    hinweis = admin.get("/einstellungen/version/").content.decode()
    assert "1.1.0" in hinweis and "./teamplaner update" in hinweis
    for rolle in (Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND):
        assert client_fuer(konten[rolle]).get("/einstellungen/version/").status_code == 403
        # „Über“ sehen alle, den Hinweis auf eine neue Version nur Admins
        ueber = client_fuer(konten[rolle]).get("/einstellungen/ueber/").content.decode()
        assert "1.0.0" in ueber and "/einstellungen/version/" not in ueber


@pytest.mark.django_db
def test_entwicklungsstand_ohne_versionspruefung(konten, client_fuer, settings):
    settings.TEAMPLANER_VERSION = ""
    seite = client_fuer(konten[Rolle.ADMIN]).get("/einstellungen/ueber/").content.decode()
    assert "Aus dem Quellcode gestartet" in seite
    assert "/einstellungen/version/" not in seite
