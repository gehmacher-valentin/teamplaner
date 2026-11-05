"""Warnung bei überschrittenem Liefertermin.

Einmal am Tag (Dienst ``mails_versenden``) bekommt für jede noch nicht erhaltene Bestellung, deren
Liefertermin vorbei ist, die Person aus „Bestellt von“ eine Benachrichtigung – ist dort niemand mit Konto
eingetragen, die aus „Eingetragen von“. Je Bestellung und Liefertermin nur einmal; wird der Termin
verschoben, wird nach Ablauf des neuen erneut gewarnt.
"""

from django.db import transaction
from django.db.models import F, Q
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from zusammenarbeit.dienste import benachrichtigen
from zusammenarbeit.models import Benachrichtigungsart

from .models import Bestellstatus, Bestellung


def _empfaenger(bestellung):
    for person in (bestellung.bestellt_von, bestellung.eingetragen_von):
        if person is not None and not person.ist_platzhalter and not person.archiviert:
            return person
    return None


def liefertermine_pruefen(heute=None):
    """Legt die fälligen Warnungen an; gibt deren Zahl zurück."""
    heute = heute or timezone.localdate()
    anzahl = 0
    with transaction.atomic():
        faellig = (Bestellung.objects.select_for_update(skip_locked=True, of=("self",))
                   .select_related("bestellt_von__konto", "eingetragen_von__konto")
                   .filter(liefertermin__lt=heute).exclude(status=Bestellstatus.ERHALTEN)
                   .filter(Q(warnung_fuer_termin__isnull=True) | ~Q(warnung_fuer_termin=F("liefertermin"))))
        for b in faellig:
            empfaenger = _empfaenger(b)
            if empfaenger is not None and benachrichtigen(
                empfaenger, Benachrichtigungsart.LIEFERTERMIN,
                _("Liefertermin überschritten: „%(bedarf)s“ (Liefertermin %(termin)s)."),
                {"bedarf": b.bedarf[:200], "termin": lambda b=b: date_format(b.liefertermin, "d.m.Y")},
            ):
                anzahl += 1
            b.warnung_fuer_termin = b.liefertermin
            b.save(update_fields=["warnung_fuer_termin"])
    return anzahl
