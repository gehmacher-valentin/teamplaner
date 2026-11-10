"""Markdown der Notizen in sicheres HTML umwandeln (eigenes HTML im Text wird entfernt).

Python-Markdown braucht für manche Eingaben quadratisch viel Zeit (viele öffnende eckige Klammern,
Backticks, unfertige HTML-Tags, tausende Kurzzeilen): schon 20 000 Zeichen können einen Worker
viele Sekunden binden. Eine Längengrenze allein reicht dagegen nicht, deshalb läuft jede Umwandlung
gegen eine Frist (``_befristet``); wird sie überschritten, erscheint der Text unformatiert.
"""

import html
import re
import sys
import threading
import time
from contextlib import contextmanager

import markdown as md
import nh3
from markdown.extensions import Extension

ERLAUBTE_TAGS = {
    "p", "br", "strong", "em", "del", "s", "code", "pre", "blockquote", "hr", "a",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
}

# Höchstdauer einer Umwandlung in Sekunden; gewöhnliche Notizen brauchen Millisekunden
FRIST_ANZEIGE = 1.0
FRIST_AUSZUG = 0.25
# Die Vorschau in der Übersicht zeigt nur den Anfang, mehr wird dafür nicht umgewandelt
AUSZUG_ZEICHEN = 1000


class _FristVorbei(Exception):
    pass


# Die Frist prüft ein Rückruf von sys.monitoring bei jedem Aufruf einer Python-Funktion im eigenen
# Thread. So bricht die Umwandlung ab, egal in welcher Schleife der Bibliothek sie festhängt.
_UEBERWACHUNG = sys.monitoring
_WERKZEUG = 4  # freie Kennung (0-2 und 5 sind für Debugger, Coverage, Profiler, Optimierer vorgesehen)
_lokal = threading.local()
_sperre = threading.Lock()
_laufend = 0


def _frist_pruefen(code, offset):
    ende = getattr(_lokal, "ende", None)
    if ende is not None and time.monotonic() > ende:
        raise _FristVorbei


try:
    _UEBERWACHUNG.use_tool_id(_WERKZEUG, "teamplaner-markdown")
    _UEBERWACHUNG.register_callback(_WERKZEUG, _UEBERWACHUNG.events.PY_START, _frist_pruefen)
    _UEBERWACHT = True
except ValueError:  # Kennung von einem anderen Werkzeug belegt: dann ohne Frist
    _UEBERWACHT = False


@contextmanager
def _befristet(sekunden):
    global _laufend
    if not _UEBERWACHT:
        yield
        return
    with _sperre:
        _laufend += 1
        _UEBERWACHUNG.set_events(_WERKZEUG, _UEBERWACHUNG.events.PY_START)
    _lokal.ende = time.monotonic() + sekunden
    try:
        yield
    finally:
        _lokal.ende = None
        with _sperre:
            _laufend -= 1
            if not _laufend:
                _UEBERWACHUNG.set_events(_WERKZEUG, 0)


class _Tilde(Extension):
    """Der Editor schreibt eine Tilde als „\\~“; ohne diese Erweiterung bliebe der Backslash stehen."""

    def extendMarkdown(self, md):  # noqa: N802 (Name von Python-Markdown vorgegeben)
        md.ESCAPED_CHARS.append("~")


def _umwandeln(text, erweiterungen, frist):
    """HTML aus Markdown, oder None, wenn die Frist abläuft oder der Text zu tief verschachtelt ist."""
    try:
        with _befristet(frist):
            return md.markdown(text, extensions=[*erweiterungen, _Tilde()], output_format="html")
    except (_FristVorbei, RecursionError):
        return None


def als_html(text):
    text = text or ""
    roh = _umwandeln(text, ["extra", "sane_lists", "nl2br"], FRIST_ANZEIGE)
    if roh is None:
        return "<p>" + html.escape(text).replace("\n", "<br>") + "</p>"
    return nh3.clean(
        roh, tags=ERLAUBTE_TAGS, attributes={"a": {"href", "title"}, "th": {"align"}, "td": {"align"}},
        url_schemes={"http", "https", "mailto"}, link_rel="noopener noreferrer nofollow",
    )


_BLOCKENDE = re.compile(r"</(p|li|h[1-6]|tr|blockquote|pre)>|<hr\s*/?>", re.I)
_ZELLE = re.compile(r"</t[dh]>|<br\s*/?>", re.I)
_TRENNER = "\ue000"  # Zeichen aus dem privaten Bereich, kommt im Text nicht vor


def als_text(text):
    """Einzeilige Vorschau ohne Markdown-Zeichen: Absätze, Listenpunkte und Tabellenzeilen mit „·“ getrennt."""
    text = (text or "")[:AUSZUG_ZEICHEN]
    roh = _umwandeln(text, ["extra", "sane_lists"], FRIST_AUSZUG)
    if roh is None:
        return re.sub(r"\s+", " ", text).strip()
    roh = _ZELLE.sub(" ", _BLOCKENDE.sub(_TRENNER, roh))
    roh = html.unescape(nh3.clean(roh, tags=set()))
    teile = (re.sub(r"\s+", " ", t).strip() for t in roh.split(_TRENNER))
    return " · ".join(t for t in teile if t)
