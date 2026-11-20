"""Formatierung aus dem Editor: Überschriften H1–H3, Schriftfarbe und Marker. Bereinigung der
Beschreibungen (HTML) und Anzeige der Notizen (Markdown)."""

from notizen.markdown import als_html, als_text
from projekte.dienste import html_bereinigen


def test_beschreibung_ueberschriften_h1_bis_h3():
    html = "<h1>Ablauf</h1><h2>Teil</h2><h3>Schritt</h3>"
    assert html_bereinigen(html) == html
    assert html_bereinigen("<h4>Tiefer</h4>") == "Tiefer"


def test_beschreibung_behaelt_gueltige_farben():
    html = '<p><span data-farbe="rot">Achtung</span> und <mark data-farbe="gelb">wichtig</mark></p>'
    assert html_bereinigen(html) == html


def test_beschreibung_entfernt_ungueltige_werte_und_styles():
    sauber = html_bereinigen(
        '<p><span data-farbe="pink" style="color:red" onclick="x()">a</span>'
        '<mark data-farbe="rot" class="y">b</mark><span data-farbe="blau">c</span></p>'
    )
    assert sauber == '<p><span>a</span><mark>b</mark><span data-farbe="blau">c</span></p>'


def test_notiz_zeigt_farben_aus_markdown():
    text = 'Termin <span data-farbe="gruen">**fix**</span> und <mark data-farbe="rosa">offen</mark>'
    html = als_html(text)
    assert '<span data-farbe="gruen"><strong>fix</strong></span>' in html
    assert '<mark data-farbe="rosa">offen</mark>' in html
    assert als_text(text) == "Termin fix und offen"


def test_notiz_entfernt_fremde_farben():
    html = als_html('<span data-farbe="x" style="color:red">a</span> <mark data-farbe="gelb" onmouseover="y()">b</mark>')
    assert "style" not in html and "onmouseover" not in html and 'data-farbe="x"' not in html
    assert '<mark data-farbe="gelb">b</mark>' in html
