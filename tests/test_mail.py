"""E-Mail-Benachrichtigungen, Einladung und Passwort-Reset."""

import re

import pytest
from django.core import mail
from django.test import Client

from kern.models import Konto, Rolle
from planung import dienste as planung
from projekte import dienste as projekte
from zusammenarbeit.mail import offene_versenden
from zusammenarbeit.models import Benachrichtigung, MailStatus

from .conftest import MI, MO

pytestmark = pytest.mark.django_db
A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


@pytest.fixture(autouse=True)
def smtp(settings):
    settings.EMAIL_HOST = "smtp.example.test"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.TEAMPLANER_ADRESSE = "https://teamplaner.example.test"


def einschalten(konto, *arten):
    konto.mail_einstellungen = {a: True for a in arten}
    konto.save(update_fields=["mail_einstellungen"])


def test_standard_alles_aus(konten, aufgabe):
    projekte.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konten[M].person}, None)
    b = Benachrichtigung.objects.get()
    assert b.mail_status == MailStatus.KEINE
    assert offene_versenden() == 0 and mail.outbox == []


def test_eingeschaltetes_ereignis_wird_sofort_verschickt(konten, aufgabe):
    einschalten(konten[M], "zuweisung")
    projekte.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konten[M].person}, None)
    assert offene_versenden() == 1
    nachricht = mail.outbox[0]
    assert nachricht.to == [konten[M].email]
    assert "Hallenboden Nord" in nachricht.subject
    assert f"https://teamplaner.example.test/aufgaben/{aufgabe.pk}/" in nachricht.body
    assert "https://teamplaner.example.test/einstellungen/benachrichtigungen/" in nachricht.body
    assert Benachrichtigung.objects.get().mail_status == MailStatus.GESENDET
    assert offene_versenden() == 0  # nicht doppelt


def test_nur_eingeschaltete_kategorie(konten, aufgabe, ansicht_a):
    einschalten(konten[M], "einteilung_neu")
    projekte.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konten[M].person}, None)  # Zuweisung: aus
    planung.einteilung_anlegen(konten[BL], aufgabe=aufgabe, person=konten[M].person, von=MO, bis=MI)
    offene_versenden()
    assert len(mail.outbox) == 1 and "eingeteilt" in mail.outbox[0].body


def test_mail_in_sprache_der_empfangenden_person(konten, aufgabe):
    konto = konten[M]
    konto.sprache = "en"
    konto.save(update_fields=["sprache"])
    einschalten(konto, "zuweisung")
    projekte.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konto.person}, None)
    offene_versenden()
    assert "assigned" in mail.outbox[0].body
    # Posteingang ebenfalls auf Englisch
    assert "assigned" in Benachrichtigung.objects.get().text


def test_kein_versand_ohne_smtp(konten, aufgabe, settings):
    settings.EMAIL_HOST = ""
    einschalten(konten[M], "zuweisung")
    projekte.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konten[M].person}, None)
    assert Benachrichtigung.objects.get().mail_status == MailStatus.KEINE


def test_kommentar_aenderung_erledigt_und_neue_projektaufgabe(konten, aufgabe, abschnitt):
    verantwortlich = konten[M].person
    projekte.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": verantwortlich}, None)
    Benachrichtigung.objects.all().delete()
    c = Client()
    c.force_login(konten[P])
    c.post(f"/aufgaben/{aufgabe.pk}/kommentare/", {"text": "Bitte prüfen"})
    projekte.aufgabe_speichern(konten[P], aufgabe, {"titel": "Hallenboden Nord neu"}, None)
    projekte.erledigt_setzen(konten[P], aufgabe, True)
    arten = list(Benachrichtigung.objects.filter(empfaenger=verantwortlich).order_by("id").values_list("art", flat=True))
    assert arten == ["kommentar", "aufgabe_geaendert", "aufgabe_erledigt"]
    projekte.aufgabe_anlegen(konten[P], aufgabe.projekt, abschnitt, "Neue Aufgabe")
    leitung = aufgabe.projekt.projektleitung  # Bereichsleitung (conftest)
    assert Benachrichtigung.objects.filter(empfaenger=leitung, art="projekt_aufgabe_neu").exists()


def test_eigene_aenderungen_ohne_benachrichtigung(konten, aufgabe):
    projekte.aufgabe_speichern(konten[M], aufgabe, {"verantwortlich": konten[M].person}, None)
    projekte.aufgabe_speichern(konten[M], aufgabe, {"titel": "Selbst geändert"}, None)
    assert not Benachrichtigung.objects.exists()


def test_einstellungen_speichern(konten):
    c = Client()
    c.force_login(konten[M])
    for art in ("erwaehnung", "einteilung_neu"):
        c.post("/einstellungen/benachrichtigungen/speichern/", {"art": art, "an": "1"}, HTTP_HX_REQUEST="true")
    konten[M].refresh_from_db()
    assert konten[M].mail_einstellungen == {"erwaehnung": True, "einteilung_neu": True}
    # Kategorie-Schalter: alle Ereignisse der Kategorie in einer Anfrage
    c.post("/einstellungen/benachrichtigungen/speichern/", {"kategorie": "einteilung"}, HTTP_HX_REQUEST="true")
    konten[M].refresh_from_db()
    assert konten[M].mail_einstellungen == {"erwaehnung": True}
    assert c.post("/einstellungen/benachrichtigungen/speichern/", {"art": "gibt_es_nicht", "an": "1"}).status_code == 400


def test_einladung_per_mail(konten, bereich_a):
    c = Client()
    c.force_login(konten[BL])
    c.post("/einstellungen/personen/einladen/", {"anzeigename": "Person 42", "email": "person42@example.test", "bereich": bereich_a.pk,
                          "rolle": Rolle.MITARBEITER, "sprache": "en"})
    assert mail.outbox == []  # verschickt der Dienst mails_versenden, nicht die Anfrage
    assert offene_versenden() == 1 and len(mail.outbox) == 1
    nachricht = mail.outbox[0]
    assert nachricht.to == ["person42@example.test"] and "Invitation" in nachricht.subject
    assert "/passwort/setzen/" in nachricht.body


def test_passwort_vergessen(konten):
    c = Client()
    assert "passwort/vergessen" in c.get("/anmelden/").content.decode()
    antwort = c.post("/passwort/vergessen/", {"email": konten[M].email.upper()})
    assert antwort.status_code == 200 and mail.outbox == []
    assert offene_versenden() == 1 and len(mail.outbox) == 1
    link = re.search(r"https://teamplaner\.example\.test(/passwort/setzen/[^\s]+)", mail.outbox[0].body)
    pfad = link.group(1)
    weiter = c.get(pfad)
    c.post(weiter.url, {"new_password1": "Neues-Passwort-2026", "new_password2": "Neues-Passwort-2026"})
    assert Konto.objects.get(pk=konten[M].pk).check_password("Neues-Passwort-2026")


def test_passwort_vergessen_verraet_keine_konten(db):
    antwort = Client().post("/passwort/vergessen/", {"email": "unbekannt@example.test"})
    assert antwort.status_code == 200 and offene_versenden() == 0 and mail.outbox == []
    assert "unterwegs" in antwort.content.decode()
