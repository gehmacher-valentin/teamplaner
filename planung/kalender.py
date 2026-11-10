"""Feiertage und Einteilungslogik – reine Funktionen ohne Datenbank (außer ``freie_tage``).

Regeln:

* Gesetzliche Feiertage Österreichs werden lokal berechnet, dazu kommen manuell
  ergänzte freie Tage. Wochenenden sind im Kalender sichtbar und werden wie
  Feiertage behandelt. Ein Balken Fr–Mo ist zusammenhängend.
* Mehrtägiger Balken über einen Feiertag oder ein Wochenende: diese Tage zählen nicht als eingeteilt.
* Eintägige Einteilung genau auf einem Feiertag oder Wochenendtag: zählt als eingeteilt (nach Bestätigung).
* Doppelbelegung: an einem Tag zählen mehrere Einteilungen einer Person oder Einteilung
  plus Abwesenheit. Sie wird nur markiert, nie verhindert.
"""

from collections import defaultdict
from datetime import date, timedelta
from functools import lru_cache

from django.utils.translation import gettext_lazy as _

from .models import FreierTag


def ostersonntag(jahr):
    """Gregorianischer Ostersonntag (anonymer gregorianischer Algorithmus)."""
    a = jahr % 19
    b, c = divmod(jahr, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7  # noqa: E741
    m = (a + 11 * h + 22 * l) // 451
    monat, tag = divmod(h + l - 7 * m + 114, 31)
    return date(jahr, monat, tag + 1)


@lru_cache(maxsize=64)
def gesetzliche_feiertage(jahr):
    """Die 13 gesetzlichen Feiertage Österreichs (Feiertagsruhegesetz) als ``{datum: name}``."""
    ostern = ostersonntag(jahr)
    return {
        date(jahr, 1, 1): _("Neujahr"),
        date(jahr, 1, 6): _("Heilige Drei Könige"),
        ostern + timedelta(days=1): _("Ostermontag"),
        date(jahr, 5, 1): _("Staatsfeiertag"),
        ostern + timedelta(days=39): _("Christi Himmelfahrt"),
        ostern + timedelta(days=50): _("Pfingstmontag"),
        ostern + timedelta(days=60): _("Fronleichnam"),
        date(jahr, 8, 15): _("Mariä Himmelfahrt"),
        date(jahr, 10, 26): _("Nationalfeiertag"),
        date(jahr, 11, 1): _("Allerheiligen"),
        date(jahr, 12, 8): _("Mariä Empfängnis"),
        date(jahr, 12, 25): _("Christtag"),
        date(jahr, 12, 26): _("Stefanitag"),
    }


def feiertage_im_zeitraum(von, bis):
    ergebnis = {}
    for jahr in range(von.year, bis.year + 1):
        for datum, name in gesetzliche_feiertage(jahr).items():
            if von <= datum <= bis:
                ergebnis[datum] = name
    return ergebnis


def freie_tage(von, bis):
    """Gesetzliche Feiertage plus manuell ergänzte freie Tage im Zeitraum (inklusive)."""
    ergebnis = feiertage_im_zeitraum(von, bis)
    for datum, bezeichnung in FreierTag.objects.filter(
        datum__gte=von, datum__lte=bis
    ).values_list("datum", "bezeichnung"):
        ergebnis.setdefault(datum, bezeichnung)
    return ergebnis


def freie_tage_mit_wochenende(von, bis):
    """Wie ``freie_tage``, dazu jedes Wochenende als „Wochenende“ – für Teamplaner und Kalender."""
    ergebnis = {d: _("Wochenende") for d in tage(von, bis) if ist_wochenende(d)}
    ergebnis.update(freie_tage(von, bis))
    return ergebnis


def ist_wochenende(datum):
    return datum.weekday() >= 5


def tage(von, bis):
    datum = von
    while datum <= bis:
        yield datum
        datum += timedelta(days=1)


def werktage(von, bis):
    """Mo–Fr im Zeitraum, Feiertage eingeschlossen (für Rasterspalten)."""
    return [d for d in tage(von, bis) if not ist_wochenende(d)]


def zaehlende_tage(von, bis, frei):
    """Tage, an denen eine Einteilung ``von``–``bis`` als eingeteilt zählt."""
    if von == bis:
        return [von]
    return [d for d in tage(von, bis) if not ist_wochenende(d) and d not in frei]


def abwesenheits_tage(von, bis):
    """Abwesend ist man an allen Tagen des Zeitraums (auch an Feiertagen und Wochenenden)."""
    return list(tage(von, bis))


def personentage(einteilungen, frei):
    """Summe der zählenden Tage über Einteilungen (Objekte mit ``von``/``bis``)."""
    return sum(len(zaehlende_tage(e.von, e.bis, frei)) for e in einteilungen)


def arbeitstage(einteilungen, frei):
    """Vereinigung der zählenden Tage aller Einteilungen einer Aufgabe."""
    ergebnis = set()
    for e in einteilungen:
        ergebnis.update(zaehlende_tage(e.von, e.bis, frei))
    return ergebnis


def belegung(einteilungen, abwesenheiten, frei):
    """``{(person_id, datum): anzahl}`` aus Einteilungen und Abwesenheiten."""
    zaehler = defaultdict(int)
    for e in einteilungen:
        for d in zaehlende_tage(e.von, e.bis, frei):
            zaehler[(e.person_id, d)] += 1
    for a in abwesenheiten:
        for d in abwesenheits_tage(a.von, a.bis):
            zaehler[(a.person_id, d)] += 1
    return zaehler


def doppelbelegungen(einteilungen, abwesenheiten, frei):
    """Menge ``{(person_id, datum)}`` mit mehr als einer Belegung."""
    return {schluessel for schluessel, n in belegung(einteilungen, abwesenheiten, frei).items() if n > 1}


def kalenderwoche(datum):
    return datum.isocalendar().week


def montag(datum):
    return datum - timedelta(days=datum.weekday())


def neue_freie_tage(von, bis, vorhanden):
    """Werktage von ``von`` bis ``bis``, die noch nicht frei sind: Wochenenden, gesetzliche
    Feiertage und schon eingetragene freie Tage (``vorhanden``) werden übersprungen."""
    gesetzlich = feiertage_im_zeitraum(von, bis)
    return [d for d in tage(von, bis) if not ist_wochenende(d) and d not in gesetzlich and d not in vorhanden]


def zeitraeume(freie):
    """Aufeinanderfolgende freie Tage mit derselben Bezeichnung als ein Zeitraum. Dazwischen
    liegende Wochenenden und gesetzliche Feiertage unterbrechen ihn nicht, z. B. Betriebsurlaub
    24.12.–02.01. ``freie``: nach Datum sortierte Objekte mit ``datum`` und ``bezeichnung``."""
    ergebnis = []
    for tag in freie:
        letzter = ergebnis[-1] if ergebnis else None
        if letzter and letzter["bezeichnung"] == tag.bezeichnung and tag.datum > letzter["bis"]:
            zwischen = tage(letzter["bis"] + timedelta(days=1), tag.datum - timedelta(days=1))
            gesetzlich = feiertage_im_zeitraum(letzter["bis"], tag.datum)
            if all(ist_wochenende(d) or d in gesetzlich for d in zwischen):
                letzter["bis"] = tag.datum
                letzter["tage"].append(tag)
                continue
        ergebnis.append({"von": tag.datum, "bis": tag.datum, "bezeichnung": tag.bezeichnung, "tage": [tag]})
    return ergebnis
