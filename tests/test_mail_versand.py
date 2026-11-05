"""E-Mail-Versand global abschaltbar, Passwort-Link als QR-Code."""

import pytest
from django.core import mail
from django.test import Client

from kern import zwei_faktor
from kern.hilfen import link_qr_svg
from kern.models import Konto, Protokolleintrag, Rolle, Systemeinstellungen
from projekte import dienste as projekte
from zusammenarbeit.mail import (
    einladung_senden,
    mail_aktiv,
    offene_versenden,
    reset_senden,
    sicherheitshinweis,
)
from zusammenarbeit.models import Benachrichtigung, MailStatus, Postausgang

from .conftest import TESTPASSWORT

pytestmark = pytest.mark.django_db
A, BL, P, M = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER
URL = "/einstellungen/allgemein/"
BENACHRICHTIGUNGEN = "/einstellungen/benachrichtigungen/"


@pytest.fixture(autouse=True)
def smtp(settings):
    settings.EMAIL_HOST = "smtp.example.test"
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    settings.TEAMPLANER_ADRESSE = "https://teamplaner.example.test"


def angemeldet(konto):
    c = Client()
    c.force_login(konto)
    return c


def versand_aus():
    Systemeinstellungen.objects.update_or_create(pk=1, defaults={"mail_versand": False})


def person_seite(c, konto):
    return c.get(f"/einstellungen/personen/{konto.pk}/").content.decode()


# ---------- Schalter ----------

def test_nur_admin_darf_umschalten(konten):
    assert angemeldet(konten[BL]).post(URL, {"feld": "mail_versand"}).status_code == 403
    assert Systemeinstellungen.laden().mail_versand is True


def test_umschalten_steht_im_protokoll(konten):
    assert angemeldet(konten[A]).post(URL, {"feld": "mail_versand"}).status_code == 204
    assert mail_aktiv() is False
    eintrag = Protokolleintrag.objects.get(objekt_typ="einstellungen", aktion="geaendert")
    assert eintrag.daten == {"mail_versand": [True, False]}
    angemeldet(konten[A]).post(URL, {"feld": "mail_versand", "an": "1"})
    assert mail_aktiv() is True


def test_ohne_smtp_laesst_sich_nichts_wirksam_einschalten(konten, settings):
    settings.EMAIL_HOST = ""
    versand_aus()
    c = angemeldet(konten[A])
    assert c.post(URL, {"feld": "mail_versand", "an": "1"}).status_code == 400
    assert Systemeinstellungen.laden().mail_versand is False and mail_aktiv() is False
    seite = c.get(URL).content.decode()
    assert "kein SMTP-Server eingerichtet" in seite
    zeile = seite[seite.index('id="mail-versand"'):]
    assert "disabled" in zeile[:zeile.index(">")] and "checked" not in zeile[:zeile.index(">")]


def test_mit_smtp_ist_der_schalter_bedienbar(konten):
    seite = angemeldet(konten[A]).get(URL).content.decode()
    zeile = seite[seite.index('id="mail-versand"'):]
    assert "kein SMTP-Server eingerichtet" not in seite
    assert "checked" in zeile[:zeile.index(">")] and "disabled" not in zeile[:zeile.index(">")]


# ---------- Abgeschalteter Versand ----------

def test_ohne_versand_landet_nichts_im_postausgang(konten):
    versand_aus()
    assert einladung_senden(konten[M], "https://x.test/link") is False
    assert reset_senden(konten[M], "https://x.test/link") is False
    sicherheitshinweis(konten[M], "passwort_geaendert")
    assert not Postausgang.objects.exists()


def test_ohne_versand_kommt_die_benachrichtigung_nur_in_den_posteingang(konten, aufgabe):
    konten[M].mail_einstellungen = {"zuweisung": True}
    konten[M].save(update_fields=["mail_einstellungen"])
    versand_aus()
    projekte.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konten[M].person}, None)
    assert Benachrichtigung.objects.get().mail_status == MailStatus.KEINE
    assert offene_versenden() == 0 and mail.outbox == []


def test_dienst_bemerkt_das_abschalten_ohne_neustart(konten):
    Postausgang.objects.create(art=Postausgang.Art.RESET, empfaenger="x@example.test", betreff="b", text="t")
    versand_aus()  # ohne wartende_verwerfen(): nur die Prüfung im Durchlauf
    assert offene_versenden() == 0 and mail.outbox == []


def test_abschalten_verwirft_wartende_mails(konten, aufgabe):
    konten[M].mail_einstellungen = {"zuweisung": True}
    konten[M].save(update_fields=["mail_einstellungen"])
    projekte.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konten[M].person}, None)
    reset_senden(konten[M], "https://x.test/geheimer-link")
    wartend = Postausgang.objects.get()
    gesendet = Postausgang.objects.create(art=Postausgang.Art.EINLADUNG, empfaenger="y@example.test", betreff="b",
                                          text="", status=MailStatus.GESENDET)
    assert Benachrichtigung.objects.get().mail_status == MailStatus.OFFEN

    c = angemeldet(konten[A])
    c.post(URL, {"feld": "mail_versand"})
    wartend.refresh_from_db()
    gesendet.refresh_from_db()
    assert wartend.status == MailStatus.KEINE and wartend.text == ""
    assert gesendet.status == MailStatus.GESENDET
    assert Benachrichtigung.objects.get().mail_status == MailStatus.KEINE

    c.post(URL, {"feld": "mail_versand", "an": "1"})
    assert offene_versenden() == 0 and mail.outbox == []


def test_anmeldeseite_und_passwort_vergessen_ohne_versand():
    versand_aus()
    seite = Client().get("/anmelden/").content.decode()
    assert "einen neuen Link anfordern" in seite and "/passwort/vergessen/" not in seite
    antwort = Client().get("/passwort/vergessen/")
    assert antwort.status_code == 302 and antwort["Location"].startswith("/anmelden/")


def test_personenseite_ohne_versand_link_kopierbar_und_passwort_gesperrt(konten):
    versand_aus()
    c = angemeldet(konten[BL])
    c.post(f"/personen/{konten[M].pk}/link/")
    seite = person_seite(c, konten[M])
    assert "/passwort/setzen/" in seite and "data-kopieren" in seite
    konten[M].refresh_from_db()
    assert not konten[M].has_usable_password()
    assert not Postausgang.objects.exists()


def test_rueckfrage_verspricht_nur_mit_versand_eine_mail(konten):
    zwei_faktor.einrichten(konten[M], zwei_faktor.neues_geheimnis(), 1)
    c = angemeldet(konten[BL])
    assert "Die Person bekommt eine E-Mail." in person_seite(c, konten[M])
    versand_aus()
    seite = person_seite(c, konten[M])
    assert "Die Person bekommt eine E-Mail." not in seite
    assert "weil das Telefon verloren ist?" in seite


# ---------- Persönliche E-Mail-Einstellungen ----------

def test_einstellung_ohne_versand_abgelehnt_und_nach_wiedereinschalten_gueltig(konten):
    konten[M].mail_einstellungen = {"erwaehnung": True}
    konten[M].save(update_fields=["mail_einstellungen"])
    versand_aus()
    c = angemeldet(konten[M])
    assert c.post("/einstellungen/benachrichtigungen/speichern/", {"art": "kommentar", "an": "1"}).status_code == 400
    konten[M].refresh_from_db()
    assert konten[M].mail_einstellungen == {"erwaehnung": True}
    Systemeinstellungen.objects.update(mail_versand=True)
    assert c.post("/einstellungen/benachrichtigungen/speichern/", {"art": "kommentar", "an": "1"}).status_code == 204
    konten[M].refresh_from_db()
    assert konten[M].mail_einstellungen == {"erwaehnung": True, "kommentar": True}


def schalter(seite):
    return [t.split(">")[0] for t in seite.split('class="schalter"')[1:]]


def test_schalter_ausgegraut_mit_meldung(konten, settings):
    c = angemeldet(konten[M])
    seite = c.get(BENACHRICHTIGUNGEN).content.decode()
    assert "meldung--warning" not in seite and not any("disabled" in s for s in schalter(seite))

    versand_aus()
    seite = c.get(BENACHRICHTIGUNGEN).content.decode()
    assert "E-Mail-Versand ist deaktiviert." in seite
    assert schalter(seite) and all("disabled" in s for s in schalter(seite))

    settings.EMAIL_HOST = ""
    Systemeinstellungen.objects.update(mail_versand=True)
    seite = c.get(BENACHRICHTIGUNGEN).content.decode()
    assert "noch nicht eingerichtet" in seite and "E-Mail-Versand ist deaktiviert." not in seite
    assert all("disabled" in s for s in schalter(seite))


# ---------- QR-Code ----------

def test_link_zeigt_qr_code_genau_dieses_links_nur_einmal(konten):
    versand_aus()
    c = angemeldet(konten[BL])
    c.post(f"/personen/{konten[M].pk}/link/")
    antwort = c.get(f"/einstellungen/personen/{konten[M].pk}/")
    seite = antwort.content.decode()
    assert str(link_qr_svg(antwort.context["link"])) in seite and "passwort-link__qr" in seite
    assert "/passwort/setzen/" not in str(link_qr_svg(antwort.context["link"]))
    zweite = person_seite(c, konten[M])
    assert "passwort-link__qr" not in zweite and "/passwort/setzen/" not in zweite


def test_qr_code_hat_hellen_grund_und_ruhezone():
    svg = str(link_qr_svg("https://teamplaner.example.test/passwort/setzen/abc/def/"))
    assert svg.startswith("<svg") and 'fill="#fff"' in svg
    assert "viewBox=" in svg and "width=" not in svg.split(">")[0]  # skaliert mit dem CSS, statt abgeschnitten zu werden
    assert "<script" not in svg and "style=" not in svg


def test_einladung_zeigt_qr_code(konten):
    c = angemeldet(konten[BL])
    konto = Konto.objects.anlegen("neu@example.test", anzeigename="Person 09", bereich=konten[M].person.bereich, rolle=M)
    c.post(f"/personen/{konto.pk}/link/")
    assert "passwort-link__qr" in person_seite(c, konto)


def test_kein_qr_code_ohne_link(konten):
    assert "passwort-link__qr" not in person_seite(angemeldet(konten[BL]), konten[M])


def test_reset_per_mail_zeigt_weder_link_noch_qr_code(konten):
    c = angemeldet(konten[BL])
    c.post(f"/personen/{konten[M].pk}/link/")
    seite = person_seite(c, konten[M])
    assert "passwort-link__qr" not in seite and "/passwort/setzen/" not in seite
    konten[M].refresh_from_db()
    assert konten[M].check_password(TESTPASSWORT)
