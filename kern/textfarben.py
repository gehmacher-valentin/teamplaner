"""Schriftfarbe und Marker im Editor (frontend/src/editor/farben.ts): feste Palette.

Gespeichert als <span data-farbe="…"> und <mark data-farbe="…">; die Bereinigung (nh3) lässt nur diese
Werte durch, keine Inline-Styles. Die Farben selbst stehen im CSS (hell und dunkel).
"""

SCHRIFTFARBEN = {"rot", "orange", "gruen", "blau", "violett", "grau"}
MARKERFARBEN = {"gelb", "gruen", "blau", "rosa"}

TAGS = {"span", "mark"}
ATTRIBUTWERTE = {"span": {"data-farbe": SCHRIFTFARBEN}, "mark": {"data-farbe": MARKERFARBEN}}
