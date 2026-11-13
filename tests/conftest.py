"""Gemeinsame Testdaten – nur Platzhalternamen („Person 01“), keine echten Namen."""

from datetime import date

import pytest
from rest_framework.test import APIClient

from kern.models import Bereich, Konto, Person, Rolle
from planung.models import AnsichtFreigabe, Recht, TeamplanerAnsicht
from projekte.models import Abschnitt, Aufgabe, Projekt, Status

TESTPASSWORT = "Testpasswort-2026!"

# Feste Testwoche: Mo 19.10.2026 … Fr 30.10.2026, Mo 26.10. ist Nationalfeiertag
MO = date(2026, 10, 19)
DI = date(2026, 10, 20)
MI = date(2026, 10, 21)
DO = date(2026, 10, 22)
FR = date(2026, 10, 23)
SA = date(2026, 10, 24)
SO = date(2026, 10, 25)
FEIERTAG = date(2026, 10, 26)
DI2 = date(2026, 10, 27)
MI2 = date(2026, 10, 28)

ROLLEN = [Rolle.ADMIN, Rolle.BEREICHSLEITUNG, Rolle.PLANER, Rolle.MITARBEITER, Rolle.LESEND]


def konto_anlegen(name, bereich, rolle):
    email = name.lower().replace(" ", ".") + "@example.test"
    return Konto.objects.anlegen(email, anzeigename=name, bereich=bereich, rolle=rolle, password=TESTPASSWORT)


@pytest.fixture(autouse=True)
def ohne_zwei_faktor_pflicht(settings):
    """Die meisten Tests melden Admin/Bereichsleitung per force_login an; die Pflicht zum zweiten
    Faktor prüft tests/test_zwei_faktor.py gezielt."""
    settings.TEAMPLANER_ZWEI_FAKTOR_PFLICHT = False


@pytest.fixture(autouse=True)
def schneller_passwort_hasher(request, settings):
    """Argon2 kostet je Testkonto rund 0,1 s und damit den Großteil der Laufzeit. Tests, die das
    Verfahren selbst prüfen, tragen ``@pytest.mark.argon2`` und laufen mit der Betriebseinstellung."""
    if "argon2" not in request.keywords:
        settings.PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]


@pytest.fixture(autouse=True)
def sprache_zuruecksetzen():
    """Jeder Test beginnt auf Deutsch, auch wenn ein vorheriger Englisch aktiviert hat."""
    from django.utils import translation

    translation.activate("de")
    yield
    translation.activate("de")


@pytest.fixture
def bereich_a(db):
    return Bereich.objects.create(name="Bereich A", sortierung=10)


@pytest.fixture
def bereich_b(db):
    return Bereich.objects.create(name="Bereich B", sortierung=20)


@pytest.fixture
def konten(bereich_a):
    """Je Rolle ein Konto im Bereich A."""
    namen = {
        Rolle.ADMIN: "Person 90",
        Rolle.BEREICHSLEITUNG: "Person 00",
        Rolle.PLANER: "Person 05",
        Rolle.MITARBEITER: "Person 01",
        Rolle.LESEND: "Person 09",
    }
    return {rolle: konto_anlegen(name, bereich_a, rolle) for rolle, name in namen.items()}


@pytest.fixture
def person_a(bereich_a):
    return Person.objects.create(anzeigename="Person 02", bereich=bereich_a)


@pytest.fixture
def person_b(bereich_b):
    return Person.objects.create(anzeigename="Person 11", bereich=bereich_b)


@pytest.fixture
def platzhalter(bereich_a, konten):
    return Person.objects.create(
        anzeigename="Aushilfe Montage", bereich=bereich_a, erstellt_von=konten[Rolle.PLANER].person
    )


@pytest.fixture
def projekt(konten):
    return Projekt.objects.create(name="Neubau Lagerhalle", farbe="bernstein",
                                  projektleitung=konten[Rolle.BEREICHSLEITUNG].person)


@pytest.fixture
def abschnitt(projekt):
    return Abschnitt.objects.create(projekt=projekt, name="Fertigung")


@pytest.fixture
def aufgabe(projekt, abschnitt):
    return Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel="Hallenboden Nord",
                                  status=Status.standard_offen(), schaetzung_personentage=4)


@pytest.fixture
def ansicht_a(bereich_a):
    ansicht = TeamplanerAnsicht.objects.create(name="Bereich A")
    ansicht.bereiche.add(bereich_a)
    return ansicht


@pytest.fixture
def ansicht_b(bereich_b):
    ansicht = TeamplanerAnsicht.objects.create(name="Bereich B")
    ansicht.bereiche.add(bereich_b)
    return ansicht


def freigeben(ansicht, konto, recht=Recht.BEARBEITEN):
    return AnsichtFreigabe.objects.create(ansicht=ansicht, konto=konto, recht=recht)


@pytest.fixture
def client_fuer():
    def erzeugen(konto):
        client = APIClient()
        if konto is not None:
            client.force_login(konto)
        return client

    return erzeugen
