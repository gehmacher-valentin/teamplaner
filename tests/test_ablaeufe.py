"""Abläufe: Einladung, Anmeldung, Sperre, Erwähnungen, Konfliktschutz, Platzhalter, Suche."""

import re

import pytest
from axes.models import AccessAttempt
from django.test import Client

from kern.models import Konto, Person, Rolle
from planung.models import AnsichtFreigabe, Einteilung, Recht
from projekte import dienste
from projekte.models import Aufgabe, Status
from zusammenarbeit.models import Benachrichtigung, Erwaehnung, Kommentar

from .conftest import DI, DI2, DO, FEIERTAG, FR, MI, MI2, MO, ROLLEN, TESTPASSWORT

pytestmark = pytest.mark.django_db
A, BL, P, M, L = ROLLEN


def angemeldet(konto):
    c = Client()
    c.force_login(konto)
    return c


# --- Einladung und Anmeldung ---

def test_einladung_annehmen_und_anmelden(konten, bereich_a):
    bl = angemeldet(konten[BL])
    antwort = bl.post("/einstellungen/personen/einladen/", {"anzeigename": "Person 41", "email": "Person41@Example.test",
                                                           "bereich": bereich_a.pk, "rolle": Rolle.MITARBEITER}, follow=True)
    konto = Konto.objects.get(email="person41@example.test")
    assert not konto.has_usable_password()
    seite = antwort.content.decode()  # die Seite der neuen Person zeigt den Einladungslink
    link = re.search(r"https?://[^/\"<\s]+(/passwort/setzen/[^\"<\s]+)", seite).group(1)

    gast = Client()
    weiter = gast.get(link)  # Django leitet auf die Token-freie URL um
    formular_url = weiter.url
    antwort = gast.post(formular_url, {"new_password1": "Neues-Passwort-2026", "new_password2": "Neues-Passwort-2026"})
    assert antwort.status_code == 302
    neu = Client()
    neu.post("/anmelden/", {"username": "PERSON41@example.test", "password": "Neues-Passwort-2026"})
    assert neu.session["_auth_user_id"] == str(konto.pk)
    # Link ist danach verbraucht
    assert "ungültig" in Client().get(link, follow=True).content.decode()


def test_deaktiviertes_konto_kann_sich_nicht_anmelden(konten):
    konten[M].person.archivieren()
    antwort = Client().post("/anmelden/", {"username": konten[M].email, "password": TESTPASSWORT})
    assert antwort.status_code == 200
    assert "_auth_user_id" not in antwort.client.session


def test_sperre_nach_fehlversuchen(konten, settings):
    c = Client()
    for _ in range(settings.AXES_FAILURE_LIMIT):
        c.post("/anmelden/", {"username": konten[M].email, "password": "falsch"})
    antwort = c.post("/anmelden/", {"username": konten[M].email, "password": TESTPASSWORT})
    assert "_auth_user_id" not in c.session
    assert antwort.status_code in (200, 403, 429)


def test_sperre_gilt_fuer_jede_schreibweise_der_email(konten, settings):
    """Andere Groß-/Kleinschreibung meldet dasselbe Konto an – und zählt deshalb auch für die Sperre."""
    email = konten[M].email
    schreibweisen = [email.upper(), email.title(), f" {email.swapcase()} ", email.capitalize(), email]
    c = Client()
    for i in range(settings.AXES_FAILURE_LIMIT):
        c.post("/anmelden/", {"username": schreibweisen[i % len(schreibweisen)], "password": "falsch"})
    c.post("/anmelden/", {"username": email.upper(), "password": TESTPASSWORT})
    assert "_auth_user_id" not in c.session
    assert set(AccessAttempt.objects.values_list("username", flat=True)) == {email}


def test_anmeldung_setzt_fehlversuche_jeder_schreibweise_zurueck(konten, settings):
    email = konten[M].email
    c = Client()
    for _ in range(settings.AXES_FAILURE_LIMIT - 1):
        c.post("/anmelden/", {"username": email.upper(), "password": "falsch"})
    c.post("/anmelden/", {"username": email, "password": TESTPASSWORT})
    assert c.session["_auth_user_id"] == str(konten[M].pk)
    assert not AccessAttempt.objects.exists()


def test_sperre_je_ip_adresse_ueber_alle_konten(konten, settings):
    """Viele Konten von einem Rechner aus durchprobieren: nach TEAMPLANER_FEHLVERSUCHE_JE_IP ist Schluss."""
    settings.TEAMPLANER_FEHLVERSUCHE_JE_IP = 3
    c = Client(REMOTE_ADDR="192.0.2.10")
    for rolle in (A, BL, P):
        c.post("/anmelden/", {"username": konten[rolle].email, "password": "falsch"})
    antwort = c.post("/anmelden/", {"username": konten[M].email, "password": TESTPASSWORT})
    assert antwort.status_code == 429
    assert "_auth_user_id" not in c.session
    # Von einer anderen Adresse aus geht es weiter
    andere = Client(REMOTE_ADDR="192.0.2.20")
    andere.post("/anmelden/", {"username": konten[M].email, "password": TESTPASSWORT})
    assert andere.session["_auth_user_id"] == str(konten[M].pk)


def test_passwort_wird_mit_argon2_gespeichert(konten):
    assert konten[M].password.startswith("argon2")


# --- Erwähnungen und Benachrichtigungen ---

def test_erwaehnung_benachrichtigt_person_und_bei_platzhalter_die_anlegende_person(konten, aufgabe, platzhalter):
    erwaehnte = konten[M].person
    angemeldet(konten[BL]).post(f"/aufgaben/{aufgabe.pk}/kommentare/", {
        "text": f"@{erwaehnte.anzeigename} und @{platzhalter.anzeigename} bitte prüfen",
        "erwaehnungen": f'{{"{erwaehnte.anzeigename}": {erwaehnte.pk}, "{platzhalter.anzeigename}": {platzhalter.pk}}}',
    })
    kommentar = Kommentar.objects.get()
    assert kommentar.text == f"@[{erwaehnte.pk}] und @[{platzhalter.pk}] bitte prüfen"
    assert set(Erwaehnung.objects.values_list("person_id", flat=True)) == {erwaehnte.pk, platzhalter.pk}
    empfaenger = set(Benachrichtigung.objects.values_list("empfaenger_id", flat=True))
    assert empfaenger == {erwaehnte.pk, platzhalter.erstellt_von_id}
    seite = angemeldet(konten[L]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert f"@{platzhalter.anzeigename}" in seite and "erwaehnung--platzhalter" in seite


def test_gefaelschte_erwaehnung_wird_entschaerft(konten, aufgabe):
    angemeldet(konten[M]).post(f"/aufgaben/{aufgabe.pk}/kommentare/", {"text": f"Hallo @[{konten[BL].pk}]"})
    assert "@[" not in Kommentar.objects.get().text
    assert not Erwaehnung.objects.exists()


def test_zuweisung_benachrichtigt(konten, aufgabe):
    dienste.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konten[M].person}, aufgabe.version)
    assert Benachrichtigung.objects.get().empfaenger == konten[M].person


def test_platzhalter_bekommt_keine_benachrichtigung(konten, aufgabe, platzhalter):
    dienste.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": platzhalter}, aufgabe.version)
    assert not Benachrichtigung.objects.exists()


# --- Konfliktschutz und Verlauf ---

def test_aufgabe_gleichzeitig_bearbeitet_ergibt_konflikt(konten, aufgabe):
    version = aufgabe.version
    dienste.aufgabe_speichern(konten[BL], aufgabe, {"titel": "Neu A"}, version)
    with pytest.raises(dienste.Konflikt):
        dienste.aufgabe_speichern(konten[P], aufgabe, {"titel": "Neu B"}, version)
    aufgabe.refresh_from_db()
    assert aufgabe.titel == "Neu A" and aufgabe.version == version + 1


def test_inline_bearbeitung_mit_veralteter_version_zeigt_hinweis(konten, aufgabe):
    alte_version = aufgabe.version
    dienste.aufgabe_speichern(konten[BL], aufgabe, {"titel": "Neu A"}, alte_version)
    antwort = angemeldet(konten[P]).post(f"/aufgaben/{aufgabe.pk}/feld/", {"feld": "faellig_am", "wert": "2026-11-05", "version": alte_version})
    assert "jemand anderem geändert" in antwort.content.decode()
    aufgabe.refresh_from_db()
    assert aufgabe.faellig_am is None


def test_verlauf_und_erledigt_zeitpunkt(konten, aufgabe):
    erledigt = Status.standard_erledigt()
    dienste.aufgabe_speichern(konten[M], aufgabe, {"status": erledigt}, None)
    aufgabe.refresh_from_db()
    assert aufgabe.erledigt_am is not None
    seite = angemeldet(konten[L]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert "Status: Offen → Erledigt" in seite


def test_beschreibung_wird_bereinigt(konten, aufgabe):
    dienste.aufgabe_speichern(konten[BL], aufgabe, {"beschreibung": '<p onclick="x()">Hallo<script>böse()</script> <a href="javascript:alert(1)">Link</a></p>'}, None)
    aufgabe.refresh_from_db()
    assert "script" not in aufgabe.beschreibung and "onclick" not in aufgabe.beschreibung
    assert "javascript:" not in aufgabe.beschreibung


def test_aufgabe_loeschen_protokolliert_einteilungen(konten, aufgabe, person_a):
    from kern.models import Protokolleintrag

    e = Einteilung.objects.create(aufgabe=aufgabe, person=person_a, von=MO, bis=MI)
    dienste.aufgabe_loeschen(konten[BL], aufgabe)
    assert Protokolleintrag.objects.filter(objekt_typ="einteilung", objekt_id=e.pk, aktion="geloescht").exists()
    assert not Einteilung.objects.exists()


# --- Ansichten verwalten ---

def test_ansicht_freigaben_speichern_und_bearbeiten_erst_ab_planer(konten, bereich_a):
    bl = angemeldet(konten[BL])
    bl.post("/einstellungen/ansichten/teamplaner/neu/", {
        "name": "Bereich A", "sortierung": 0, "bereiche": [bereich_a.pk], "wochen": 2,
        f"freigabe-{konten[P].pk}": "bearbeiten",
        f"freigabe-{konten[M].pk}": "bearbeiten",  # wird auf „sehen“ herabgestuft
        f"freigabe-{konten[L].pk}": "",
    })
    rechte = dict(AnsichtFreigabe.objects.values_list("konto_id", "recht"))
    assert rechte == {konten[P].pk: Recht.BEARBEITEN, konten[M].pk: Recht.SEHEN}


# --- Platzhalter ---

def test_platzhalter_archivieren_blendet_aus_vorschlaegen_aus(konten, platzhalter):
    c = angemeldet(konten[P])
    c.post(f"/platzhalter/{platzhalter.pk}/archivieren/")
    namen = [p["name"] for p in c.get("/personen/vorschlaege/?q=Aushilfe").json()["personen"]]
    assert platzhalter.anzeigename not in namen
    c.post(f"/platzhalter/{platzhalter.pk}/wiederherstellen/")
    namen = [p["name"] for p in c.get("/personen/vorschlaege/?q=Aushilfe").json()["personen"]]
    assert platzhalter.anzeigename in namen


def test_platzhalter_bereich_nicht_aenderbar(konten, platzhalter, bereich_b):
    angemeldet(konten[P]).post(f"/einstellungen/personen/{platzhalter.pk}/", {"anzeigename": "Neu", "bereich": bereich_b.pk, "notiz": ""})
    platzhalter.refresh_from_db()
    assert platzhalter.bereich.name == "Bereich A" and platzhalter.anzeigename == "Neu"


def test_platzhalter_in_konto_umwandeln_behaelt_einteilungen(konten, platzhalter, aufgabe):
    e = Einteilung.objects.create(aufgabe=aufgabe, person=platzhalter, von=MO, bis=MI)
    antwort = angemeldet(konten[BL]).post(f"/platzhalter/{platzhalter.pk}/umwandeln/",
                                         {"email": "aushilfe@example.test", "rolle": Rolle.MITARBEITER})
    assert antwort.status_code == 302
    konto = Konto.objects.get(email="aushilfe@example.test")
    assert konto.pk == platzhalter.pk
    e.refresh_from_db()
    assert e.person_id == konto.pk and not Person.objects.get(pk=platzhalter.pk).ist_platzhalter


# --- Meine Aufgaben, Widget, Suche ---

def test_arbeitstage_widget(konten, aufgabe, person_a, platzhalter):
    from projekte.ansicht import arbeitstage_widget

    e1 = Einteilung.objects.create(aufgabe=aufgabe, person=person_a, von=FR, bis=MI2)  # Fr + Di, Mi (Mo Feiertag)
    e2 = Einteilung.objects.create(aufgabe=aufgabe, person=platzhalter, von=DI, bis=DO)
    widget = arbeitstage_widget(aufgabe, [e1, e2], "2026-10")
    an = {z["datum"] for z in widget["zellen"] if z and z["an"]}
    assert an == {DI, MI, DO, FR, DI2, MI2} and FEIERTAG not in an
    assert widget["anzahl"] == 6


def test_meine_aufgaben_zeigt_einteilung_und_zuweisung(konten, aufgabe, projekt, abschnitt):
    from datetime import date, timedelta

    from django.utils import timezone

    heute = timezone.localdate()
    werktag = heute if heute.weekday() < 5 else heute + timedelta(days=7 - heute.weekday())
    Einteilung.objects.create(aufgabe=aufgabe, person=konten[M].person, von=werktag, bis=werktag)
    Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel="Regal Lager", status=Status.standard_offen(),
                           verantwortlich=konten[M].person, faellig_am=date(2020, 1, 1))
    seite = angemeldet(konten[M]).get("/meine-aufgaben/").content.decode()
    assert "Hallenboden Nord" in seite and "Regal Lager" in seite and "Überfällig" in seite


def test_suche_findet_aufgabe_projekt_und_kommentar(konten, aufgabe):
    Kommentar.objects.create(aufgabe=aufgabe, autor=konten[M].person, text="Dichtbänder fehlen noch")
    c = angemeldet(konten[L])
    seite = c.get("/suche/?q=Hallen").content.decode()
    assert "Hallenboden Nord" in seite
    assert "Neubau Lagerhalle" in c.get("/suche/?q=Lagerhalle").content.decode()
    assert "Dichtbänder" in c.get("/suche/?q=Dichtband").content.decode()


def test_suchvorschlaege_beim_tippen(konten, aufgabe):
    """Vorschläge unter der Suche der Kopfzeile: ab zwei Zeichen die besten Treffer und ein Link zur vollen Suche."""
    Kommentar.objects.create(aufgabe=aufgabe, autor=konten[M].person, text="Dichtbänder fehlen noch")
    c = angemeldet(konten[L])
    assert c.get("/suche/vorschlaege/?q=H").content == b""
    vorschlaege = c.get("/suche/vorschlaege/?q=Hallen").content.decode()
    assert "Hallenboden Nord" in vorschlaege and f"/aufgaben/{aufgabe.pk}/" in vorschlaege
    assert "/suche/?q=Hallen" in vorschlaege and 'role="option"' in vorschlaege
    assert "Neubau Lagerhalle" in c.get("/suche/vorschlaege/?q=Neubau").content.decode()
    assert "Dichtbänder" in c.get("/suche/vorschlaege/?q=Dichtb").content.decode()
    assert "Keine Treffer" in c.get("/suche/vorschlaege/?q=xyzxyz").content.decode()
    assert Client().get("/suche/vorschlaege/?q=Hallen").status_code == 302
