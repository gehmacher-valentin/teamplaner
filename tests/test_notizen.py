"""Notizen: persönliche Notizen nur für die eigene Person, Gruppenordner nur für Freigegebene."""

import pytest
from django.test import Client

from kern.hilfen import TEXT_MAX_ZEICHEN
from kern.models import Rolle
from notizen import markdown
from notizen.markdown import als_html, als_text
from notizen.models import Notiz, Ordner

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


@pytest.fixture
def ordner(konten):
    o = Ordner.objects.create(name="Bereich A intern", erstellt_von=konten[P].person)
    o.mitglieder.add(konten[P], konten[M], konten[L])
    return o


def speichern(client, **daten):
    return client.post("/notizen/speichern/", {"notiz": "", "ordner": "", "version": "", **daten}, HTTP_HX_REQUEST="true")


def test_persoenliche_notiz_sieht_nur_besitzer(konten):
    c = client_fuer(konten[M])
    antwort = speichern(c, titel="Einkauf", text="- Schrauben\n- **Kleber**")
    notiz = Notiz.objects.get()
    assert antwort.status_code == 200 and notiz.besitzer == konten[M].person and notiz.ordner is None
    assert antwort["HX-Replace-Url"] == f"/notizen/{notiz.pk}/"
    seite = c.get(f"/notizen/{notiz.pk}/").content.decode()
    assert "- **Kleber**</textarea>" in seite and 'data-format="markdown"' in seite  # im Editor als Markdown
    for rolle in (A, BL, P, L):
        assert client_fuer(konten[rolle]).get(f"/notizen/{notiz.pk}/").status_code == 403
        assert "Einkauf" not in client_fuer(konten[rolle]).get("/notizen/").content.decode()


def test_gruppenordner_nur_fuer_freigegebene(konten, ordner):
    notiz = Notiz.objects.create(ordner=ordner, titel="Aufzugsprüfung", text="Termin offen")
    for rolle in (P, M, L):
        assert client_fuer(konten[rolle]).get(f"/notizen/ordner/{ordner.pk}/").status_code == 200
        assert client_fuer(konten[rolle]).get(f"/notizen/{notiz.pk}/").status_code == 200
    # nicht freigegeben – die Bereichsleitung sieht ihn nicht
    assert client_fuer(konten[BL]).get(f"/notizen/ordner/{ordner.pk}/").status_code == 403
    assert client_fuer(konten[BL]).get(f"/notizen/{notiz.pk}/").status_code == 403
    # Admins sehen alle Gruppenordner (als Systemkonto stehen sie in keiner Mitgliederauswahl)
    assert client_fuer(konten[A]).get(f"/notizen/ordner/{ordner.pk}/").status_code == 200
    assert "Bereich A intern" in client_fuer(konten[A]).get("/notizen/").content.decode()


def test_schreiben_ab_mitarbeiter(konten, ordner):
    assert speichern(client_fuer(konten[M]), ordner=ordner.pk, titel="A", text="").status_code == 200
    assert speichern(client_fuer(konten[L]), ordner=ordner.pk, titel="B", text="").status_code == 403
    assert list(ordner.notizen.values_list("titel", flat=True)) == ["A"]
    notiz = ordner.notizen.get()
    antwort = speichern(client_fuer(konten[L]), notiz=notiz.pk, version=notiz.version, titel="A", text="geändert")
    assert antwort.status_code == 403
    # Lesend sieht nur die Anzeige, ohne Eingabefelder und Editor
    seite = client_fuer(konten[L]).get(f"/notizen/{notiz.pk}/").content.decode()
    assert 'id="notiz-titel-eingabe"' not in seite and "data-editor" not in seite
    assert client_fuer(konten[L]).get(f"/notizen/neu/?ordner={ordner.pk}").status_code == 403



def ordnerspalte(client, adresse):
    return client.get(adresse).content.decode().split("data-notizbaum", 1)[1].split("</nav>", 1)[0]


def test_ordnerspalte_als_baum_nur_mit_sichtbaren_notizen(konten, ordner):
    """Die Spalte zeigt die Titel aller Notizen je Ordner – aber nur, was man öffnen darf."""
    Notiz.objects.create(besitzer=konten[A].person, titel="Zettel Admin")
    Notiz.objects.create(besitzer=konten[M].person, titel="Geheim Mitarbeiter")
    gruppe_b = Notiz.objects.create(ordner=ordner, titel="b Bericht")
    Notiz.objects.create(ordner=ordner, titel="A Ablage")
    gesperrt = Ordner.objects.create(name="Nur Bereichsleitung", erstellt_von=konten[BL].person)
    gesperrt.mitglieder.add(konten[BL])
    Notiz.objects.create(ordner=gesperrt, titel="Personalplanung")

    spalte = ordnerspalte(client_fuer(konten[P]), f"/notizen/{gruppe_b.pk}/")
    assert "Geheim Mitarbeiter" not in spalte and "Zettel Admin" not in spalte and "Personalplanung" not in spalte
    assert spalte.index("A Ablage") < spalte.index("b Bericht")  # alphabetisch, unabhängig von Groß/klein
    assert f'href="/notizen/{gruppe_b.pk}/" aria-current="page"' in spalte
    assert f'aria-controls="notizbaum-{ordner.pk}"' in spalte
    # aufgeklappt ist der Ordner der geöffneten Notiz, nicht die persönlichen Notizen
    assert f'aria-expanded="true" aria-controls="notizbaum-{ordner.pk}"' in spalte
    assert 'aria-expanded="false" aria-controls="notizbaum-persoenlich"' in spalte

    # Admin sieht alle Gruppenordner, aber keine fremden persönlichen Notizen
    spalte = ordnerspalte(client_fuer(konten[A]), "/notizen/")
    assert "Zettel Admin" in spalte and "Personalplanung" in spalte and "A Ablage" in spalte
    assert "Geheim Mitarbeiter" not in spalte
    # leerer Ordner
    leer = ordnerspalte(client_fuer(konten[BL]), "/notizen/")
    assert "Noch keine Notizen." in leer.split('id="notizbaum-persoenlich"', 1)[1].split("</ul>", 1)[0]


def test_ordnerspalte_nach_dem_speichern_aktuell(konten, ordner):
    """Neuer oder geänderter Titel erscheint nach dem Speichern in der Spalte (hx-swap-oob)."""
    c = client_fuer(konten[M])
    antwort = speichern(c, ordner=ordner.pk, titel="Neue Notiz im Ordner", text="").content.decode()
    notiz = ordner.notizen.get()
    assert f'id="notizbaum-{ordner.pk}" class="notiz-ordner__notizen" hx-swap-oob="true"' in antwort
    assert f'href="/notizen/{notiz.pk}/" aria-current="page"><span class="zelle-text">Neue Notiz im Ordner' in antwort
    antwort = speichern(c, notiz=notiz.pk, version=notiz.version, titel="Umbenannt", text="").content.decode()
    assert "Umbenannt" in antwort and 'id="notizbaum-persoenlich"' not in antwort


def test_ordner_verwalten_ab_planer(konten, ordner):
    assert client_fuer(konten[M]).get("/notizen/ordner/neu/").status_code == 403
    assert client_fuer(konten[M]).get(f"/notizen/ordner/{ordner.pk}/bearbeiten/").status_code == 403
    # Planer:in legt an; das eigene Konto ist vorausgewählt
    antwort = client_fuer(konten[P]).post("/notizen/ordner/neu/", {"name": "Firma", "mitglieder": [konten[P].pk, konten[BL].pk]})
    neu = Ordner.objects.get(name="Firma")
    assert antwort.status_code == 302 and set(neu.mitglieder.all()) == {konten[P], konten[BL]}
    assert client_fuer(konten[P]).post(f"/notizen/ordner/{ordner.pk}/loeschen/").status_code == 302
    assert not Ordner.objects.filter(pk=ordner.pk).exists()


def test_gleichzeitig_bearbeitet(konten, ordner):
    notiz = Notiz.objects.create(ordner=ordner, titel="Liste", text="alt")
    c = client_fuer(konten[M])
    # Mehrmals hintereinander mit der jeweils neuen Version: kein falscher Konflikt
    assert speichern(c, notiz=notiz.pk, version=1, titel="Liste", text="neu").status_code == 200
    antwort = speichern(c, notiz=notiz.pk, version=2, titel="Liste", text="neuer")
    assert 'name="version" value="3"' in antwort.content.decode()  # Version für das nächste Speichern
    # Die andere Person speichert mit veralteter Version: nichts wird überschrieben, Hinweis mit aktueller Fassung
    antwort = speichern(client_fuer(konten[P]), notiz=notiz.pk, version=1, titel="Liste", text="veraltet")
    inhalt = antwort.content.decode()
    assert antwort.status_code == 200 and antwort["HX-Retarget"] == "#notiz-konflikt" and "inzwischen" in inhalt
    assert "neuer" in inhalt and 'hx-vals=\'{"version": "3"}\'' in inhalt  # „Meine Fassung speichern“
    notiz.refresh_from_db()
    assert notiz.text == "neuer" and notiz.version == 3


def test_titel_ist_pflicht_und_alte_bearbeiten_seite_leitet_weiter(konten, ordner):
    notiz = Notiz.objects.create(ordner=ordner, titel="Liste", text="alt")
    c = client_fuer(konten[M])
    antwort = speichern(c, notiz=notiz.pk, version=1, titel="  ", text="neu")
    assert antwort["HX-Retarget"] == "#notiz-titel" and "Titel" in antwort.content.decode()
    notiz.refresh_from_db()
    assert (notiz.titel, notiz.text, notiz.version) == ("Liste", "alt", 1)
    # Neue Notiz ohne Titel: es bleibt keine leere Notiz zurück
    speichern(c, ordner=ordner.pk, titel="", text="nur Text")
    assert ordner.notizen.count() == 1
    assert c.get(f"/notizen/neu/?ordner={ordner.pk}").status_code == 200


def test_markdown_ohne_html_und_skripte():
    html = als_html("# Titel\n<script>alert(1)</script>\n[x](javascript:alert(1)) *k* <b onclick=\"x()\">b</b>")
    assert "<h1>Titel</h1>" in html and "<em>k</em>" in html
    assert "<script" not in html and "javascript:" not in html and "onclick" not in html


def test_markdown_aus_dem_editor():
    """So schreibt der Editor: Umbruch als „  \\n“, Tilde maskiert, Tabellen als Pipes."""
    html = als_html("## Messung\n\nca. \\~5 cm  \nzweite Zeile\n\n| A   | B   |\n| --- | --- |\n| 1   | 2   |")
    assert "<h2>Messung</h2>" in html and "ca. ~5 cm<br" in html and "\\" not in html
    assert html.count("<br") == 1 and "<table>" in html and "<td>1</td>" in html


def test_vorschau_ohne_markdown_zeichen():
    assert als_text("## Themen\n1. Boden **fertig**\n2. Material\n\n> Montag 8:00") == \
        "Themen · Boden fertig · Material · Montag 8:00"
    assert als_text("| Person | Termin |\n| --- | --- |\n| Person 01 | Di 9:00 |") == "Person Termin · Person 01 Di 9:00"
    assert als_text("A & B <script>x</script>") == "A & B"


def test_anhaenge_an_notizen(konten, ordner, settings, tmp_path):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from notizen.models import NotizAnhang

    settings.MEDIA_ROOT = tmp_path
    notiz = Notiz.objects.create(ordner=ordner, titel="Fotos Halle", text="")
    from io import BytesIO

    from PIL import Image

    puffer = BytesIO()
    Image.new("RGB", (4, 4)).save(puffer, "JPEG")  # echtes Bild: die Vorschau prüft die Dateibytes
    bild = SimpleUploadedFile("halle.jpg", puffer.getvalue(), content_type="image/jpeg")
    assert client_fuer(konten[L]).post(f"/notizen/{notiz.pk}/anhaenge/", {"datei": bild}).status_code == 403  # nur lesen
    bild.seek(0)
    assert client_fuer(konten[M]).post(f"/notizen/{notiz.pk}/anhaenge/", {"datei": bild}).status_code == 302
    anhang = NotizAnhang.objects.get()
    seite = client_fuer(konten[L]).get(f"/notizen/{notiz.pk}/").content.decode()
    assert f'<img src="/notizen/anhaenge/{anhang.pk}/"' in seite and 'target="_blank"' in seite
    assert client_fuer(konten[L]).get(f"/notizen/anhaenge/{anhang.pk}/").status_code == 200
    assert client_fuer(konten[BL]).get(f"/notizen/anhaenge/{anhang.pk}/").status_code == 403  # Ordner nicht freigegeben
    assert client_fuer(konten[A]).get(f"/notizen/anhaenge/{anhang.pk}/").status_code == 200  # Admin sieht alle Gruppenordner
    assert client_fuer(konten[L]).post(f"/notizen/anhaenge/{anhang.pk}/loeschen/").status_code == 403
    assert client_fuer(konten[M]).post(f"/notizen/{notiz.pk}/loeschen/").status_code == 302
    assert not NotizAnhang.objects.exists() and not list(tmp_path.rglob("*.jpg"))


def test_beispiel_notizen(konten, settings):
    from django.core.management import call_command

    settings.TEAMPLANER_DEMO = True
    call_command("demodaten", "--notizen", verbosity=0)
    assert Notiz.objects.filter(besitzer=konten[P].person).exists()  # Person 05
    assert Ordner.objects.filter(mitglieder=konten[A]).exists()  # Person 90 in der Leitungsrunde


def test_zu_langer_text_wird_abgelehnt(konten):
    c = client_fuer(konten[M])
    assert speichern(c, titel="Lang", text="a" * (TEXT_MAX_ZEICHEN + 1)).status_code == 400
    assert not Notiz.objects.exists()
    assert speichern(c, titel="Lang", text="a" * TEXT_MAX_ZEICHEN).status_code == 200


@pytest.mark.parametrize("muster", ["[" * 30000, "`" * 30000, "<a " * 20000, "-\n" * 40000, "a\n: b\n" * 1000])
def test_aufwendiges_markdown_bricht_nach_frist_ab(muster):
    """Python-Markdown braucht für solche Texte viele Sekunden bis Minuten; dann erscheint der Text unformatiert."""
    import time

    beginn = time.monotonic()
    ausgabe = als_html(muster)
    assert time.monotonic() - beginn < markdown.FRIST_ANZEIGE + 1.5
    assert ausgabe.startswith("<p>") and "<a " not in ausgabe
    beginn = time.monotonic()
    als_text(muster)  # Vorschau: nur der Anfang, also schnell
    assert time.monotonic() - beginn < 1


def test_frist_stoert_gewoehnliche_notizen_nicht():
    text = "# Titel\n\nAbsatz mit **fett** und [Link](https://example.org).\n\n- eins\n- zwei\n\n" * 300
    assert als_html(text).count("<h1>") == 300
    assert als_text(text).startswith("Titel · Absatz mit fett und Link. · eins · zwei")
