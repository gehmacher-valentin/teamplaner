"""Abhängigkeitsrichtung der Apps: verwaltung -> Fach-Apps -> kern (docs/entwicklung.md, Aufbau)."""

import ast
from pathlib import Path

WURZEL = Path(__file__).resolve().parent.parent
FACH_APPS = {"projekte", "planung", "gantt", "notizen", "bestellungen", "zusammenarbeit"}
OBEN = "verwaltung"


def _importe(app):
    """(Datei, importiertes Modul) für jeden Import der App, auch innerhalb von Funktionen."""
    for datei in sorted((WURZEL / app).rglob("*.py")):
        if "migrations" in datei.parts:
            continue
        for knoten in ast.walk(ast.parse(datei.read_text(encoding="utf-8"))):
            if isinstance(knoten, ast.Import):
                module = [a.name for a in knoten.names]
            elif isinstance(knoten, ast.ImportFrom) and knoten.level == 0:
                # "from gantt import dienste" zählt als gantt.dienste
                module = [f"{knoten.module}.{a.name}" for a in knoten.names]
            else:
                continue
            for modul in module:
                yield str(datei.relative_to(WURZEL)), modul


def _verstoesse(app, verboten):
    return sorted({f"{datei}: {modul}" for datei, modul in _importe(app) if modul.split(".")[0] in verboten})


def test_kern_ist_basis():
    assert _verstoesse("kern", FACH_APPS | {OBEN}) == [], "kern darf aus keiner anderen App importieren"


def test_fach_apps_kennen_die_verwaltung_nicht():
    for app in sorted(FACH_APPS):
        assert _verstoesse(app, {OBEN}) == [], f"{app} darf nicht aus verwaltung importieren"


def test_keine_importe_aus_fremden_views():
    """Gemeinsame Helfer gehören in ein eigenes Modul ohne View-Code."""
    for app in sorted(FACH_APPS | {"kern", OBEN}):
        fremd = sorted({f"{datei}: {modul}" for datei, modul in _importe(app)
                        if modul.split(".")[0] in (FACH_APPS | {"kern", OBEN}) - {app} and ".views" in f"{modul}."})
        assert fremd == [], f"{app} importiert aus der views.py einer anderen App"
