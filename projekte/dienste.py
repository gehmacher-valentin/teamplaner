"""Aufgaben ändern mit Konfliktschutz, Verlauf und Benachrichtigung."""

import nh3
from django.db import transaction
from django.db.models import F, Max
from django.utils import timezone

from kern.hilfen import als_zahl
from kern.protokoll import aenderungen, protokollieren
from planung.dienste import einteilungen_entfernt_melden
from zusammenarbeit.dienste import (
    aufgabe_geaendert_benachrichtigen,
    projekt_aufgabe_benachrichtigen,
    zuweisung_benachrichtigen,
)

from . import termine
from .models import UNTERAUFGABEN_EBENEN, Aufgabe, Status

ERLAUBTE_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "h3", "a", "blockquote", "code", "pre",
                 "hr"}

VERLAUF_FELDER = ["titel", "abschnitt", "verantwortlich", "gewerk", "beginn_am", "faellig_am", "status",
                  "schaetzung_personentage", "beschreibung"]


class Konflikt(Exception):
    """Die Aufgabe wurde inzwischen von jemand anderem geändert."""


class KeineUnteraufgabe(Exception):
    """Unteraufgaben gibt es höchstens UNTERAUFGABEN_EBENEN Ebenen tief."""


class UngueltigesZiel(Exception):
    """Verschieben in die eigene Unteraufgabe, in ein anderes Projekt oder zu tief."""


def nachkommen(aufgabe_id):
    """IDs aller Unteraufgaben (alle Ebenen)."""
    ergebnis, ebene = [], [aufgabe_id]
    while ebene:
        ebene = list(Aufgabe.objects.filter(eltern_id__in=ebene).values_list("pk", flat=True))
        ergebnis.extend(ebene)
    return ergebnis


def hoehe(aufgabe_id):
    """Wie viele Ebenen Unteraufgaben unter der Aufgabe hängen (0 = keine)."""
    ebenen, ebene = 0, [aufgabe_id]
    while True:
        ebene = list(Aufgabe.objects.filter(eltern_id__in=ebene).values_list("pk", flat=True))
        if not ebene:
            return ebenen
        ebenen += 1


def darf_unteraufgaben_haben(aufgabe):
    return aufgabe.tiefe < UNTERAUFGABEN_EBENEN


def html_bereinigen(html):
    return nh3.clean(html or "", tags=ERLAUBTE_TAGS, attributes={"a": {"href"}},
                     link_rel="noopener noreferrer nofollow").strip()


def _schnappschuss(aufgabe):
    return {feld: getattr(aufgabe, feld) for feld in VERLAUF_FELDER}


def _verlauf_diff(alt, neu):
    """Geänderte Felder fürs Protokoll; die Beschreibung nur als „…“, ihr Inhalt kommt nicht hinein."""
    diff = aenderungen(alt, neu)
    if "beschreibung" in diff:
        diff["beschreibung"] = ["…" if alt["beschreibung"] else "", "…" if neu["beschreibung"] else ""]
    return diff


def aufgabe_speichern(konto, aufgabe, daten, version, nachziehen=True):
    """Übernimmt ``daten`` (Feld → Wert), wenn ``version`` noch aktuell ist.

    Geänderte Termine ziehen Hauptaufgaben und Nachfolger nach (``projekte.termine``);
    ``nachziehen=False`` nur für die Folgeänderungen selbst.
    """
    with transaction.atomic():
        aktuell = Aufgabe.objects.select_for_update().get(pk=aufgabe.pk)
        if version is not None and als_zahl(version) != aktuell.version:
            raise Konflikt
        if aktuell.eltern_id:
            # Unteraufgaben liegen immer im Abschnitt ihrer Hauptaufgabe
            daten = {k: v for k, v in daten.items() if k != "abschnitt"}
        alt = _schnappschuss(aktuell)
        war_erledigt = aktuell.status.ist_erledigt
        alter_verantwortlicher = aktuell.verantwortlich_id
        for feld, wert in daten.items():
            if feld == "beschreibung":
                wert = html_bereinigen(wert)
            setattr(aktuell, feld, wert)
        if "status" in daten:
            if aktuell.status.ist_erledigt and aktuell.erledigt_am is None:
                aktuell.erledigt_am = timezone.now()
            elif not aktuell.status.ist_erledigt:
                aktuell.erledigt_am = None
        diff = _verlauf_diff(alt, _schnappschuss(aktuell))
        if not diff:
            return aktuell
        aktuell.version = F("version") + 1
        aktuell.save()
        aktuell.refresh_from_db()
        protokollieren(konto, "aufgabe", aktuell.pk, "geaendert", diff, aufgabe_id=aktuell.pk)
        if "abschnitt" in diff and not aktuell.eltern_id:
            Aufgabe.objects.filter(pk__in=nachkommen(aktuell.pk)).update(abschnitt=aktuell.abschnitt)
        if aktuell.eltern_id and aktuell.status.ist_erledigt != war_erledigt:
            # Im Verlauf der Hauptaufgabe sichtbar
            protokollieren(konto, "unteraufgabe", aktuell.pk, "erledigt" if aktuell.status.ist_erledigt else "wieder_offen",
                           {"titel": aktuell.titel}, aufgabe_id=aktuell.eltern_id)
        if aktuell.verantwortlich_id and aktuell.verantwortlich_id != alter_verantwortlicher:
            zuweisung_benachrichtigen(konto, aktuell)
        aufgabe_geaendert_benachrichtigen(konto, aktuell, list(diff))
        if nachziehen and ("beginn_am" in diff or "faellig_am" in diff):
            termine.nach_aenderung(konto, [aktuell.pk])
            aktuell.refresh_from_db()
    return aktuell


def termine_setzen(konto, aufgabe, beginn, ende, version):
    """Geplanter Beginn und Fälligkeit (Gantt-Diagramm). Sammelaufgaben, deren Termine sich aus den
    Unteraufgaben ergeben, werden als Ganzes verschoben – ihre Dauer ändert sich dabei nicht."""
    if not termine.ist_sammelaufgabe(aufgabe):
        return aufgabe_speichern(konto, aufgabe, {"beginn_am": beginn, "faellig_am": ende}, version)
    with transaction.atomic():
        aktuell = Aufgabe.objects.select_for_update().get(pk=aufgabe.pk)
        if version is not None and als_zahl(version) != aktuell.version:
            raise Konflikt
        alt, neu = termine.anfang(aktuell.beginn_am, aktuell.faellig_am), termine.anfang(beginn, ende)
        if alt and neu and neu != alt:
            termine.sammelaufgabe_verschieben(konto, aktuell, (neu - alt).days)
        aktuell.refresh_from_db()
    return aktuell


def _ans_ende(projekt, abschnitt, eltern):
    geschwister = Aufgabe.objects.filter(projekt=projekt, eltern=eltern)
    if eltern is None:
        geschwister = geschwister.filter(abschnitt=abschnitt)
    return (geschwister.aggregate(m=Max("sortierung"))["m"] or 0) + 10


def aufgabe_anlegen(konto, projekt, abschnitt, titel, eltern=None, **felder):
    """Neue Aufgabe (``abschnitt`` darf None sein); mit ``eltern`` eine Unteraufgabe in Projekt und
    Abschnitt der Hauptaufgabe."""
    if eltern is not None:
        if not darf_unteraufgaben_haben(eltern):
            raise KeineUnteraufgabe
        projekt, abschnitt = eltern.projekt, eltern.abschnitt
    sortierung = _ans_ende(projekt, abschnitt, eltern)
    aufgabe = Aufgabe.objects.create(
        projekt=projekt, abschnitt=abschnitt, eltern=eltern, titel=titel,
        status=felder.pop("status", None) or Status.standard_offen(),
        sortierung=sortierung, erstellt_von=konto.person, **felder,
    )
    protokollieren(konto, "aufgabe", aufgabe.pk, "angelegt", {"titel": titel}, aufgabe_id=aufgabe.pk)
    if eltern is not None:
        protokollieren(konto, "unteraufgabe", aufgabe.pk, "angelegt", {"titel": titel}, aufgabe_id=eltern.pk)
    if aufgabe.verantwortlich_id:
        zuweisung_benachrichtigen(konto, aufgabe)
    projekt_aufgabe_benachrichtigen(konto, aufgabe)
    if eltern is not None and (aufgabe.beginn_am or aufgabe.faellig_am):
        termine.nach_aenderung(konto, [aufgabe.pk])
    return aufgabe


def aufgabe_verschieben(konto, aufgabe, *, eltern=None, abschnitt=None, vor=None):
    """Drag-and-drop in der Projektliste: ``aufgabe`` wird samt Unteraufgaben zur
    Unteraufgabe von ``eltern`` bzw. ohne ``eltern`` zur Hauptaufgabe im ``abschnitt`` (None = ohne
    Abschnitt) und steht direkt vor ``vor`` (None = am Ende). Ausgeblendete Geschwister (Filter)
    behalten ihren Platz."""
    with transaction.atomic():
        aktuell = Aufgabe.objects.select_for_update().get(pk=aufgabe.pk)
        if eltern is not None:
            if (eltern.projekt_id != aktuell.projekt_id or eltern.pk == aktuell.pk
                    or eltern.pk in nachkommen(aktuell.pk)
                    or eltern.tiefe + 1 + hoehe(aktuell.pk) > UNTERAUFGABEN_EBENEN):
                raise UngueltigesZiel
            abschnitt = eltern.abschnitt
        elif abschnitt is not None and abschnitt.projekt_id != aktuell.projekt_id:
            raise UngueltigesZiel
        geschwister = Aufgabe.objects.filter(projekt_id=aktuell.projekt_id, eltern=eltern)
        if eltern is None:
            geschwister = geschwister.filter(abschnitt=abschnitt)
        reihe = [a.pk for a in geschwister.exclude(pk=aktuell.pk).order_by("sortierung", "id")]
        reihe.insert(reihe.index(vor.pk) if vor is not None and vor.pk in reihe else len(reihe), aktuell.pk)
        for i, pk in enumerate(reihe):
            Aufgabe.objects.filter(pk=pk).exclude(sortierung=(i + 1) * 10).update(sortierung=(i + 1) * 10)

        alt_eltern, alt_abschnitt = aktuell.eltern, aktuell.abschnitt
        if alt_eltern == eltern and alt_abschnitt == abschnitt:
            return aktuell
        aktuell.eltern, aktuell.abschnitt = eltern, abschnitt
        aktuell.version = F("version") + 1
        aktuell.save(update_fields=["eltern", "abschnitt", "version", "geaendert_am"])
        aktuell.refresh_from_db()
        Aufgabe.objects.filter(pk__in=nachkommen(aktuell.pk)).update(abschnitt=abschnitt)
        protokollieren(konto, "aufgabe", aktuell.pk, "geaendert",
                       aenderungen({"abschnitt": alt_abschnitt, "eltern": alt_eltern},
                                   {"abschnitt": abschnitt, "eltern": eltern}), aufgabe_id=aktuell.pk)
        if alt_eltern != eltern:
            if alt_eltern is not None:
                protokollieren(konto, "unteraufgabe", aktuell.pk, "weg", {"titel": aktuell.titel},
                               aufgabe_id=alt_eltern.pk)
            if eltern is not None:
                protokollieren(konto, "unteraufgabe", aktuell.pk, "hierher", {"titel": aktuell.titel},
                               aufgabe_id=eltern.pk)
            termine.nach_aenderung(konto, [aktuell.pk, alt_eltern.pk if alt_eltern else None])
    return aktuell


def unteraufgaben_erledigen(konto, aufgabe):
    """Alle offenen Unteraufgaben (alle Ebenen) auf den ersten erledigten Status setzen."""
    ziel = Status.standard_erledigt()
    for unter in (Aufgabe.objects.filter(pk__in=nachkommen(aufgabe.pk), status__ist_erledigt=False)
                  .select_related("status")):
        aufgabe_speichern(konto, unter, {"status": ziel}, None)


def erledigt_setzen(konto, aufgabe, erledigt, unteraufgaben_mit=False):
    """Abhaken bzw. wieder öffnen. ``unteraufgaben_mit``: offene Unteraufgaben (alle Ebenen) mit erledigen."""
    ziel = Status.standard_erledigt() if erledigt else Status.standard_offen()
    if ziel is None:
        return aufgabe
    with transaction.atomic():
        if erledigt and unteraufgaben_mit:
            unteraufgaben_erledigen(konto, aufgabe)
        if aufgabe.status.ist_erledigt == erledigt:
            return aufgabe
        return aufgabe_speichern(konto, aufgabe, {"status": ziel}, None)


def offene_unteraufgaben(aufgabe):
    """Offene Unteraufgaben aller Ebenen – für die Rückfrage beim Abhaken."""
    return Aufgabe.objects.filter(pk__in=nachkommen(aufgabe.pk), status__ist_erledigt=False).count()


def aufgabe_loeschen(konto, aufgabe, _nachziehen=True):
    with transaction.atomic():
        einteilungen = list(aufgabe.einteilungen.select_related("person"))
        einteilungen_entfernt_melden(konto, einteilungen)
        for e in einteilungen:
            protokollieren(konto, "einteilung", e.pk, "geloescht",
                           {"person": e.person, "von": e.von, "bis": e.bis, "aufgabe": aufgabe.pk},
                           aufgabe_id=aufgabe.pk)
        for unter in aufgabe.unteraufgaben.all():
            aufgabe_loeschen(konto, unter, _nachziehen=False)
        protokollieren(konto, "aufgabe", aufgabe.pk, "geloescht", {"titel": aufgabe.titel}, aufgabe_id=aufgabe.pk)
        if aufgabe.eltern_id:
            protokollieren(konto, "unteraufgabe", aufgabe.pk, "geloescht", {"titel": aufgabe.titel},
                           aufgabe_id=aufgabe.eltern_id)
        eltern_id = aufgabe.eltern_id
        aufgabe.delete()
        if _nachziehen and eltern_id:
            termine.nach_aenderung(konto, [eltern_id])
