"""Rechtematrix je Rolle (Rechtematrix) – Funktionsebene.

Die serverseitige Durchsetzung an den Endpunkten prüfen test_planung_api.py und
test_seiten_rechte.py.
"""

import pytest

from kern import rechte
from kern.models import Rolle

from .conftest import ROLLEN

A, BL, P, M, L = ROLLEN

# (Prüffunktion, Rollen mit Recht)
MATRIX = [
    (rechte.darf_systemeinstellungen, {A}),
    (rechte.darf_konten_verwalten, {A, BL}),
    (rechte.darf_projekte_verwalten, {A, BL, P}),
    (rechte.darf_abschliessen_und_kommentieren, {A, BL, P, M}),
    (rechte.darf_bestellungen_bearbeiten, {A, BL, P, M}),
    (rechte.darf_planen, {A, BL, P}),
    (rechte.darf_platzhalter_verwalten, {A, BL, P}),
    (rechte.darf_lesen, {A, BL, P, M, L}),
    (rechte.darf_protokoll_sehen, {A, BL}),
    (rechte.darf_erledigte_sehen, {A, BL, P}),
    (rechte.darf_ansichten_verwalten, {A, BL}),
    (rechte.sieht_alles_im_teamplaner, {A, BL}),
]


@pytest.mark.django_db
@pytest.mark.parametrize("pruefung, erlaubt", MATRIX, ids=[m[0].__name__ for m in MATRIX])
@pytest.mark.parametrize("rolle", ROLLEN)
def test_rechtematrix(konten, pruefung, erlaubt, rolle):
    assert pruefung(konten[rolle]) is (rolle in erlaubt)


@pytest.mark.django_db
@pytest.mark.parametrize("rolle", ROLLEN)
def test_deaktiviertes_konto_hat_keine_rechte(konten, rolle):
    konto = konten[rolle]
    konto.person.archivieren()
    for pruefung, _ in MATRIX:
        assert pruefung(konto) is False


def test_nicht_angemeldet_hat_keine_rechte():
    from django.contrib.auth.models import AnonymousUser

    for pruefung, _ in MATRIX:
        assert pruefung(AnonymousUser()) is False


@pytest.mark.django_db
def test_rollen_vergeben_bis_zur_eigenen_rolle(konten):
    assert set(rechte.vergebbare_rollen(konten[A])) == set(Rolle)
    assert set(rechte.vergebbare_rollen(konten[BL])) == {BL, P, M, L}
    assert rechte.vergebbare_rollen(konten[P]) == []
    # Bereichsleitung darf kein Admin-Konto ändern und niemanden zum Admin machen
    assert not rechte.darf_konto_bearbeiten(konten[BL], konten[A])
    assert not rechte.darf_rolle_vergeben(konten[BL], konten[M], A)
    assert rechte.darf_rolle_vergeben(konten[BL], konten[M], BL)
    assert rechte.darf_rolle_vergeben(konten[A], konten[BL], A)


@pytest.mark.django_db
def test_konten_gleicher_rolle_nur_durch_hoehere_rolle(konten, bereich_a):
    """Sonst könnten sich Kolleg:innen gleicher Rolle gegenseitig übernehmen."""
    from .conftest import konto_anlegen

    andere_bl = konto_anlegen("Person 03", bereich_a, BL)
    anderer_admin = konto_anlegen("Person 91", bereich_a, A)
    assert not rechte.darf_konto_bearbeiten(konten[BL], andere_bl)
    assert not rechte.darf_konto_bearbeiten(konten[A], anderer_admin)
    assert rechte.darf_konto_bearbeiten(konten[A], andere_bl)
    assert rechte.darf_konto_bearbeiten(konten[BL], konten[P])
    # Eigenes Konto: ja, aber ohne die eigene Rolle
    assert rechte.darf_konto_bearbeiten(konten[BL], konten[BL])
    assert rechte.darf_rolle_vergeben(konten[BL], konten[BL], BL)
    assert not rechte.darf_rolle_vergeben(konten[BL], konten[BL], P)
    assert not rechte.darf_konto_bearbeiten(konten[P], konten[P])


@pytest.mark.django_db
def test_aufgaben_bearbeiten_mitarbeiter_nur_als_projektmitglied(konten, projekt):
    assert rechte.darf_aufgaben_bearbeiten(konten[P], projekt)
    assert not rechte.darf_aufgaben_bearbeiten(konten[M], projekt)
    assert not rechte.darf_aufgaben_bearbeiten(konten[L], projekt)
    projekt.mitglieder.add(konten[M].person, konten[L].person)
    assert rechte.darf_aufgaben_bearbeiten(konten[M], projekt)
    assert not rechte.darf_aufgaben_bearbeiten(konten[L], projekt)  # Lesend nie
