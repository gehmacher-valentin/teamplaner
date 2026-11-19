"""Abläufe: Einladung, Anmeldung, Sperre, Erwähnungen, Konfliktschutz, Platzhalter, Suche."""

import re

import pytest
from axes.models import AccessAttempt
from django.test import Client

from kern.models import Konto, Person, Protokolleintrag, Rolle
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

@pytest.mark.parametrize("rolle", [A, BL])
def test_einladen_in_der_eigenen_rolle_zeigt_den_link(konten, bereich_a, rolle):
    """Einladen in der eigenen Rolle ist erlaubt, Bearbeiten des neuen Kontos nicht: statt 403 eine
    Bestätigungsseite mit dem Link, der genau einmal und nur zu diesem Konto erscheint."""
    c = angemeldet(konten[rolle])
    antwort = c.post("/einstellungen/personen/einladen/", {"anzeigename": "Person 43", "email": "person43@example.test",
                                                          "bereich": bereich_a.pk, "rolle": rolle}, follow=True)
    neu = Konto.objects.get(email="person43@example.test")
    assert antwort.redirect_chain[-1][0] == f"/einstellungen/personen/{neu.pk}/eingeladen/"
    assert antwort.status_code == 200
    seite = antwort.content.decode()
    assert "/passwort/setzen/" in seite and "Konto für Person 43 angelegt." in seite
    assert 'name="anzeigename"' not in seite  # kein Formular zum Bearbeiten
    # Einmalig: beim zweiten Aufruf zurück zur Liste; die Seite der Person bleibt gesperrt
    assert c.get(f"/einstellungen/personen/{neu.pk}/eingeladen/").url == "/einstellungen/personen/"
    assert c.get(f"/einstellungen/personen/{neu.pk}/").status_code == 403


def test_link_erscheint_nur_beim_eingeladenen_konto(konten, bereich_a):
    c = angemeldet(konten[A])
    c.post("/einstellungen/personen/einladen/", {"anzeigename": "Person 44", "email": "person44@example.test",
                                                "bereich": bereich_a.pk, "rolle": A})
    # Bevor die Bestätigungsseite geöffnet wird: eine andere Personenseite zeigt den Link nicht
    assert "/passwort/setzen/" not in c.get(f"/einstellungen/personen/{konten[M].pk}/").content.decode()
    neu = Konto.objects.get(email="person44@example.test")
    assert "/passwort/setzen/" in c.get(f"/einstellungen/personen/{neu.pk}/eingeladen/").content.decode()


def test_bestaetigungsseite_ohne_einladung(konten):
    """Ohne gemerkten Link gibt die Seite nichts preis; bearbeitbare Konten haben ihre normale Seite."""
    c = angemeldet(konten[BL])
    assert c.get(f"/einstellungen/personen/{konten[A].pk}/eingeladen/").url == "/einstellungen/personen/"
    assert c.get(f"/einstellungen/personen/{konten[M].pk}/eingeladen/").url == f"/einstellungen/personen/{konten[M].pk}/"
    assert angemeldet(konten[P]).get(f"/einstellungen/personen/{konten[M].pk}/eingeladen/").status_code == 403


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


@pytest.mark.argon2
def test_passwort_wird_mit_argon2_gespeichert(konten, settings):
    assert settings.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")
    assert konten[M].password.startswith("argon2")


def test_tests_laufen_mit_schnellem_hasher(konten):
    """Gegenprobe zur Fixture ``schneller_passwort_hasher``."""
    assert konten[M].password.startswith("md5$")


# --- Erwähnungen und Benachrichtigungen ---

def test_erwaehnung_benachrichtigt_person_und_bei_platzhalter_die_eingetragenen_konten(konten, aufgabe, platzhalter):
    erwaehnte = konten[M].person
    platzhalter.weiterleiten_an.add(konten[L].person)
    angemeldet(konten[BL]).post(f"/aufgaben/{aufgabe.pk}/kommentare/", {
        "text": f"@{erwaehnte.anzeigename} und @{platzhalter.anzeigename} bitte prüfen",
        "erwaehnungen": f'{{"{erwaehnte.anzeigename}": {erwaehnte.pk}, "{platzhalter.anzeigename}": {platzhalter.pk}}}',
    })
    kommentar = Kommentar.objects.get()
    assert kommentar.text == f"@[{erwaehnte.pk}] und @[{platzhalter.pk}] bitte prüfen"
    assert set(Erwaehnung.objects.values_list("person_id", flat=True)) == {erwaehnte.pk, platzhalter.pk}
    empfaenger = set(Benachrichtigung.objects.values_list("empfaenger_id", flat=True))
    assert empfaenger == {erwaehnte.pk, konten[L].pk}  # nicht mehr an erstellt_von (alte Sonderregel)
    weiter = Benachrichtigung.objects.get(empfaenger=konten[L].person)
    assert weiter.art == "erwaehnung" and weiter.text.endswith("(für Platzhalter „Aushilfe Montage“)")
    seite = angemeldet(konten[L]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert f"@{platzhalter.anzeigename}" in seite and "erwaehnung--platzhalter" in seite


def test_gefaelschte_erwaehnung_wird_entschaerft(konten, aufgabe):
    angemeldet(konten[M]).post(f"/aufgaben/{aufgabe.pk}/kommentare/", {"text": f"Hallo @[{konten[BL].pk}]"})
    assert "@[" not in Kommentar.objects.get().text
    assert not Erwaehnung.objects.exists()


def test_zuweisung_benachrichtigt(konten, aufgabe):
    dienste.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": konten[M].person}, aufgabe.version)
    assert Benachrichtigung.objects.get().empfaenger == konten[M].person


def test_platzhalter_ohne_eintrag_benachrichtigt_niemanden(konten, aufgabe, platzhalter):
    dienste.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": platzhalter}, aufgabe.version)
    assert not Benachrichtigung.objects.exists()  # auch nicht erstellt_von


def test_platzhalter_leitet_an_ein_konto_weiter(konten, aufgabe, platzhalter):
    platzhalter.weiterleiten_an.add(konten[M].person)
    dienste.aufgabe_speichern(konten[BL], aufgabe, {"verantwortlich": platzhalter}, aufgabe.version)
    b = Benachrichtigung.objects.get()
    assert b.empfaenger == konten[M].person and b.art == "zuweisung"
    assert b.text == f"{konten[BL].person.anzeigename} hat Ihnen „{aufgabe.titel}“ zugewiesen. (für Platzhalter „Aushilfe Montage“)"


def test_platzhalter_leitet_an_mehrere_weiter_ohne_archivierte_und_ausloeser(konten, aufgabe, platzhalter):
    from zusammenarbeit.dienste import benachrichtigen

    platzhalter.weiterleiten_an.add(konten[M].person, konten[L].person, konten[P].person, konten[BL].person)
    konten[L].person.archivieren()
    ergebnis = benachrichtigen(platzhalter, "kommentar", "%(titel)s", {"titel": "X"}, ausloeser=konten[BL].person)
    assert {b.empfaenger_id for b in ergebnis} == {konten[M].pk, konten[P].pk}
    assert set(Benachrichtigung.objects.values_list("empfaenger_id", flat=True)) == {konten[M].pk, konten[P].pk}


def test_weiterleitung_englisch_und_mail_nach_einstellung_der_empfangenden(konten, platzhalter, settings):
    from zusammenarbeit.dienste import benachrichtigen
    from zusammenarbeit.models import MailStatus

    settings.EMAIL_HOST = "localhost"
    m, l_ = konten[M], konten[L]
    m.sprache, m.mail_einstellungen = "en", {"kommentar": True}
    m.save(update_fields=["sprache", "mail_einstellungen"])
    platzhalter.weiterleiten_an.add(m.person, l_.person)
    benachrichtigen(platzhalter, "kommentar", "%(titel)s", {"titel": "X"})
    bm = Benachrichtigung.objects.get(empfaenger=m.person)
    assert bm.text == "X (for placeholder “Aushilfe Montage”)" and bm.mail_status == MailStatus.OFFEN
    assert Benachrichtigung.objects.get(empfaenger=l_.person).mail_status == MailStatus.KEINE


def test_weiterleitung_im_formular_standard_leer_und_protokoll(konten, platzhalter):
    c = angemeldet(konten[P])
    url = f"/einstellungen/personen/{platzhalter.pk}/"
    seite = c.get(url).content.decode()
    assert "Benachrichtigungen weiterleiten an" in seite
    assert 'name="weiterleiten_an"' in seite and "checked" not in seite.split("weiterleiten_an")[1].split("</fieldset>")[0]
    assert konten[A].person.anzeigename in seite  # Personenauswahl: aktive Konten …
    assert f'value="{platzhalter.pk}"' not in seite.split("weiterleiten_an")[1].split("</fieldset>")[0]  # … ohne Platzhalter
    antwort = c.post(url, {"anzeigename": platzhalter.anzeigename, "bereich": platzhalter.bereich_id, "notiz": "",
                           "weiterleiten_an": [konten[M].pk, konten[L].pk]})
    assert antwort.status_code == 302
    assert set(platzhalter.weiterleiten_an.values_list("pk", flat=True)) == {konten[M].pk, konten[L].pk}
    eintrag = Protokolleintrag.objects.get(objekt_typ="platzhalter", objekt_id=platzhalter.pk, aktion="geaendert")
    assert eintrag.daten["weiterleiten_an"][1] == sorted([konten[M].person.anzeigename, konten[L].person.anzeigename])


def test_neuer_platzhalter_ohne_weiterleitung(konten):
    c = angemeldet(konten[P])
    c.post("/einstellungen/personen/platzhalter/", {"anzeigename": "Aushilfe Neu", "bereich": konten[P].person.bereich_id})
    neu = Person.objects.get(anzeigename="Aushilfe Neu")
    assert not neu.weiterleiten_an.exists()


def test_umwandeln_entfernt_weiterleitung(konten, platzhalter):
    platzhalter.weiterleiten_an.add(konten[M].person)
    angemeldet(konten[A]).post(f"/platzhalter/{platzhalter.pk}/umwandeln/",
                               {"email": "aushilfe@example.test", "rolle": "mitarbeiter"})
    platzhalter.refresh_from_db()
    assert not platzhalter.ist_platzhalter and not platzhalter.weiterleiten_an.exists()


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


def test_platzhalter_bereich_aenderbar(konten, platzhalter, bereich_b, ansicht_a, ansicht_b):
    """Bereichswechsel: Protokoll, und die Person wandert in die Ansichten des neuen Bereichs."""
    seite = angemeldet(konten[P]).get(f"/einstellungen/personen/{platzhalter.pk}/").content.decode()
    assert 'name="bereich"' in seite
    angemeldet(konten[P]).post(f"/einstellungen/personen/{platzhalter.pk}/", {"anzeigename": "Neu", "bereich": bereich_b.pk, "notiz": ""})
    platzhalter.refresh_from_db()
    assert platzhalter.bereich == bereich_b and platzhalter.anzeigename == "Neu"
    eintrag = Protokolleintrag.objects.get(objekt_typ="platzhalter", objekt_id=platzhalter.pk, aktion="geaendert")
    assert eintrag.daten["bereich"] == [{"id": konten[P].person.bereich_id, "name": "Bereich A"},
                                        {"id": bereich_b.pk, "name": "Bereich B"}]
    assert platzhalter not in ansicht_a.personen_queryset() and platzhalter in ansicht_b.personen_queryset()


def test_konto_bereich_aenderbar(konten, bereich_a, bereich_b, ansicht_a, ansicht_b):
    ziel = konten[M]
    seite = angemeldet(konten[BL]).get(f"/einstellungen/personen/{ziel.pk}/").content.decode()
    assert 'name="bereich"' in seite
    antwort = angemeldet(konten[BL]).post(f"/einstellungen/personen/{ziel.pk}/", {
        "anzeigename": ziel.person.anzeigename, "email": ziel.email, "rolle": ziel.rolle, "bereich": bereich_b.pk})
    assert antwort.status_code == 302
    ziel.person.refresh_from_db()
    assert ziel.person.bereich == bereich_b
    eintrag = Protokolleintrag.objects.get(objekt_typ="konto", objekt_id=ziel.pk, aktion="geaendert")
    assert eintrag.daten["bereich"] == [{"id": bereich_a.pk, "name": "Bereich A"}, {"id": bereich_b.pk, "name": "Bereich B"}]
    assert ziel.person not in ansicht_a.personen_queryset() and ziel.person in ansicht_b.personen_queryset()
    # Ohne Bereich speichert das Formular nicht
    antwort = angemeldet(konten[BL]).post(f"/einstellungen/personen/{ziel.pk}/", {
        "anzeigename": ziel.person.anzeigename, "email": ziel.email, "rolle": ziel.rolle})
    assert antwort.status_code == 200
    ziel.person.refresh_from_db()
    assert ziel.person.bereich == bereich_b


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


# --- Meine Aufgaben: betreute Platzhalter ---

@pytest.fixture
def betreut(konten, bereich_a):
    """Zwei Platzhalter, deren Benachrichtigungen an die Mitarbeiterin gehen, und einer für jemand anderen."""
    eins = Person.objects.create(anzeigename="Aushilfe Eins", bereich=bereich_a)
    zwei = Person.objects.create(anzeigename="Aushilfe Zwei", bereich=bereich_a)
    fremd = Person.objects.create(anzeigename="Aushilfe Fremd", bereich=bereich_a)
    eins.weiterleiten_an.add(konten[M].person)
    zwei.weiterleiten_an.add(konten[M].person)
    fremd.weiterleiten_an.add(konten[L].person)
    return eins, zwei, fremd


def _werktag():
    from datetime import timedelta

    from django.utils import timezone

    heute = timezone.localdate()
    return heute if heute.weekday() < 5 else heute + timedelta(days=7 - heute.weekday())


def test_meine_aufgaben_ohne_betreute_platzhalter_unveraendert(konten, aufgabe):
    seite = angemeldet(konten[M]).get("/meine-aufgaben/").content.decode()
    assert "Mir zugewiesen" in seite
    for text in ("Platzhaltern zugewiesen", "eingeteilt-wahl", "meine-umschalter", "meine-raster--platzhalter"):
        assert text not in seite


def test_meine_aufgaben_dropdown_eingeteilt_mit_abwesenheit(konten, aufgabe, betreut):
    from planung.models import Abwesenheit

    eins, zwei, fremd = betreut
    tag = _werktag()
    Einteilung.objects.create(aufgabe=aufgabe, person=eins, von=tag, bis=tag)
    Abwesenheit.objects.create(person=eins, von=tag, bis=tag)
    c = angemeldet(konten[M])
    seite = c.get("/meine-aufgaben/").content.decode()
    assert 'id="eingeteilt-wahl"' in seite and "Aushilfe Eins" in seite and "Aushilfe Zwei" in seite
    assert "Aushilfe Fremd" not in seite
    assert "Hallenboden Nord" not in seite.split('id="karte-mir"')[0]  # „Ich“: nichts eingeteilt
    seite = c.get(f"/meine-aufgaben/?eingeteilt={eins.pk}").content.decode()
    karte = seite.split('id="karte-mir"')[0]
    assert "Hallenboden Nord" in karte and "Abwesend" in karte
    assert f'<option value="{eins.pk}" selected>' in karte
    # Fremde Person-ID: keine Daten, zurück auf „Ich“
    Einteilung.objects.create(aufgabe=aufgabe, person=fremd, von=tag, bis=tag)
    karte = c.get(f"/meine-aufgaben/?eingeteilt={fremd.pk}").content.decode().split('id="karte-mir"')[0]
    assert "Hallenboden Nord" not in karte and "Aushilfe Fremd" not in karte


def test_meine_aufgaben_platzhaltern_zugewiesen_mit_filter(konten, projekt, abschnitt, betreut):
    eins, zwei, fremd = betreut
    for titel, person in [("Regal Eins", eins), ("Regal Zwei", zwei), ("Regal Fremd", fremd),
                          ("Regal Ich", konten[M].person)]:
        Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel=titel, status=Status.standard_offen(),
                               verantwortlich=person)
    c = angemeldet(konten[M])
    seite = c.get("/meine-aufgaben/").content.decode()
    mir, platzhalter = seite.split('id="karte-mir"')[1].split('id="karte-platzhalter"')
    assert "Regal Ich" in mir and "Regal Eins" not in mir
    assert "Regal Eins" in platzhalter and "Regal Zwei" in platzhalter and "Regal Fremd" not in platzhalter
    assert 'id="platzhalter-filter"' in platzhalter and "Aushilfe Eins" in platzhalter  # Avatar/Name je Zeile
    assert 'data-zugewiesen="ich"' in seite
    gefiltert = c.get(f"/meine-aufgaben/?zugewiesen=platzhalter&platzhalter={zwei.pk}").content.decode()
    teil = gefiltert.split('id="karte-platzhalter"')[1]
    assert "Regal Zwei" in teil and "Regal Eins" not in teil
    assert 'data-zugewiesen="platzhalter"' in gefiltert
    # Rücksprung nach dem Abhaken behält den Zustand
    assert f'name="weiter" value="/meine-aufgaben/?zugewiesen=platzhalter&amp;platzhalter={zwei.pk}"' in gefiltert
    # Fremder Filter: ignoriert, „Alle“
    teil = c.get(f"/meine-aufgaben/?platzhalter={fremd.pk}").content.decode().split('id="karte-platzhalter"')[1]
    assert "Regal Eins" in teil and "Regal Fremd" not in teil


def test_meine_aufgaben_filter_erst_ab_zwei_platzhaltern(konten, betreut):
    eins, zwei, _fremd = betreut
    zwei.weiterleiten_an.clear()
    seite = angemeldet(konten[M]).get("/meine-aufgaben/").content.decode()
    assert "Platzhaltern zugewiesen" in seite and 'id="platzhalter-filter"' not in seite


def test_meine_aufgaben_archivierte_platzhalter_nicht_betreut(konten, betreut):
    eins, zwei, _fremd = betreut
    eins.archivieren()
    seite = angemeldet(konten[M]).get("/meine-aufgaben/").content.decode()
    assert "Aushilfe Zwei" in seite and "Aushilfe Eins" not in seite


def test_platzhalter_aufgabe_abhaken_wie_eigene(konten, projekt, abschnitt, betreut):
    eins = betreut[0]
    a = Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel="Regal Eins", status=Status.standard_offen(),
                               verantwortlich=eins)
    antwort = angemeldet(konten[M]).post(f"/aufgaben/{a.pk}/erledigt/", {"erledigt": "1", "zeile": "meine"},
                                         HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200 and "zugewiesen__zeile--erledigt" in antwort.content.decode()
    a.refresh_from_db()
    assert a.status.ist_erledigt
    # Lesende dürfen nicht abhaken, auch nicht für betreute Platzhalter
    eins.weiterleiten_an.add(konten[L].person)
    b = Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel="Regal B", status=Status.standard_offen(),
                               verantwortlich=eins)
    assert angemeldet(konten[L]).post(f"/aufgaben/{b.pk}/erledigt/", {"erledigt": "1"}).status_code == 403


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
