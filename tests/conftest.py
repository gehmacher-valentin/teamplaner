"""Gemeinsame Testdaten – nur Platzhalternamen („Person 01“), keine echten Namen."""

import asyncio
import time
from contextlib import contextmanager
from datetime import date
from importlib import import_module

import pytest
from asgiref.sync import sync_to_async
from django.conf import settings
from django.db import connections
from django.test import Client, RequestFactory
from rest_framework.test import APIClient

from kern.middleware import LETZTE_AKTIVITAET
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
def mails_sofort(settings):
    """Benachrichtigungen ohne Sammelfenster; das Zusammenfassen prüft tests/test_mail_sammeln.py."""
    settings.TEAMPLANER_MAIL_SAMMELN_SEKUNDEN = 0


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


# --- Datenbankstand bei Rechte-Tests ---
# Ein 403 beweist nicht, dass nichts geschrieben wurde (eine View könnte erst speichern und dann prüfen),
# ein 2xx nicht, dass gespeichert wurde. Rechte-Tests für Schreibzugriffe prüfen deshalb beides.

def _zeile(obj):
    return type(obj).objects.filter(pk=obj.pk).values().first()


@contextmanager
def unveraendert(*objekte):
    """Die Zeilen der Objekte stehen danach genau so in der Datenbank wie vorher (und existieren noch)."""
    vorher = [_zeile(o) for o in objekte]
    assert None not in vorher, "Objekt fehlt schon vorher in der Datenbank"
    yield
    for obj, zeile in zip(objekte, vorher, strict=True):
        assert _zeile(obj) == zeile, f"{type(obj).__name__} {obj.pk} geändert"


@contextmanager
def anzahl_gleich(*modelle):
    """Keine Zeile angelegt oder gelöscht."""
    vorher = [m.objects.count() for m in modelle]
    yield
    assert [m.objects.count() for m in modelle] == vorher, [m.__name__ for m in modelle]


@contextmanager
def nichts_geaendert(*objekte_oder_modelle):
    """``unveraendert`` für Objekte und ``anzahl_gleich`` für Modelle in einem."""
    modelle = [o for o in objekte_oder_modelle if isinstance(o, type)]
    objekte = [o for o in objekte_oder_modelle if not isinstance(o, type)]
    with anzahl_gleich(*modelle), unveraendert(*objekte):
        yield

# --- Live-Verbindung (SSE) direkt aus der View lesen ---

class SseLeser:
    """Liest die Teile eines SSE-Streams, wie die View sie erzeugt."""

    def __init__(self, antwort):
        self.teile = antwort.streaming_content.__aiter__()

    async def naechstes(self):
        return (await asyncio.wait_for(self.teile.__anext__(), timeout=5)).decode()

    async def endet(self):
        try:
            await asyncio.wait_for(self.teile.__anext__(), timeout=5)
        except StopAsyncIteration:
            return True
        return False


def stream_anfrage(konto, pfad):
    """Anfrage wie nach der AuthenticationMiddleware: Konto und Sitzung eines angemeldeten Clients."""
    client = Client()
    client.force_login(konto)
    sitzung = client.session
    sitzung[LETZTE_AKTIVITAET] = time.time()
    sitzung.save()
    anfrage = RequestFactory().get(pfad)
    anfrage.session = import_module(settings.SESSION_ENGINE).SessionStore(sitzung.session_key)

    async def auser():
        return konto

    anfrage.auser = auser
    return anfrage


async def mit_eigener_verbindung(ablauf):
    """sync_to_async öffnet im Hilfsthread eine eigene Datenbankverbindung; danach wieder schließen,
    sonst lässt sich die Testdatenbank nicht löschen. Tests damit brauchen ``transaction=True``."""
    try:
        await ablauf()
    finally:
        await sync_to_async(connections.close_all)()


@pytest.fixture
def eigene_warteschlange(monkeypatch):
    """Verteiler ohne LISTEN-Verbindung: der Test legt die Ereignisse selbst in die Warteschlange."""

    def ersetzen(verteiler):
        schlangen = []

        def anmelden():
            schlangen.append(asyncio.Queue())
            return schlangen[-1]

        monkeypatch.setattr(verteiler, "anmelden", anmelden)
        monkeypatch.setattr(verteiler, "abmelden", lambda warteschlange: None)
        return schlangen

    return ersetzen
