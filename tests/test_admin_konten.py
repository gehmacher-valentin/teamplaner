"""Admin-Konten: herabstufen, deaktivieren, letzter Admin, Schutzfrist, konto_aendern."""

from datetime import timedelta
from io import StringIO

import pytest
from django.core.management import CommandError, call_command
from django.test import Client
from django.utils import timezone

from kern import rechte
from kern.models import Konto, Protokolleintrag, Rolle
from zusammenarbeit.models import Postausgang

from .conftest import konto_anlegen

A, BL, P, M = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER

pytestmark = pytest.mark.django_db


@pytest.fixture
def zweiter(konten, bereich_a):
    return konto_anlegen("Person 91", bereich_a, A)


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


@pytest.mark.parametrize("name", ["link", "zwei_faktor_zuruecksetzen", "foto_entfernen"])
def test_anmeldung_anderer_admins_gesperrt(konten, zweiter, name):
    assert aktion(konten[A], zweiter, name).status_code == 403
    assert frisch(zweiter).has_usable_password()


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


@pytest.mark.parametrize("zustand", ["keiner", "deaktiviert", "ohne_passwort"])
def test_letzter_admin_bleibt(konten, zweiter, zustand):
    if zustand == "keiner":
        Konto.objects.filter(pk=zweiter.pk).update(rolle=BL)
    elif zustand == "deaktiviert":
        zweiter.person.archivieren()
    else:
        zweiter.set_unusable_password()
        zweiter.save()
    rolle_senden(konten[A], konten[A], BL)
    assert frisch(konten[A]).rolle == A
    for option in (["--rolle", "planer"], ["--deaktivieren"]):
        with pytest.raises(CommandError, match="letzte Admin"):
            befehl(konten[A], *option)
    assert frisch(konten[A]).rolle == A and frisch(konten[A]).is_active


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
