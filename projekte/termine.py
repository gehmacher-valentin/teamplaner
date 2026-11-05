"""Geplante Termine nachziehen.

* Hauptaufgaben umfassen ihre Unteraufgaben: Hat mindestens eine Unteraufgabe Termine, reicht die
  Hauptaufgabe vom frühesten Beginn bis zur spätesten Fälligkeit darunter – auch ohne
  Abhängigkeitspfeile. Wird eine solche Hauptaufgabe verschoben, wandern alle Unteraufgaben mit.
* „A vor B“: Endet A an oder nach dem Beginn von B, rückt B mit gleicher Dauer auf den ersten
  Werktag nach dem Ende von A. Nachfolger werden nur nach hinten geschoben, nie vorgezogen;
  erledigte Aufgaben bleiben, wo sie sind.

Alles wird zuerst im Speicher berechnet und danach je Aufgabe einmal gespeichert (mit Verlauf und
Benachrichtigung wie eine Änderung von Hand). Tatsächliche Einteilungen bleiben unberührt.
"""

from collections import deque
from datetime import timedelta

from django.utils.translation import gettext as _

from planung.kalender import freie_tage_mit_wochenende

from .models import Abhaengigkeit, Aufgabe

HOECHSTENS_SCHRITTE = 5000


class TermineFehler(Exception):
    """Die Termine lassen sich nicht widerspruchsfrei nachziehen (sollte nie vorkommen)."""


def anfang(beginn, ende):
    return beginn or ende


def schluss(beginn, ende):
    return ende or beginn


def _plus(datum, tage):
    return datum + timedelta(days=tage) if datum else None


def naechster_werktag(datum):
    """Erster Tag nach ``datum``, der weder Wochenende noch Feiertag oder freier Tag ist."""
    frei = freie_tage_mit_wochenende(datum + timedelta(days=1), datum + timedelta(days=40))
    tag = datum + timedelta(days=1)
    while tag in frei:
        tag += timedelta(days=1)
    return tag


def mit_gleicher_dauer(beginn, ende, neuer_beginn):
    """Ende für ``neuer_beginn``, sodass gleich viele Werktage dazwischen liegen wie von ``beginn``
    bis ``ende`` (mindestens einer) – ein Nachfolger Mi–Fr rutscht so z. B. auf Fr–Di."""
    frei = freie_tage_mit_wochenende(beginn, ende)
    werktage = max(1, sum(1 for i in range((ende - beginn).days + 1) if beginn + timedelta(days=i) not in frei))
    tag = neuer_beginn
    for _i in range(werktage - 1):
        tag = naechster_werktag(tag)
    return tag


class Plan:
    """Termine der berührten Aufgaben; ``neu`` enthält nur die geänderten (ID → (Beginn, Fälligkeit))."""

    def __init__(self):
        self._aufgaben = {}
        self._kinder = {}
        self._nachfolger = {}
        self.neu = {}

    def aufgabe(self, pk):
        if pk not in self._aufgaben:
            self._aufgaben[pk] = Aufgabe.objects.select_related("status").get(pk=pk)
        return self._aufgaben[pk]

    def kinder(self, pk):
        if pk not in self._kinder:
            liste = list(Aufgabe.objects.filter(eltern_id=pk).select_related("status"))
            for k in liste:
                self._aufgaben.setdefault(k.pk, k)
            self._kinder[pk] = [k.pk for k in liste]
        return self._kinder[pk]

    def nachfolger(self, pk):
        if pk not in self._nachfolger:
            self._nachfolger[pk] = list(Abhaengigkeit.objects.filter(vorher_id=pk).values_list("nachher_id", flat=True))
        return self._nachfolger[pk]

    def termine(self, pk):
        if pk in self.neu:
            return self.neu[pk]
        a = self.aufgabe(pk)
        return a.beginn_am, a.faellig_am

    def setzen(self, pk, termine):
        a = self.aufgabe(pk)
        if tuple(termine) == (a.beginn_am, a.faellig_am):
            self.neu.pop(pk, None)
        else:
            self.neu[pk] = tuple(termine)

    def spanne(self, pk):
        """Zeitraum der Unteraufgaben mit Terminen, None wenn keine welche hat."""
        anfaenge, enden = [], []
        for k in self.kinder(pk):
            b, e = self.termine(k)
            if b or e:
                anfaenge.append(anfang(b, e))
                enden.append(schluss(b, e))
        return (min(anfaenge), max(enden)) if anfaenge else None

    def verschieben(self, pk, tage, offen):
        """Um ``tage`` verschieben; Sammelaufgaben verschieben ihre Unteraufgaben (alle Ebenen)."""
        if not tage:
            return
        if self.spanne(pk) is not None:
            for k in self.kinder(pk):
                if any(self.termine(k)):
                    self.verschieben(k, tage, offen)
            self.setzen(pk, self.spanne(pk))
        else:
            b, e = self.termine(pk)
            self.setzen(pk, (_plus(b, tage), _plus(e, tage)))
        offen.append(pk)


def nachziehen(plan, start_ids):
    """Folgeänderungen ab ``start_ids`` in ``plan.neu`` eintragen (siehe Moduldoku)."""
    offen = deque(start_ids)
    schritte = 0
    while offen:
        schritte += 1
        if schritte > HOECHSTENS_SCHRITTE:
            raise TermineFehler(_("Die Termine lassen sich wegen widersprüchlicher Abhängigkeiten nicht nachziehen."))
        pk = offen.popleft()
        eigene = plan.spanne(pk)
        if eigene is not None and eigene != plan.termine(pk):
            plan.setzen(pk, eigene)
        a = plan.aufgabe(pk)
        if a.eltern_id:
            spanne = plan.spanne(a.eltern_id)
            if spanne is not None and spanne != plan.termine(a.eltern_id):
                plan.setzen(a.eltern_id, spanne)
                offen.append(a.eltern_id)
        ende = schluss(*plan.termine(pk))
        if ende is None:
            continue
        for nachher in plan.nachfolger(pk):
            if plan.aufgabe(nachher).status.ist_erledigt:
                continue
            nb, ne = plan.termine(nachher)
            start = anfang(nb, ne)
            if start is None or start > ende:
                continue
            ziel = naechster_werktag(ende)
            if plan.spanne(nachher) is not None or not (nb and ne):
                plan.verschieben(nachher, (ziel - start).days, offen)
            else:
                plan.setzen(nachher, (ziel, mit_gleicher_dauer(nb, ne, ziel)))
                offen.append(nachher)


def speichern(konto, plan):
    from .dienste import aufgabe_speichern

    for pk, (beginn, ende) in sorted(plan.neu.items()):
        aufgabe_speichern(konto, plan.aufgabe(pk), {"beginn_am": beginn, "faellig_am": ende}, None, nachziehen=False)


def nach_aenderung(konto, aufgabe_ids):
    """Nach geänderten Terminen oder Unteraufgaben: Hauptaufgaben und Nachfolger anpassen und speichern."""
    plan = Plan()
    nachziehen(plan, [pk for pk in aufgabe_ids if pk])
    speichern(konto, plan)
    return plan


def ist_sammelaufgabe(aufgabe):
    """Termine ergeben sich aus den Unteraufgaben (mindestens eine hat Termine)."""
    return Aufgabe.objects.filter(eltern=aufgabe).exclude(beginn_am=None, faellig_am=None).exists()


def sammelaufgabe_verschieben(konto, aufgabe, tage):
    """Sammelaufgabe (z. B. im Gantt-Diagramm gezogen) samt Unteraufgaben verschieben."""
    plan = Plan()
    offen = deque()
    plan.verschieben(aufgabe.pk, tage, offen)
    nachziehen(plan, offen)
    speichern(konto, plan)
    return plan
