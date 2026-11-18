"""E-Mails: Benachrichtigungen innerhalb einer Minute als eine Mail (#39), HTML-Teil im Stil des Teamplaners (#40)."""

import logging
from datetime import timedelta

import pytest
from django.core import mail
from django.utils import timezone

from kern.models import Rolle
from zusammenarbeit.mail import (
    MAX_VERSUCHE,
    einladung_senden,
    offene_versenden,
    reset_senden,
    sicherheitshinweis,
)
from zusammenarbeit.models import Benachrichtigung, Benachrichtigungsart, MailStatus, Postausgang

pytestmark = pytest.mark.django_db
A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND
LINK = "https://teamplaner.example.test/passwort/setzen/MQ/geheim/"


@pytest.fixture(autouse=True)
def smtp(settings):
    settings.EMAIL_HOST = "smtp.example.test"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.TEAMPLANER_ADRESSE = "https://teamplaner.example.test"
    settings.TEAMPLANER_MAIL_SAMMELN_SEKUNDEN = 60


def hinweis(konto, text="Sie wurden eingeteilt: Hallenboden Nord", vor=0, aufgabe=None,
            art=Benachrichtigungsart.EINTEILUNG_NEU):
    return Benachrichtigung.objects.create(
        empfaenger=konto.person, art=art, text=text, aufgabe=aufgabe, mail_status=MailStatus.OFFEN,
        erstellt_am=timezone.now() - timedelta(seconds=vor))


def html_teil(nachricht):
    (inhalt, typ), = nachricht.alternatives
    assert typ == "text/html"
    return inhalt


# ---------- Zusammenfassen (#39) ----------

def test_zwei_benachrichtigungen_in_einer_mail(konten, aufgabe):
    erste = hinweis(konten[M], "Sie wurden eingeteilt: Montag", vor=70, aufgabe=aufgabe)
    zweite = hinweis(konten[M], "Sie wurden eingeteilt: Dienstag", vor=20, aufgabe=aufgabe)
    assert offene_versenden() == 1
    (nachricht,) = mail.outbox
    assert nachricht.subject == "[Teamplaner] 2 neue Benachrichtigungen"
    text = nachricht.body
    assert text.index("Montag") < text.index("Dienstag")  # zeitliche Reihenfolge
    assert text.count(f"https://teamplaner.example.test/aufgaben/{aufgabe.pk}/") == 2
    assert "Zum Posteingang: https://teamplaner.example.test/posteingang/" in text
    html = html_teil(nachricht)
    assert "Montag" in html and "Dienstag" in html and 'href="https://teamplaner.example.test/posteingang/"' in html
    for b in (erste, zweite):
        b.refresh_from_db()
        assert b.mail_status == MailStatus.GESENDET and b.gesendet_am
    assert offene_versenden() == 0


def test_einzelne_erst_nach_dem_fenster_und_wie_bisher(konten, aufgabe):
    b = hinweis(konten[M], aufgabe=aufgabe, vor=30)
    assert offene_versenden() == 0 and mail.outbox == []
    Benachrichtigung.objects.filter(pk=b.pk).update(erstellt_am=timezone.now() - timedelta(seconds=61))
    assert offene_versenden() == 1
    (nachricht,) = mail.outbox
    assert nachricht.subject == "[Teamplaner] Sie wurden eingeteilt: Hallenboden Nord"
    assert nachricht.body.startswith("Sie wurden eingeteilt: Hallenboden Nord\n\nZur Aufgabe: https://")


def test_verschiedene_personen_nie_zusammen(konten):
    hinweis(konten[M], vor=90)
    hinweis(konten[P], vor=90)
    hinweis(konten[M], vor=10)
    assert offene_versenden() == 2
    empfaenger = sorted(n.to[0] for n in mail.outbox)
    assert empfaenger == sorted([konten[M].email, konten[P].email])
    assert next(n for n in mail.outbox if n.to == [konten[M].email]).subject.endswith("2 neue Benachrichtigungen")


def test_smtp_fehler_zaehlt_alle_hoch(konten, monkeypatch, caplog):
    def kaputt(*args, **kwargs):
        raise ConnectionRefusedError("Verbindung abgelehnt")

    monkeypatch.setattr("zusammenarbeit.mail._senden", kaputt)
    a, b = hinweis(konten[M], vor=90), hinweis(konten[M], vor=80)
    with caplog.at_level(logging.INFO, logger="zusammenarbeit.mail"):
        for _i in range(MAX_VERSUCHE):
            assert offene_versenden() == 0
    assert f"(Benachrichtigungen {a.pk}, {b.pk})" in caplog.records[0].getMessage()
    for x in (a, b):
        x.refresh_from_db()
        assert (x.mail_versuche, x.mail_status) == (MAX_VERSUCHE, MailStatus.FEHLER)


def test_eine_protokollzeile_je_sammelmail(konten, caplog):
    a, b = hinweis(konten[M], vor=90), hinweis(konten[M], vor=5)
    with caplog.at_level(logging.INFO, logger="zusammenarbeit.mail"):
        offene_versenden()
    assert [r.getMessage() for r in caplog.records] == [
        f"E-Mail verschickt: sammelmail an {konten[M].email} (Benachrichtigungen {a.pk}, {b.pk})"]
    assert "Hallenboden" not in caplog.text


def test_fenster_null_wie_bisher(konten, settings):
    settings.TEAMPLANER_MAIL_SAMMELN_SEKUNDEN = 0
    hinweis(konten[M])
    hinweis(konten[M])
    assert offene_versenden() == 2 and len(mail.outbox) == 2


def test_sammelmail_in_sprache_der_person(konten):
    konten[M].sprache = "en"
    konten[M].save(update_fields=["sprache"])
    hinweis(konten[M], vor=90)
    hinweis(konten[M], vor=5)
    offene_versenden()
    assert mail.outbox[0].subject == "[Team planner] 2 new notifications"
    assert "Go to inbox" in html_teil(mail.outbox[0])


# ---------- HTML-Teil (#40) ----------

def test_benachrichtigung_mit_html_und_gleichen_links(konten, aufgabe):
    hinweis(konten[M], vor=90, aufgabe=aufgabe)
    offene_versenden()
    nachricht = mail.outbox[0]
    html = html_teil(nachricht)
    for url in (f"https://teamplaner.example.test/aufgaben/{aufgabe.pk}/",
                "https://teamplaner.example.test/einstellungen/benachrichtigungen/"):
        assert url in nachricht.body and f'href="{url}"' in html
    assert ">Zur Aufgabe</a>" in html and "<script" not in html and "<img" not in html
    assert "\n-- \n" in nachricht.body  # Text-Teil unverändert


def test_titel_wird_im_html_escaped(konten, aufgabe):
    hinweis(konten[M], text="Neu: <script>alert(1)</script> & Co", vor=90, aufgabe=aufgabe)
    offene_versenden()
    html = html_teil(mail.outbox[0])
    assert "<script>" not in html and "&lt;script&gt;alert(1)&lt;/script&gt; &amp; Co" in html
    assert "<script>alert(1)</script> & Co" in mail.outbox[0].body


def test_bestellung_mit_knopf_zur_bestellliste(konten):
    hinweis(konten[M], text="Liefertermin überschritten: Rohr", vor=90, art=Benachrichtigungsart.LIEFERTERMIN)
    offene_versenden()
    assert ">Zur Bestellliste</a>" in html_teil(mail.outbox[0])
    assert "Zur Bestellliste: https://teamplaner.example.test/bestellungen/" in mail.outbox[0].body


@pytest.mark.parametrize("ausloesen, knopf", [
    (lambda k: einladung_senden(k, LINK), "Passwort festlegen"),
    (lambda k: reset_senden(k, LINK), "Passwort festlegen"),
    (lambda k: sicherheitshinweis(k, "passwort_geaendert"), "Zur Anmeldung"),
])
def test_system_mails_mit_html_das_nach_dem_versand_geleert_wird(konten, ausloesen, knopf):
    ausloesen(konten[M])
    m = Postausgang.objects.get()
    assert knopf in m.html
    assert offene_versenden() == 1
    html = html_teil(mail.outbox[0])
    assert f">{knopf}</a>" in html and "Teamplaner" in html
    if "passwort" in knopf.lower():
        assert f'href="{LINK}"' in html and LINK in mail.outbox[0].body
    m.refresh_from_db()
    assert (m.status, m.text, m.html) == (MailStatus.GESENDET, "", "")


def test_name_in_system_mail_escaped(konten):
    konto = konten[M]
    konto.person.anzeigename = "Eva <b>&</b>"
    konto.person.save(update_fields=["anzeigename"])
    einladung_senden(konto, LINK)
    html = Postausgang.objects.get().html
    assert "Eva &lt;b&gt;&amp;&lt;/b&gt;" in html and "<b>" not in html
