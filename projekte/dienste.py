"""Aufgaben ändern mit Konfliktschutz, Verlauf und Benachrichtigung."""

import nh3
from django.db import transaction
from django.db.models import F, Max, Q
from django.utils import timezone

from kern import textfarben
from kern.hilfen import als_zahl
from kern.models import Protokolleintrag
from kern.protokoll import aenderungen, protokollieren
from planung.dienste import einteilungen_entfernt_melden
from zusammenarbeit.dienste import (
    aufgabe_geaendert_benachrichtigen,
    projekt_aufgabe_benachrichtigen,
    zuweisung_benachrichtigen,
)

from . import termine, wiederholung
from .models import UNTERAUFGABEN_EBENEN, Aufgabe, Status

ERLAUBTE_TAGS = {"p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol", "li", "h1", "h2", "h3", "a", "blockquote", "code", "pre",
                 "hr", *textfarben.TAGS}

VERLAUF_FELDER = ["titel", "abschnitt", "verantwortlich", "gewerk", "beginn_am", "faellig_am", "wiederholung", "status",
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
                     tag_attribute_values=textfarben.ATTRIBUTWERTE, link_rel="noopener noreferrer nofollow").strip()


def _schnappschuss(aufgabe):
    return {feld: getattr(aufgabe, feld) for feld in VERLAUF_FELDER}


def _verlauf_diff(alt, neu):
    """Geänderte Felder fürs Protokoll; die Beschreibung nur als „…“, ihr Inhalt kommt nicht hinein."""
    diff = aenderungen(alt, neu)
    if "beschreibung" in diff:
        diff["beschreibung"] = ["…" if alt["beschreibung"] else "", "…" if neu["beschreibung"] else ""]
    if "wiederholung" in diff:
        # Lesbar statt als Dict; ändert sich nur der Anker (Stichtag verschoben), zählt das nicht
        texte = [wiederholung.regel_text(alt["wiederholung"]), wiederholung.regel_text(neu["wiederholung"])]
        if texte[0] == texte[1]:
            del diff["wiederholung"]
        else:
            diff["wiederholung"] = texte
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
        if aktuell.wiederholung:
            # Wiederkehrend: nur ein Stichtag, keine Zeitspanne; der Anker folgt dem Stichtag
            aktuell.beginn_am = None
            aktuell.wiederholung = wiederholung.mit_anker(aktuell.wiederholung, aktuell.faellig_am)
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
        folge = None
        if aktuell.status.ist_erledigt and not war_erledigt:
            folge = folgeaufgabe_anlegen(konto, aktuell)
    aktuell.neue_folgeaufgabe = folge
    return aktuell


def _kopie(konto, vorlage, *, eltern, abschnitt, versatz, **felder):
    """Offene Kopie für die Wiederholung: Titel, Beschreibung, Verantwortlich, Gruppe, Schätzung, Regel,
    Sortierung; Termine um ``versatz`` verschoben. Verlauf, Einteilungen, Kommentare, Anhänge und
    Abhängigkeiten bleiben bei der alten Aufgabe."""
    werte = {
        "projekt_id": vorlage.projekt_id, "abschnitt": abschnitt, "eltern": eltern, "titel": vorlage.titel,
        "beschreibung": vorlage.beschreibung, "verantwortlich_id": vorlage.verantwortlich_id,
        "gewerk_id": vorlage.gewerk_id, "schaetzung_personentage": vorlage.schaetzung_personentage,
        "wiederholung": vorlage.wiederholung, "sortierung": vorlage.sortierung,
        "beginn_am": vorlage.beginn_am + versatz if vorlage.beginn_am else None,
        "faellig_am": vorlage.faellig_am + versatz if vorlage.faellig_am else None,
        "status": Status.standard_offen(), "erstellt_von": konto.person,
    }
    werte.update(felder)
    neu = Aufgabe.objects.create(**werte)
    protokollieren(konto, "aufgabe", neu.pk, "angelegt",
                   {"titel": neu.titel, "wiederholung_von": vorlage}, aufgabe_id=neu.pk)
    if neu.verantwortlich_id:
        zuweisung_benachrichtigen(konto, neu)
    return neu


def _unteraufgaben_kopieren(konto, vorlage_id, neu, versatz):
    """Alle Ebenen als offene Kopien. Folgeaufgaben wiederkehrender Unteraufgaben, die beim Abhaken gerade
    erst entstanden sind, werden nicht noch einmal kopiert – ihre Vorlage wird es schon."""
    teilbaum = set(nachkommen(vorlage_id))
    for unter in Aufgabe.objects.filter(eltern_id=vorlage_id).order_by("sortierung", "id"):
        if unter.wiederholt_von_id in teilbaum:
            continue
        kopie = _kopie(konto, unter, eltern=neu, abschnitt=neu.abschnitt, versatz=versatz)
        protokollieren(konto, "unteraufgabe", kopie.pk, "angelegt", {"titel": kopie.titel}, aufgabe_id=neu.pk)
        _unteraufgaben_kopieren(konto, unter.pk, kopie, versatz)


def folgeaufgabe_anlegen(konto, aufgabe):
    """Beim Abhaken einer wiederkehrenden Aufgabe die nächste am selben Ort anlegen (samt Unteraufgaben).

    Nicht, wenn es schon eine Folgeaufgabe gibt (wieder geöffnet und erneut abgehakt), wenn die Wiederholung
    entfernt wurde oder der nächste Termin nach dem Enddatum liegt. Teil der laufenden Transaktion."""
    regel = aufgabe.wiederholung
    if not regel or not aufgabe.faellig_am or Aufgabe.objects.filter(wiederholt_von=aufgabe).exists():
        return None
    termin = wiederholung.naechster_termin(aufgabe.faellig_am, regel)
    bis = wiederholung.ende(regel)
    if bis and termin > bis:
        return None
    versatz = termin - aufgabe.faellig_am
    neu = _kopie(konto, aufgabe, eltern=aufgabe.eltern, abschnitt=aufgabe.abschnitt, versatz=versatz,
                 faellig_am=termin, beginn_am=None, wiederholt_von=aufgabe)
    if neu.eltern_id:
        protokollieren(konto, "unteraufgabe", neu.pk, "angelegt", {"titel": neu.titel}, aufgabe_id=neu.eltern_id)
    _unteraufgaben_kopieren(konto, aufgabe.pk, neu, versatz)
    projekt_aufgabe_benachrichtigen(konto, neu)
    termine.nach_aenderung(konto, [neu.pk] + ([neu.eltern_id] if neu.eltern_id else []))
    return neu


def termine_setzen(konto, aufgabe, beginn, ende, version):
    """Geplanter Beginn und Fälligkeit (Gantt-Diagramm). Sammelaufgaben, deren Termine sich aus den
    Unteraufgaben ergeben, werden als Ganzes verschoben – ihre Dauer ändert sich dabei nicht."""
    if aufgabe.wiederholung:  # wiederkehrend: nur der Stichtag
        return aufgabe_speichern(konto, aufgabe, {"faellig_am": ende or beginn}, version)
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


# So lange nach dem Abhaken lässt sich eine unberührte Folgeaufgabe beim Wieder-Öffnen zurücknehmen
FOLGE_ZURUECKNEHMEN_SEKUNDEN = 120


def folgeaufgabe_zuruecknehmen(konto, aufgabe, folge_id):
    """„Rückgängig“ direkt nach dem Abhaken einer wiederkehrenden Aufgabe: Die eben angelegte Folgeaufgabe
    wird wieder gelöscht – nur, wenn sie (samt Unteraufgaben) noch unberührt ist: frisch, ohne Änderungen,
    Einteilungen, Kommentare oder Anhänge. Sonst bleibt sie stehen. Gibt zurück, ob gelöscht wurde."""
    folge = Aufgabe.objects.filter(pk=als_zahl(folge_id), wiederholt_von=aufgabe).first()
    if folge is None or aufgabe.status.ist_erledigt:
        return False
    if (timezone.now() - folge.erstellt_am).total_seconds() > FOLGE_ZURUECKNEHMEN_SEKUNDEN:
        return False
    teil = [folge.pk, *nachkommen(folge.pk)]
    beruehrt = (
        Protokolleintrag.objects.filter(aufgabe_id__in=teil).exclude(aktion="angelegt").exists()
        or Aufgabe.objects.filter(pk__in=teil).filter(
            Q(einteilungen__isnull=False) | Q(kommentare__isnull=False) | Q(anhaenge__isnull=False)).exists()
        or Aufgabe.objects.filter(wiederholt_von_id__in=teil).exists()
    )
    if beruehrt:
        return False
    aufgabe_loeschen(konto, folge)
    return True


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
