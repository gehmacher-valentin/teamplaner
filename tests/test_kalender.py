"""Feiertage und Einteilungslogik (reine Funktionen)."""

from datetime import date
from types import SimpleNamespace as E

import pytest

from planung import kalender
from planung.models import FreierTag

from .conftest import DI, DI2, DO, FEIERTAG, FR, MI, MI2, MO, SA, SO


@pytest.mark.parametrize("jahr, erwartet", [
    (2019, date(2019, 4, 21)),
    (2024, date(2024, 3, 31)),
    (2025, date(2025, 4, 20)),
    (2026, date(2026, 4, 5)),
    (2027, date(2027, 3, 28)),
    (2038, date(2038, 4, 25)),
])
def test_ostersonntag(jahr, erwartet):
    assert kalender.ostersonntag(jahr) == erwartet


def test_gesetzliche_feiertage_2026():
    f = kalender.gesetzliche_feiertage(2026)
    assert len(f) == 13
    assert f[date(2026, 4, 6)] == "Ostermontag"
    assert f[date(2026, 5, 14)] == "Christi Himmelfahrt"
    assert f[date(2026, 5, 25)] == "Pfingstmontag"
    assert f[date(2026, 6, 4)] == "Fronleichnam"
    assert f[date(2026, 10, 26)] == "Nationalfeiertag"
    # keine Landespatrone, kein Karfreitag, kein 24./31.12.
    for kein_feiertag in [date(2026, 11, 15), date(2026, 4, 3), date(2026, 12, 24), date(2026, 12, 31)]:
        assert kein_feiertag not in f


def test_feiertage_ueber_jahreswechsel():
    f = kalender.feiertage_im_zeitraum(date(2026, 12, 20), date(2027, 1, 10))
    assert set(f) == {date(2026, 12, 25), date(2026, 12, 26), date(2027, 1, 1), date(2027, 1, 6)}


@pytest.mark.django_db
def test_freie_tage_enthalten_manuelle_tage():
    FreierTag.objects.create(datum=date(2026, 12, 24), bezeichnung="Betriebsurlaub")
    frei = kalender.freie_tage(date(2026, 12, 21), date(2026, 12, 31))
    assert frei[date(2026, 12, 24)] == "Betriebsurlaub"
    assert frei[date(2026, 12, 25)] == "Christtag"


FREI = {FEIERTAG: "Nationalfeiertag"}


class TestZaehlendeTage:
    def test_normale_woche(self):
        assert kalender.zaehlende_tage(MO, FR, FREI) == [MO, DI, MI, DO, FR]

    def test_wochenende_zaehlt_im_balken_nicht_balken_fr_bis_mo_zusammenhaengend(self):
        assert kalender.zaehlende_tage(FR, DI2, FREI) == [FR, DI2]  # Mo ist Feiertag
        assert kalender.zaehlende_tage(date(2026, 10, 30), date(2026, 11, 2), {}) == [
            date(2026, 10, 30), date(2026, 11, 2)]

    def test_mehrtaegiger_balken_ueber_feiertag_zaehlt_feiertag_nicht(self):
        assert kalender.zaehlende_tage(FEIERTAG, MI2, FREI) == [DI2, MI2]

    def test_eintaegige_einteilung_auf_feiertag_zaehlt(self):
        assert kalender.zaehlende_tage(FEIERTAG, FEIERTAG, FREI) == [FEIERTAG]

    def test_wochenende_wie_feiertag(self):
        # eintägig zählt (nach Bestätigung), mehrtägig nur über das Wochenende zählt nichts
        assert kalender.zaehlende_tage(SA, SA, FREI) == [SA]
        assert kalender.zaehlende_tage(SA, SO, FREI) == []

    @pytest.mark.django_db
    def test_freie_tage_mit_wochenende(self):
        frei = kalender.freie_tage_mit_wochenende(FR, FEIERTAG)
        assert set(frei) == {SA, SO, FEIERTAG}
        assert str(frei[SA]) == "Wochenende" and str(frei[FEIERTAG]) == "Nationalfeiertag"


def test_personentage_und_arbeitstage():
    einteilungen = [
        E(person_id=1, von=MO, bis=MI),          # 3
        E(person_id=2, von=DI, bis=DO),          # 3, überlappt Tage mit Person 1
        E(person_id=1, von=FR, bis=DI2),         # Fr + Di (Mo Feiertag) = 2
        E(person_id=3, von=FEIERTAG, bis=FEIERTAG),  # eintägig auf Feiertag = 1
    ]
    assert kalender.personentage(einteilungen, FREI) == 9
    assert kalender.arbeitstage(einteilungen, FREI) == {MO, DI, MI, DO, FR, FEIERTAG, DI2}


class TestDoppelbelegung:
    def test_zwei_einteilungen_am_selben_tag(self):
        e = [E(person_id=1, von=MO, bis=MI), E(person_id=1, von=MI, bis=FR)]
        assert kalender.doppelbelegungen(e, [], FREI) == {(1, MI)}

    def test_verschiedene_personen_kein_konflikt(self):
        e = [E(person_id=1, von=MO, bis=MI), E(person_id=2, von=MO, bis=MI)]
        assert kalender.doppelbelegungen(e, [], FREI) == set()

    def test_einteilung_und_abwesenheit(self):
        e = [E(person_id=1, von=MO, bis=DI)]
        a = [E(person_id=1, von=DI, bis=DO)]
        assert kalender.doppelbelegungen(e, a, FREI) == {(1, DI)}

    def test_balken_ueber_feiertag_kein_konflikt_am_feiertag(self):
        e = [E(person_id=1, von=FR, bis=DI2), E(person_id=1, von=FEIERTAG, bis=MI2)]
        assert kalender.doppelbelegungen(e, [], FREI) == {(1, DI2)}

    def test_eintaegig_auf_feiertag_plus_abwesenheit_ist_konflikt(self):
        e = [E(person_id=1, von=FEIERTAG, bis=FEIERTAG)]
        a = [E(person_id=1, von=FR, bis=MI2)]
        assert kalender.doppelbelegungen(e, a, FREI) == {(1, FEIERTAG)}
