"""Notizen gemeinsam bearbeiten (notizen.live): Yjs-Änderungen speichern und verteilen, Titel und Markdown
mitführen, Stand zusammenfassen, Anwesenheit – mit denselben Rechten wie beim Bearbeiten."""

import base64
import json

import pytest
from django.test import Client

from kern.hilfen import TEXT_MAX_ZEICHEN
from kern.models import Rolle
from notizen.live import _nachholen
from notizen.models import Notiz, NotizAenderung, Ordner

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def client_fuer(konto):
    c = Client()
    c.force_login(konto)
    return c


def b64(daten):
    return base64.b64encode(daten).decode()


def post(client, url, daten):
    return client.post(url, json.dumps(daten), content_type="application/json")


@pytest.fixture
def ordner(konten):
    o = Ordner.objects.create(name="Labor", erstellt_von=konten[P].person)
    o.mitglieder.add(konten[P], konten[M], konten[L])
    return o


@pytest.fixture
def notiz(ordner):
    return Notiz.objects.create(ordner=ordner, titel="Liste", text="alt")


def test_aenderung_speichern_mit_titel_und_text(konten, notiz):
    c = client_fuer(konten[M])
    antwort = post(c, f"/notizen/{notiz.pk}/aenderung/", {"update": b64(b"\x01\x02"), "text": "neu", "titel": " Liste  2 ",
                                                          "eigen": True})
    assert antwort.status_code == 200 and antwort.json()["id"]
    notiz.refresh_from_db()
    assert (notiz.text, notiz.titel, notiz.version, notiz.geaendert_von) == ("neu", "Liste 2", 2, konten[M].person)
    assert [bytes(d) for d in NotizAenderung.objects.values_list("daten", flat=True)] == [b"\x01\x02"]
    # Nur abgleichen (nach Änderungen anderer): kein neuer Eintrag, „zuletzt geändert von“ bleibt
    assert post(client_fuer(konten[P]), f"/notizen/{notiz.pk}/aenderung/", {"text": "zusammen"}).json()["id"] is None
    notiz.refresh_from_db()
    assert notiz.text == "zusammen" and notiz.geaendert_von == konten[M].person
    assert NotizAenderung.objects.count() == 1
    # Leerer Titel bleibt ungespeichert
    post(c, f"/notizen/{notiz.pk}/aenderung/", {"titel": "  "})
    notiz.refresh_from_db()
    assert notiz.titel == "Liste 2"


@pytest.mark.parametrize("rolle, status", [(M, 200), (P, 200), (L, 403), (BL, 403)])
def test_aenderung_rechte(konten, notiz, rolle, status):
    assert post(client_fuer(konten[rolle]), f"/notizen/{notiz.pk}/aenderung/", {"update": b64(b"x")}).status_code == status


@pytest.mark.parametrize("daten", [{"update": "kein base64!"}, {"text": "x" * (TEXT_MAX_ZEICHEN + 1)}, {"text": 5}])
def test_aenderung_ungueltig(konten, notiz, daten):
    antwort = post(client_fuer(konten[M]), f"/notizen/{notiz.pk}/aenderung/", daten)
    assert antwort.status_code == 400
    assert not NotizAenderung.objects.exists()
    notiz.refresh_from_db()
    assert notiz.text == "alt"


def test_start_nur_einmal_danach_kein_ueberschreiben_mehr(konten, notiz):
    c = client_fuer(konten[M])
    assert post(c, f"/notizen/{notiz.pk}/start/", {"zustand": b64(b"stand"), "text": "alt", "titel": "Liste"}).status_code == 200
    # Wer zu spät kommt, lädt neu
    assert post(client_fuer(konten[P]), f"/notizen/{notiz.pk}/start/", {"zustand": b64(b"anders")}).status_code == 409
    # Das alte Speichern ersetzt den Text nicht mehr, sondern lässt die Seite neu laden
    antwort = c.post("/notizen/speichern/", {"notiz": notiz.pk, "ordner": "", "version": notiz.version, "titel": "Liste",
                                             "text": "ganz anders"}, HTTP_HX_REQUEST="true")
    assert antwort["HX-Refresh"] == "true"
    notiz.refresh_from_db()
    assert notiz.text == "alt"


def test_nachholen_und_zusammenfassen(konten, notiz):
    c = client_fuer(konten[M])
    ids = [post(c, f"/notizen/{notiz.pk}/aenderung/", {"update": b64(bytes([i]))}).json()["id"] for i in range(1, 5)]
    paket, gesendet = _nachholen(notiz.pk, ids[1])
    assert gesendet == ids[3] and json.loads(paket.split("data: ")[1])["daten"] == [b64(b"\x03"), b64(b"\x04")]
    assert _nachholen(notiz.pk, ids[3]) == (None, ids[3])
    # Bis zur dritten Änderung zusammenfassen; ungültiges „bis“ ändert nichts
    assert post(c, f"/notizen/{notiz.pk}/zusammenfassen/", {"zustand": b64(b"gesamt"), "bis": ids[3] + 100}).status_code == 204
    assert NotizAenderung.objects.count() == 4
    assert post(c, f"/notizen/{notiz.pk}/zusammenfassen/", {"zustand": b64(b"gesamt"), "bis": ids[2]}).status_code == 204
    assert list(NotizAenderung.objects.values_list("id", flat=True)) == [ids[3]]
    # Wer weiter hinten ist, bekommt den Gesamtstand und alles danach
    paket, gesendet = _nachholen(notiz.pk, ids[0])
    assert json.loads(paket.split("data: ")[1])["daten"] == [b64(b"gesamt"), b64(b"\x04")] and gesendet == ids[3]
    # Seite öffnen: Startdaten mit Stand und späteren Änderungen
    seite = c.get(f"/notizen/{notiz.pk}/").content.decode()
    assert f'"zustand": "{b64(b"gesamt")}"' in seite and f'"ab": {ids[3]}' in seite


def test_anwesend_und_stream_nur_mit_rechten(konten, notiz):
    assert post(client_fuer(konten[M]), f"/notizen/{notiz.pk}/anwesend/", {"client": "abc"}).status_code == 204
    assert post(client_fuer(konten[L]), f"/notizen/{notiz.pk}/anwesend/", {"client": "abc"}).status_code == 403
    assert post(client_fuer(konten[M]), f"/notizen/{notiz.pk}/anwesend/", {"client": ""}).status_code == 400
    assert client_fuer(konten[BL]).get(f"/api/planung/stream/notiz/{notiz.pk}").status_code == 403
    assert Client().get(f"/api/planung/stream/notiz/{notiz.pk}").status_code == 401


def test_persoenliche_notiz_nur_fuer_besitzer(konten):
    notiz = Notiz.objects.create(besitzer=konten[M].person, titel="Meine", text="")
    assert post(client_fuer(konten[M]), f"/notizen/{notiz.pk}/aenderung/", {"update": b64(b"x")}).status_code == 200
    assert post(client_fuer(konten[A]), f"/notizen/{notiz.pk}/aenderung/", {"update": b64(b"x")}).status_code == 403
    assert client_fuer(konten[A]).get(f"/api/planung/stream/notiz/{notiz.pk}").status_code == 403
