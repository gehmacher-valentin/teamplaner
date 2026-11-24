"""Admin-Konten: herabstufen, deaktivieren, letzter Admin, Schutzfrist, konto_aendern."""

from datetime import timedelta
from importlib import import_module
from io import StringIO

import pytest
from django.apps import apps
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone

from kern import rechte, zwei_faktor
from kern.hilfen import passwort_link
from kern.models import Konto, Person, Protokolleintrag, Rolle
from verwaltung.aufraeumen import aufraeumen
from zusammenarbeit.models import Postausgang

from .conftest import TESTPASSWORT, konto_anlegen

A, BL, P, M = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER

pytestmark = pytest.mark.django_db


@pytest.fixture
def zweiter(konten, bereich_a):
    """Zweiter Admin. Beide haben sich schon einmal angemeldet und schützen einander als letzter Admin."""
    neu = konto_anlegen("Person 91", bereich_a, A)
    Konto.objects.filter(pk__in=[neu.pk, konten[A].pk]).update(last_login=timezone.now())
    return frisch(neu)


def angemeldet(konto):
    c = Client()
    c.force_login(konto)
    return c


def seite(ziel):
    return f"/einstellungen/personen/{ziel.pk}/"


def rolle_senden(wer, ziel, rolle, **weitere):
    return angemeldet(wer).post(seite(ziel), {
        "anzeigename": ziel.person.anzeigename, "email": ziel.email, "rolle": rolle,
        "bereich": ziel.person.bereich_id, **weitere})


def aktion(wer, ziel, name):
    return angemeldet(wer).post(f"/personen/{ziel.pk}/{name}/")


def frisch(konto):
    return Konto.objects.select_related("person").get(pk=konto.pk)


def befehl(konto, *args):
    aus = StringIO()
    call_command("konto_aendern", konto.email, *args, stdout=aus)
    return aus.getvalue()


def test_anderen_admin_herabstufen_aendert_sonst_nichts(konten, zweiter, settings):
    settings.EMAIL_HOST = "mail.example.test"
    assert 'name="email"' not in angemeldet(konten[A]).get(seite(zweiter)).content.decode()
    antwort = rolle_senden(konten[A], zweiter, BL, anzeigename="Übernommen", email="boese@example.test")
    assert antwort.status_code == 302
    neu = frisch(zweiter)
    assert (neu.rolle, neu.email, neu.person.anzeigename) == (BL, zweiter.email, "Person 91")
    assert neu.admin_bis is not None
    eintrag = Protokolleintrag.objects.filter(objekt_typ="konto", objekt_id=neu.pk, aktion="geaendert").get()
    assert eintrag.daten["rolle"] == ["admin", "bereichsleitung"]
    assert "Admin nicht mehr" in Postausgang.objects.get(empfaenger=zweiter.email).text


def test_anderen_admin_deaktivieren_und_reaktivieren(konten, zweiter):
    aktion(konten[A], zweiter, "deaktivieren")
    assert not frisch(zweiter).is_active
    aktion(konten[A], zweiter, "reaktivieren")
    assert frisch(zweiter).is_active


@pytest.mark.parametrize("weg", ["oberflaeche", "befehl"])
def test_deaktivieren_beendet_sitzungen_und_links(konten, weg):
    konto = konten[M]
    c = angemeldet(konto)
    assert c.get("/projekte/").status_code == 200
    link = passwort_link(konto)
    if weg == "befehl":
        befehl(konto, "--deaktivieren")
        befehl(konto, "--reaktivieren")
    else:
        aktion(konten[A], konto, "deaktivieren")
        aktion(konten[A], konto, "reaktivieren")
    assert c.get("/projekte/").status_code == 302
    assert "ungültig" in Client().get(link, follow=True).content.decode()
    # Das Passwort bleibt, neue Sitzungen und Links gelten
    neu = Client()
    neu.post("/anmelden/", {"username": konto.email, "password": TESTPASSWORT})
    assert neu.get("/projekte/").status_code == 200
    assert "ungültig" not in Client().get(passwort_link(frisch(konto)), follow=True).content.decode()


def test_deaktivieren_beendet_die_offene_code_eingabe(konten):
    konto = konten[M]
    zwei_faktor.einrichten(konto, zwei_faktor.neues_geheimnis(), 1)
    c = Client()
    c.post("/anmelden/", {"username": konto.email, "password": TESTPASSWORT})
    assert c.get("/anmelden/code/").status_code == 200
    befehl(konto, "--deaktivieren")
    befehl(konto, "--reaktivieren")
    assert c.get("/anmelden/code/").status_code == 302


def test_nie_deaktivierte_konten_behalten_ihre_sitzung(konten):
    """Nach dem Update bleibt angemeldet, wer angemeldet war: ohne Deaktivierung derselbe Wert wie in Django."""
    assert konten[M].zugang_marke == ""
    assert konten[M].get_session_auth_hash() == super(Konto, konten[M])._get_session_auth_hash()


@pytest.mark.parametrize("name", ["link", "zwei_faktor_zuruecksetzen", "foto_entfernen"])
def test_anmeldung_anderer_admins_gesperrt(konten, zweiter, name):
    assert aktion(konten[A], zweiter, name).status_code == 403
    assert frisch(zweiter).has_usable_password()


@pytest.mark.parametrize("rolle", [A, BL])
@pytest.mark.parametrize("name", ["link", "zwei_faktor_zuruecksetzen"])
def test_eigene_anmeldung_nicht_ueber_die_personenverwaltung(konten, rolle, name):
    konto = konten[rolle]
    zwei_faktor.einrichten(konto, zwei_faktor.neues_geheimnis(), 1)
    c = angemeldet(konto)
    sitzung = c.session
    sitzung[zwei_faktor.SITZUNG] = zwei_faktor.marke(konto)
    sitzung.save()
    assert c.post(f"/personen/{konto.pk}/{name}/").status_code == 403
    neu = frisch(konto)
    assert neu.has_usable_password() and zwei_faktor.aktiv(neu)
    assert c.get(seite(konto)).status_code == 200  # Sitzung läuft weiter


def test_schutzfrist_nach_dem_herabstufen(konten, zweiter):
    rolle_senden(konten[A], zweiter, P)
    for wer in (konten[A], konten[BL]):
        assert aktion(wer, zweiter, "link").status_code == 403
        assert aktion(wer, zweiter, "zwei_faktor_zuruecksetzen").status_code == 403
        rolle_senden(wer, frisch(zweiter), P, email="boese@example.test")
        assert frisch(zweiter).email == zweiter.email
        assert "war bis vor Kurzem Admin" in angemeldet(wer).get(seite(zweiter)).content.decode()
    Konto.objects.filter(pk=zweiter.pk).update(admin_bis=timezone.now() - rechte.ADMIN_SCHUTZFRIST - timedelta(minutes=1))
    assert aktion(konten[A], zweiter, "link").status_code == 302


def test_sich_selbst_herabstufen(konten, zweiter):
    assert rolle_senden(konten[A], konten[A], BL).url == seite(konten[A])
    assert frisch(konten[A]).rolle == BL
    assert rolle_senden(zweiter, zweiter, M).status_code == 302
    assert frisch(zweiter).rolle == A  # inzwischen der letzte


def test_weit_herabgestuft_fuehrt_zur_startseite(konten, zweiter):
    assert rolle_senden(konten[A], konten[A], M).url == "/meine-aufgaben/"
    assert frisch(konten[A]).rolle == M


@pytest.mark.parametrize("zustand", ["keiner", "deaktiviert", "ohne_passwort", "nie_angemeldet"])
def test_letzter_admin_bleibt(konten, zweiter, zustand):
    if zustand == "keiner":
        Konto.objects.filter(pk=zweiter.pk).update(rolle=BL)
    elif zustand == "deaktiviert":
        zweiter.person.archivieren()
    elif zustand == "nie_angemeldet":
        Konto.objects.filter(pk=zweiter.pk).update(last_login=None)
    else:
        zweiter.set_unusable_password()
        zweiter.save()
    rolle_senden(konten[A], konten[A], BL)
    assert frisch(konten[A]).rolle == A
    for option in (["--rolle", "planer"], ["--deaktivieren"]):
        with pytest.raises(CommandError, match="letzte Admin"):
            befehl(konten[A], *option)
    assert frisch(konten[A]).rolle == A and frisch(konten[A]).is_active


def test_anmeldung_setzt_last_login(konten):
    """Darauf baut der Schutz des letzten Admins, auch bei Konten von vor dieser Regel."""
    assert konten[A].last_login is None
    Client().post("/anmelden/", {"username": konten[A].email, "password": TESTPASSWORT})
    assert frisch(konten[A]).last_login is not None


def test_bereichsleitung_weder_sich_noch_admins(konten, zweiter):
    assert rolle_senden(konten[BL], zweiter, M).status_code == 403
    assert aktion(konten[BL], zweiter, "deaktivieren").status_code == 403
    rolle_senden(konten[BL], konten[BL], A)
    rolle_senden(konten[BL], konten[BL], M)
    assert frisch(konten[BL]).rolle == BL


def test_befehl_aendert_konten(konten, zweiter):
    assert "Admin, aktiv" in befehl(zweiter)
    assert "Bereichsleitung, deaktiviert" in befehl(zweiter, "--rolle", "bereichsleitung", "--deaktivieren")
    assert frisch(zweiter).admin_bis is not None
    assert "aktiv" in befehl(zweiter, "--reaktivieren", "--neue-email", "Neu@example.test")
    neu = frisch(zweiter)
    assert neu.email == "neu@example.test" and neu.is_active
    # Auch innerhalb der Schutzfrist; das bisherige Passwort bleibt gültig
    assert "http" in befehl(neu, "--passwort-link")
    assert frisch(neu).has_usable_password()


def test_befehl_weist_falsche_eingaben_ab(konten, zweiter):
    for neu in ("keine-adresse", konten[A].email):
        with pytest.raises(CommandError):
            befehl(zweiter, "--neue-email", neu)
    zweiter.person.archivieren()
    with pytest.raises(CommandError, match="deaktiviert"):
        befehl(zweiter, "--passwort-link")


# --- Nach der Frist bereinigte Admins ---

def bereinigt(konto):
    konto.person.archivieren()
    Person.objects.filter(pk=konto.pk).update(archiviert_am=timezone.now() - timedelta(days=91))
    aufraeumen()
    return frisch(konto)


def test_bereinigter_admin_verliert_die_rolle(konten, zweiter):
    Konto.objects.filter(pk=zweiter.pk).update(admin_bis=timezone.now())
    neu = bereinigt(zweiter)
    assert (neu.rolle, neu.admin_bis, neu.email_entfernt) == (Rolle.LESEND, None, True)
    eintrag = Protokolleintrag.objects.get(objekt_typ="konto", objekt_id=neu.pk, aktion="geaendert")
    assert eintrag.daten["rolle"] == ["admin", "lesend"] and eintrag.akteur is None


def test_bereinigte_rollen_unter_admin_bleiben(konten):
    assert bereinigt(konten[P]).rolle == P


def test_bereinigten_admin_wieder_in_betrieb_nehmen(konten, zweiter, settings):
    settings.EMAIL_HOST = "mail.example.test"
    bereinigt(zweiter)
    c = angemeldet(konten[A])
    assert "Nach dem Reaktivieren" in c.get(seite(zweiter)).content.decode()
    aktion(konten[A], zweiter, "reaktivieren")
    html = c.get(seite(zweiter)).content.decode()
    assert "die Rolle neu vergeben" in html and "Neuen Einladungslink erzeugen" not in html
    # Vor der neuen Adresse kein Link
    aktion(konten[A], zweiter, "link")
    assert not Postausgang.objects.exists()
    rolle_senden(konten[A], frisch(zweiter), M, email="wieder@example.test")
    neu = frisch(zweiter)
    assert (neu.email, neu.rolle, neu.is_active) == ("wieder@example.test", M, True)
    assert not Postausgang.objects.exists()  # kein Hinweis an die Ersatzadresse
    aktion(konten[A], neu, "link")
    assert Postausgang.objects.get().empfaenger == "wieder@example.test"


def test_migration_fuer_bereits_bereinigte_admins(konten, zweiter, bereich_a):
    migration = import_module("kern.migrations.0009_bereinigte_admins")
    Konto.objects.filter(pk=zweiter.pk).update(email=f"entfernt-{zweiter.pk}@konto.invalid", password="!x")
    benutzt = konto_anlegen("Person 92", bereich_a, A)
    Konto.objects.filter(pk=benutzt.pk).update(email=f"entfernt-{benutzt.pk}@konto.invalid")
    migration.herabsetzen(apps, None)
    assert frisch(zweiter).rolle == Rolle.LESEND
    assert frisch(benutzt).rolle == A and frisch(konten[A]).rolle == A
    assert Protokolleintrag.objects.get(objekt_id=zweiter.pk).daten["rolle"] == ["admin", "lesend"]
