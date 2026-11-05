"""Einträge ins Änderungsprotokoll schreiben."""

from datetime import date, datetime
from decimal import Decimal

from .models import Protokolleintrag


def _json(wert):
    if isinstance(wert, (date, datetime)):
        return wert.isoformat()
    if isinstance(wert, Decimal):
        return str(wert)
    if hasattr(wert, "pk"):
        return {"id": wert.pk, "name": str(wert)}
    return wert


def protokollieren(akteur, objekt_typ, objekt_id, aktion, daten=None, aufgabe_id=None):
    """``akteur`` ist ein Konto oder eine Person (oder None für Systemaktionen)."""
    person = getattr(akteur, "person", akteur)
    return Protokolleintrag.objects.create(
        akteur=person,
        objekt_typ=objekt_typ,
        objekt_id=objekt_id,
        aktion=aktion,
        aufgabe_id=aufgabe_id,
        daten={k: _json(v) for k, v in (daten or {}).items()},
    )


def aenderungen(alt, neu):
    """Dict ``{feld: [alt, neu]}`` für alle geänderten Felder."""
    return {
        feld: [_json(alt.get(feld)), _json(wert)]
        for feld, wert in neu.items()
        if alt.get(feld) != wert
    }
