"""Sicherheit: Zwei-Faktor-Anmeldung, Sitzungen,
Konten übernehmen, Passwort-Links und Postausgang, Live-Verbindung."""

import asyncio
import base64
import json
import re
import time
from datetime import timedelta

import pytest
from django.core import mail
from django.test import Client
from django.utils import timezone

from kern import zwei_faktor
from kern.hilfen import PasswortLinks, passwort_link, passwort_links
from kern.middleware import LETZTE_AKTIVITAET
from kern.models import Rolle
from zusammenarbeit.mail import offene_versenden
from zusammenarbeit.models import Postausgang

from .conftest import TESTPASSWORT, konto_anlegen

pytestmark = pytest.mark.django_db
A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


@pytest.fixture
def smtp(settings):
    settings.EMAIL_HOST = "smtp.example.test"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.TEAMPLANER_ADRESSE = "https://teamplaner.example.test"


@pytest.fixture
def pflicht(settings):
    settings.TEAMPLANER_ZWEI_FAKTOR_PFLICHT = True


def angemeldet(konto):
    c = Client()
    c.force_login(konto)
    return c


def anmelden(email, passwort=TESTPASSWORT):
    c = Client()
    return c, c.post("/anmelden/", {"username": email, "password": passwort})


def schritt_jetzt():
    return int(time.time() // zwei_faktor.SCHRITT)


def mit_zwei_faktor(konto):
    geheimnis = zwei_faktor.neues_geheimnis()
    codes = zwei_faktor.einrichten(konto, geheimnis, schritt_jetzt() - 5)
    return geheimnis, codes


def sitzung_setzen(client, **werte):
    sitzung = client.session
    sitzung.update(werte)
    sitzung.save()


# --- Zwei-Faktor-Anmeldung ---

def test_totp_nach_rfc_6238():
    geheimnis = base64.b32encode(b"12345678901234567890").decode()
    assert zwei_faktor.code(geheimnis, 59 // 30) == "287082"
    assert zwei_faktor.code(geheimnis, 1111111109 // 30) == "081804"
    assert zwei_faktor.passender_schritt(geheimnis, "287 082", jetzt=59) == 1
    assert zwei_faktor.passender_schritt(geheimnis, "287082", nach_schritt=1, jetzt=59) is None


def test_anmeldung_verlangt_den_code_und_jeder_code_gilt_einmal(konten):
    konto = konten[M]
    geheimnis, _ = mit_zwei_faktor(konto)
    c, antwort = anmelden(konto.email)
    assert antwort.url == "/anmelden/code/"
    assert "_auth_user_id" not in c.session
    richtig = zwei_faktor.code(geheimnis, schritt_jetzt())
    antwort = c.post("/anmelden/code/", {"code": richtig})
    assert antwort.status_code == 302 and c.session["_auth_user_id"] == str(konto.pk)
    c2, _ = anmelden(konto.email)
    assert c2.post("/anmelden/code/", {"code": richtig}).status_code == 200
    assert "_auth_user_id" not in c2.session


def test_falsche_codes_beenden_die_anmeldung_und_sperren_das_konto(konten):
    konto = konten[M]
    mit_zwei_faktor(konto)
    c, _ = anmelden(konto.email)
    for _ in range(4):
        assert c.post("/anmelden/code/", {"code": "12345x"}).status_code == 200
    # Der fünfte falsche Code sperrt das Konto (wie fünf falsche Passwörter) und beendet die Anmeldung
    assert c.post("/anmelden/code/", {"code": "12345x"}).status_code == 429
    assert c.get("/anmelden/code/").url == "/anmelden/"
    c2, antwort = anmelden(konto.email)
    assert antwort.status_code in (403, 429)
    assert "_auth_user_id" not in c2.session


def test_ersatzcode_gilt_einmal(konten):
    konto = konten[M]
    _, codes = mit_zwei_faktor(konto)
    c, _ = anmelden(konto.email)
    assert c.post("/anmelden/code/", {"code": codes[0].lower()}).status_code == 302
    c2, _ = anmelden(konto.email)
    assert c2.post("/anmelden/code/", {"code": codes[0]}).status_code == 200
    konto.refresh_from_db()
    assert zwei_faktor.ersatzcodes_uebrig(konto) == 9


def test_admin_ohne_zwei_faktor_kommt_nur_auf_die_einrichtung(konten, pflicht):
    c = angemeldet(konten[A])
    antwort = c.get("/projekte/")
    assert antwort.status_code == 302 and antwort.url == "/konto/zwei-faktor/"
    assert c.get("/api/planung/ansichten").status_code == 403
    assert c.get("/konto/zwei-faktor/").status_code == 200
    # Für Mitarbeiter:innen freiwillig
    assert angemeldet(konten[M]).get("/projekte/").status_code == 200


def test_einrichten_mit_passwort_und_code(konten, pflicht):
    konto = konten[BL]
    c = angemeldet(konto)
    assert b"<svg" in c.get("/konto/zwei-faktor/").content
    geheimnis = c.session["zwei_faktor_neu"]
    code = zwei_faktor.code(geheimnis, schritt_jetzt())
    c.post("/konto/zwei-faktor/", {"code": code, "passwort": "falsch"})
    konto.refresh_from_db()
    assert not zwei_faktor.aktiv(konto)
    antwort = c.post("/konto/zwei-faktor/", {"code": code, "passwort": TESTPASSWORT})
    assert len(re.findall(r"\b[A-Z0-9]{5}-[A-Z0-9]{5}\b", antwort.content.decode())) == 10
    konto.refresh_from_db()
    assert zwei_faktor.aktiv(konto)
    assert c.get("/projekte/").status_code == 200  # diese Sitzung hat den zweiten Faktor bestanden


def test_pflicht_laesst_sich_nicht_ausschalten(konten, pflicht):
    mit_zwei_faktor(konten[BL])
    c = angemeldet(konten[BL])
    sitzung_setzen(c, **{zwei_faktor.SITZUNG: zwei_faktor.marke(konten[BL])})
    assert c.post("/konto/zwei-faktor/ausschalten/", {"passwort": TESTPASSWORT}).status_code == 403
    konten[BL].refresh_from_db()
    assert zwei_faktor.aktiv(konten[BL])


def test_sitzung_ohne_bestandenen_faktor_wird_beendet(konten):
    konto = konten[M]
    c = angemeldet(konto)  # Sitzung von vor der Einrichtung
    mit_zwei_faktor(konto)
    antwort = c.get("/projekte/")
    assert antwort.status_code == 302 and antwort.url.startswith("/anmelden/")
    assert "_auth_user_id" not in c.session


def test_verwaltung_setzt_zwei_faktor_zurueck_und_die_person_erfaehrt_es(konten, smtp):
    mit_zwei_faktor(konten[M])
    angemeldet(konten[BL]).post(f"/personen/{konten[M].pk}/zwei_faktor_zuruecksetzen/")
    konten[M].refresh_from_db()
    assert not zwei_faktor.aktiv(konten[M])
    assert Postausgang.objects.filter(empfaenger=konten[M].email, art=Postausgang.Art.SICHERHEIT).exists()


# --- Sitzungen ---

def test_sitzung_gilt_dreissig_tage_ab_anmeldung(konten):
    c = angemeldet(konten[BL])
    ablauf = c.session.get_expiry_date()
    assert timedelta(days=29) < ablauf - timezone.now() <= timedelta(days=30)
    c.get("/projekte/")
    assert c.session.get_expiry_date() == ablauf  # Nutzung verlängert nicht


def test_admin_nach_einer_stunde_ohne_aktivitaet_abgemeldet(konten):
    c = angemeldet(konten[A])
    sitzung_setzen(c, **{LETZTE_AKTIVITAET: time.time() - 3601})
    antwort = c.get("/projekte/")
    assert antwort.status_code == 302 and antwort.url.startswith("/anmelden/")
    assert "_auth_user_id" not in c.session


def test_hintergrundabfragen_verlaengern_die_admin_sitzung_nicht(konten):
    c = angemeldet(konten[A])
    hintergrund = {"X-Hintergrund": "1", "HX-Request": "true"}
    vorher = time.time() - 1800
    sitzung_setzen(c, **{LETZTE_AKTIVITAET: vorher})
    c.get("/posteingang/zahl/", headers=hintergrund)
    assert c.session[LETZTE_AKTIVITAET] == vorher
    c.get("/projekte/")
    assert c.session[LETZTE_AKTIVITAET] > vorher
    # Nach Ablauf schickt die Glocke die ganze Seite zur Anmeldung
    sitzung_setzen(c, **{LETZTE_AKTIVITAET: time.time() - 3700})
    assert c.get("/posteingang/zahl/", headers=hintergrund)["HX-Redirect"] == "/anmelden/"


def test_restzeit_in_der_kopfzeile_nur_fuer_admins(konten):
    """Admins sehen die Restzeit bis zur Abmeldung; jede Antwort trägt das Fristende mit."""
    c = angemeldet(konten[A])
    vorher = time.time() - 1800
    sitzung_setzen(c, **{LETZTE_AKTIVITAET: vorher})
    hintergrund = {"X-Hintergrund": "1"}
    antwort = c.get("/sitzung/frist/", headers=hintergrund)
    assert antwort.status_code == 204 and int(antwort["X-Sitzung-Ablauf"]) == int(vorher + 3600)
    assert abs(int(antwort["X-Sitzung-Jetzt"]) - time.time()) < 5
    assert c.session[LETZTE_AKTIVITAET] == vorher  # nur nachgefragt, nicht verlängert
    seite = c.get("/projekte/").content.decode()  # eigene Aktivität: Frist beginnt neu
    assert "data-sitzungsfrist" in seite
    ablauf = int(seite.split('data-ablauf="')[1].split('"')[0])
    assert abs(ablauf - (time.time() + 3600)) < 5
    for rolle in (BL, P, M, L):
        andere = angemeldet(konten[rolle])
        antwort = andere.get("/projekte/")
        assert "data-sitzungsfrist" not in antwort.content.decode() and "X-Sitzung-Ablauf" not in antwort


def test_knopf_setzt_die_restzeit_zurueck(konten):
    c = angemeldet(konten[A])
    sitzung_setzen(c, **{LETZTE_AKTIVITAET: time.time() - 3500})
    antwort = c.post("/sitzung/frist/")
    assert antwort.status_code == 204
    assert abs(int(antwort["X-Sitzung-Ablauf"]) - (time.time() + 3600)) < 5
    assert c.session[LETZTE_AKTIVITAET] > time.time() - 5
    # Abgelaufen: die Nachfrage im Hintergrund meldet ab, statt zu verlängern
    sitzung_setzen(c, **{LETZTE_AKTIVITAET: time.time() - 3700})
    antwort = c.get("/sitzung/frist/", headers={"X-Hintergrund": "1"})
    assert antwort.status_code == 302 and antwort.url.startswith("/anmelden/")
    assert "_auth_user_id" not in c.session
    assert Client().post("/sitzung/frist/").status_code == 302  # nicht angemeldet


def test_andere_rollen_bleiben_trotz_inaktivitaet_angemeldet(konten):
    c = angemeldet(konten[BL])
    sitzung_setzen(c, **{LETZTE_AKTIVITAET: time.time() - 10 * 3600})
    assert c.get("/projekte/").status_code == 200


# --- Konten übernehmen ---

def test_bereichsleitung_darf_andere_bereichsleitung_nicht_bearbeiten(konten, bereich_a):
    andere = konto_anlegen("Person 03", bereich_a, BL)
    c = angemeldet(konten[BL])
    assert c.get(f"/einstellungen/personen/{andere.pk}/").status_code == 403
    assert c.post(f"/personen/{andere.pk}/link/").status_code == 403


def test_link_fuer_konto_mit_passwort_nur_per_mail_an_die_person(konten, smtp):
    c = angemeldet(konten[BL])
    c.post(f"/personen/{konten[M].pk}/link/")
    assert "/passwort/setzen/" not in c.get(f"/einstellungen/personen/{konten[M].pk}/").content.decode()
    assert Postausgang.objects.filter(empfaenger=konten[M].email, art=Postausgang.Art.RESET).exists()
    konten[M].refresh_from_db()
    assert konten[M].check_password(TESTPASSWORT)


def test_ohne_mailversand_gilt_das_alte_passwort_nicht_mehr(konten, settings):
    settings.EMAIL_HOST = ""
    c = angemeldet(konten[BL])
    c.post(f"/personen/{konten[M].pk}/link/")
    assert "/passwort/setzen/" in c.get(f"/einstellungen/personen/{konten[M].pk}/").content.decode()
    konten[M].refresh_from_db()
    assert not konten[M].has_usable_password()


def test_aenderung_der_email_meldet_die_bisherige_adresse(konten, smtp):
    alt = konten[M].email
    angemeldet(konten[BL]).post(f"/einstellungen/personen/{konten[M].pk}/", {
        "anzeigename": konten[M].person.anzeigename, "email": "neu@example.test", "rolle": M,
    })
    hinweis = Postausgang.objects.get(art=Postausgang.Art.SICHERHEIT)
    assert hinweis.empfaenger == alt and "neu@example.test" in hinweis.text


def test_passwort_aendern_schickt_einen_hinweis(konten, smtp):
    angemeldet(konten[M]).post("/einstellungen/sicherheit/", {
        "old_password": TESTPASSWORT, "new_password1": "Ganz-neues-2026", "new_password2": "Ganz-neues-2026",
    })
    assert Postausgang.objects.filter(art=Postausgang.Art.SICHERHEIT, empfaenger=konten[M].email).exists()


def test_eigene_rolle_laesst_sich_nicht_aendern(konten):
    angemeldet(konten[BL]).post(f"/einstellungen/personen/{konten[BL].pk}/", {
        "anzeigename": "Person 00", "email": konten[BL].email, "rolle": A,
    })
    konten[BL].refresh_from_db()
    assert konten[BL].rolle == BL


# --- Passwort-Links und Postausgang ---

def test_reset_link_gilt_stunden_einladung_tage(konten, monkeypatch):
    konto = konten[M]  # hat ein Passwort: Zurücksetzen
    token = passwort_links.make_token(konto)
    in_drei_stunden = passwort_links._now() + timedelta(hours=3)
    monkeypatch.setattr(PasswortLinks, "_now", lambda self: in_drei_stunden)
    assert not passwort_links.check_token(konto, token)
    monkeypatch.undo()
    konto.set_unusable_password()  # Einladung noch nicht angenommen
    konto.save()
    token = passwort_links.make_token(konto)
    in_drei_tagen = passwort_links._now() + timedelta(days=3)
    monkeypatch.setattr(PasswortLinks, "_now", lambda self: in_drei_tagen)
    assert passwort_links.check_token(konto, token)


def test_link_kommt_aus_teamplaner_adresse_nicht_aus_der_anfrage(konten, settings):
    settings.TEAMPLANER_ADRESSE = "https://teamplaner.example.test/"
    assert passwort_link(konten[M]).startswith("https://teamplaner.example.test/passwort/setzen/")


def test_passwort_vergessen_hoechstens_eine_mail_je_viertelstunde(konten, smtp):
    c = Client()
    for _ in range(3):
        c.post("/passwort/vergessen/", {"email": konten[M].email})
    assert Postausgang.objects.filter(art=Postausgang.Art.RESET).count() == 1


def test_passwort_vergessen_gedrosselt_je_ip(db, smtp):
    c = Client(REMOTE_ADDR="192.0.2.30")
    for i in range(10):
        assert c.post("/passwort/vergessen/", {"email": f"person{i}@example.test"}).status_code == 200
    assert c.post("/passwort/vergessen/", {"email": "noch.eine@example.test"}).status_code == 429
    andere = Client(REMOTE_ADDR="192.0.2.31")
    assert andere.post("/passwort/vergessen/", {"email": "noch.eine@example.test"}).status_code == 200


def test_postausgang_leert_den_text_nach_dem_versand(konten, smtp):
    Client().post("/passwort/vergessen/", {"email": konten[M].email})
    assert offene_versenden() == 1
    gesendet = Postausgang.objects.get()
    assert gesendet.text == "" and gesendet.gesendet_am is not None
    assert "/passwort/setzen/" in mail.outbox[0].body


# --- Content-Security-Policy ---

def test_html_seiten_haben_eine_csp_ohne_inline_skripte(konten):
    csp = angemeldet(konten[M]).get("/projekte/")["Content-Security-Policy"]
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert Client().get("/anmelden/")["Content-Security-Policy"] == csp


def test_anhaenge_behalten_ihre_strengere_csp(konten, aufgabe):
    from django.core.files.uploadedfile import SimpleUploadedFile

    c = angemeldet(konten[M])
    c.post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": SimpleUploadedFile("a.txt", b"x", "text/plain")})
    from zusammenarbeit.models import Anhang

    antwort = c.get(f"/anhaenge/{Anhang.objects.get().pk}/")
    assert antwort["Content-Security-Policy"].startswith("default-src 'none'")


def test_templates_ohne_inline_skripte_und_handler():
    """Alles, was die CSP blockieren würde: <script> ohne src, on…-Attribute, hx-on, eval-Filter."""
    from pathlib import Path

    muster = re.compile(r"<script(?![^>]*\bsrc=)|\son[a-z]+=\"|hx-on|javascript:|hx-trigger=\"[^\"]*\[")
    funde = [f"{p}: {m.group(0)}" for p in Path("templates").rglob("*.html") for m in muster.finditer(p.read_text())]
    assert funde == []


# --- Lösch- und Aufbewahrungsfristen ---

def test_protokolle_und_benachrichtigungen_nach_einem_jahr_geloescht(konten, aufgabe):
    from axes.models import AccessLog
    from django.db import DatabaseError, transaction

    from kern.aufraeumen import aufraeumen
    from kern.models import Protokolleintrag
    from zusammenarbeit.models import Benachrichtigung

    alt = timezone.now() - timedelta(days=400)
    Protokolleintrag.objects.create(zeitpunkt=alt, objekt_typ="aufgabe", aktion="geaendert")
    neu = Protokolleintrag.objects.create(objekt_typ="aufgabe", aktion="geaendert")
    b = Benachrichtigung.objects.create(empfaenger=konten[M].person, art="kommentar", text="x")
    Benachrichtigung.objects.filter(pk=b.pk).update(erstellt_am=alt)
    log = AccessLog.objects.create(username=konten[M].email, ip_address="192.0.2.1", user_agent="x")
    AccessLog.objects.filter(pk=log.pk).update(attempt_time=alt)

    ergebnis = aufraeumen()
    assert ergebnis["protokoll"] == 1 and ergebnis["benachrichtigungen"] == 1 and ergebnis["anmeldeprotokoll"] == 1
    assert list(Protokolleintrag.objects.values_list("pk", flat=True)) == [neu.pk]
    # Jüngere Einträge lassen sich weiterhin nicht löschen (Datenbank-Trigger)
    with pytest.raises(DatabaseError, match="unveränderlich"), transaction.atomic():
        neu.delete()


def test_deaktivierte_konten_nach_drei_monaten_bereinigt_name_und_kommentare_bleiben(konten, aufgabe):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from kern.aufraeumen import aufraeumen
    from notizen.models import Notiz
    from zusammenarbeit.models import Anhang, Kommentar

    konto = konten[M]
    mit_zwei_faktor(konto)
    Notiz.objects.create(besitzer=konto.person, titel="Privat", text="x")
    Kommentar.objects.create(aufgabe=aufgabe, autor=konto.person, text="Erledigt")
    Anhang.objects.create(aufgabe=aufgabe, datei=SimpleUploadedFile("a.txt", b"x"), dateiname="a.txt", groesse=1,
                          hochgeladen_von=konto.person)
    konto.person.archivieren()
    kurz = konten[L]
    kurz.person.archivieren()
    type(konto.person).objects.filter(pk=konto.pk).update(archiviert_am=timezone.now() - timedelta(days=91))

    assert aufraeumen()["deaktivierte_konten"] == 1
    konto.refresh_from_db()
    konto.person.refresh_from_db()
    assert konto.email.endswith("@konto.invalid") and not konto.has_usable_password()
    assert not zwei_faktor.aktiv(konto) and konto.daten_entfernt_am is not None
    assert konto.person.anzeigename == "Person 01"
    assert not Notiz.objects.filter(besitzer=konto.person).exists()
    assert Kommentar.objects.filter(autor=konto.person).exists() and Anhang.objects.exists()
    kurz.refresh_from_db()
    assert kurz.email.endswith("@example.test")  # erst 0 Tage deaktiviert
    assert aufraeumen()["deaktivierte_konten"] == 0  # nur einmal


# --- ---

def test_keine_django_administration(konten):
    assert angemeldet(konten[A]).get("/django-admin/").status_code == 404


def test_admin_uebersicht_der_anhaenge(konten, aufgabe):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from zusammenarbeit.models import Anhang

    angemeldet(konten[M]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": SimpleUploadedFile("gross.txt", b"x" * 500)})
    angemeldet(konten[M]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": SimpleUploadedFile("klein.txt", b"x")})
    assert angemeldet(konten[BL]).get("/einstellungen/speicherplatz/").status_code == 403
    c = angemeldet(konten[A])
    seite = c.get("/einstellungen/speicherplatz/?sort=groesse").content.decode()
    assert seite.index("gross.txt") < seite.index("klein.txt")
    klein = Anhang.objects.get(dateiname="klein.txt")
    assert c.post(f"/einstellungen/speicherplatz/{klein.pk}/loeschen/").status_code == 302
    assert list(Anhang.objects.values_list("dateiname", flat=True)) == ["gross.txt"]
    assert angemeldet(konten[BL]).post(f"/einstellungen/speicherplatz/{Anhang.objects.get().pk}/loeschen/").status_code == 403


def test_vorschau_typ_aus_den_dateibytes(konten, aufgabe):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from zusammenarbeit.models import Anhang

    c = angemeldet(konten[M])
    c.post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": SimpleUploadedFile("bild.png", b"<html>", "image/png")})
    c.post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": SimpleUploadedFile("plan.pdf", b"%PDF-1.7 x", "text/plain")})
    typen = dict(Anhang.objects.values_list("dateiname", "content_type"))
    assert typen == {"bild.png": "application/octet-stream", "plan.pdf": "application/pdf"}


def test_ungueltige_eingaben_ergeben_400_statt_500(konten, projekt, abschnitt, aufgabe, client_fuer):
    c = angemeldet(konten[BL])
    assert c.post(f"/projekte/{projekt.pk}/abschnitte/sortieren/", "kein json",
                  content_type="application/json").status_code == 400
    assert c.post(f"/projekte/{projekt.pk}/aufgaben/verschieben/", {"id": "x"},
                  content_type="application/json").status_code == 400
    api = client_fuer(konten[BL])
    antwort = api.post("/api/planung/einteilungen", {"aufgabe_id": "abc", "person_id": konten[M].person.pk,
                                                     "von": "2026-10-19", "bis": "2026-10-19"}, format="json")
    assert antwort.status_code == 404


@pytest.mark.parametrize("wert", ["1.5", "abc", "99999999999999999999999"])
def test_ungueltige_filter_ergeben_keinen_fehler_500(konten, client_fuer, wert):
    api = client_fuer(konten[BL])
    for name in ("projekt", "gewerk", "tag"):
        erwartet = 200 if wert.isdigit() else 400  # zu große Zahl: gültig, findet nur nichts
        assert api.get(f"/api/planung/palette?{name}={wert}").status_code == erwartet
    assert angemeldet(konten[BL]).get(f"/projekte/?tag={wert}").status_code == (200 if wert.isdigit() else 400)


@pytest.mark.parametrize("monat", ["9999-99", "2026-13", "2026-00", "0000-01", "0001-01", "9999-12", "abc"])
def test_arbeitstage_widget_ungueltiger_monat(konten, aufgabe, monat):
    assert angemeldet(konten[BL]).get(f"/aufgaben/{aufgabe.pk}/?monat={monat}").status_code == 200


def test_arbeitstage_widget_monat(konten, aufgabe):
    seite = angemeldet(konten[BL]).get(f"/aufgaben/{aufgabe.pk}/?monat=2031-02").content.decode()
    assert "monat=2031-01" in seite and "monat=2031-03" in seite


def test_nul_zeichen_ergibt_400(konten, aufgabe, client_fuer):
    c = angemeldet(konten[BL])
    assert c.post("/notizen/speichern/", {"notiz": "", "ordner": "", "version": "", "titel": "A", "text": "a\x00b"},
                  HTTP_HX_REQUEST="true").status_code == 400
    assert c.post(f"/aufgaben/{aufgabe.pk}/kommentare/", "text=a%00b",
                  content_type="application/x-www-form-urlencoded").status_code == 400
    assert c.get("/suche/?q=a%00b").status_code == 400
    api = client_fuer(konten[BL])
    assert api.put("/api/planung/tagesinfo/2026-10-19", {"text": "a\x00b"}, format="json").status_code == 400
    # ohne NUL-Zeichen geht dieselbe Anfrage durch
    assert c.post("/notizen/speichern/", {"notiz": "", "ordner": "", "version": "", "titel": "A", "text": "a b"},
                  HTTP_HX_REQUEST="true").status_code == 200


def test_demodaten_nicht_im_produktivbetrieb(db, settings):
    from django.core.management import CommandError, call_command

    settings.TEAMPLANER_DEMO = False
    with pytest.raises(CommandError):
        call_command("demodaten", "--neu", verbosity=0)


# --- Live-Verbindung ---

def test_live_ereignis_nur_mit_sichtbaren_personen():
    from planung.live import _fuer_konto

    nutzlast = json.dumps({"art": "einteilung", "person_ids": [1, 2], "alle": False, "akteur_id": 9, "client": "x"})
    assert json.loads(_fuer_konto(nutzlast, None)) == {"art": "einteilung", "person_ids": [1, 2], "alle": False,
                                                       "client": "x"}
    assert json.loads(_fuer_konto(nutzlast, {2, 5}))["person_ids"] == [2]
    assert _fuer_konto(nutzlast, {7}) is None
    assert _fuer_konto(json.dumps({"art": "tagesinfo", "person_ids": [], "alle": True}), {7}) is not None


def test_live_stream_endet_nach_deaktivierung_und_abmeldung(konten):
    from planung.live import _noch_gueltig

    c = angemeldet(konten[M])
    schluessel = c.session.session_key
    assert _noch_gueltig(konten[M].pk, schluessel) is not None
    konten[M].person.archivieren()
    assert _noch_gueltig(konten[M].pk, schluessel) is None
    konten[M].person.wiederherstellen()
    c.post("/abmelden/")
    assert _noch_gueltig(konten[M].pk, schluessel) is None


def test_live_stream_hoechstens_fuenf_je_konto(konten):
    from planung import live

    live._offen[konten[M].pk] = live.MAX_STREAMS_JE_KONTO
    try:
        assert angemeldet(konten[M]).get("/api/planung/stream").status_code == 429
    finally:
        live._offen.pop(konten[M].pk)


def test_verteiler_laesst_bei_rueckstand_neu_laden():
    from planung.live import NEU_LADEN, WARTESCHLANGE, Verteiler

    async def ablauf():
        verteiler = Verteiler()
        warteschlange = asyncio.Queue(maxsize=WARTESCHLANGE)  # ohne LISTEN-Verbindung
        verteiler.warteschlangen.add(warteschlange)
        for i in range(WARTESCHLANGE + 1):
            verteiler.verteilen(str(i))
        return [warteschlange.get_nowait() for _ in range(warteschlange.qsize())]

    assert asyncio.run(ablauf()) == [NEU_LADEN]
