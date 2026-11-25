"""Jede Route verlangt eine Anmeldung.

Es gibt keine globale Login-Pflicht, jede View hängt an ihrem ``@erfordert`` (bzw. prüft in der API
selbst). Dieser Test läuft über alle Routen der Anwendung und schützt davor, dass eine neue View die
Prüfung vergisst. Platzhalter in den Pfaden werden durch ``1`` bzw. ``x`` ersetzt; da die Anmeldung vor
dem Laden der Objekte geprüft wird, muss es die Objekte dafür nicht geben.
"""

import re

import pytest
from django.test import Client
from django.urls import URLResolver, get_resolver

# Route-Name: warum sie ohne Anmeldung erreichbar ist
OEFFENTLICH = {
    "login": "Anmeldeseite",
    "gesund": "Gesundheitsprüfung für Webserver und Installationsprobe",
    "passwort_setzen": "Link aus der Einladungs- bzw. Passwort-Mail, prüft selbst Benutzer und Token",
    "set_language": "Sprachwahl von Django, ändert nur ein Cookie",
}


def routen(muster=None, praefix=""):
    for eintrag in get_resolver().url_patterns if muster is None else muster:
        teil = str(eintrag.pattern)
        if isinstance(eintrag, URLResolver):
            yield from routen(eintrag.url_patterns, praefix + teil)
        else:
            yield praefix + teil, eintrag.name


def konkret(route):
    route = re.sub(r"<int:\w+>", "1", route)
    route = re.sub(r"<uuid:\w+>", "00000000-0000-0000-0000-000000000000", route)
    route = re.sub(r"<(?:str:|slug:|path:)?\w+>", "x", route)
    return "/" + route.lstrip("^").rstrip("$")


ALLE = sorted({(konkret(route), name) for route, name in routen()})


def test_alle_routen_erfasst():
    assert len(ALLE) > 120
    assert not [url for url, _name in ALLE if "<" in url or "(" in url], "Platzhalter nicht ersetzt"
    assert set(OEFFENTLICH) <= {name for _url, name in ALLE}, "Ausnahme ohne passende Route"


def abgewiesen(antwort):
    if antwort.status_code == 302:
        return antwort["Location"].split("?", 1)[0] == "/anmelden/"
    return antwort.status_code == 401


@pytest.mark.parametrize("url, name", [r for r in ALLE if r[1] not in OEFFENTLICH], ids=lambda w: str(w))
def test_ohne_anmeldung_abgewiesen(db, url, name):
    get, post = Client().get(url), Client().post(url)
    # Reine POST-Routen lehnen GET schon vorher ab (405); dann muss POST abgewiesen werden
    assert abgewiesen(get) or get.status_code == 405, (url, "GET", get.status_code, get.get("Location"))
    assert abgewiesen(post), (url, "POST", post.status_code, post.get("Location"))
