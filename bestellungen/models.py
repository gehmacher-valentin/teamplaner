"""Bestellungsverfolgung: eine gemeinsame Liste, in die alle Bedarfe eintragen."""

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from kern.models import Person


class Bestellstatus(models.TextChoices):
    OFFEN = "offen", _("offen")
    RECHERCHE = "recherche", _("Recherche")
    BESTELLT = "bestellt", _("bestellt")
    ERHALTEN = "erhalten", _("erhalten")
    ACHTUNG = "achtung", _("Achtung")


# Sortierung der Liste: offene immer oben, erhaltene unten
REIHENFOLGE = [
    Bestellstatus.OFFEN, Bestellstatus.ACHTUNG, Bestellstatus.RECHERCHE, Bestellstatus.BESTELLT,
    Bestellstatus.ERHALTEN,
]


class Bestellung(models.Model):
    # Dringend: nur gesetzt oder nicht, keine Skala; die Liste wird danach nicht sortiert
    prio = models.BooleanField(_("Prio"), default=False)
    bedarf = models.CharField(_("Bedarf"), max_length=500)
    aufnahmedatum = models.DateField(_("Aufnahmedatum"), default=timezone.localdate)
    projekt = models.CharField(_("Projekt"), max_length=200, blank=True)
    bestellt_am = models.DateField(_("Bestellt am"), null=True, blank=True)
    lieferant = models.CharField(_("Lieferant"), max_length=200, blank=True)
    # Vom Lieferanten zugesagt; überschritten und nicht erhalten → Markierung und Warnung
    liefertermin = models.DateField(_("Liefertermin"), null=True, blank=True)
    # Liefertermin, für den schon gewarnt wurde – nach einer Verschiebung wird erneut gewarnt
    warnung_fuer_termin = models.DateField(null=True, blank=True, editable=False)
    status = models.CharField(_("Status"), max_length=20, choices=Bestellstatus.choices, default=Bestellstatus.OFFEN)
    # In der Liste wählbar; vorbelegt mit der Person, die die Zeile anlegt
    eingetragen_von = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                        verbose_name=_("Eingetragen von"))
    bestellt_von = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+",
                                     verbose_name=_("Bestellt von"))
    # Wer die Zeile tatsächlich angelegt hat – unveränderlich, daran hängt das Recht zu löschen
    erstellt_von = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-aufnahmedatum", "-id"]
        verbose_name = _("Bestellung")
        verbose_name_plural = _("Bestellungen")

    def __str__(self):
        return self.bedarf

    def ueberfaellig(self, heute=None):
        heute = heute or timezone.localdate()
        return bool(self.liefertermin and self.liefertermin < heute and self.status != Bestellstatus.ERHALTEN)
