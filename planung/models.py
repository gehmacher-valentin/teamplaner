"""Einteilungen, Abwesenheiten, freie Tage, Tagesinfos und Teamplaner-Ansichten."""

from django.db import models
from django.db.models import F, Q
from django.utils.translation import gettext_lazy as _

from kern.models import Bereich, Konto, Person
from projekte.models import Aufgabe


class Einteilung(models.Model):
    """Ein Balken im Teamplaner: eine Person, ein zusammenhängender Tagesbereich.

    Überlappungen sind erlaubt (Doppelbelegung wird nur markiert), deshalb gibt es
    keinen Exclusion-Constraint. ``von`` und ``bis`` sind inklusive.
    """

    aufgabe = models.ForeignKey(Aufgabe, on_delete=models.CASCADE, related_name="einteilungen")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="einteilungen")
    von = models.DateField()
    bis = models.DateField()
    version = models.PositiveIntegerField(default=1)
    erstellt_von = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["von", "id"]
        verbose_name = _("Einteilung")
        verbose_name_plural = _("Einteilungen")
        constraints = [
            models.CheckConstraint(condition=Q(bis__gte=F("von")), name="einteilung_bis_nach_von"),
        ]
        indexes = [models.Index(fields=["person", "von", "bis"])]

    def __str__(self):
        return f"{self.aufgabe} · {self.person} · {self.von:%d.%m.}–{self.bis:%d.%m.%Y}"


class Abwesenheit(models.Model):
    """Genau eine Art „Abwesend“: nur Person und Tage, kein Grund."""

    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="abwesenheiten")
    von = models.DateField()
    bis = models.DateField()
    version = models.PositiveIntegerField(default=1)
    erstellt_von = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["von", "id"]
        verbose_name = _("Abwesenheit")
        verbose_name_plural = _("Abwesenheiten")
        constraints = [
            models.CheckConstraint(condition=Q(bis__gte=F("von")), name="abwesenheit_bis_nach_von"),
        ]
        indexes = [models.Index(fields=["person", "von", "bis"])]

    def __str__(self):
        return f"{self.person} · {self.von:%d.%m.}–{self.bis:%d.%m.%Y}"


class FreierTag(models.Model):
    """Manuell ergänzter freier Tag für alle, z. B. Betriebsurlaub.

    Gesetzliche Feiertage werden nicht gespeichert, sondern berechnet.
    """

    datum = models.DateField(_("Datum"), unique=True)
    bezeichnung = models.CharField(_("Bezeichnung"), max_length=100)

    class Meta:
        ordering = ["datum"]
        verbose_name = _("Freier Tag")
        verbose_name_plural = _("Freie Tage")

    def __str__(self):
        return f"{self.datum:%d.%m.%Y} {self.bezeichnung}"


class TagesInfo(models.Model):
    """Freitext zu einem Tag für alle, z. B. „Wartungsarbeiten Aufzug“ (Info-Zeile im Teamplaner)."""

    datum = models.DateField(_("Datum"), unique=True)
    text = models.CharField(_("Text"), max_length=120)
    geaendert_von = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["datum"]
        verbose_name = _("Tagesinfo")
        verbose_name_plural = _("Tagesinfos")

    def __str__(self):
        return f"{self.datum:%d.%m.%Y} {self.text}"


class FreigabeStufe(models.Model):
    """Wählbare Stufe der Zeile „Tagesfreigabe“, vom Admin gepflegt."""

    name = models.CharField(_("Name"), max_length=40, unique=True)
    sortierung = models.PositiveIntegerField(_("Sortierung"), default=0)

    class Meta:
        ordering = ["sortierung", "name"]
        verbose_name = _("Freigabestufe")
        verbose_name_plural = _("Freigabestufen")

    def __str__(self):
        return self.name


class Tagesfreigabe(models.Model):
    """Ein Wert je Tag; kein Datensatz = „keine Freigabe“."""

    datum = models.DateField(_("Datum"), unique=True)
    stufe = models.ForeignKey(FreigabeStufe, on_delete=models.PROTECT, related_name="tage", verbose_name=_("Stufe"))
    geaendert_von = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["datum"]
        verbose_name = _("Tagesfreigabe")
        verbose_name_plural = _("Tagesfreigaben")

    def __str__(self):
        return f"{self.datum:%d.%m.%Y} {self.stufe}"


class TeamplanerAnsicht(models.Model):
    """Gespeicherte Ansicht. Enthaltene Bereiche/Personen bestimmen die Rechte,
    ``filter`` (Gewerke, Projekte, Zeitraum) wirkt nur auf die Anzeige."""

    name = models.CharField(_("Name"), max_length=120)
    sortierung = models.PositiveIntegerField(_("Sortierung"), default=0)
    bereiche = models.ManyToManyField(
        Bereich, blank=True, related_name="ansichten", verbose_name=_("Bereiche")
    )
    personen = models.ManyToManyField(
        Person, blank=True, related_name="ansichten", verbose_name=_("Einzelne Personen")
    )
    filter = models.JSONField(default=dict, blank=True)
    erstellt_von = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sortierung", "name", "id"]
        verbose_name = _("Teamplaner-Ansicht")
        verbose_name_plural = _("Teamplaner-Ansichten")

    def __str__(self):
        return self.name

    def personen_queryset(self):
        return Person.objects.filter(Q(ansichten=self) | Q(bereich__ansichten=self)).distinct()


class Recht(models.TextChoices):
    SEHEN = "sehen", _("nur sehen")
    BEARBEITEN = "bearbeiten", _("bearbeiten")


class AnsichtFreigabe(models.Model):
    """Freigabe einer Ansicht an eine einzelne Person mit Konto.

    Keine Zeile = nicht sehen. ``bearbeiten`` wirkt nur ab Rolle Planer:in.
    """

    ansicht = models.ForeignKey(TeamplanerAnsicht, on_delete=models.CASCADE, related_name="freigaben")
    konto = models.ForeignKey(Konto, on_delete=models.CASCADE, related_name="ansicht_freigaben")
    recht = models.CharField(_("Recht"), max_length=20, choices=Recht.choices)

    class Meta:
        verbose_name = _("Freigabe")
        verbose_name_plural = _("Freigaben")
        constraints = [
            models.UniqueConstraint(fields=["ansicht", "konto"], name="freigabe_eindeutig"),
        ]

    def __str__(self):
        return f"{self.ansicht} → {self.konto.person} ({self.get_recht_display()})"
