"""Aufgabendetail als Seitenleiste neben der Projektliste."""

import json
import re

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from kern.models import Rolle
from projekte.models import Aufgabe, Projekt, Status
from zusammenarbeit.models import Anhang, Kommentar

pytestmark = pytest.mark.django_db
A, P, M, L = Rolle.ADMIN, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND
HX = {"HTTP_HX_REQUEST": "true"}


def unteraufgabe(aufgabe, titel="Unteraufgabe"):
    return Aufgabe.objects.create(projekt=aufgabe.projekt, abschnitt=aufgabe.abschnitt, eltern=aufgabe, titel=titel,
                                  status=aufgabe.status)


def leiste(client, aufgabe):
    return client.get(f"/aufgaben/{aufgabe.pk}/?seitenleiste=1", **HX)


def senden(client, url, aufgabe, **daten):
    return client.post(url, {"seitenleiste": aufgabe.pk, **daten}, **HX)


def version_in_zeile(html, aufgabe):
    zeile = html[html.index(f'id="aufgabe-{aufgabe.pk}"'):]
    return int(re.search(r'name="version" value="(\d+)"', zeile).group(1))


# --- Laden ---

def test_seitenleiste_liefert_nur_den_teil(client_fuer, konten, aufgabe):
    antwort = leiste(client_fuer(konten[P]), aufgabe)
    html = antwort.content.decode()
    assert antwort.status_code == 200
    assert 'id="seitenleiste-inhalt"' in html and 'id="aufgabe-felder"' in html
    assert "<html" not in html
    assert "Vollansicht" in html and f'href="/aufgaben/{aufgabe.pk}/"' in html


def test_ohne_htmx_bleibt_es_die_ganze_seite(client_fuer, konten, aufgabe):
    html = client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/?seitenleiste=1").content.decode()
    assert "<html" in html and 'id="seitenleiste-inhalt"' not in html


def test_detailseite_bleibt_ohne_htmx_formulare(client_fuer, konten, aufgabe):
    html = client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert f'action="/aufgaben/{aufgabe.pk}/kommentare/"' in html
    assert 'hx-target="#seitenleiste-inhalt"' not in html and "data-aufgabe-link" not in html


def test_projektseite_rendert_seitenleiste_mit(client_fuer, konten, aufgabe):
    html = client_fuer(konten[P]).get(f"/projekte/{aufgabe.projekt_id}/?aufgabe={aufgabe.pk}&status=alle").content.decode()
    assert f'data-seitenleiste-aufgabe="{aufgabe.pk}"' in html
    assert 'class="projekt-raster projekt-raster--offen"' in html
    assert f'id="filter-aufgabe" name="aufgabe" value="{aufgabe.pk}"' in html


def test_projektseite_ohne_aufgabe_hat_leere_seitenleiste(client_fuer, konten, aufgabe):
    html = client_fuer(konten[P]).get(f"/projekte/{aufgabe.projekt_id}/").content.decode()
    assert 'id="seitenleiste-inhalt"' not in html
    assert re.search(r'<aside id="seitenleiste"[^>]* hidden>', html)


@pytest.mark.parametrize("wert", ["abc", "999999", ""])
def test_ungueltige_aufgabe_wird_ignoriert(client_fuer, konten, aufgabe, wert):
    antwort = client_fuer(konten[P]).get(f"/projekte/{aufgabe.projekt_id}/?aufgabe={wert}")
    assert antwort.status_code == 200 and 'id="seitenleiste-inhalt"' not in antwort.content.decode()


def test_aufgabe_eines_anderen_projekts_wird_ignoriert(client_fuer, konten, aufgabe):
    anderes = Projekt.objects.create(name="Anderes Projekt")
    html = client_fuer(konten[P]).get(f"/projekte/{anderes.pk}/?aufgabe={aufgabe.pk}").content.decode()
    assert 'id="seitenleiste-inhalt"' not in html


def test_aufgaben_anderer_projekte_oeffnen_als_seite(client_fuer, konten, aufgabe):
    from projekte.models import Abhaengigkeit

    anderes = Projekt.objects.create(name="Anderes Projekt")
    fremd = Aufgabe.objects.create(projekt=anderes, titel="Fremd", status=aufgabe.status)
    gleich = Aufgabe.objects.create(projekt=aufgabe.projekt, titel="Gleich", status=aufgabe.status)
    Abhaengigkeit.objects.create(vorher=fremd, nachher=aufgabe)
    Abhaengigkeit.objects.create(vorher=aufgabe, nachher=gleich)
    html = leiste(client_fuer(konten[P]), aufgabe).content.decode()
    assert f'data-aufgabe-link="{gleich.pk}"' in html
    assert f'data-aufgabe-link="{fremd.pk}"' not in html


# --- Rechte ---

def test_lesend_sieht_seitenleiste_ohne_bearbeitungsfelder(client_fuer, konten, aufgabe):
    html = leiste(client_fuer(konten[L]), aufgabe).content.decode()
    assert 'id="seitenleiste-inhalt"' in html and aufgabe.titel in html
    assert "hx-post" not in html and 'name="wert"' not in html


def test_ohne_anmeldung_keine_seitenleiste(client, aufgabe):
    antwort = client.get(f"/aufgaben/{aufgabe.pk}/?seitenleiste=1", **HX)
    assert antwort.status_code == 204 and antwort["HX-Refresh"] == "true"


@pytest.mark.parametrize("pfad, daten", [
    ("feld/", {"ansicht": "detail", "feld": "titel", "wert": "Neu", "version": 1}),
    ("loeschen/", {}),
    ("erledigt/", {"erledigt": "1"}),
])
def test_lesend_darf_aus_der_seitenleiste_nichts_aendern(client_fuer, konten, aufgabe, pfad, daten):
    antwort = senden(client_fuer(konten[L]), f"/aufgaben/{aufgabe.pk}/{pfad}", aufgabe, **daten)
    assert antwort.status_code == 403
    assert Aufgabe.objects.get(pk=aufgabe.pk).titel == aufgabe.titel


# --- Zeile und Seitenleiste synchron ---

def test_feld_aus_der_seitenleiste_liefert_zeile_mit_neuer_version(client_fuer, konten, aufgabe):
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/feld/", aufgabe, ansicht="detail", feld="titel",
                     wert="Neuer Titel", version=aufgabe.version)
    html = antwort.content.decode()
    neu = Aufgabe.objects.get(pk=aufgabe.pk)
    assert neu.titel == "Neuer Titel" and neu.version == aufgabe.version + 1
    assert f'id="aufgabe-{aufgabe.pk}" hx-swap-oob="true"' in html
    assert version_in_zeile(html, aufgabe) == neu.version


def test_beschreibung_tauscht_den_editor_nicht_aber_die_zeile(client_fuer, konten, aufgabe):
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/feld/", aufgabe, ansicht="detail",
                     feld="beschreibung", wert="<p>Text</p>", version=aufgabe.version)
    assert antwort["HX-Reswap"] == "none"
    assert f'id="aufgabe-{aufgabe.pk}" hx-swap-oob="true"' in antwort.content.decode()


def test_konflikt_aus_der_seitenleiste_zieht_die_zeile_nach(client_fuer, konten, aufgabe):
    Aufgabe.objects.filter(pk=aufgabe.pk).update(version=aufgabe.version + 3)
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/feld/", aufgabe, ansicht="detail", feld="titel",
                     wert="Neu", version=aufgabe.version)
    html = antwort.content.decode()
    assert "Inzwischen von jemand anderem geändert" in html
    assert version_in_zeile(html, aufgabe) == aufgabe.version + 3
    assert Aufgabe.objects.get(pk=aufgabe.pk).titel == aufgabe.titel


def test_feld_von_der_detailseite_liefert_keine_zeile(client_fuer, konten, aufgabe):
    antwort = client_fuer(konten[P]).post(f"/aufgaben/{aufgabe.pk}/feld/", {
        "ansicht": "detail", "feld": "titel", "wert": "Neu", "version": aufgabe.version}, **HX)
    assert f'id="aufgabe-{aufgabe.pk}"' not in antwort.content.decode()


def test_aenderung_in_der_zeile_meldet_sich_bei_der_seitenleiste(client_fuer, konten, aufgabe):
    haupt = Aufgabe.objects.create(projekt=aufgabe.projekt, titel="Haupt", status=aufgabe.status)
    unter = unteraufgabe(haupt)
    antwort = client_fuer(konten[P]).post(f"/aufgaben/{unter.pk}/feld/", {
        "feld": "faellig_am", "wert": "2026-11-20", "version": unter.version}, **HX)
    assert json.loads(antwort["HX-Trigger-After-Settle"]) == {"aufgabe-geaendert": {"ids": [unter.pk, haupt.pk]}}


def test_haken_in_der_zeile_meldet_sich_samt_unteraufgaben(client_fuer, konten, aufgabe):
    unter = unteraufgabe(aufgabe)
    antwort = client_fuer(konten[P]).post(f"/aufgaben/{aufgabe.pk}/erledigt/", {
        "erledigt": "1", "zeile": "1", "unteraufgaben": "alle"}, **HX)
    assert json.loads(antwort["HX-Trigger-After-Settle"])["aufgabe-geaendert"]["ids"] == [aufgabe.pk, unter.pk]


# --- Formulare ohne Weiterleitung ---

def test_formulare_der_seitenleiste_gehen_ueber_htmx(client_fuer, konten, aufgabe):
    unteraufgabe(aufgabe)
    html = leiste(client_fuer(konten[P]), aufgabe).content.decode()
    formulare = re.findall(r'<form method="post" action="[^"]+"[^>]*>', html)
    assert len(formulare) >= 5
    assert all('hx-target="#seitenleiste-inhalt"' in f for f in formulare), formulare
    assert 'hx-encoding="multipart/form-data"' in html


def test_kommentar_antwortet_ohne_weiterleitung(client_fuer, konten, aufgabe):
    client = client_fuer(konten[M])
    antwort = senden(client, f"/aufgaben/{aufgabe.pk}/kommentare/", aufgabe, text="Hallo aus der Leiste")
    assert antwort.status_code == 200 and "Hallo aus der Leiste" in antwort.content.decode()
    assert 'id="seitenleiste-inhalt"' in antwort.content.decode()
    kommentar = Kommentar.objects.get()
    antwort = senden(client, f"/kommentare/{kommentar.pk}/loeschen/", aufgabe)
    assert antwort.status_code == 200 and not Kommentar.objects.exists()
    assert json.loads(antwort["HX-Trigger"])["toasts"][0]["art"] == "erfolg"


def test_kommentar_von_der_detailseite_leitet_weiter(client_fuer, konten, aufgabe):
    antwort = client_fuer(konten[M]).post(f"/aufgaben/{aufgabe.pk}/kommentare/", {"text": "Hallo"})
    assert antwort.status_code == 302


def test_anhang_antwortet_ohne_weiterleitung(client_fuer, konten, aufgabe, settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    client = client_fuer(konten[M])
    datei = SimpleUploadedFile("plan.txt", b"Inhalt", content_type="text/plain")
    antwort = client.post(f"/aufgaben/{aufgabe.pk}/anhaenge/", {"seitenleiste": aufgabe.pk, "datei": datei}, **HX)
    assert antwort.status_code == 200 and "plan.txt" in antwort.content.decode()
    anhang = Anhang.objects.get()
    antwort = senden(client, f"/anhaenge/{anhang.pk}/loeschen/", aufgabe)
    assert antwort.status_code == 200 and not Anhang.objects.exists()


def test_unteraufgabe_anlegen_liefert_den_block(client_fuer, konten, aufgabe):
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/unteraufgaben/", aufgabe, titel="Neue Unteraufgabe")
    html = antwort.content.decode()
    unter = Aufgabe.objects.get(eltern=aufgabe)
    assert antwort.status_code == 200 and 'id="seitenleiste-inhalt"' in html
    assert f'id="aufgabe-block-{aufgabe.pk}" hx-swap-oob="true"' in html
    assert f'id="aufgabe-block-{unter.pk}"' in html and f'id="aufgabe-block-{unter.pk}" hx-swap-oob' not in html


def test_erledigt_im_kopf_liefert_seitenleiste_und_zeile(client_fuer, konten, aufgabe):
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/erledigt/", aufgabe, erledigt="1")
    html = antwort.content.decode()
    assert antwort.status_code == 200 and Aufgabe.objects.get(pk=aufgabe.pk).status.ist_erledigt
    assert 'id="seitenleiste-inhalt"' in html and f'id="aufgabe-{aufgabe.pk}" hx-swap-oob="true"' in html


def test_unteraufgabe_abhaken_bleibt_bei_der_hauptaufgabe(client_fuer, konten, aufgabe):
    unter = unteraufgabe(aufgabe)
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{unter.pk}/erledigt/", aufgabe, erledigt="1")
    html = antwort.content.decode()
    assert f'data-seitenleiste-aufgabe="{aufgabe.pk}"' in html
    assert f'id="aufgabe-{unter.pk}" hx-swap-oob="true"' in html
    assert f'id="aufgabe-{aufgabe.pk}" hx-swap-oob="true"' in html


def test_alle_unteraufgaben_erledigen_tauscht_den_block(client_fuer, konten, aufgabe):
    unter = unteraufgabe(aufgabe)
    html = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/erledigt/", aufgabe, erledigt="1",
                  unteraufgaben="alle").content.decode()
    assert Aufgabe.objects.get(pk=unter.pk).status.ist_erledigt
    assert f'id="aufgabe-block-{aufgabe.pk}" hx-swap-oob="true"' in html


def test_status_alle_erledigt_laedt_die_seite_neu(client_fuer, konten, aufgabe):
    unteraufgabe(aufgabe)
    fertig = Status.objects.filter(ist_erledigt=True).first()
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/feld/", aufgabe, ansicht="detail", feld="status",
                     wert=fertig.pk, version=aufgabe.version, unteraufgaben="alle")
    assert antwort["HX-Refresh"] == "true"


def test_feiern_aus_der_seitenleiste(client_fuer, konten, aufgabe):
    konten[P].feier_animation = True
    konten[P].save(update_fields=["feier_animation"])
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/erledigt/", aufgabe, erledigt="1")
    assert antwort["HX-Trigger"] == "feiern"


def test_loeschen_schliesst_und_entfernt_die_zeile(client_fuer, konten, aufgabe):
    antwort = senden(client_fuer(konten[P]), f"/aufgaben/{aufgabe.pk}/loeschen/", aufgabe)
    html = antwort.content.decode()
    assert antwort.status_code == 200 and not Aufgabe.objects.filter(pk=aufgabe.pk).exists()
    assert antwort["HX-Trigger-After-Settle"] == "seitenleiste-schliessen"
    assert f'id="aufgabe-block-{aufgabe.pk}" hx-swap-oob="delete"' in html
    assert 'id="seitenleiste-inhalt"' not in html


def test_loeschen_einer_unteraufgabe_zieht_die_hauptaufgabe_nach(client_fuer, konten, aufgabe):
    unter = unteraufgabe(aufgabe)
    html = senden(client_fuer(konten[P]), f"/aufgaben/{unter.pk}/loeschen/", unter).content.decode()
    assert f'id="aufgabe-{aufgabe.pk}" hx-swap-oob="true"' in html


def test_monatswechsel_nur_im_widget(client_fuer, konten, aufgabe):
    html = leiste(client_fuer(konten[P]), aufgabe).content.decode()
    assert 'hx-target="#arbeitstage-widget"' in html and 'hx-select="#arbeitstage-widget"' in html
    monat = client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/?monat=2026-02&seitenleiste={aufgabe.pk}", **HX).content.decode()
    assert "Februar 2026" in monat


def test_hauptaufgabe_steht_nur_im_pfad(client_fuer, konten, aufgabe):
    unter = unteraufgabe(aufgabe)
    html = client_fuer(konten[P]).get(f"/aufgaben/{unter.pk}/").content.decode()
    assert html.count(f'href="/aufgaben/{aufgabe.pk}/"') == 1
    assert 'id="aufgabe-pfad"' in html and "Unteraufgabe von" not in html
