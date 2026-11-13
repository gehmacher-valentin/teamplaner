"""Serverseitige Rechteprüfung der Seiten je Rolle."""

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from kern.models import Konto, Person, Rolle
from planung.models import TeamplanerAnsicht
from projekte.models import Aufgabe, Projekt, Status
from zusammenarbeit.models import Anhang, Kommentar

from .conftest import ROLLEN

pytestmark = pytest.mark.django_db

A, BL, P, M, L = ROLLEN


def client_fuer(konto):
    c = Client()
    if konto:
        c.force_login(konto)
    return c


GET_SEITEN = [
    # Einstellungsbereich: persönliche Seiten für alle, Team und System je nach Recht
    ("/einstellungen/profil/", {A, BL, P, M, L}),
    ("/einstellungen/sicherheit/", {A, BL, P, M, L}),
    ("/einstellungen/benachrichtigungen/", {A, BL, P, M, L}),
    ("/einstellungen/darstellung/", {A, BL, P, M, L}),
    ("/einstellungen/ueber/", {A, BL, P, M, L}),
    ("/einstellungen/personen/", {A, BL, P}),
    ("/einstellungen/personen/einladen/", {A, BL}),
    ("/einstellungen/personen/platzhalter/", {A, BL, P}),
    ("/einstellungen/ansichten/", {A, BL}),
    ("/einstellungen/ansichten/teamplaner/neu/", {A, BL}),
    ("/einstellungen/ansichten/gantt/neu/", {A, BL}),
    ("/einstellungen/rollen/", {A, BL}),
    ("/einstellungen/allgemein/", {A}),
    ("/einstellungen/mailversand/", {A}),
    ("/einstellungen/listen/", {A}),
    ("/einstellungen/kalender/", {A}),
    ("/einstellungen/speicherplatz/", {A}),
    ("/protokoll/", {A, BL, P}),
    ("/protokoll/?ansicht=erledigt", {A, BL, P}),
    ("/projekte/neu/", {A, BL, P}),
    ("/meine-aufgaben/", {A, BL, P, M, L}),
    ("/kalender/", {A, BL, P, M, L}),
    ("/projekte/", {A, BL, P, M, L}),
    ("/posteingang/", {A, BL, P, M, L}),
    ("/posteingang/feld/", {A, BL, P, M, L}),
    ("/notizen/", {A, BL, P, M, L}),
    ("/notizen/ordner/neu/", {A, BL, P}),
    ("/bestellungen/", {A, BL, P, M, L}),
]


@pytest.mark.parametrize("url, erlaubt", GET_SEITEN, ids=[s[0] for s in GET_SEITEN])
@pytest.mark.parametrize("rolle", ROLLEN)
def test_seitenzugriff(konten, url, erlaubt, rolle):
    antwort = client_fuer(konten[rolle]).get(url)
    assert antwort.status_code == (200 if rolle in erlaubt else 403)


@pytest.mark.parametrize("url", [s[0] for s in GET_SEITEN] + ["/", "/aufgaben/1/"])
def test_ohne_anmeldung_weiter_zur_anmeldung(db, url):
    antwort = Client().get(url)
    assert antwort.status_code == 302 and antwort.url.startswith("/anmelden/")


def test_einstellungen_starten_beim_profil(konten):
    antwort = client_fuer(konten[M]).get("/einstellungen/")
    assert antwort.status_code == 302 and antwort.url == "/einstellungen/profil/"


PERSOENLICH = {"Profil", "Anmeldung &amp; Sicherheit", "Benachrichtigungen", "Darstellung", "Über"}
TEAM = {"Personen", "Ansichten &amp; Freigaben", "Rollen &amp; Rechte"}
SYSTEM = {"Allgemein", "E-Mail-Versand", "Listen", "Kalender", "Speicherplatz"}


@pytest.mark.parametrize("rolle, sichtbar", [
    (A, PERSOENLICH | TEAM | SYSTEM),
    (BL, PERSOENLICH | TEAM),
    (P, PERSOENLICH | {"Personen"}),
    (M, PERSOENLICH),
    (L, PERSOENLICH),
])
def test_unternavigation_je_rolle(konten, rolle, sichtbar):
    import re

    seite = client_fuer(konten[rolle]).get("/einstellungen/profil/").content.decode()
    beginn = seite.index('<nav class="einst-nav"')
    nav = seite[beginn:seite.index("</nav>", beginn)]
    assert set(re.findall(r'<a href="[^"]+"(?: aria-current="page")?>([^<]+)</a>', nav)) == sichtbar
    # „Verwaltung“ zeigt Einstellungen und Protokoll
    assert "Platzhalter-Personen" not in seite and "Teamplaner-Ansichten" not in seite


# --- Konten und Rollen ---

@pytest.mark.parametrize("rolle, erwartet", [(A, 302), (BL, 302), (P, 403), (M, 403), (L, 403)])
def test_person_einladen(konten, bereich_a, rolle, erwartet):
    antwort = client_fuer(konten[rolle]).post("/einstellungen/personen/einladen/", {
        "anzeigename": "Person 40", "email": "person40@example.test", "bereich": bereich_a.pk, "rolle": Rolle.MITARBEITER,
    })
    assert antwort.status_code == erwartet
    assert Konto.objects.filter(email="person40@example.test").exists() is (erwartet == 302)


def test_bereichsleitung_kann_niemanden_zum_admin_machen(konten):
    ziel = konten[M]
    antwort = client_fuer(konten[BL]).post(f"/einstellungen/personen/{ziel.pk}/", {
        "anzeigename": ziel.person.anzeigename, "email": ziel.email, "rolle": Rolle.ADMIN,
    })
    assert antwort.status_code == 200  # Formularfehler, keine Änderung
    ziel.refresh_from_db()
    assert ziel.rolle == Rolle.MITARBEITER


def test_bereichsleitung_darf_admin_konto_nicht_bearbeiten(konten):
    c = client_fuer(konten[BL])
    assert c.get(f"/einstellungen/personen/{konten[A].pk}/").status_code == 403
    assert c.post(f"/personen/{konten[A].pk}/deaktivieren/").status_code == 403
    assert konten[A].is_active


def test_rollenaenderung_wird_protokolliert(konten):
    from kern.models import Protokolleintrag

    ziel = konten[M]
    client_fuer(konten[BL]).post(f"/einstellungen/personen/{ziel.pk}/", {
        "anzeigename": ziel.person.anzeigename, "email": ziel.email, "rolle": Rolle.PLANER,
    })
    eintrag = Protokolleintrag.objects.get(objekt_typ="konto", objekt_id=ziel.pk, aktion="geaendert")
    assert eintrag.daten["rolle"] == [Rolle.MITARBEITER, Rolle.PLANER]
    assert eintrag.akteur == konten[BL].person


# --- Platzhalter, Ansichten, Einstellungen ---

@pytest.mark.parametrize("rolle, erwartet", [(BL, 302), (P, 302), (M, 403), (L, 403)])
def test_platzhalter_anlegen(konten, bereich_a, rolle, erwartet):
    antwort = client_fuer(konten[rolle]).post("/einstellungen/personen/platzhalter/", {"anzeigename": "Aushilfe 3", "bereich": bereich_a.pk})
    assert antwort.status_code == erwartet


@pytest.mark.parametrize("rolle, erwartet", [(A, 302), (BL, 302), (P, 403), (M, 403)])
def test_ansicht_anlegen(konten, bereich_a, rolle, erwartet):
    antwort = client_fuer(konten[rolle]).post("/einstellungen/ansichten/teamplaner/neu/", {
        "name": "Bereich A", "bereiche": [bereich_a.pk], "wochen": 2,
    })
    assert antwort.status_code == erwartet
    assert TeamplanerAnsicht.objects.exists() is (erwartet == 302)


@pytest.mark.parametrize("rolle, erwartet", [(A, 200), (BL, 403), (P, 403)])
def test_status_anlegen_nur_admin(konten, rolle, erwartet):
    antwort = client_fuer(konten[rolle]).post("/einstellungen/listen/status/neu/", {"neu-name": "Abgenommen"},
                                              HTTP_HX_REQUEST="true")
    assert antwort.status_code == erwartet
    assert Status.objects.filter(name="Abgenommen").exists() is (erwartet == 200)


# --- Projekte und Aufgaben ---

@pytest.mark.parametrize("rolle, erwartet", [(BL, 302), (P, 302), (M, 403), (L, 403)])
def test_projekt_anlegen(konten, rolle, erwartet):
    antwort = client_fuer(konten[rolle]).post("/projekte/neu/", {"name": "Prototyp Förderband", "farbe": "blau"})
    assert antwort.status_code == erwartet
    assert Projekt.objects.filter(name="Prototyp Förderband").exists() is (erwartet == 302)


def test_projekt_bearbeiten_nur_ab_planer(konten, projekt):
    assert client_fuer(konten[M]).post(f"/projekte/{projekt.pk}/bearbeiten/", {"name": "x", "farbe": "rot"}).status_code == 403


def feld_aendern(konto, aufgabe, feld, wert):
    return client_fuer(konto).post(f"/aufgaben/{aufgabe.pk}/feld/", {"feld": feld, "wert": wert, "version": aufgabe.version})


def test_aufgabe_bearbeiten_mitarbeiter_nur_als_mitglied(konten, aufgabe, projekt):
    datum = "2026-11-05"
    assert feld_aendern(konten[M], aufgabe, "faellig_am", datum).status_code == 403
    assert feld_aendern(konten[L], aufgabe, "faellig_am", datum).status_code == 403
    projekt.mitglieder.add(konten[M].person, konten[L].person)
    assert feld_aendern(konten[M], aufgabe, "faellig_am", datum).status_code == 200
    assert feld_aendern(konten[L], aufgabe, "faellig_am", datum).status_code == 403
    aufgabe.refresh_from_db()
    assert aufgabe.faellig_am.isoformat() == datum


@pytest.mark.parametrize("rolle, erwartet", [(P, 302), (M, 302), (L, 403)])
def test_abschliessen(konten, aufgabe, rolle, erwartet):
    antwort = client_fuer(konten[rolle]).post(f"/aufgaben/{aufgabe.pk}/erledigt/", {"erledigt": "1"})
    assert antwort.status_code == erwartet
    aufgabe.refresh_from_db()
    assert aufgabe.status.ist_erledigt is (erwartet == 302)


@pytest.mark.parametrize("rolle, erwartet", [(P, 302), (M, 302), (L, 403)])
def test_kommentieren(konten, aufgabe, rolle, erwartet):
    antwort = client_fuer(konten[rolle]).post(f"/aufgaben/{aufgabe.pk}/kommentare/", {"text": "Erledigt bis Mittwoch"})
    assert antwort.status_code == erwartet
    assert Kommentar.objects.exists() is (erwartet == 302)


def test_aufgabe_loeschen_nur_mit_bearbeitungsrecht(konten, aufgabe):
    assert client_fuer(konten[M]).post(f"/aufgaben/{aufgabe.pk}/loeschen/").status_code == 403
    assert client_fuer(konten[P]).post(f"/aufgaben/{aufgabe.pk}/loeschen/").status_code == 302
    assert not Aufgabe.objects.filter(pk=aufgabe.pk).exists()


def test_aufgabe_lesen_alle_rollen(konten, aufgabe):
    for rolle in ROLLEN:
        assert client_fuer(konten[rolle]).get(f"/aufgaben/{aufgabe.pk}/").status_code == 200


# --- Anhänge ---

def test_anhang_hochladen_und_herunterladen(konten, aufgabe, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    datei = SimpleUploadedFile("Zeichnung_Halle.pdf", b"%PDF-1.4 test", content_type="application/pdf")
    assert client_fuer(konten[L]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": datei}).status_code == 403
    datei.seek(0)
    assert client_fuer(konten[M]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": datei}).status_code == 302
    anhang = Anhang.objects.get()
    assert anhang.dateiname == "Zeichnung_Halle.pdf" and "Zeichnung" not in anhang.datei.name
    antwort = client_fuer(konten[L]).get(f"/anhaenge/{anhang.pk}/")
    assert antwort.status_code == 200 and antwort["Content-Type"] == "application/pdf"
    assert Client().get(f"/anhaenge/{anhang.pk}/").status_code == 302  # nicht angemeldet


def test_html_anhang_wird_nur_als_download_ausgeliefert(konten, aufgabe, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    datei = SimpleUploadedFile("x.html", b"<script>alert(1)</script>", content_type="text/html")
    client_fuer(konten[M]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": datei})
    antwort = client_fuer(konten[M]).get(f"/anhaenge/{Anhang.objects.get().pk}/")
    assert antwort["Content-Type"] == "application/octet-stream"
    assert "attachment" in antwort["Content-Disposition"]


def test_anhang_groessenlimit(konten, aufgabe, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    settings.TEAMPLANER_ANHANG_MAX_MB = 1
    datei = SimpleUploadedFile("gross.bin", b"0" * (1024 * 1024 + 1))
    client_fuer(konten[M]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": datei})
    assert not Anhang.objects.exists()


def test_anhang_loeschen_nur_eigene_oder_mit_bearbeitungsrecht(konten, aufgabe, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    datei = SimpleUploadedFile("foto.jpg", b"jpg", content_type="image/jpeg")
    client_fuer(konten[P]).post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"datei": datei})
    anhang = Anhang.objects.get()
    assert client_fuer(konten[M]).post(f"/anhaenge/{anhang.pk}/loeschen/").status_code == 403
    assert client_fuer(konten[P]).post(f"/anhaenge/{anhang.pk}/loeschen/").status_code == 302
    assert not Anhang.objects.exists()


def test_einteilung_im_verlauf_nur_fuer_berechtigte_sichtbar(konten, aufgabe, person_b, ansicht_a):
    from planung import dienste
    from tests.conftest import MI, MO, freigeben

    dienste.einteilung_anlegen(konten[BL], aufgabe=aufgabe, person=person_b, von=MO, bis=MI)
    freigeben(ansicht_a, konten[P])
    text_bl = client_fuer(konten[BL]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    text_p = client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert "auf Person 11" in text_bl
    assert "auf Person 11" not in text_p


def test_person_wird_nicht_geloescht_sondern_deaktiviert(konten):
    client_fuer(konten[BL]).post(f"/personen/{konten[M].pk}/deaktivieren/")
    person = Person.objects.get(pk=konten[M].pk)
    assert person.archiviert and not Konto.objects.get(pk=person.pk).is_active
