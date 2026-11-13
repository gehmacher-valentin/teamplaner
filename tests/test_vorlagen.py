"""Vorlagen: keine Kommentare, die Django als Text ausgibt."""

from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string


def test_keine_mehrzeiligen_kurzkommentare():
    """``{# ... #}`` gilt nur innerhalb einer Zeile. Mit Zeilenumbruch erscheint der Kommentar als
    Text auf der Seite; dafür gibt es ``{% comment %}``."""
    funde = []
    for ordner in settings.TEMPLATES[0]["DIRS"]:
        for datei in sorted(Path(ordner).rglob("*.html")):
            for nr, zeile in enumerate(datei.read_text(encoding="utf-8").splitlines(), 1):
                if zeile.count("{#") != zeile.count("#}"):
                    funde.append(f"{datei.relative_to(ordner)}:{nr}")
    assert funde == []


def test_anhang_kacheln_ohne_kommentartext():
    assert "{#" not in render_to_string("teile/anhaenge.html", {"anhaenge": []})
