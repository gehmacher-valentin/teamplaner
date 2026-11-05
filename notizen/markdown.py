"""Markdown der Notizen in sicheres HTML umwandeln (eigenes HTML im Text wird entfernt)."""

import html
import re

import markdown as md
import nh3
from markdown.extensions import Extension

ERLAUBTE_TAGS = {
    "p", "br", "strong", "em", "del", "s", "code", "pre", "blockquote", "hr", "a",
    "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td",
}


class _Tilde(Extension):
    """Der Editor schreibt eine Tilde als „\\~“; ohne diese Erweiterung bliebe der Backslash stehen."""

    def extendMarkdown(self, md):  # noqa: N802 (Name von Python-Markdown vorgegeben)
        md.ESCAPED_CHARS.append("~")


def als_html(text):
    html = md.markdown(text or "", extensions=["extra", "sane_lists", "nl2br", _Tilde()], output_format="html")
    return nh3.clean(
        html, tags=ERLAUBTE_TAGS, attributes={"a": {"href", "title"}, "th": {"align"}, "td": {"align"}},
        url_schemes={"http", "https", "mailto"}, link_rel="noopener noreferrer nofollow",
    )


_BLOCKENDE = re.compile(r"</(p|li|h[1-6]|tr|blockquote|pre)>|<hr\s*/?>", re.I)
_ZELLE = re.compile(r"</t[dh]>|<br\s*/?>", re.I)
_TRENNER = "\ue000"  # Zeichen aus dem privaten Bereich, kommt im Text nicht vor


def als_text(text):
    """Einzeilige Vorschau ohne Markdown-Zeichen: Absätze, Listenpunkte und Tabellenzeilen mit „·“ getrennt."""
    roh = md.markdown(text or "", extensions=["extra", "sane_lists", _Tilde()], output_format="html")
    roh = _ZELLE.sub(" ", _BLOCKENDE.sub(_TRENNER, roh))
    roh = html.unescape(nh3.clean(roh, tags=set()))
    teile = (re.sub(r"\s+", " ", t).strip() for t in roh.split(_TRENNER))
    return " · ".join(t for t in teile if t)
