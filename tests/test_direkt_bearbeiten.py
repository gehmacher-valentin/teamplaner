"""Aufgabendetail direkt bearbeiten, Abhängigkeiten eingeklappt, Verlauf per Umschalter,
Rückmeldungen als Toast, Gantt-Einstellung am Konto."""

import json

import pytest

from kern.models import Protokolleintrag, Rolle
from projekte.models import Abhaengigkeit, Aufgabe, Status
from zusammenarbeit.models import Kommentar

from .conftest import DI, MI, MO

pytestmark = pytest.mark.django_db
A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def feld(client, aufgabe, name, wert, version=None, **extra):
    return client.post(f"/aufgaben/{aufgabe.pk}/feld/", {
        "ansicht": "detail", "feld": name, "wert": wert,
        "version": aufgabe.version if version is None else version, **extra,
    }, HTTP_HX_REQUEST="true")


# --- Felder direkt bearbeiten ---

@pytest.mark.parametrize("name, wert, erwartet", [
    ("titel", "  Verkleidung montieren  ", "Verkleidung montieren"),
    ("beginn_am", MO.isoformat(), MO),
    ("faellig_am", MI.isoformat(), MI),
    ("schaetzung_personentage", "2,5", 2.5),
    ("beschreibung", "<p>Erst <strong>messen</strong></p><script>x()</script>", "<p>Erst <strong>messen</strong></p>"),
])
def test_felder_speichern_mit_verlauf(client_fuer, konten, aufgabe, name, wert, erwartet):
    antwort = feld(client_fuer(konten[P]), aufgabe, name, wert)
    assert antwort.status_code == 200
    gespeichert = Aufgabe.objects.get(pk=aufgabe.pk)
    wert_db = getattr(gespeichert, name)
    assert (float(wert_db) if name == "schaetzung_personentage" else wert_db) == erwartet
    assert gespeichert.version == aufgabe.version + 1
    # Die Antwort bringt die neue Version für das nächste Feld mit (out of band)
    assert f'id="aufgabe-version" name="version" value="{gespeichert.version}" hx-swap-oob="true"' in antwort.content.decode()
    eintrag = Protokolleintrag.objects.filter(objekt_typ="aufgabe", aktion="geaendert", aufgabe_id=aufgabe.pk).latest("id")
    assert name in eintrag.daten


def test_beschreibung_aendern_und_ohne_inhalt_im_protokoll(client_fuer, konten, aufgabe):
    c = client_fuer(konten[P])
    feld(c, aufgabe, "beschreibung", "<p>eins</p>")
    aufgabe.refresh_from_db()
    antwort = feld(c, aufgabe, "beschreibung", "<p>zwei</p>")
    assert antwort["HX-Reswap"] == "none"  # Editor bleibt stehen, nur Version und Kopf
    aufgabe.refresh_from_db()
    assert aufgabe.beschreibung == "<p>zwei</p>"
    eintrag = Protokolleintrag.objects.filter(objekt_typ="aufgabe", aufgabe_id=aufgabe.pk).latest("id")
    assert eintrag.daten["beschreibung"] == ["…", "…"]


def test_mehrere_felder_nacheinander_ohne_konflikt(client_fuer, konten, aufgabe):
    c = client_fuer(konten[P])
    version = aufgabe.version
    for name, wert in [("titel", "Neu"), ("verantwortlich", konten[M].person.pk), ("faellig_am", DI.isoformat())]:
        antwort = feld(c, aufgabe, name, wert, version=version)
        assert "Inzwischen" not in antwort.content.decode()
        version += 1
    aufgabe.refresh_from_db()
    assert (aufgabe.titel, aufgabe.verantwortlich, aufgabe.faellig_am, aufgabe.version) == ("Neu", konten[M].person, DI, version)


def test_gleichzeitige_aenderung_wird_gemeldet(client_fuer, konten, aufgabe):
    feld(client_fuer(konten[BL]), aufgabe, "titel", "Von der Bereichsleitung")
    antwort = feld(client_fuer(konten[P]), aufgabe, "titel", "Veraltet", version=aufgabe.version)
    inhalt = antwort.content.decode()
    assert "Inzwischen von jemand anderem geändert" in inhalt and 'value="Von der Bereichsleitung"' in inhalt
    assert Aufgabe.objects.get(pk=aufgabe.pk).titel == "Von der Bereichsleitung"


@pytest.mark.parametrize("name, wert, meldung", [
    ("titel", "   ", "Bitte einen Titel eingeben."),
    ("titel", "x" * 301, "Höchstens 300 Zeichen."),
    ("schaetzung_personentage", "-1", "Bitte eine Zahl ab 0 eingeben."),
    ("faellig_am", "2026-10-01", "Die Fälligkeit liegt vor dem geplanten Beginn."),
])
def test_ungueltig_am_feld_gemeldet_und_nicht_gespeichert(client_fuer, konten, aufgabe, name, wert, meldung):
    aufgabe.beginn_am = MO
    aufgabe.save()
    antwort = feld(client_fuer(konten[P]), aufgabe, name, wert)
    assert antwort.status_code == 200 and meldung in antwort.content.decode()
    gespeichert = Aufgabe.objects.get(pk=aufgabe.pk)
    assert gespeichert.version == aufgabe.version and gespeichert.titel == aufgabe.titel


@pytest.mark.parametrize("rolle", [M, L])
def test_ohne_bearbeitungsrecht_nur_anzeige(client_fuer, konten, aufgabe, rolle):
    c = client_fuer(konten[rolle])
    assert feld(c, aufgabe, "titel", "Fremd").status_code == 403
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert 'id="eingabe-titel"' not in seite and "data-editor" not in seite and f">{aufgabe.titel}</h1>" in seite
    assert Aufgabe.objects.get(pk=aufgabe.pk).titel == aufgabe.titel


def test_detailseite_ohne_bearbeiten_ansicht(client_fuer, konten, aufgabe):
    seite = client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/?bearbeiten=1").content.decode()
    for feldname in ("titel", "verantwortlich", "abschnitt", "status", "beginn_am", "faellig_am",
                     "schaetzung_personentage", "gewerk"):
        assert f'id="eingabe-{feldname}"' in seite
    assert 'data-editor="eingabe-beschreibung"' in seite
    assert ">Bearbeiten<" not in seite and ">Abbrechen<" not in seite


def test_unteraufgabe_ohne_abschnitt_feld(client_fuer, konten, aufgabe):
    unter = Aufgabe.objects.create(projekt=aufgabe.projekt, abschnitt=aufgabe.abschnitt, eltern=aufgabe, titel="U",
                                   status=Status.standard_offen())
    assert feld(client_fuer(konten[P]), unter, "abschnitt", "").status_code == 400
    assert 'id="eingabe-abschnitt"' not in client_fuer(konten[P]).get(f"/aufgaben/{unter.pk}/").content.decode()


def test_status_erledigt_mit_unteraufgaben_und_feier(client_fuer, konten, aufgabe):
    unter = Aufgabe.objects.create(projekt=aufgabe.projekt, abschnitt=aufgabe.abschnitt, eltern=aufgabe, titel="U",
                                   status=Status.standard_offen())
    konten[P].feier_animation = True
    konten[P].save()
    c = client_fuer(konten[P])
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert 'data-unteraufgaben-offen="1"' in seite and "data-erledigt-status" in seite  # Rückfrage im Browser
    erledigt = Status.standard_erledigt()
    antwort = feld(c, aufgabe, "status", erledigt.pk, unteraufgaben="alle")
    assert antwort["HX-Refresh"] == "true" and c.session.get("feiern")
    unter.refresh_from_db()
    aufgabe.refresh_from_db()
    assert unter.status.ist_erledigt and aufgabe.status == erledigt and aufgabe.erledigt_am


def test_status_erledigt_nur_hauptaufgabe(client_fuer, konten, aufgabe):
    unter = Aufgabe.objects.create(projekt=aufgabe.projekt, abschnitt=aufgabe.abschnitt, eltern=aufgabe, titel="U",
                                   status=Status.standard_offen())
    antwort = feld(client_fuer(konten[P]), aufgabe, "status", Status.standard_erledigt().pk, unteraufgaben="keine")
    assert antwort.status_code == 200 and "HX-Refresh" not in antwort
    unter.refresh_from_db()
    assert not unter.status.ist_erledigt


def test_termine_ziehen_die_hauptaufgabe_nach(client_fuer, konten, aufgabe):
    unter = Aufgabe.objects.create(projekt=aufgabe.projekt, abschnitt=aufgabe.abschnitt, eltern=aufgabe, titel="U",
                                   status=Status.standard_offen())
    feld(client_fuer(konten[P]), unter, "faellig_am", DI.isoformat())
    aufgabe.refresh_from_db()
    assert aufgabe.faellig_am == DI


# --- Abhängigkeiten eingeklappt, Verlauf per Umschalter ---

def test_abhaengigkeiten_eingeklappt_mit_anzahl_und_warnung(client_fuer, konten, aufgabe, projekt):
    vorher = Aufgabe.objects.create(projekt=projekt, titel="Vorher", status=Status.standard_offen(),
                                    beginn_am=MO, faellig_am=MI)
    aufgabe.beginn_am, aufgabe.faellig_am = DI, MI
    aufgabe.save()
    Abhaengigkeit.objects.create(vorher=vorher, nachher=aufgabe)
    seite = client_fuer(konten[P]).get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert '<details class="aufklappbar" id="abhaengigkeiten">' in seite  # ohne open: eingeklappt
    zusammenfassung = seite[seite.index('id="abhaengigkeiten"'):seite.index("</summary>")]
    assert '<span class="zaehler">1</span>' in zusammenfassung and "Termine überschneiden sich" in zusammenfassung


def test_verlauf_nur_mit_umschalter(client_fuer, konten, aufgabe):
    c = client_fuer(konten[P])
    feld(c, aufgabe, "titel", "Geändert")
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    # Nur Verlauf, kein Kommentar: Leerzustand trotzdem sichtbar, Umschalter aus
    assert "Noch keine Kommentare." in seite and 'aria-pressed="false" data-verlauf-umschalten' in seite
    assert 'class="verlauf"' in seite  # im Browser ausgeblendet (.kommentare:not(.kommentare--verlauf))
    Kommentar.objects.create(aufgabe=aufgabe, autor=konten[P].person, text="Hallo")
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert "Noch keine Kommentare." not in seite


# --- Rückmeldungen als Toast ---

def test_meldungen_aus_htmx_als_toast(client_fuer, konten):
    from bestellungen.models import Bestellung

    b = Bestellung.objects.create(bedarf="Kleber")
    antwort = client_fuer(konten[M]).post(f"/bestellungen/{b.pk}/", {"status": "weg"}, HTTP_HX_REQUEST="true")
    ereignisse = json.loads(antwort["HX-Trigger"])
    assert ereignisse["toasts"][0]["art"] == "fehler" and "Nicht gespeichert" in ereignisse["toasts"][0]["text"]
    assert "Nicht gespeichert" not in antwort.content.decode()  # keine Zeile, die die Liste verschiebt


def test_toast_und_feiern_im_selben_header(client_fuer, konten, aufgabe):
    konten[P].feier_animation = True
    konten[P].save()
    from django.contrib import messages
    from django.test import RequestFactory

    from kern.middleware import HtmxMeldungenMiddleware

    def ansicht(request):
        from django.http import HttpResponse

        messages.success(request, "Gespeichert.")
        antwort = HttpResponse()
        antwort["HX-Trigger"] = "feiern"
        return antwort

    from django.contrib.messages.storage.fallback import FallbackStorage
    from django.contrib.sessions.backends.db import SessionStore

    request = RequestFactory().post("/", HTTP_HX_REQUEST="true")
    request.htmx = True
    request.session = SessionStore()
    request._messages = FallbackStorage(request)
    antwort = HtmxMeldungenMiddleware(ansicht)(request)
    assert json.loads(antwort["HX-Trigger"]) == {"feiern": "", "toasts": [{"text": "Gespeichert.", "art": "erfolg"}]}


def test_meldungen_auf_seiten_als_toast(client_fuer, konten, aufgabe):
    c = client_fuer(konten[P])
    antwort = c.post(f"/aufgaben/{aufgabe.pk}/loeschen/", follow=True)
    inhalt = antwort.content.decode()
    assert 'class="toast toast--erfolg"' in inhalt and "Aufgabe gelöscht." in inhalt
    assert 'class="meldungen"' not in inhalt


# --- Gantt: Unteraufgaben aufgeklappt am Konto ---

def test_gantt_einstellung_am_eigenen_konto(client_fuer, konten):
    c = client_fuer(konten[M])
    assert c.get("/api/gantt/ansichten").json()["unteraufgaben_offen"] is False
    antwort = c.patch("/api/gantt/einstellungen", {"unteraufgaben_offen": True}, content_type="application/json")
    assert antwort.status_code == 200
    konten[M].refresh_from_db()
    konten[P].refresh_from_db()
    assert konten[M].gantt_unteraufgaben_offen and not konten[P].gantt_unteraufgaben_offen
    assert c.get("/api/gantt/ansichten").json()["unteraufgaben_offen"] is True
    assert c.patch("/api/gantt/einstellungen", {"unteraufgaben_offen": "ja"},
                   content_type="application/json").status_code == 400

