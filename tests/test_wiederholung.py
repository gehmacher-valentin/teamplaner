"""Wiederkehrende Aufgaben: Regelberechnung, Folgeaufgabe beim Abhaken (alle Wege), kein Doppelanlegen,
übernommene Unteraufgaben, nicht übernommene Daten, Ende der Wiederholung, Eingabe im Aufgabendetail."""

from datetime import date

import pytest

from kern.models import Protokolleintrag, Rolle
from planung.models import Einteilung
from projekte import dienste
from projekte.models import Abhaengigkeit, Aufgabe, Status
from projekte.wiederholung import (
    UngueltigeRegel,
    auswahl,
    ende,
    naechster_termin,
    regel_bauen,
    regel_text,
)
from zusammenarbeit.models import Kommentar
from zusammenarbeit.verlauf import verlauf_eintraege

from .conftest import DI, MI, MO

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


def regel(frequenz, stichtag, **extra):
    return regel_bauen(frequenz, extra.pop("intervall", 1), extra.pop("wochentage", ()), extra.pop("bis", None), stichtag)


# ---------- Regelberechnung ----------

@pytest.mark.parametrize("frequenz, intervall, stichtag, erwartet", [
    ("taeglich", 1, date(2026, 12, 31), date(2027, 1, 1)),
    ("taeglich", 3, date(2026, 10, 19), date(2026, 10, 22)),
    ("woechentlich", 1, date(2026, 10, 19), date(2026, 10, 26)),  # Feiertag zählt nicht: Kalendertag
    ("woechentlich", 2, date(2026, 10, 19), date(2026, 11, 2)),
    ("monatlich", 1, date(2026, 1, 15), date(2026, 2, 15)),
    ("monatlich", 3, date(2026, 11, 30), date(2027, 2, 28)),
    ("monatlich", 1, date(2026, 12, 10), date(2027, 1, 10)),
    ("jaehrlich", 1, date(2026, 3, 1), date(2027, 3, 1)),
    ("jaehrlich", 2, date(2026, 6, 30), date(2028, 6, 30)),
])
def test_naechster_termin(frequenz, intervall, stichtag, erwartet):
    assert naechster_termin(stichtag, regel(frequenz, stichtag, intervall=intervall)) == erwartet


def test_monatsende_faellt_auf_den_letzten_tag_und_kehrt_zurueck():
    r = regel("monatlich", date(2027, 1, 31))
    termine, d = [], date(2027, 1, 31)
    for _ in range(4):
        d = naechster_termin(d, r)
        termine.append(d)
    assert termine == [date(2027, 2, 28), date(2027, 3, 31), date(2027, 4, 30), date(2027, 5, 31)]
    # Schaltjahr und jährlich am 29. Februar
    assert naechster_termin(date(2028, 1, 31), regel("monatlich", date(2028, 1, 31))) == date(2028, 2, 29)
    j = regel("jaehrlich", date(2028, 2, 29))
    assert naechster_termin(date(2028, 2, 29), j) == date(2029, 2, 28)
    assert naechster_termin(date(2031, 2, 28), j) == date(2032, 2, 29)


def test_woechentlich_mit_wochentagen():
    r = regel("woechentlich", MO, wochentage=["0", "2"])  # Mo und Mi
    assert naechster_termin(MO, r) == MI
    assert naechster_termin(MI, r) == date(2026, 10, 26)
    alle2 = regel("woechentlich", MO, intervall=2, wochentage=["0", "2"])
    assert naechster_termin(MO, alle2) == MI
    assert naechster_termin(MI, alle2) == date(2026, 11, 2)  # Woche dazwischen ausgelassen
    sonntag = regel("woechentlich", date(2026, 10, 25), wochentage=["6"])
    assert naechster_termin(date(2026, 10, 25), sonntag) == date(2026, 11, 1)


def test_regel_pruefen_und_text():
    assert regel_bauen("", 1, (), None, MO) is None
    for falsch in [dict(frequenz="stuendlich"), dict(frequenz="taeglich", intervall="0"),
                   dict(frequenz="taeglich", intervall="100"), dict(frequenz="taeglich", intervall="x"),
                   dict(frequenz="woechentlich", wochentage=["7"]), dict(frequenz="taeglich", bis="2026-10-01")]:
        with pytest.raises(UngueltigeRegel):
            regel_bauen(falsch.pop("frequenz"), falsch.get("intervall", 1), falsch.get("wochentage", ()),
                        falsch.get("bis"), MO)
    # Wochentage nur bei wöchentlich
    assert "wochentage" not in regel("taeglich", MO, wochentage=["1"])
    assert regel_text(regel("woechentlich", MO, intervall=2, wochentage=["2", "0"], bis="2027-06-30")) == \
        "Alle 2 Wochen (Mo, Mi) bis 30.06.2027"
    assert regel_text(regel("monatlich", MO)) == "Monatlich"


# ---------- Vierteljährlich und halbjährlich (#87) ----------

def termine_ab(stichtag, r, anzahl):
    termine, d = [], stichtag
    for _ in range(anzahl):
        d = naechster_termin(d, r)
        termine.append(d)
    return termine


def test_vierteljaehrlich_und_halbjaehrlich_als_monatlich_gespeichert():
    # Gespeichert wie „monatlich alle 3 bzw. 6 Monate“, ein eingegebenes Intervall zählt nicht
    assert regel("vierteljaehrlich", date(2027, 1, 15), intervall="7") == \
        {"frequenz": "monatlich", "intervall": 3, "tag": 15}
    assert regel("halbjaehrlich", date(2027, 1, 15)) == {"frequenz": "monatlich", "intervall": 6, "tag": 15}
    assert regel_text(regel("vierteljaehrlich", MO)) == "Vierteljährlich"
    assert regel_text(regel("halbjaehrlich", MO, bis="2028-12-31")) == "Halbjährlich bis 31.12.2028"
    assert regel_text(regel("monatlich", MO, intervall=2)) == "Alle 2 Monate"


def test_vierteljaehrlich_vom_monatsletzten_und_ueber_den_jahreswechsel():
    r = regel("vierteljaehrlich", date(2027, 1, 31))
    assert termine_ab(date(2027, 1, 31), r, 4) == [date(2027, 4, 30), date(2027, 7, 31), date(2027, 10, 31),
                                                    date(2028, 1, 31)]
    r = regel("vierteljaehrlich", date(2026, 11, 30))
    assert termine_ab(date(2026, 11, 30), r, 2) == [date(2027, 2, 28), date(2027, 5, 30)]
    h = regel("halbjaehrlich", date(2026, 8, 31))
    assert termine_ab(date(2026, 8, 31), h, 3) == [date(2027, 2, 28), date(2027, 8, 31), date(2028, 2, 29)]


def test_bestehende_regeln_mit_3_und_6_monaten():
    # Alte Regeln „monatlich alle 3/6 Monate“ erscheinen als die neuen Einträge, andere bleiben, wie sie sind
    assert auswahl({"frequenz": "monatlich", "intervall": 3, "tag": 1}) == "vierteljaehrlich"
    assert auswahl({"frequenz": "monatlich", "intervall": 6}) == "halbjaehrlich"
    assert auswahl({"frequenz": "monatlich", "intervall": 4}) == "monatlich"
    assert auswahl({"frequenz": "jaehrlich", "intervall": 3}) == "jaehrlich"
    assert auswahl(None) == ""
    assert regel_text({"frequenz": "monatlich", "intervall": 6, "tag": 5}) == "Halbjährlich"
    assert regel_text({"frequenz": "woechentlich", "intervall": 3}) == "Alle 3 Wochen"


def test_vierteljaehrlich_im_detail(client_fuer, konten, aufgabe):
    aufgabe.faellig_am = date(2027, 1, 31)
    aufgabe.save()
    c = client_fuer(konten[P])
    assert feld(c, aufgabe, frequenz="vierteljaehrlich", bis="2027-12-31")["HX-Refresh"] == "true"
    aufgabe.refresh_from_db()
    assert aufgabe.wiederholung == {"frequenz": "monatlich", "intervall": 3, "bis": "2027-12-31", "tag": 31}
    verlauf = Protokolleintrag.objects.filter(aufgabe_id=aufgabe.pk, aktion="geaendert").first()
    assert verlauf.daten["wiederholung"] == ["", "Vierteljährlich bis 31.12.2027"]
    # Vorbelegt, ohne Feld „alle …“
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert '<option value="vierteljaehrlich" selected>' in seite
    assert 'name="intervall"' not in seite and 'name="bis"' in seite
    # Ende der Wiederholung gilt wie bei allen Regeln
    assert ende(aufgabe.wiederholung) == date(2027, 12, 31)
    # Zurück auf monatlich: Intervall 1, Feld „alle …“ wieder da
    feld(c, aufgabe, frequenz="monatlich")
    aufgabe.refresh_from_db()
    assert aufgabe.wiederholung["intervall"] == 1
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert '<option value="monatlich" selected>' in seite and 'name="intervall"' in seite
    # Monatlich alle 6 Monate eingegeben: als halbjährlich angezeigt
    feld(c, aufgabe, frequenz="monatlich", intervall="6")
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert '<option value="halbjaehrlich" selected>' in seite and 'name="intervall"' not in seite


def test_vierteljaehrlich_folgeaufgabe_beim_abhaken(konten, aufgabe):
    aufgabe.wiederholung = regel("vierteljaehrlich", date(2027, 1, 31))
    aufgabe.faellig_am = date(2027, 1, 31)
    aufgabe.save()
    dienste.erledigt_setzen(konten[P], aufgabe, True)
    assert folge(aufgabe).faellig_am == date(2027, 4, 30)
    assert folge(aufgabe).wiederholung == aufgabe.wiederholung


# ---------- Folgeaufgabe beim Abhaken ----------

@pytest.fixture
def wiederkehrend(aufgabe, konten):
    aufgabe.wiederholung = regel("woechentlich", MO)
    aufgabe.faellig_am = MO
    aufgabe.verantwortlich = konten[M].person
    aufgabe.beschreibung = "<p>Ölstand prüfen</p>"
    aufgabe.sortierung = 30
    aufgabe.save()
    return aufgabe


def folge(aufgabe):
    return Aufgabe.objects.get(wiederholt_von=aufgabe)


def test_abhaken_legt_folgeaufgabe_an(client_fuer, konten, wiederkehrend):
    antwort = client_fuer(konten[M]).post(f"/aufgaben/{wiederkehrend.pk}/erledigt/", {"erledigt": "1"})
    assert antwort.status_code == 302
    wiederkehrend.refresh_from_db()
    assert wiederkehrend.status.ist_erledigt  # die alte bleibt als erledigt bestehen
    neu = folge(wiederkehrend)
    assert not neu.status.ist_erledigt
    assert neu.faellig_am == date(2026, 10, 26) and neu.beginn_am is None
    assert (neu.projekt, neu.abschnitt, neu.eltern, neu.titel, neu.beschreibung, neu.verantwortlich, neu.gewerk,
            neu.schaetzung_personentage, neu.wiederholung, neu.sortierung) == (
        wiederkehrend.projekt, wiederkehrend.abschnitt, None, wiederkehrend.titel, wiederkehrend.beschreibung,
        wiederkehrend.verantwortlich, wiederkehrend.gewerk, wiederkehrend.schaetzung_personentage,
        wiederkehrend.wiederholung, wiederkehrend.sortierung)
    # Eigener Verlauf: nur „angelegt (Wiederholung von …)“
    eintraege = Protokolleintrag.objects.filter(aufgabe_id=neu.pk)
    assert [(e.objekt_typ, e.aktion) for e in eintraege] == [("aufgabe", "angelegt")]
    texte = [e["text"] for e in verlauf_eintraege(konten[M], neu) if e["art"] != "kommentar"]
    assert texte == ["hat die Aufgabe angelegt (Wiederholung von „Hallenboden Nord“)."]


def test_naechster_termin_vom_stichtag_nicht_vom_abhaken(konten, wiederkehrend):
    # Stichtag lag in der Vergangenheit (Testwoche 2026): der nächste Termin folgt dem Plan
    dienste.erledigt_setzen(konten[M], wiederkehrend, True)
    assert folge(wiederkehrend).faellig_am == date(2026, 10, 26)


@pytest.mark.parametrize("weg", ["haken", "status_detail", "status_zeile", "erledigt_setzen", "unteraufgaben_erledigen"])
def test_alle_wege_des_abhakens(client_fuer, konten, aufgabe, wiederkehrend, weg):
    c = client_fuer(konten[A])
    ziel = wiederkehrend
    if weg == "haken":
        c.post(f"/aufgaben/{ziel.pk}/erledigt/", {"erledigt": "1", "zeile": "1"}, HTTP_HX_REQUEST="true")
    elif weg in ("status_detail", "status_zeile"):
        antwort = c.post(f"/aufgaben/{ziel.pk}/feld/", {
            "feld": "status", "wert": Status.standard_erledigt().pk, "version": ziel.version,
            **({"ansicht": "detail"} if weg == "status_detail" else {})}, HTTP_HX_REQUEST="true")
        assert antwort.status_code == 204 and antwort["HX-Refresh"] == "true"
    elif weg == "erledigt_setzen":
        dienste.erledigt_setzen(konten[A], ziel, True)
    else:
        # Wiederkehrende Unteraufgabe einer anderen Aufgabe, über „alle Unteraufgaben erledigen“
        haupt = Aufgabe.objects.create(projekt=aufgabe.projekt, titel="Wartung", status=Status.standard_offen())
        ziel.eltern = haupt
        ziel.save()
        dienste.erledigt_setzen(konten[A], haupt, True, unteraufgaben_mit=True)
    neu = folge(ziel)
    assert neu.faellig_am == date(2026, 10, 26)
    assert neu.eltern_id == ziel.eltern_id


def test_htmx_haken_liefert_erledigte_zeile_mit_folgeaufgabe_und_meldet(client_fuer, konten, wiederkehrend):
    """Kein Neuladen mehr: Die erledigte Zeile bleibt stehen, die Folgeaufgabe liegt als <template> bei und
    erscheint erst nach Ablauf (lib/abhaken.ts); die Meldung kommt als Toast."""
    import json

    c = client_fuer(konten[M])
    antwort = c.post(f"/aufgaben/{wiederkehrend.pk}/erledigt/", {"erledigt": "1", "zeile": "1"}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200 and "HX-Refresh" not in antwort
    html = antwort.content.decode()
    neu = folge(wiederkehrend)
    assert f'id="aufgabe-{wiederkehrend.pk}"' in html and "data-erledigt" in html.split("<template")[0]
    assert f'name="folge" value="{neu.pk}"' in html  # für „rückgängig“
    assert "<template data-folgeaufgabe>" in html and f'id="aufgabe-block-{neu.pk}"' in html.split("<template")[1]
    toasts = json.loads(antwort["HX-Trigger"])["toasts"]
    assert toasts[0]["text"] == "Nächster Termin angelegt: Hallenboden Nord, 26.10.2026."
    seite = c.get(f"/projekte/{wiederkehrend.projekt_id}/").content.decode()
    assert seite.count('class="wiederkehrend"') == 1  # nur die offene steht in der Liste (Filter „Offen“)


def test_rueckgaengig_nimmt_unberuehrte_folgeaufgabe_zurueck(client_fuer, konten, wiederkehrend):
    c = client_fuer(konten[M])
    c.post(f"/aufgaben/{wiederkehrend.pk}/erledigt/", {"erledigt": "1", "zeile": "1"}, HTTP_HX_REQUEST="true")
    neu = folge(wiederkehrend)
    antwort = c.post(f"/aufgaben/{wiederkehrend.pk}/erledigt/", {"erledigt": "0", "zeile": "1", "folge": neu.pk},
                     HTTP_HX_REQUEST="true")
    assert antwort.status_code == 200 and "data-erledigt" not in antwort.content.decode()
    wiederkehrend.refresh_from_db()
    assert not wiederkehrend.status.ist_erledigt
    assert not Aufgabe.objects.filter(pk=neu.pk).exists()
    # Erneut abhaken legt wieder genau eine Folgeaufgabe an
    c.post(f"/aufgaben/{wiederkehrend.pk}/erledigt/", {"erledigt": "1", "zeile": "1"}, HTTP_HX_REQUEST="true")
    assert Aufgabe.objects.filter(titel="Hallenboden Nord").count() == 2


def test_rueckgaengig_laesst_bearbeitete_oder_fremde_folgeaufgabe_stehen(client_fuer, konten, wiederkehrend, aufgabe):
    c = client_fuer(konten[M])
    dienste.erledigt_setzen(konten[M], wiederkehrend, True)
    neu = folge(wiederkehrend)
    dienste.aufgabe_speichern(konten[M], neu, {"titel": "Geändert"}, neu.version)
    wiederkehrend.refresh_from_db()
    c.post(f"/aufgaben/{wiederkehrend.pk}/erledigt/", {"erledigt": "0", "folge": neu.pk})
    assert Aufgabe.objects.filter(pk=neu.pk).exists()  # schon bearbeitet: bleibt
    # Fremde ID (keine Folgeaufgabe dieser Aufgabe) wird nie gelöscht
    dienste.erledigt_setzen(konten[M], wiederkehrend, True)
    wiederkehrend.refresh_from_db()
    c.post(f"/aufgaben/{wiederkehrend.pk}/erledigt/", {"erledigt": "0", "folge": aufgabe.pk})
    assert Aufgabe.objects.filter(pk=aufgabe.pk).exists()


def test_meine_aufgaben_haken_liefert_zeile_mit_folgeaufgabe(client_fuer, konten, wiederkehrend):
    wiederkehrend.verantwortlich = konten[M].person
    wiederkehrend.save()
    c = client_fuer(konten[M])
    antwort = c.post(f"/aufgaben/{wiederkehrend.pk}/erledigt/", {
        "erledigt": "1", "zeile": "meine", "weiter": "/meine-aufgaben/?zugewiesen=platzhalter"}, HTTP_HX_REQUEST="true")
    html = antwort.content.decode()
    neu = folge(wiederkehrend)
    assert antwort.status_code == 200 and "HX-Refresh" not in antwort
    assert f'id="meine-{wiederkehrend.pk}"' in html and "zugewiesen__zeile--erledigt" in html
    assert f'id="meine-{neu.pk}"' in html.split("<template data-folgeaufgabe>")[1]
    assert 'name="weiter" value="/meine-aufgaben/?zugewiesen=platzhalter"' in html


def test_kein_doppeltes_anlegen_beim_wieder_oeffnen(konten, wiederkehrend):
    dienste.erledigt_setzen(konten[M], wiederkehrend, True)
    wiederkehrend.refresh_from_db()
    dienste.erledigt_setzen(konten[M], wiederkehrend, False)
    wiederkehrend.refresh_from_db()
    dienste.erledigt_setzen(konten[M], wiederkehrend, True)
    assert Aufgabe.objects.filter(titel="Hallenboden Nord").count() == 2


def test_enddatum_und_ende_der_wiederholung(konten, wiederkehrend, aufgabe):
    wiederkehrend.wiederholung = regel("woechentlich", MO, bis="2026-10-25")
    wiederkehrend.save()
    dienste.erledigt_setzen(konten[M], wiederkehrend, True)
    assert not Aufgabe.objects.filter(wiederholt_von=wiederkehrend).exists()
    # Enddatum genau am nächsten Termin: wird noch angelegt
    zweite = Aufgabe.objects.create(projekt=aufgabe.projekt, titel="Filter tauschen", status=Status.standard_offen(),
                                    faellig_am=MO, wiederholung=regel("woechentlich", MO, bis="2026-10-26"))
    dienste.erledigt_setzen(konten[M], zweite, True)
    assert folge(zweite).faellig_am == date(2026, 10, 26)
    # Wiederholung entfernt: keine neue
    dritte = Aufgabe.objects.create(projekt=aufgabe.projekt, titel="Pumpe", status=Status.standard_offen(),
                                    faellig_am=MO, wiederholung=regel("taeglich", MO))
    dritte = dienste.aufgabe_speichern(konten[A], dritte, {"wiederholung": None}, None)
    dienste.erledigt_setzen(konten[M], dritte, True)
    assert not Aufgabe.objects.filter(wiederholt_von=dritte).exists()


def test_unteraufgaben_werden_mitgenommen(konten, wiederkehrend):
    u1 = Aufgabe.objects.create(projekt=wiederkehrend.projekt, abschnitt=wiederkehrend.abschnitt, eltern=wiederkehrend,
                                titel="Filter", status=Status.standard_erledigt(), faellig_am=MO, beginn_am=MO,
                                verantwortlich=konten[P].person, sortierung=10)
    u2 = Aufgabe.objects.create(projekt=wiederkehrend.projekt, abschnitt=wiederkehrend.abschnitt, eltern=wiederkehrend,
                                titel="Öl", status=Status.standard_offen(), sortierung=20)
    tief = Aufgabe.objects.create(projekt=wiederkehrend.projekt, abschnitt=wiederkehrend.abschnitt, eltern=u2,
                                  titel="Ölsorte prüfen", status=Status.standard_offen(), faellig_am=DI)
    dienste.erledigt_setzen(konten[M], wiederkehrend, True, unteraufgaben_mit=True)
    neu = folge(wiederkehrend)
    kopien = list(neu.unteraufgaben.order_by("sortierung"))
    assert [k.titel for k in kopien] == ["Filter", "Öl"]
    assert all(not k.status.ist_erledigt for k in kopien)
    assert (kopien[0].faellig_am, kopien[0].beginn_am, kopien[0].verantwortlich) == (
        date(2026, 10, 26), date(2026, 10, 26), konten[P].person)  # um denselben Abstand verschoben
    tiefe_kopie = kopien[1].unteraufgaben.get()
    assert (tiefe_kopie.titel, tiefe_kopie.faellig_am, tiefe_kopie.status.ist_erledigt) == (
        "Ölsorte prüfen", date(2026, 10, 27), False)
    assert tiefe_kopie.abschnitt == wiederkehrend.abschnitt
    # Alte Unteraufgaben bleiben unverändert bei der alten Aufgabe
    for alt in (u1, u2, tief):
        alt.refresh_from_db()
    assert u1.eltern == wiederkehrend and tief.eltern == u2


def test_wiederkehrende_unteraufgabe_wird_nicht_doppelt_kopiert(konten, wiederkehrend):
    Aufgabe.objects.create(projekt=wiederkehrend.projekt, eltern=wiederkehrend, titel="Täglich lüften",
                           status=Status.standard_offen(), faellig_am=MO, wiederholung=regel("taeglich", MO))
    dienste.erledigt_setzen(konten[M], wiederkehrend, True, unteraufgaben_mit=True)
    assert [u.titel for u in folge(wiederkehrend).unteraufgaben.all()] == ["Täglich lüften"]


def test_nicht_uebernommene_daten(konten, wiederkehrend, person_a):
    andere = Aufgabe.objects.create(projekt=wiederkehrend.projekt, titel="Vorher", status=Status.standard_offen())
    Abhaengigkeit.objects.create(vorher=andere, nachher=wiederkehrend)
    Einteilung.objects.create(aufgabe=wiederkehrend, person=person_a, von=MO, bis=MI)
    Kommentar.objects.create(aufgabe=wiederkehrend, autor=konten[M].person, text="Erledigt mit Hilfe")
    dienste.erledigt_setzen(konten[M], wiederkehrend, True)
    neu = folge(wiederkehrend)
    assert not neu.einteilungen.exists()
    assert not neu.kommentare.exists()
    assert not neu.anhaenge.exists()
    assert not neu.vorgaenger_links.exists() and not neu.nachfolger_links.exists()
    assert wiederkehrend.einteilungen.count() == 1 and wiederkehrend.kommentare.count() == 1


# ---------- Eingabe im Aufgabendetail ----------

def feld(c, aufgabe, **daten):
    aufgabe.refresh_from_db()
    return c.post(f"/aufgaben/{aufgabe.pk}/feld/", {"ansicht": "detail", "feld": "wiederholung",
                                                    "version": aufgabe.version, **daten}, HTTP_HX_REQUEST="true")


def test_wiederholung_im_detail_eingeben(client_fuer, konten, aufgabe):
    aufgabe.beginn_am, aufgabe.faellig_am = MO, MI
    aufgabe.save()
    c = client_fuer(konten[P])
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert 'name="frequenz"' in seite and "eingabe-beginn_am" in seite
    antwort = feld(c, aufgabe, frequenz="woechentlich")
    assert antwort["HX-Refresh"] == "true"  # Zeitspanne → Stichtag
    aufgabe.refresh_from_db()
    assert aufgabe.wiederholung == {"frequenz": "woechentlich", "intervall": 1}
    assert (aufgabe.beginn_am, aufgabe.faellig_am) == (None, MI)  # statt Zeitspanne nur der Stichtag
    seite = c.get(f"/aufgaben/{aufgabe.pk}/").content.decode()
    assert "Stichtag" in seite and "eingabe-beginn_am" not in seite and 'name="wochentage"' in seite
    antwort = feld(c, aufgabe, frequenz="woechentlich", intervall="2", wochentage=["0", "4"], bis="2027-01-31")
    assert antwort.status_code == 200
    aufgabe.refresh_from_db()
    assert aufgabe.wiederholung == {"frequenz": "woechentlich", "intervall": 2, "wochentage": [0, 4],
                                    "bis": "2027-01-31"}
    verlauf = Protokolleintrag.objects.filter(aufgabe_id=aufgabe.pk, aktion="geaendert").first()
    assert verlauf.daten["wiederholung"] == ["Wöchentlich", "Alle 2 Wochen (Mo, Fr) bis 31.01.2027"]
    # Ungültig: Meldung am Feld, nichts gespeichert
    assert "zwischen 1 und 99" in feld(c, aufgabe, frequenz="taeglich", intervall="0").content.decode()
    # Ohne Stichtag geht es nicht; Beginn ist gesperrt
    antwort = c.post(f"/aufgaben/{aufgabe.pk}/feld/", {"ansicht": "detail", "feld": "faellig_am", "wert": "",
                                                       "version": aufgabe.version}, HTTP_HX_REQUEST="true")
    assert "brauchen einen Stichtag" in antwort.content.decode()
    # Wiederholung entfernen
    assert feld(c, aufgabe, frequenz="")["HX-Refresh"] == "true"
    aufgabe.refresh_from_db()
    assert aufgabe.wiederholung is None and aufgabe.faellig_am == MI


def test_ohne_faelligkeit_heute_als_stichtag(client_fuer, konten, aufgabe):
    from django.utils import timezone
    feld(client_fuer(konten[P]), aufgabe, frequenz="monatlich")
    aufgabe.refresh_from_db()
    heute = timezone.localdate()
    assert aufgabe.faellig_am == heute and aufgabe.wiederholung["tag"] == heute.day


def test_wiederholung_nur_mit_bearbeitungsrecht(client_fuer, konten, aufgabe):
    assert feld(client_fuer(konten[M]), aufgabe, frequenz="taeglich").status_code == 403
    aufgabe.refresh_from_db()
    assert aufgabe.wiederholung is None
