"""PDF-Anhänge zeigen die erste Seite als Vorschau (Aufgaben und Notizen): Erzeugen im getrennten Prozess mit
Grenzen, beschädigte und verschlüsselte PDFs ohne Vorschau, Rechte und Kopfzeilen der Vorschau-Adresse,
Löschen mit Anhang, Aufgabe, Notiz, Ordner und beim Aufräumen, Nachtragen mit ``pdf_vorschauen``.

Die Test-PDFs entstehen hier im Code: ``pdf_aus`` schreibt ein PDF aus einzelnen Objekten, ``bild_pdf``
eins mit einer einfarbigen Seite je Farbe (Pillow).
"""

import signal
import subprocess
import sys
from datetime import timedelta
from io import BytesIO, StringIO

import pytest
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import Client
from django.utils import timezone
from PIL import Image

from kern.models import Rolle
from notizen.models import Notiz, NotizAnhang, Ordner
from projekte import dienste
from verwaltung.aufraeumen import aufraeumen
from zusammenarbeit import pdf_vorschau
from zusammenarbeit.models import Anhang

pytestmark = pytest.mark.django_db
A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


def pdf_aus(objekte, trailer=b""):
    """PDF aus Objekten (1 = Katalog), mit richtiger Querverweistabelle."""
    teile, stellen = [b"%PDF-1.4\n"], []
    for nummer, objekt in enumerate(objekte, 1):
        stellen.append(sum(map(len, teile)))
        teile.append(b"%d 0 obj\n%s\nendobj\n" % (nummer, objekt))
    xref, anzahl = sum(map(len, teile)), len(objekte) + 1
    teile.append(b"xref\n0 %d\n0000000000 65535 f \n" % anzahl + b"".join(b"%010d 00000 n \n" % s for s in stellen))
    teile.append(b"trailer\n<< /Size %d /Root 1 0 R %s>>\nstartxref\n%d\n%%%%EOF\n" % (anzahl, trailer, xref))
    return b"".join(teile)


def hohe_seite():
    """Eine Seite 200 × 2000 pt, oben ein rotes Quadrat, sonst weiß."""
    inhalt = b"1 0 0 rg 0 1800 200 200 re f"
    return [b"<< /Type /Catalog /Pages 2 0 R >>", b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 200 2000] /Contents 4 0 R >>",
            b"<< /Length %d >>\nstream\n%s\nendstream" % (len(inhalt), inhalt)]


def verschluesselt():
    """Mit Passwort geschützt: der Schlüssel passt nicht zum leeren Passwort."""
    schutz = b"<< /Filter /Standard /V 1 /R 2 /O <%s> /U <%s> /P -4 >>" % (b"11" * 32, b"22" * 32)
    return pdf_aus([*hohe_seite(), schutz], b"/Encrypt 5 0 R /ID [<%s><%s>] " % (b"33" * 16, b"33" * 16))


def bild_pdf(*farben):
    puffer = BytesIO()
    seiten = [Image.new("RGB", (600, 800), farbe) for farbe in farben]
    seiten[0].save(puffer, "PDF", save_all=True, append_images=seiten[1:])
    return puffer.getvalue()


def bild(daten):
    with Image.open(BytesIO(daten)) as b:
        b.load()
        return b


def hochladen(client, ziel, daten, name="Plan.pdf"):
    return client.post(ziel, {"datei": SimpleUploadedFile(name, daten, content_type="application/pdf")})


@pytest.fixture
def medien(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    return tmp_path


@pytest.fixture
def ordner(konten):
    o = Ordner.objects.create(name="Bereich A intern", erstellt_von=konten[P].person)
    o.mitglieder.add(konten[P], konten[M], konten[L])
    return o


# --- Erzeugen ---

def test_mehrere_seiten_zeigt_die_erste():
    vorschau = bild(pdf_vorschau.erzeugen(bild_pdf("red", "blue", "blue")))
    assert vorschau.format == "WEBP" and vorschau.size == (480, 640)
    rot, gruen, blau = vorschau.getpixel((240, 320))
    assert rot > 200 and gruen < 60 and blau < 60


def test_eine_seite_nur_oberer_teil_und_begrenzte_groesse():
    vorschau = bild(pdf_vorschau.erzeugen(pdf_aus(hohe_seite())))
    assert vorschau.size == (pdf_vorschau.BREITE, pdf_vorschau.MAX_HOEHE)  # nicht 480 × 4800
    assert vorschau.getpixel((20, 20))[1] < 60  # oben das rote Quadrat
    assert vorschau.getpixel((20, 700)) == (255, 255, 255)


@pytest.mark.parametrize("daten", [b"%PDF-1.4 test", bild_pdf("red")[:300], b"", verschluesselt()],
                         ids=["kaputt", "abgeschnitten", "leer", "verschluesselt"])
def test_beschaedigt_oder_verschluesselt_ohne_vorschau(daten):
    assert pdf_vorschau.erzeugen(daten) is None


def test_zeitgrenze(monkeypatch):
    monkeypatch.setattr(pdf_vorschau, "ZEIT_SEKUNDEN", 0.01)
    assert pdf_vorschau.erzeugen(bild_pdf("red")) is None


def test_speichergrenze(monkeypatch):
    monkeypatch.setattr(pdf_vorschau, "SPEICHER_MB", 16)
    assert pdf_vorschau.erzeugen(bild_pdf("red")) is None


def test_rechenzeit_wird_im_kindprozess_begrenzt():
    """Grenze für die Rechenzeit: der Prozess endet durch SIGXCPU, auch ohne Zeitgrenze der Anwendung."""
    code = ("import importlib.util as u, sys; s = u.spec_from_file_location('p', sys.argv[1]); "
            "m = u.module_from_spec(s); s.loader.exec_module(m); m.grenzen_setzen(1, 256)\nwhile True: pass")
    ergebnis = subprocess.run([sys.executable, "-I", "-c", code, str(pdf_vorschau.PROZESS)], timeout=30, check=False)
    assert ergebnis.returncode in (-signal.SIGXCPU, -signal.SIGKILL)


def test_unerwartete_ausgabe_wird_verworfen(monkeypatch):
    monkeypatch.setattr(pdf_vorschau, "_befehl", lambda: [sys.executable, "-I", "-c", "print('<svg>')"])
    assert pdf_vorschau.erzeugen(bild_pdf("red")) is None


def test_prozess_fehlt(monkeypatch):
    monkeypatch.setattr(pdf_vorschau, "_befehl", lambda: ["/gibt/es/nicht"])
    assert pdf_vorschau.erzeugen(bild_pdf("red")) is None


# --- Hochladen und Anzeigen ---

def test_aufgabe_pdf_mit_vorschau(konten, aufgabe, medien):
    c = client_fuer(konten[M])
    assert hochladen(c, f"/aufgaben/{aufgabe.pk}/anhaenge/", bild_pdf("red", "blue")).status_code == 302
    anhang = Anhang.objects.get()
    assert anhang.content_type == "application/pdf" and anhang.vorschau.name.endswith(".webp")
    assert anhang.vorschau.name.startswith("anhaenge/vorschau/")
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert f'<img src="/anhaenge/{anhang.pk}/vorschau/"' in seite and "anhang-kachel--pdf" in seite
    assert f'href="/anhaenge/{anhang.pk}/" target="_blank"' in seite  # Klick öffnet das PDF
    antwort = client_fuer(konten[L]).get(f"/anhaenge/{anhang.pk}/vorschau/")
    assert antwort.status_code == 200 and antwort["Content-Type"] == "image/webp"
    assert antwort["X-Content-Type-Options"] == "nosniff" and antwort["Cache-Control"] == "private"
    assert antwort["Content-Security-Policy"].startswith("default-src 'none'")
    assert bild(b"".join(antwort.streaming_content)).size == (480, 640)
    pdf = c.get(f"/anhaenge/{anhang.pk}/")
    assert pdf["Content-Type"] == "application/pdf" and pdf["Cache-Control"] == "private"


def test_aufgabe_in_der_seitenleiste(konten, aufgabe, medien):
    c = client_fuer(konten[M])
    hochladen(c, f"/aufgaben/{aufgabe.pk}/anhaenge/", bild_pdf("red"))
    anhang = Anhang.objects.get()
    leiste = c.get(f"/projekte/{aufgabe.projekt_id}/?aufgabe={aufgabe.pk}").content.decode()
    assert f'<img src="/anhaenge/{anhang.pk}/vorschau/"' in leiste


@pytest.mark.parametrize("daten, name", [(b"%PDF-1.4 test", "kaputt.pdf"), (verschluesselt(), "geheim.pdf"),
                                         (b"kein pdf", "falsch.pdf")])
def test_ohne_vorschau_trotzdem_gespeichert(konten, aufgabe, medien, daten, name):
    c = client_fuer(konten[M])
    assert hochladen(c, f"/aufgaben/{aufgabe.pk}/anhaenge/", daten, name).status_code == 302
    anhang = Anhang.objects.get()
    assert anhang.dateiname == name and not anhang.vorschau
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert "anhang-kachel__endung" in seite and "/vorschau/" not in seite  # Symbol mit Endung
    assert c.get(f"/anhaenge/{anhang.pk}/vorschau/").status_code == 404


def test_zeitgrenze_beim_hochladen(konten, aufgabe, medien, monkeypatch):
    monkeypatch.setattr(pdf_vorschau, "ZEIT_SEKUNDEN", 0.01)
    assert hochladen(client_fuer(konten[M]), f"/aufgaben/{aufgabe.pk}/anhaenge/", bild_pdf("red")).status_code == 302
    assert not Anhang.objects.get().vorschau


def test_nur_was_der_server_als_pdf_erkennt(konten, aufgabe, medien):
    puffer = BytesIO()
    Image.new("RGB", (4, 4)).save(puffer, "PNG")
    c = client_fuer(konten[M])
    hochladen(c, f"/aufgaben/{aufgabe.pk}/anhaenge/", puffer.getvalue(), "foto.pdf")  # Angabe des Browsers: PDF
    anhang = Anhang.objects.get()
    assert anhang.content_type == "image/png" and not anhang.vorschau


def test_vorschau_rechte_aufgabe(konten, aufgabe, medien):
    hochladen(client_fuer(konten[M]), f"/aufgaben/{aufgabe.pk}/anhaenge/", bild_pdf("red"))
    pk = Anhang.objects.get().pk
    for rolle in (A, BL, P, M, L):
        assert client_fuer(konten[rolle]).get(f"/anhaenge/{pk}/vorschau/").status_code == 200
    assert Client().get(f"/anhaenge/{pk}/vorschau/").status_code == 302  # nicht angemeldet
    assert client_fuer(konten[M]).get(f"/anhaenge/{pk + 1}/vorschau/").status_code == 404


def test_notiz_pdf_mit_vorschau_und_rechten(konten, ordner, medien):
    notiz = Notiz.objects.create(ordner=ordner, titel="Pläne", text="")
    assert hochladen(client_fuer(konten[L]), f"/notizen/{notiz.pk}/anhaenge/", bild_pdf("red")).status_code == 403
    assert hochladen(client_fuer(konten[M]), f"/notizen/{notiz.pk}/anhaenge/", bild_pdf("red")).status_code == 302
    anhang = NotizAnhang.objects.get()
    assert anhang.vorschau.name.startswith("notizen/vorschau/")
    seite = client_fuer(konten[L]).get(f"/notizen/{notiz.pk}/").content.decode()
    assert f'<img src="/notizen/anhaenge/{anhang.pk}/vorschau/"' in seite
    adresse = f"/notizen/anhaenge/{anhang.pk}/vorschau/"
    antwort = client_fuer(konten[L]).get(adresse)
    assert antwort.status_code == 200 and antwort["Content-Type"] == "image/webp"
    assert antwort["X-Content-Type-Options"] == "nosniff" and antwort["Cache-Control"] == "private"
    assert client_fuer(konten[A]).get(adresse).status_code == 200  # Admin sieht alle Gruppenordner
    assert client_fuer(konten[BL]).get(adresse).status_code == 403  # Ordner nicht freigegeben
    assert Client().get(adresse).status_code == 302


def test_persoenliche_notiz_vorschau_nur_fuer_besitzer(konten, medien):
    notiz = Notiz.objects.create(besitzer=konten[M].person, titel="Privat", text="")
    hochladen(client_fuer(konten[M]), f"/notizen/{notiz.pk}/anhaenge/", bild_pdf("red"))
    adresse = f"/notizen/anhaenge/{NotizAnhang.objects.get().pk}/vorschau/"
    assert client_fuer(konten[M]).get(adresse).status_code == 200
    for rolle in (A, BL, P, L):
        assert client_fuer(konten[rolle]).get(adresse).status_code == 403


# --- Löschen ---

def dateien(medien):
    return sorted(p.suffix for p in medien.rglob("*") if p.is_file())


def test_loeschen_mit_anhang(konten, aufgabe, medien, django_capture_on_commit_callbacks):
    c = client_fuer(konten[M])
    hochladen(c, f"/aufgaben/{aufgabe.pk}/anhaenge/", bild_pdf("red"))
    assert dateien(medien) == [".pdf", ".webp"]
    with django_capture_on_commit_callbacks(execute=True):
        assert c.post(f"/anhaenge/{Anhang.objects.get().pk}/loeschen/").status_code == 302
    assert dateien(medien) == []


def test_loeschen_in_der_speicherverwaltung(konten, aufgabe, medien, django_capture_on_commit_callbacks):
    hochladen(client_fuer(konten[M]), f"/aufgaben/{aufgabe.pk}/anhaenge/", bild_pdf("red"))
    with django_capture_on_commit_callbacks(execute=True):
        antwort = client_fuer(konten[A]).post(f"/einstellungen/speicherplatz/{Anhang.objects.get().pk}/loeschen/")
    assert antwort.status_code == 302 and not Anhang.objects.exists() and dateien(medien) == []


def test_loeschen_mit_aufgabe(konten, aufgabe, medien, django_capture_on_commit_callbacks):
    hochladen(client_fuer(konten[M]), f"/aufgaben/{aufgabe.pk}/anhaenge/", bild_pdf("red"))
    with django_capture_on_commit_callbacks(execute=True):
        dienste.aufgabe_loeschen(konten[P], aufgabe)
    assert not Anhang.objects.exists() and dateien(medien) == []


def test_zurueckgerollt_bleiben_die_dateien(konten, aufgabe, medien, django_capture_on_commit_callbacks):
    from django.db import transaction

    hochladen(client_fuer(konten[M]), f"/aufgaben/{aufgabe.pk}/anhaenge/", bild_pdf("red"))
    with django_capture_on_commit_callbacks(execute=True) as rueckrufe:
        try:
            with transaction.atomic():
                Anhang.objects.get().delete()
                raise RuntimeError
        except RuntimeError:
            pass
    assert rueckrufe == [] and dateien(medien) == [".pdf", ".webp"]


def test_loeschen_mit_notiz_und_ordner(konten, ordner, medien, django_capture_on_commit_callbacks):
    c = client_fuer(konten[P])
    erste = Notiz.objects.create(ordner=ordner, titel="Eins", text="")
    zweite = Notiz.objects.create(ordner=ordner, titel="Zwei", text="")
    for notiz in (erste, zweite):
        hochladen(c, f"/notizen/{notiz.pk}/anhaenge/", bild_pdf("red"))
    assert dateien(medien) == [".pdf", ".pdf", ".webp", ".webp"]
    with django_capture_on_commit_callbacks(execute=True):
        assert c.post(f"/notizen/{erste.pk}/loeschen/").status_code == 302
    assert dateien(medien) == [".pdf", ".webp"]
    with django_capture_on_commit_callbacks(execute=True):
        assert c.post(f"/notizen/ordner/{ordner.pk}/loeschen/").status_code == 302
    assert not NotizAnhang.objects.exists() and dateien(medien) == []


def test_loeschen_beim_aufraeumen(konten, medien, settings, django_capture_on_commit_callbacks):
    konto = konten[M]
    notiz = Notiz.objects.create(besitzer=konto.person, titel="Privat", text="")
    hochladen(client_fuer(konto), f"/notizen/{notiz.pk}/anhaenge/", bild_pdf("red"))
    assert dateien(medien) == [".pdf", ".webp"]
    konto.person.archiviert_am = timezone.now() - timedelta(days=settings.TEAMPLANER_DEAKTIVIERT_TAGE + 1)
    konto.person.save()
    with django_capture_on_commit_callbacks(execute=True):
        assert aufraeumen()["deaktivierte_konten"] == 1
    assert not NotizAnhang.objects.exists() and dateien(medien) == []


# --- Nachtragen ---

def test_nachtragen(konten, aufgabe, ordner, medien):
    person = konten[M].person
    alt = Anhang.objects.create(aufgabe=aufgabe, datei=ContentFile(bild_pdf("red"), name="alt.pdf"),
                                dateiname="alt.pdf", groesse=1, content_type="application/pdf", hochgeladen_von=person)
    kaputt = Anhang.objects.create(aufgabe=aufgabe, datei=ContentFile(b"%PDF-1.4 x", name="kaputt.pdf"),
                                   dateiname="kaputt.pdf", groesse=1, content_type="application/pdf", hochgeladen_von=person)
    text = Anhang.objects.create(aufgabe=aufgabe, datei=ContentFile(b"Hallo", name="a.txt"), dateiname="a.txt",
                                 groesse=1, content_type="text/plain", hochgeladen_von=person)
    notiz = Notiz.objects.create(ordner=ordner, titel="Alt", text="")
    notiz_alt = NotizAnhang.objects.create(notiz=notiz, datei=ContentFile(bild_pdf("blue"), name="n.pdf"), dateiname="n.pdf",
                                           groesse=1, content_type="application/pdf", hochgeladen_von=person)
    ausgabe = StringIO()
    call_command("pdf_vorschauen", stdout=ausgabe)
    assert "Aufgaben: 1 Vorschauen erzeugt, 1 PDFs ohne Vorschau" in ausgabe.getvalue()
    assert "Notizen: 1 Vorschauen erzeugt, 0 PDFs ohne Vorschau" in ausgabe.getvalue()
    for anhang in (alt, kaputt, text, notiz_alt):
        anhang.refresh_from_db()
    assert alt.vorschau and notiz_alt.vorschau and not kaputt.vorschau and not text.vorschau
    assert client_fuer(konten[L]).get(f"/anhaenge/{alt.pk}/vorschau/").status_code == 200

    # Ein zweiter Lauf lässt vorhandene Vorschauen stehen, --neu ersetzt sie (die alte Datei verschwindet)
    vorher = alt.vorschau.name
    ausgabe = StringIO()
    call_command("pdf_vorschauen", stdout=ausgabe)
    assert "Aufgaben: 0 Vorschauen erzeugt, 1 PDFs ohne Vorschau" in ausgabe.getvalue()
    call_command("pdf_vorschauen", "--neu", stdout=StringIO())
    alt.refresh_from_db()
    assert alt.vorschau.name != vorher and not (medien / vorher).exists() and (medien / alt.vorschau.name).exists()
