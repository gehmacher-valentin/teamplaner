"""Gantt-Ansichten mit Projektauswahl und Freigaben."""

from django.db import models
from django.utils.translation import gettext_lazy as _

from kern.models import Konto, Person
from planung.models import Recht
from projekte.models import Projekt


class GanttAnsicht(models.Model):
    """Eine frei zusammengestellte Auswahl von Projekten; jederzeit erweiterbar."""

    name = models.CharField(_("Name"), max_length=120)
    sortierung = models.PositiveIntegerField(_("Sortierung"), default=0)
    projekte = models.ManyToManyField(Projekt, blank=True, related_name="gantt_ansichten", verbose_name=_("Projekte"))
    neue_projekte_automatisch = models.BooleanField(_("Neue Projekte automatisch aufnehmen"), default=False)
    erstellt_von = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sortierung", "name", "id"]
        verbose_name = _("Gantt-Ansicht")
        verbose_name_plural = _("Gantt-Ansichten")

    def __str__(self):
        return self.name


class GanttFreigabe(models.Model):
    """Wie AnsichtFreigabe im Teamplaner: keine Zeile = nicht sehen; „bearbeiten“ ab Planer:in."""

    ansicht = models.ForeignKey(GanttAnsicht, on_delete=models.CASCADE, related_name="freigaben")
    konto = models.ForeignKey(Konto, on_delete=models.CASCADE, related_name="gantt_freigaben")
    recht = models.CharField(_("Recht"), max_length=20, choices=Recht.choices)

    class Meta:
        verbose_name = _("Gantt-Freigabe")
        verbose_name_plural = _("Gantt-Freigaben")
        constraints = [models.UniqueConstraint(fields=["ansicht", "konto"], name="gantt_freigabe_eindeutig")]

    def __str__(self):
        return f"{self.ansicht} → {self.konto.person} ({self.get_recht_display()})"
