"""Änderungen aus dem Gantt-Diagramm: Termine und Abhängigkeiten."""

from collections import defaultdict, deque

from django.db import transaction
from django.utils.translation import gettext as _

from kern.protokoll import aenderungen, protokollieren
from planung.models import Recht
from projekte import dienste as projekt_dienste
from projekte import termine
from projekte.models import Abhaengigkeit

from . import rechte
from .models import GanttAnsicht


class GanttFehler(Exception):
    def __init__(self, code, nachricht, status=400, daten=None):
        super().__init__(nachricht)
        self.code, self.nachricht, self.status, self.daten = code, nachricht, status, daten or {}


def neues_projekt_aufnehmen(projekt):
    """Neu angelegtes Projekt in alle Ansichten mit „Neue Projekte automatisch aufnehmen“ legen."""
    for ansicht in GanttAnsicht.objects.filter(neue_projekte_automatisch=True):
        ansicht.projekte.add(projekt)


def _pruefe_bearbeiten(konto, ansicht, projekt_ids):
    if rechte.recht(konto, ansicht) != Recht.BEARBEITEN:
        raise GanttFehler("keine_berechtigung", _("Sie dürfen diese Gantt-Ansicht nicht bearbeiten."), 403)
    enthalten = set(ansicht.projekte.values_list("id", flat=True))
    if not set(projekt_ids) <= enthalten:
        raise GanttFehler("keine_berechtigung", _("Das Projekt gehört nicht zu dieser Ansicht."), 403)


def _pruefe_zeitraum(beginn, ende):
    if beginn and ende and ende < beginn:
        raise GanttFehler("zeitraum", _("Das Ende liegt vor dem Beginn."))


def aufgabe_termine(konto, ansicht, aufgabe, *, beginn, ende, version):
    """Geplanten Beginn und Fälligkeit setzen – mit Versionsprüfung und Verlauf. Hauptaufgaben
    und Nachfolger rücken nach, Sammelaufgaben verschieben ihre Unteraufgaben (projekte.termine)."""
    _pruefe_bearbeiten(konto, ansicht, [aufgabe.projekt_id])
    _pruefe_zeitraum(beginn, ende)
    try:
        with transaction.atomic():
            return projekt_dienste.termine_setzen(konto, aufgabe, beginn, ende, version)
    except projekt_dienste.Konflikt:
        raise GanttFehler(
            "konflikt", _("Die Aufgabe wurde inzwischen von jemand anderem geändert. Die Ansicht wurde aktualisiert."), 409,
        ) from None
    except termine.TermineFehler as f:
        raise GanttFehler("termine", str(f)) from None


def projekt_termine(konto, ansicht, projekt, *, beginn, ende):
    _pruefe_bearbeiten(konto, ansicht, [projekt.pk])
    _pruefe_zeitraum(beginn, ende)
    alt = {"beginn": projekt.beginn, "ende": projekt.ende}
    projekt.beginn, projekt.ende = beginn, ende
    projekt.save(update_fields=["beginn", "ende"])
    diff = aenderungen(alt, {"beginn": beginn, "ende": ende})
    if diff:
        protokollieren(konto, "projekt", projekt.pk, "geaendert", {"name": projekt.name, **diff})
    return projekt


def _erreichbar(start_id, ziel_id):
    """Gibt es einen Weg start → … → ziel über bestehende Abhängigkeiten?"""
    kanten = defaultdict(list)
    for vorher, nachher in Abhaengigkeit.objects.values_list("vorher_id", "nachher_id"):
        kanten[vorher].append(nachher)
    gesehen, offen = {start_id}, deque([start_id])
    while offen:
        knoten = offen.popleft()
        if knoten == ziel_id:
            return True
        for weiter in kanten[knoten]:
            if weiter not in gesehen:
                gesehen.add(weiter)
                offen.append(weiter)
    return False


def abhaengigkeit_anlegen(konto, ansicht, vorher, nachher):
    _pruefe_bearbeiten(konto, ansicht, [vorher.projekt_id, nachher.projekt_id])
    if vorher.pk == nachher.pk:
        raise GanttFehler("ungueltig", _("Eine Aufgabe kann nicht von sich selbst abhängen."))
    if vorher in nachher.vorfahren() or nachher in vorher.vorfahren():
        raise GanttFehler("ungueltig", _("Eine Hauptaufgabe umfasst ihre Unteraufgaben – zwischen ihnen gibt es keine "
                                         "Abhängigkeit."))
    with transaction.atomic():
        if Abhaengigkeit.objects.filter(vorher=vorher, nachher=nachher).exists():
            raise GanttFehler("besteht", _("Diese Abhängigkeit gibt es bereits."))
        if _erreichbar(nachher.pk, vorher.pk):
            raise GanttFehler("ringschluss", _("Das ergäbe einen Ringschluss: „%(b)s“ liegt bereits vor „%(a)s“.")
                              % {"a": vorher.titel, "b": nachher.titel})
        abh = Abhaengigkeit.objects.create(vorher=vorher, nachher=nachher, erstellt_von=konto.person)
        daten = {"vorher": vorher, "nachher": nachher}
        # im Verlauf beider Aufgaben sichtbar
        for aufgabe_id in (nachher.pk, vorher.pk):
            protokollieren(konto, "abhaengigkeit", abh.pk, "angelegt", daten, aufgabe_id=aufgabe_id)
        try:
            termine.nach_aenderung(konto, [vorher.pk])  # beginnt B zu früh, rückt B gleich nach
        except termine.TermineFehler as f:
            raise GanttFehler("termine", str(f)) from None
    return abh


def abhaengigkeit_loeschen(konto, ansicht, abh):
    _pruefe_bearbeiten(konto, ansicht, [abh.vorher.projekt_id, abh.nachher.projekt_id])
    daten = {"vorher": abh.vorher, "nachher": abh.nachher}
    pk, vorher_id, nachher_id = abh.pk, abh.vorher_id, abh.nachher_id
    abh.delete()
    for aufgabe_id in (nachher_id, vorher_id):
        protokollieren(konto, "abhaengigkeit", pk, "geloescht", daten, aufgabe_id=aufgabe_id)
