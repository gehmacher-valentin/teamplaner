"""Mailversand nachvollziehbar: Protokollzeilen je E-Mail, Ausgabe des Versanddienstes, Befehl
mail_protokoll, Einladung bei konto_anlegen, Seite „E-Mail-Versand“ in den Einstellungen."""

import logging
from datetime import timedelta
from io import StringIO
from pathlib import Path

import pytest
from django.conf import settings as django_settings
from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from kern.models import Konto, Protokolleintrag, Rolle, Systemeinstellungen
from zusammenarbeit import mailverlauf
from zusammenarbeit.mail import MAX_VERSUCHE, einladung_senden, offene_versenden
from zusammenarbeit.models import Benachrichtigung, Benachrichtigungsart, MailStatus, Postausgang

pytestmark = pytest.mark.django_db
A, BL, P, M = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER
SEITE = "/einstellungen/mailversand/"
MAILER = "verwaltung.management.commands.mails_versenden"


@pytest.fixture(autouse=True)
def smtp(settings):
    settings.EMAIL_HOST = "smtp.example.test"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.TEAMPLANER_ADRESSE = "https://teamplaner.example.test"


@pytest.fixture
def smtp_kaputt(monkeypatch):
    def fehler(*args, **kwargs):
        raise ConnectionRefusedError("Verbindung abgelehnt")

    monkeypatch.setattr("zusammenarbeit.mail._senden", fehler)


def angemeldet(konto):
    c = Client()
    c.force_login(konto)
    return c


def hinweis(konto, status=MailStatus.OFFEN, versuche=0, text="Sie wurden eingeteilt: Hallenboden Nord"):
    return Benachrichtigung.objects.create(empfaenger=konto.person, art=Benachrichtigungsart.EINTEILUNG_NEU, text=text,
                                           mail_status=status, mail_versuche=versuche)


def befehl(kommando, /, **optionen):
    aus = StringIO()
    call_command(kommando, stdout=aus, **optionen)
    return aus.getvalue()


# ---------- Protokollzeilen je E-Mail (#11) ----------

def test_je_verschickter_mail_eine_zeile_ohne_betreff_und_text(konten, caplog):
    einladung_senden(konten[M], "https://teamplaner.example.test/passwort/setzen/MQ/geheim/")
    b = hinweis(konten[P])
    with caplog.at_level(logging.INFO, logger="zusammenarbeit.mail"):
        assert offene_versenden() == 2
    zeilen = [r.getMessage() for r in caplog.records]
    system = Postausgang.objects.get()
    assert zeilen == [
        f"E-Mail verschickt: einladung an {konten[M].email} (System-Mail {system.pk})",
        f"E-Mail verschickt: einteilung_neu an {konten[P].email} (Benachrichtigung {b.pk})",
    ]
    assert all(r.levelno == logging.INFO for r in caplog.records)
    # Nie Betreff (Aufgabentitel) oder Text (Passwort-Link)
    assert "geheim" not in caplog.text and "Hallenboden" not in caplog.text and "Einladung" not in caplog.text


def test_fehlversuche_als_warnung_und_aufgeben_als_fehler(konten, smtp_kaputt, caplog):
    einladung_senden(konten[M], "https://teamplaner.example.test/passwort/setzen/MQ/geheim/")
    system = Postausgang.objects.get()
    with caplog.at_level(logging.INFO, logger="zusammenarbeit.mail"):
        for _i in range(MAX_VERSUCHE):
            assert offene_versenden() == 0
    stufen = [r.levelno for r in caplog.records]
    assert stufen == [logging.WARNING] * (MAX_VERSUCHE - 1) + [logging.ERROR]
    assert caplog.records[0].getMessage() == (
        f"E-Mail fehlgeschlagen, Versuch 1 von {MAX_VERSUCHE}: einladung an {konten[M].email} "
        f"(System-Mail {system.pk}): ConnectionRefusedError: Verbindung abgelehnt")
    assert caplog.records[-1].getMessage().startswith(f"E-Mail aufgegeben nach {MAX_VERSUCHE} Versuchen: einladung an ")
    assert all(r.exc_info is None for r in caplog.records)  # eine Zeile, kein Traceback alle paar Sekunden
    system.refresh_from_db()
    assert (system.status, system.text) == (MailStatus.FEHLER, "")


def test_empfaenger_im_protokoll_kuerzbar(konten, settings, caplog):
    settings.TEAMPLANER_PROTOKOLL_EMPFAENGER = False
    hinweis(konten[P])
    with caplog.at_level(logging.INFO, logger="zusammenarbeit.mail"):
        offene_versenden()
    assert konten[P].email not in caplog.text
    assert f"an {konten[P].email[0]}***@example.test" in caplog.text


# ---------- Versanddienst schreibt ins Journal (#9) ----------

def dienst_einmal(monkeypatch):
    """Ein Durchlauf des Dauerbetriebs: der Schlaf am Ende beendet ihn."""
    def schluss(_sekunden):
        raise KeyboardInterrupt

    monkeypatch.setattr(f"{MAILER}.time.sleep", schluss)
    monkeypatch.setattr(f"{MAILER}.close_old_connections", lambda: None)  # sonst schließt er die Verbindung des Tests
    aus = StringIO()
    with pytest.raises(KeyboardInterrupt):
        call_command("mails_versenden", dauerhaft=True, stdout=aus)
    return aus.getvalue()


def test_dauerbetrieb_meldet_ueber_logging_nicht_ueber_stdout(konten, monkeypatch, caplog):
    """Ohne Terminal puffert Python stdout blockweise: die wenigen Zeilen am Tag erreichten das Journal
    nie. logging schreibt ungepuffert nach stderr."""
    hinweis(konten[P])
    with caplog.at_level(logging.INFO):
        stdout = dienst_einmal(monkeypatch)
    assert stdout == ""
    dienst = [r.getMessage() for r in caplog.records if r.name == MAILER]
    assert dienst[0].startswith("Versanddienst gestartet")
    assert "E-Mail-Versand ist eingeschaltet." in dienst
    assert any(z.startswith("Aufgeräumt: ") for z in dienst)
    assert [r.getMessage() for r in caplog.records if r.name == "zusammenarbeit.mail"] == [
        f"E-Mail verschickt: einteilung_neu an {konten[P].email} (Benachrichtigung {Benachrichtigung.objects.get().pk})"]
    assert len(mail.outbox) == 1


def test_dauerbetrieb_warnt_wenn_nichts_verschickt_wird(monkeypatch, caplog):
    Systemeinstellungen.objects.update_or_create(pk=1, defaults={"mail_versand": False})
    with caplog.at_level(logging.INFO, logger=MAILER):
        dienst_einmal(monkeypatch)
    warnungen = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnungen) == 1 and "es wird nichts verschickt" in warnungen[0]


def test_protokoll_geht_auf_stderr():
    """Voraussetzung dafür, dass die Zeilen ungepuffert im Journal landen."""
    konsole = django_settings.LOGGING["handlers"]["console"]
    assert konsole["class"] == "logging.StreamHandler" and "stream" not in konsole  # Standard: stderr
    assert "{levelname}" in django_settings.LOGGING["formatters"][konsole["formatter"]]["format"]
    assert django_settings.LOGGING["root"]["handlers"] == ["console"]


def test_einheit_des_versanddienstes_puffert_nicht():
    einheit = Path(django_settings.BASE_DIR, "betrieb/linux/systemd/teamplaner-mailer.service").read_text(encoding="utf-8")
    assert "Environment=PYTHONUNBUFFERED=1" in einheit


def test_einzelner_versandlauf_sagt_klar_was_er_tat(konten):
    assert befehl("mails_versenden") == (
        "Keine offenen E-Mails, nichts zu verschicken.\nWas wann an wen verschickt wurde: mail_protokoll\n")
    hinweis(konten[P])
    assert befehl("mails_versenden").startswith("1 E-Mail(s) verschickt.\n")


def test_einzelner_versandlauf_nennt_offene_nach_fehlschlag(konten, smtp_kaputt):
    hinweis(konten[P])
    assert "1 E-Mail(s) noch offen" in befehl("mails_versenden")


# ---------- Befehl mail_protokoll (#11) ----------

def test_mail_protokoll_zeigt_verlauf_ohne_betreff_und_text(konten):
    einladung_senden(konten[M], "https://teamplaner.example.test/passwort/setzen/MQ/geheim/")
    hinweis(konten[P])
    offene_versenden()
    hinweis(konten[BL], status=MailStatus.FEHLER, versuche=MAX_VERSUCHE)
    hinweis(konten[A], status=MailStatus.KEINE)  # ohne E-Mail: gehört nicht in den Verlauf
    ausgabe = befehl("mail_protokoll")
    zeilen = ausgabe.splitlines()
    assert zeilen[0].split() == ["Erstellt", "Verschickt", "Art", "Empfänger", "Status", "Versuche", "Eintrag"]
    assert sum(konten[M].email in z and "Einladung" in z and "verschickt" in z for z in zeilen) == 1
    assert sum(konten[P].email in z and "verschickt" in z for z in zeilen) == 1
    assert sum(konten[BL].email in z and "Fehler" in z and f"{MAX_VERSUCHE}/{MAX_VERSUCHE}" in z for z in zeilen) == 1
    assert konten[A].email not in ausgabe
    assert "geheim" not in ausgabe and "Hallenboden" not in ausgabe
    assert "Offen: 0, aufgegeben: 1, in den letzten 24 Stunden verschickt: 2" in ausgabe


def test_mail_protokoll_filter_und_zeitraum(konten):
    alt = hinweis(konten[P], status=MailStatus.GESENDET)
    Benachrichtigung.objects.filter(pk=alt.pk).update(erstellt_am=timezone.now() - timedelta(days=30))
    hinweis(konten[M], status=MailStatus.FEHLER, versuche=MAX_VERSUCHE)
    assert konten[P].email not in befehl("mail_protokoll")  # Standard: 7 Tage
    assert konten[P].email in befehl("mail_protokoll", tage=60)
    nur_fehler = befehl("mail_protokoll", tage=60, status="fehler")
    assert konten[M].email in nur_fehler and konten[P].email not in nur_fehler
    assert "Keine Einträge in den letzten 7 Tagen mit Status offen." in befehl("mail_protokoll", status="offen")


def test_mail_protokoll_warnt_wenn_der_versand_haengt(konten):
    b = hinweis(konten[P])
    assert "Läuft der Dienst?" not in befehl("mail_protokoll")
    Benachrichtigung.objects.filter(pk=b.pk).update(erstellt_am=timezone.now() - timedelta(minutes=20))
    assert "Läuft der Dienst?" in befehl("mail_protokoll")


def test_mail_protokoll_ohne_smtp(settings):
    settings.EMAIL_HOST = ""
    assert befehl("mail_protokoll").startswith("Kein SMTP-Server eingerichtet")


# ---------- konto_anlegen verschickt die Einladung (#8) ----------

KONTO = {"email": "it@example.test", "name": "Person 91", "bereich": "Allgemein", "rolle": "admin"}


def test_konto_anlegen_verschickt_einladung_mit_demselben_link():
    ausgabe = befehl("konto_anlegen", **KONTO)
    link = next(z for z in ausgabe.splitlines() if "/passwort/setzen/" in z)
    assert "Der Link geht zusätzlich per E-Mail an it@example.test" in ausgabe
    einladung = Postausgang.objects.get()
    assert (einladung.art, einladung.empfaenger) == (Postausgang.Art.EINLADUNG, "it@example.test")
    assert link in einladung.text
    assert offene_versenden() == 1 and mail.outbox[0].to == ["it@example.test"]


def test_konto_anlegen_ohne_versand_sagt_es_ausdruecklich(settings):
    settings.EMAIL_HOST = ""
    ausgabe = befehl("konto_anlegen", **KONTO)
    assert "/passwort/setzen/" in ausgabe and "Es wird keine E-Mail verschickt" in ausgabe
    assert not Postausgang.objects.exists()


def test_konto_anlegen_keine_mail_und_passwort():
    ausgabe = befehl("konto_anlegen", **KONTO, keine_mail=True)
    assert "Es wird keine E-Mail verschickt (--keine-mail)." in ausgabe and not Postausgang.objects.exists()
    # Mit --passwort gibt es keinen Link, also auch keine Einladung
    ausgabe = befehl("konto_anlegen", **{**KONTO, "email": "it2@example.test"}, passwort="Testpasswort-2026!")
    assert "/passwort/setzen/" not in ausgabe and not Postausgang.objects.exists()
    assert Konto.objects.get(email="it2@example.test").has_usable_password()


def test_konto_anlegen_adresse_gilt_auch_in_der_mail():
    befehl("konto_anlegen", **KONTO, adresse="https://intern.example.test")
    assert "https://intern.example.test/passwort/setzen/" in Postausgang.objects.get().text


# ---------- Seite „E-Mail-Versand“ (#15) ----------

def test_seite_zeigt_zahlen_und_verlauf_ohne_betreff_und_text(konten):
    einladung_senden(konten[M], "https://teamplaner.example.test/passwort/setzen/MQ/geheim/")
    offene_versenden()
    hinweis(konten[P])
    hinweis(konten[BL], status=MailStatus.FEHLER, versuche=MAX_VERSUCHE)
    seite = angemeldet(konten[A]).get(SEITE).content.decode()
    assert '<dd id="mail-offen">1' in seite
    assert '<dd id="mail-fehler"><span class="badge badge--warn">1</span>' in seite
    assert '<dd id="mail-gesendet">1 ' in seite
    for konto in (konten[M], konten[P], konten[BL]):
        assert konto.email in seite
    assert "Einladung" in seite and "aufgegeben" in seite
    assert "geheim" not in seite and "Hallenboden" not in seite
    # Aufgegebene und offene stehen vor den verschickten
    assert seite.index(konten[BL].email) < seite.index(konten[P].email) < seite.index(konten[M].email)


def test_seite_filtert_nach_status(konten):
    hinweis(konten[P])
    hinweis(konten[BL], status=MailStatus.FEHLER, versuche=MAX_VERSUCHE)
    seite = angemeldet(konten[A]).get(SEITE + "?status=fehler").content.decode()
    assert konten[BL].email in seite and konten[P].email not in seite
    assert angemeldet(konten[A]).get(SEITE + "?status=unsinn&seite=x").status_code == 200


def test_seite_warnt_wenn_der_versand_haengt(konten):
    b = hinweis(konten[P])
    c = angemeldet(konten[A])
    assert "läuft der Versanddienst nicht" not in c.get(SEITE).content.decode()
    Benachrichtigung.objects.filter(pk=b.pk).update(erstellt_am=timezone.now() - timedelta(minutes=20))
    assert "läuft der Versanddienst nicht" in c.get(SEITE).content.decode()


def test_seite_nennt_abgeschalteten_versand_und_fehlenden_smtp(konten, settings):
    c = angemeldet(konten[A])
    Systemeinstellungen.objects.update_or_create(pk=1, defaults={"mail_versand": False})
    assert "Der E-Mail-Versand ist abgeschaltet" in c.get(SEITE).content.decode()
    settings.EMAIL_HOST = ""
    assert "kein SMTP-Server eingerichtet" in c.get(SEITE).content.decode()


def test_seite_steht_nur_fuer_admin_in_der_navigation(konten):
    assert SEITE in angemeldet(konten[A]).get("/einstellungen/profil/").content.decode()
    assert SEITE not in angemeldet(konten[BL]).get("/einstellungen/profil/").content.decode()


def test_erneut_versuchen_reiht_aufgegebene_benachrichtigung_wieder_ein(konten):
    b = hinweis(konten[P], status=MailStatus.FEHLER, versuche=MAX_VERSUCHE)
    c = angemeldet(konten[A])
    assert "Erneut versuchen" in c.get(SEITE).content.decode()
    antwort = c.post(f"{SEITE}{b.pk}/erneut/")
    assert antwort.status_code == 302 and antwort.url == SEITE
    b.refresh_from_db()
    assert (b.mail_status, b.mail_versuche) == (MailStatus.OFFEN, 0)
    eintrag = Protokolleintrag.objects.get(objekt_typ="benachrichtigung", aktion="mail_erneut")
    assert (eintrag.objekt_id, eintrag.akteur) == (b.pk, konten[A].person)
    assert offene_versenden() == 1 and mail.outbox[0].to == [konten[P].email]
    # Ein zweites Mal gibt es nichts mehr einzureihen
    c.post(f"{SEITE}{b.pk}/erneut/")
    assert Protokolleintrag.objects.filter(aktion="mail_erneut").count() == 1


def test_erneut_versuchen_nur_admin_und_nur_per_post(konten):
    b = hinweis(konten[P], status=MailStatus.FEHLER, versuche=MAX_VERSUCHE)
    assert angemeldet(konten[BL]).post(f"{SEITE}{b.pk}/erneut/").status_code == 403
    assert angemeldet(konten[A]).get(f"{SEITE}{b.pk}/erneut/").status_code == 405
    b.refresh_from_db()
    assert b.mail_status == MailStatus.FEHLER


def test_aufgegebene_system_mail_ist_nicht_wiederholbar(konten, smtp_kaputt):
    """Ihr Text mit dem Passwort-Link ist gelöscht: die Seite verweist auf einen neuen Link."""
    einladung_senden(konten[M], "https://teamplaner.example.test/passwort/setzen/MQ/geheim/")
    for _i in range(MAX_VERSUCHE):
        offene_versenden()
    eintrag = mailverlauf.verlauf()[0]
    assert (eintrag.quelle, eintrag.status, eintrag.wiederholbar) == ("system", MailStatus.FEHLER, False)
    seite = angemeldet(konten[A]).get(SEITE).content.decode()
    assert "Erneut versuchen" not in seite and "neuen Link erzeugen" in seite
