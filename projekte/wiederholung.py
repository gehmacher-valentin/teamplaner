"""Wiederkehrende Aufgaben: Regel prüfen, nächsten Termin berechnen, Regel als Text.

Eine Regel ist ein kleines Dict (``Aufgabe.wiederholung``)::

    {"frequenz": "woechentlich", "intervall": 2, "wochentage": [0, 2], "bis": "2027-06-30", "tag": 15, "monat": 3}

``tag`` und ``monat`` sind der Anker für monatlich/jährlich: „monatlich am 31.“ fällt in kürzeren Monaten auf den
letzten Tag, kehrt danach aber zum 31. zurück. Der Stichtag (``faellig_am``) gilt als Kalendertag; Wochenenden,
Feiertage und freie Tage spielen keine Rolle.

„Vierteljährlich“ und „Halbjährlich“ sind nur Einträge der Auswahl: gespeichert als monatlich alle 3 bzw. 6 Monate.
"""

import calendar
from datetime import date, timedelta

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext, npgettext

FREQUENZEN = [
    ("taeglich", gettext_lazy("Täglich")),
    ("woechentlich", gettext_lazy("Wöchentlich")),
    ("monatlich", gettext_lazy("Monatlich")),
    ("jaehrlich", gettext_lazy("Jährlich")),
]
# Einträge der Auswahl, die als monatlich mit festem Intervall gespeichert werden (ohne Feld „alle …“)
MONATSVIELFACHE = {
    "vierteljaehrlich": (3, gettext_lazy("Vierteljährlich")),
    "halbjaehrlich": (6, gettext_lazy("Halbjährlich")),
}
# Auswahl im Aufgabendetail in der Reihenfolge der Abstände
AUSWAHL = [*FREQUENZEN[:3], *((wert, name) for wert, (_n, name) in MONATSVIELFACHE.items()), FREQUENZEN[3]]
INTERVALL_MAX = 99


class UngueltigeRegel(ValueError):
    """Eingabe der Wiederholung abgelehnt."""


def wochentag_namen():
    return [_("Mo"), _("Di"), _("Mi"), _("Do"), _("Fr"), _("Sa"), _("So")]


def regel_bauen(frequenz, intervall=1, wochentage=(), bis=None, stichtag=None):
    """Prüft die Eingabe und gibt die Regel zurück (None = keine Wiederholung).

    ``intervall`` und ``wochentage`` dürfen Text sein (Formular); ``bis`` ein Datum oder ISO-Text.
    """
    if not frequenz:
        return None
    if frequenz in MONATSVIELFACHE:
        frequenz, intervall = "monatlich", MONATSVIELFACHE[frequenz][0]
    if frequenz not in dict(FREQUENZEN):
        raise UngueltigeRegel(_("Ungültige Eingabe."))
    try:
        intervall = int(intervall or 1)
        tage = sorted({int(t) for t in wochentage if str(t).strip() != ""})
        if isinstance(bis, str):
            bis = date.fromisoformat(bis) if bis.strip() else None
    except ValueError as fehler:
        raise UngueltigeRegel(_("Ungültige Eingabe.")) from fehler
    if not 1 <= intervall <= INTERVALL_MAX:
        raise UngueltigeRegel(_("Das Intervall muss zwischen 1 und %(n)s liegen.") % {"n": INTERVALL_MAX})
    if any(t < 0 or t > 6 for t in tage):
        raise UngueltigeRegel(_("Ungültige Eingabe."))
    if stichtag and bis and bis < stichtag:
        raise UngueltigeRegel(_("Das Enddatum liegt vor dem Stichtag."))
    regel = {"frequenz": frequenz, "intervall": intervall}
    if frequenz == "woechentlich" and tage:
        regel["wochentage"] = tage
    if bis:
        regel["bis"] = bis.isoformat()
    return mit_anker(regel, stichtag)


def mit_anker(regel, stichtag):
    """Tag (und Monat) des Stichtags als Anker für monatlich/jährlich."""
    if not regel:
        return regel
    regel = {k: v for k, v in regel.items() if k not in ("tag", "monat")}
    if stichtag and regel["frequenz"] in ("monatlich", "jaehrlich"):
        regel["tag"] = stichtag.day
        if regel["frequenz"] == "jaehrlich":
            regel["monat"] = stichtag.month
    return regel


def auswahl(regel):
    """Eintrag der Auswahl zu einer gespeicherten Regel: monatlich alle 3 bzw. 6 Monate als eigener Eintrag."""
    if not regel:
        return ""
    if regel["frequenz"] == "monatlich":
        n = int(regel.get("intervall") or 1)
        for wert, (monate, _name) in MONATSVIELFACHE.items():
            if n == monate:
                return wert
    return regel["frequenz"]


def mit_intervall(regel):
    """Ob die Eingabe „alle … “ angeboten wird (nicht bei vierteljährlich und halbjährlich)."""
    return bool(regel) and auswahl(regel) not in MONATSVIELFACHE


def _tag_im_monat(jahr, monat, tag):
    return date(jahr, monat, min(tag, calendar.monthrange(jahr, monat)[1]))


def naechster_termin(stichtag, regel):
    """Nächster Termin nach ``stichtag`` laut Regel – vom bisherigen Stichtag aus, nicht vom Tag des Abhakens."""
    n = max(1, int(regel.get("intervall") or 1))
    frequenz = regel["frequenz"]
    if frequenz == "taeglich":
        return stichtag + timedelta(days=n)
    if frequenz == "woechentlich":
        tage = set(regel.get("wochentage") or [])
        if not tage:
            return stichtag + timedelta(weeks=n)
        montag = stichtag - timedelta(days=stichtag.weekday())
        d = stichtag + timedelta(days=1)
        # Nur in jeder n-ten Woche (gezählt ab der Woche des Stichtags) an den gewählten Wochentagen
        while True:
            if ((d - montag).days // 7) % n == 0 and d.weekday() in tage:
                return d
            d += timedelta(days=1)
    tag = regel.get("tag") or stichtag.day
    if frequenz == "monatlich":
        monate = stichtag.year * 12 + stichtag.month - 1 + n
        return _tag_im_monat(monate // 12, monate % 12 + 1, tag)
    if frequenz == "jaehrlich":
        return _tag_im_monat(stichtag.year + n, regel.get("monat") or stichtag.month, tag)
    raise UngueltigeRegel(frequenz)


def ende(regel):
    bis = (regel or {}).get("bis")
    return date.fromisoformat(bis) if bis else None


def regel_text(regel):
    """„Alle 2 Wochen (Mo, Mi) bis 30.06.2027“ – für Anzeige und Verlauf."""
    if not regel:
        return ""
    n = int(regel.get("intervall") or 1)
    frequenz = regel["frequenz"]
    if auswahl(regel) in MONATSVIELFACHE:
        text = str(MONATSVIELFACHE[auswahl(regel)][1])
    elif n == 1:
        text = str(dict(FREQUENZEN)[frequenz])
    else:
        text = {
            "taeglich": ngettext("Alle %(n)s Tage", "Alle %(n)s Tage", n),
            "woechentlich": ngettext("Alle %(n)s Wochen", "Alle %(n)s Wochen", n),
            "monatlich": ngettext("Alle %(n)s Monate", "Alle %(n)s Monate", n),
            "jaehrlich": ngettext("Alle %(n)s Jahre", "Alle %(n)s Jahre", n),
        }[frequenz] % {"n": n}
    if regel.get("wochentage"):
        namen = wochentag_namen()
        text += " (" + ", ".join(namen[t] for t in regel["wochentage"]) + ")"
    if regel.get("bis"):
        text += " " + _("bis %(datum)s") % {"datum": ende(regel).strftime("%d.%m.%Y")}
    return text


def einheit(regel):
    """Einheit hinter „alle n …“ im Eingabefeld."""
    n = int((regel or {}).get("intervall") or 1)
    return {
        "taeglich": npgettext("Wiederholung", "Tag", "Tage", n),
        "woechentlich": npgettext("Wiederholung", "Woche", "Wochen", n),
        "monatlich": npgettext("Wiederholung", "Monat", "Monate", n),
        "jaehrlich": npgettext("Wiederholung", "Jahr", "Jahre", n),
    }.get((regel or {}).get("frequenz"), "")
