"""Eigene E-Mail-Adresse ändern: Passwort, Bestätigungslink, ohne E-Mail-Versand doppelte Eingabe (#75)."""

import re
from datetime import timedelta

import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.test import Client
from django.utils import timezone

from kern import zwei_faktor
from kern.models import EmailWechsel, Konto, Protokolleintrag, Rolle
from verwaltung import konten as kontenlogik
from verwaltung.aufraeumen import aufraeumen
from verwaltung.templatetags.verwaltung import protokoll_text
from zusammenarbeit.mail import offene_versenden
from zusammenarbeit.models import Postausgang

from .conftest import TESTPASSWORT, konto_anlegen

pytestmark = pytest.mark.django_db
A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND
NEU = "neu@example.test"


@pytest.fixture
def smtp(settings):
    settings.EMAIL_HOST = "smtp.example.test"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.TEAMPLANER_ADRESSE = "https://teamplaner.example.test"


@pytest.fixture
def ohne_smtp(settings):
    settings.EMAIL_HOST = ""


def angemeldet(konto):
    c = Client()
    c.force_login(konto)
    return c


def frisch(konto):
    return Konto.objects.select_related("person").get(pk=konto.pk)


def anfordern(client, email=NEU, passwort=TESTPASSWORT, **weitere):
    return client.post("/konto/email/", {"email": email, "passwort": passwort, **weitere})


def link():
    mail = Postausgang.objects.filter(art=Postausgang.Art.EMAIL_WECHSEL).latest("id")
    return re.search(r"https://teamplaner\.example\.test(/konto/email/bestaetigen/\w+/)", mail.text).group(1)


def protokoll(konto, aktion):
    return Protokolleintrag.objects.filter(objekt_typ="konto", objekt_id=konto.pk, aktion=aktion)


# --- Mit E-Mail-Versand ---

@pytest.mark.parametrize("rolle", [A, BL])
def test_neue_adresse_gilt_erst_nach_dem_bestaetigen(konten, smtp, rolle):
    konto, alt = konten[rolle], konten[rolle].email
    c = angemeldet(konto)
    antwort = anfordern(c, "Neu@Example.test")
    assert antwort.status_code == 302 and antwort.url == f"/einstellungen/personen/{konto.pk}/"
    assert frisch(konto).email == alt
    # Nur die neue Adresse bekommt den Link, die bisherige noch nichts
    assert [(m.art, m.empfaenger) for m in Postausgang.objects.all()] == [(Postausgang.Art.EMAIL_WECHSEL, NEU)]
    assert NEU in protokoll_text(protokoll(konto, "email_wechsel_angefordert").get())
    seite = c.get(f"/einstellungen/personen/{konto.pk}/").content.decode()
    assert f"Wechsel auf {NEU} offen" in seite and "Wechsel abbrechen" in seite

    ziel = link()
    seite = c.get(ziel).content.decode()
    assert alt in seite and NEU in seite
    assert frisch(konto).email == alt  # das Öffnen allein ändert nichts
    assert c.post(ziel).status_code == 302
    assert frisch(konto).email == NEU and not EmailWechsel.objects.exists()
    assert protokoll(konto, "geaendert").get().daten["email"] == [alt, NEU]
    hinweis = Postausgang.objects.get(art=Postausgang.Art.SICHERHEIT)
    assert hinweis.empfaenger == alt and NEU in hinweis.text
    # Sitzung bleibt, der Link gilt nur einmal
    assert "Link ungültig" in c.post(ziel).content.decode()
    assert c.get(f"/einstellungen/personen/{konto.pk}/").status_code == 200


def test_mail_ist_im_versandverlauf_und_wird_nach_dem_versand_geleert(konten, smtp):
    anfordern(angemeldet(konten[A]))
    assert offene_versenden() == 1
    mail = Postausgang.objects.get()
    assert (mail.text, mail.html, mail.get_art_display()) == ("", "", "E-Mail-Adresse bestätigen")


def test_abbrechen_macht_den_link_ungueltig(konten, smtp):
    c, alt = angemeldet(konten[A]), konten[A].email
    anfordern(c)
    assert c.get("/konto/email/abbrechen/").status_code == 405
    c.post("/konto/email/abbrechen/")
    assert not EmailWechsel.objects.exists()
    assert protokoll(konten[A], "email_wechsel_abgebrochen").get().daten["email"] == NEU
    assert "Link ungültig" in c.post(link()).content.decode()
    assert frisch(konten[A]).email == alt
    c.post("/konto/email/abbrechen/")  # nichts mehr offen
    assert protokoll(konten[A], "email_wechsel_abgebrochen").count() == 1


def test_neuer_wechsel_ersetzt_den_offenen(konten, smtp):
    c = angemeldet(konten[A])
    anfordern(c)
    erster = link()
    anfordern(c, "anders@example.test")
    assert "Link ungültig" in c.post(erster).content.decode()
    c.post(link())
    assert frisch(konten[A]).email == "anders@example.test"


def test_link_laeuft_ab_und_wird_aufgeraeumt(konten, smtp):
    c, alt = angemeldet(konten[A]), konten[A].email
    anfordern(c)
    ziel = link()
    # Nur die Uhr weiterstellen, nicht den Eintrag: sonst passt der Link schon wegen des Zeitpunkts nicht
    abgelaufen = timezone.now() + timedelta(hours=settings.TEAMPLANER_RESET_GUELTIG_STUNDEN, minutes=1)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr("kern.models.timezone.now", lambda: abgelaufen)
        mp.setattr("kern.middleware.settings.TEAMPLANER_ADMIN_INAKTIV_MINUTEN", 10_000)
        assert "Link ungültig" in c.get(ziel).content.decode()
        c.post(ziel)
        assert "Wechsel abbrechen" not in c.get(f"/einstellungen/personen/{konten[A].pk}/").content.decode()
    assert frisch(konten[A]).email == alt
    aufraeumen()
    assert EmailWechsel.objects.exists()  # gilt noch
    aufraeumen(abgelaufen)
    assert not EmailWechsel.objects.exists()


@pytest.mark.parametrize("aenderung", ["passwort", "deaktivieren", "adresse"])
def test_wechsel_ist_hinfaellig_wenn_sich_am_konto_etwas_aendert(konten, smtp, aenderung):
    konto = konten[BL]
    anfordern(angemeldet(konto))
    ziel = link()
    if aenderung == "passwort":
        konto.set_password("Ganz-neues-2026")
        konto.save(update_fields=["password"])
    elif aenderung == "deaktivieren":
        kontenlogik.deaktivieren(konten[A], konto)
        kontenlogik.reaktivieren(konten[A], konto)
    else:
        Konto.objects.filter(pk=konto.pk).update(email="vom-admin@example.test")
    c = angemeldet(frisch(konto))
    assert "Link ungültig" in c.get(ziel).content.decode()
    c.post(ziel)
    assert frisch(konto).email != NEU


def test_link_gilt_nur_angemeldet_im_eigenen_konto(konten, smtp):
    alt = konten[A].email
    anfordern(angemeldet(konten[A]))
    ziel = link()
    antwort = Client().get(ziel)  # z. B. fremde Person nach einem Tippfehler
    assert antwort.status_code == 302 and antwort.url == f"/anmelden/?next={ziel}"
    assert Client().post(ziel).status_code == 302
    assert "Link ungültig" in angemeldet(konten[BL]).post(ziel).content.decode()
    assert angemeldet(konten[M]).post(ziel).status_code == 403
    assert frisch(konten[A]).email == alt and EmailWechsel.objects.exists()


def test_anmelden_fuehrt_zurueck_zum_link(konten, smtp):
    anfordern(angemeldet(konten[A]))
    ziel = link()
    c = Client()
    antwort = c.post(f"/anmelden/?next={ziel}", {"username": konten[A].email, "password": TESTPASSWORT})
    assert antwort.url == ziel
    c.post(ziel)  # die Anmeldung dazwischen macht den Link nicht ungültig
    assert frisch(konten[A]).email == NEU


def test_adresse_inzwischen_vergeben(konten, smtp, bereich_a):
    c, alt = angemeldet(konten[A]), konten[A].email
    anfordern(c)
    Konto.objects.filter(pk=konto_anlegen("Person 77", bereich_a, M).pk).update(email=NEU.upper())
    antwort = c.post(link())
    assert "bereits ein Konto" in str(list(get_messages(antwort.wsgi_request))[-1])
    assert frisch(konten[A]).email == alt


def test_versand_inzwischen_abgeschaltet(konten, ohne_smtp):
    assert not kontenlogik.email_wechsel_beginnen(konten[A], NEU)
    assert not EmailWechsel.objects.exists() and not protokoll(konten[A], "email_wechsel_angefordert").exists()


def test_mail_in_der_sprache_des_kontos(konten, smtp):
    Konto.objects.filter(pk=konten[A].pk).update(sprache="en")
    c = angemeldet(konten[A])
    assert "Send link" in c.get("/konto/email/").content.decode()
    anfordern(c)
    mail = Postausgang.objects.get()
    assert "Confirm email address" in mail.betreff and "Please confirm the change" in mail.text


# --- Ohne E-Mail-Versand ---

def test_ohne_versand_zweimal_eingeben(konten, ohne_smtp):
    c, alt = angemeldet(konten[A]), konten[A].email
    assert 'name="email2"' in c.get("/konto/email/").content.decode()
    assert "stimmen nicht überein" in anfordern(c, email2="nue@example.test").content.decode()
    assert anfordern(c).status_code == 200  # ohne Wiederholung
    assert frisch(konten[A]).email == alt
    assert anfordern(c, email2=NEU.upper()).status_code == 302
    assert frisch(konten[A]).email == NEU
    assert protokoll(konten[A], "geaendert").get().daten["email"] == [alt, NEU]
    assert not EmailWechsel.objects.exists() and not Postausgang.objects.exists()


def test_mit_versand_nur_einmal(konten, smtp):
    assert 'name="email2"' not in angemeldet(konten[A]).get("/konto/email/").content.decode()


# --- Passwort und Sperre ---

@pytest.mark.parametrize("versand", [True, False])
def test_falsches_passwort_aendert_nichts(konten, settings, versand):
    settings.EMAIL_HOST = "smtp.example.test" if versand else ""
    c, alt = angemeldet(konten[A]), konten[A].email
    antwort = anfordern(c, passwort="Falsch-2026", email2=NEU).content.decode()
    assert "Das Passwort stimmt nicht." in antwort and "Falsch-2026" not in antwort
    assert frisch(konten[A]).email == alt and not EmailWechsel.objects.exists() and not Postausgang.objects.exists()


def test_fehlversuche_zaehlen_fuer_die_sperre(konten, smtp, settings):
    c = angemeldet(konten[A])
    for _i in range(settings.AXES_FAILURE_LIMIT):
        anfordern(c, passwort="Falsch-2026")
    assert anfordern(c).status_code == 429 and not EmailWechsel.objects.exists()  # richtig, aber gesperrt
    # Gleicher Schlüssel wie bei der Anmeldung
    antwort = Client().post("/anmelden/", {"username": konten[A].email, "password": TESTPASSWORT})
    assert antwort.status_code == 429


@pytest.mark.parametrize("eingabe", ["kein-mail", "", "person.00@example.test", "PERSON.90@example.test"])
def test_ungueltige_vergebene_oder_gleiche_adresse(konten, smtp, eingabe):
    antwort = anfordern(angemeldet(konten[A]), eingabe)
    assert antwort.status_code == 200 and "fehlerliste" in antwort.content.decode()
    assert not EmailWechsel.objects.exists()


# --- Rechte und Seite der Person ---

@pytest.mark.parametrize("rolle,status", [(A, 200), (BL, 200), (P, 403), (M, 403), (L, 403)])
def test_nur_admin_und_bereichsleitung(konten, smtp, rolle, status):
    c, alt = angemeldet(konten[rolle]), konten[rolle].email
    assert c.get("/konto/email/").status_code == status
    if status == 403:
        assert anfordern(c).status_code == 403
        assert c.post("/konto/email/abbrechen/").status_code == 403
        assert frisch(konten[rolle]).email == alt and not EmailWechsel.objects.exists()


@pytest.mark.parametrize("versand", [True, False])
@pytest.mark.parametrize("rolle", [A, BL])
def test_seite_der_person_aendert_die_eigene_adresse_nicht(konten, settings, rolle, versand):
    settings.EMAIL_HOST = "smtp.example.test" if versand else ""
    konto, alt = konten[rolle], konten[rolle].email
    c = angemeldet(konto)
    seite = c.get(f"/einstellungen/personen/{konto.pk}/").content.decode()
    assert 'name="email"' not in seite and 'href="/konto/email/"' in seite
    c.post(f"/einstellungen/personen/{konto.pk}/", {
        "anzeigename": "Anders", "email": NEU, "rolle": rolle, "bereich": konto.person.bereich_id})
    assert frisch(konto).email == alt and frisch(konto).person.anzeigename == "Anders"
    assert not Postausgang.objects.exists()


def test_adresse_anderer_personen_weiter_direkt(konten, smtp):
    c = angemeldet(konten[BL])
    seite = c.get(f"/einstellungen/personen/{konten[M].pk}/").content.decode()
    assert 'name="email"' in seite and 'href="/konto/email/"' not in seite
    c.post(f"/einstellungen/personen/{konten[M].pk}/", {
        "anzeigename": "Person 01", "email": NEU, "rolle": M, "bereich": konten[M].person.bereich_id})
    assert frisch(konten[M]).email == NEU and not EmailWechsel.objects.exists()


def test_zweiter_faktor_bleibt(konten, smtp):
    zwei_faktor.einrichten(konten[A], zwei_faktor.neues_geheimnis(), 1)
    c = angemeldet(konten[A])
    sitzung = c.session
    sitzung[zwei_faktor.SITZUNG] = zwei_faktor.marke(frisch(konten[A]))
    sitzung.save()
    anfordern(c)
    c.post(link())
    assert frisch(konten[A]).email == NEU and zwei_faktor.aktiv(frisch(konten[A]))
    assert c.get("/projekte/").status_code == 200
