"""Teamplaner-Ansichten und Freigaben."""

import re

import pytest

from kern.models import Person, Rolle
from planung import rechte
from planung.models import Recht, TeamplanerAnsicht

from .conftest import freigeben

pytestmark = pytest.mark.django_db

A, BL, P, M, L = Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND


@pytest.mark.parametrize("rolle", [A, BL])
def test_admin_und_bereichsleitung_sehen_und_bearbeiten_alles(konten, rolle, person_b):
    konto = konten[rolle]
    assert rechte.sichtbare_personen_ids(konto) is None
    assert rechte.einteilbare_personen_ids(konto) is None
    assert rechte.darf_einteilen(konto, person_b)


@pytest.mark.parametrize("rolle", [P, M, L])
def test_ohne_freigabe_nur_eigene_einteilung_sichtbar_und_nichts_einteilbar(konten, rolle, person_a):
    konto = konten[rolle]
    assert rechte.sichtbare_personen_ids(konto) == {konto.person_id}
    assert rechte.einteilbare_personen_ids(konto) == set()
    assert not rechte.darf_einteilen(konto, konto.person)
    assert not rechte.darf_sehen(konto, person_a)


def test_planer_mit_freigabe_fuer_a_sieht_b_nicht(konten, ansicht_a, person_a, person_b):
    planer = konten[P]
    freigeben(ansicht_a, planer, Recht.BEARBEITEN)
    assert rechte.darf_einteilen(planer, person_a)
    assert rechte.darf_sehen(planer, person_a)
    assert not rechte.darf_einteilen(planer, person_b)
    assert not rechte.darf_sehen(planer, person_b)


def test_nur_sehen_erlaubt_kein_einteilen(konten, ansicht_a, person_a):
    planer = konten[P]
    freigeben(ansicht_a, planer, Recht.SEHEN)
    assert rechte.darf_sehen(planer, person_a)
    assert not rechte.darf_einteilen(planer, person_a)
    assert not rechte.hat_planungsansicht(planer)


@pytest.mark.parametrize("rolle", [M, L])
def test_bearbeiten_wirkt_erst_ab_planer(konten, rolle, ansicht_a, person_a):
    konto = konten[rolle]
    freigeben(ansicht_a, konto, Recht.BEARBEITEN)
    assert rechte.darf_sehen(konto, person_a)
    assert not rechte.darf_einteilen(konto, person_a)
    assert rechte.freigaben(konto) == {ansicht_a.pk: Recht.SEHEN}


def test_hoechstes_recht_ueber_alle_ansichten(konten, bereich_a, ansicht_a, person_a):
    planer = konten[P]
    einzel = TeamplanerAnsicht.objects.create(name="Vertretung")
    einzel.personen.add(person_a)
    freigeben(ansicht_a, planer, Recht.SEHEN)
    freigeben(einzel, planer, Recht.BEARBEITEN)
    assert rechte.darf_einteilen(planer, person_a)


def test_neue_person_im_bereich_ist_automatisch_enthalten(konten, bereich_a, ansicht_a):
    planer = konten[P]
    freigeben(ansicht_a, planer)
    neu = Person.objects.create(anzeigename="Person 03", bereich=bereich_a)
    assert rechte.darf_einteilen(planer, neu)


def test_sichtbare_ansichten(konten, ansicht_a, ansicht_b):
    freigeben(ansicht_a, konten[M], Recht.SEHEN)
    assert list(rechte.sichtbare_ansichten(konten[M])) == [ansicht_a]
    assert set(rechte.sichtbare_ansichten(konten[BL])) == {ansicht_a, ansicht_b}
    assert list(rechte.sichtbare_ansichten(konten[L])) == []


def test_bereiche_der_ansicht_sind_beschriftet(konten, ansicht_a, bereich_b, client_fuer):
    """Jedes Kästchen trägt den Namen seines Bereichs (teile/auswahl.html)."""
    seite = client_fuer(konten[BL]).get(f"/einstellungen/ansichten/teamplaner/{ansicht_a.pk}/").content.decode()
    for name in ("Bereich A", "Bereich B"):
        assert re.search(rf'<label class="chip"><input[^>]*name="bereiche"[^>]*>(<svg.*?</svg>)?{name}</label>', seite), name
