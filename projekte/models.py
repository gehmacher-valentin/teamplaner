"""Projekte, Tags, Abschnitte, Status, Aufgaben und Unteraufgaben."""

from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F
from django.db.models.functions import Lower
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from kern.models import Gewerk, Person


class Projektfarbe(models.TextChoices):
    """Feste Palette statt freier Farbwerte, damit Kontraste stimmen."""

    BERNSTEIN = "bernstein", _("Bernstein")
    BLAU = "blau", _("Blau")
    GRUEN = "gruen", _("Grün")
    VIOLETT = "violett", _("Violett")
    ROT = "rot", _("Rot")
    PETROL = "petrol", _("Petrol")
    OLIV = "oliv", _("Oliv")
    GRAU = "grau", _("Grau")


PRIORITAETEN = [(i, str(i)) for i in range(1, 6)]


class Tag(models.Model):
    name = models.CharField(_("Name"), max_length=60)

    class Meta:
        ordering = [Lower("name")]
        verbose_name = _("Tag")
        verbose_name_plural = _("Tags")
        constraints = [models.UniqueConstraint(Lower("name"), name="tag_name_eindeutig_ci")]

    def __str__(self):
        return self.name


class ProjektQuerySet(models.QuerySet):
    def aktiv(self):
        return self.filter(archiviert_am__isnull=True)


class Projekt(models.Model):
    """Gehört keinem Bereich, sondern trägt Tags."""

    name = models.CharField(_("Name"), max_length=150)
    farbe = models.CharField(
        _("Farbe"), max_length=20, choices=Projektfarbe.choices, default=Projektfarbe.BLAU
    )
    beschreibung = models.TextField(_("Beschreibung"), blank=True)
    projektleitung = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True,
        related_name="geleitete_projekte", verbose_name=_("Projektleitung"),
    )
    mitglieder = models.ManyToManyField(
        Person, blank=True, related_name="projekte", verbose_name=_("Mitglieder")
    )
    tags = models.ManyToManyField(Tag, blank=True, related_name="projekte", verbose_name=_("Tags"))
    # 1 = höchste Priorität; Projekte ohne Priorität stehen hinten
    prioritaet = models.PositiveSmallIntegerField(_("Priorität"), choices=PRIORITAETEN, null=True, blank=True)
    archiviert_am = models.DateTimeField(_("archiviert am"), null=True, blank=True)
    # Geplanter Zeitraum für das Gantt-Diagramm
    beginn = models.DateField(_("Beginn"), null=True, blank=True)
    ende = models.DateField(_("Ende"), null=True, blank=True)
    erstellt_von = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    objects = ProjektQuerySet.as_manager()

    class Meta:
        ordering = [F("prioritaet").asc(nulls_last=True), Lower("name")]
        verbose_name = _("Projekt")
        verbose_name_plural = _("Projekte")

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("projekt", args=[self.pk])

    @property
    def archiviert(self):
        return self.archiviert_am is not None


class Abschnitt(models.Model):
    projekt = models.ForeignKey(Projekt, on_delete=models.CASCADE, related_name="abschnitte")
    name = models.CharField(_("Name"), max_length=120)
    sortierung = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["sortierung", "id"]
        verbose_name = _("Abschnitt")
        verbose_name_plural = _("Abschnitte")

    def __str__(self):
        return self.name


class Statusfarbe(models.TextChoices):
    GRAU = "grau", _("Grau")
    BLAU = "blau", _("Blau")
    GELB = "gelb", _("Gelb")
    ORANGE = "orange", _("Orange")
    GRUEN = "gruen", _("Grün")


class Status(models.Model):
    """Systemweit konfigurierbar."""

    name = models.CharField(_("Name"), max_length=60, unique=True)
    sortierung = models.PositiveIntegerField(_("Sortierung"), default=0)
    ist_erledigt = models.BooleanField(_("gilt als erledigt"), default=False)
    farbe = models.CharField(
        _("Farbe"), max_length=20, choices=Statusfarbe.choices, default=Statusfarbe.GRAU
    )

    class Meta:
        ordering = ["sortierung", "id"]
        verbose_name = _("Status")
        verbose_name_plural = _("Status")

    def __str__(self):
        return self.name

    @classmethod
    def standard_offen(cls):
        return cls.objects.filter(ist_erledigt=False).first()

    @classmethod
    def standard_erledigt(cls):
        return cls.objects.filter(ist_erledigt=True).first()


# Unteraufgaben gibt es bis zu drei Ebenen unter der Hauptaufgabe
UNTERAUFGABEN_EBENEN = 3


class Aufgabe(models.Model):
    """Aufgabe oder – mit ``eltern`` – Unteraufgabe (bis zu UNTERAUFGABEN_EBENEN tief).

    Unteraufgaben sind vollwertige Aufgaben (Detailseite, Termine, Kommentare, Einteilungen …)
    und liegen immer im Projekt und Abschnitt ihrer Hauptaufgabe. Aufgaben ohne Abschnitt stehen
    in der Projektliste oben (neue Projekte haben keine Abschnitte).
    """

    projekt = models.ForeignKey(Projekt, on_delete=models.CASCADE, related_name="aufgaben")
    abschnitt = models.ForeignKey(Abschnitt, on_delete=models.PROTECT, null=True, blank=True,
                                  related_name="aufgaben", verbose_name=_("Abschnitt"))
    eltern = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True, related_name="unteraufgaben",
        verbose_name=_("Hauptaufgabe"),
    )
    titel = models.CharField(_("Titel"), max_length=300)
    beschreibung = models.TextField(_("Beschreibung"), blank=True)  # bereinigtes HTML
    verantwortlich = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True,
        related_name="verantwortete_aufgaben", verbose_name=_("Verantwortlich"),
    )
    gewerk = models.ForeignKey(
        Gewerk, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="aufgaben", verbose_name=_("Gewerk"),
    )
    beginn_am = models.DateField(_("Geplanter Beginn"), null=True, blank=True)  # Gantt
    faellig_am = models.DateField(_("Fällig am"), null=True, blank=True)
    status = models.ForeignKey(Status, on_delete=models.PROTECT, related_name="+",
                               verbose_name=_("Status"))
    schaetzung_personentage = models.DecimalField(
        _("Geschätzte Personentage"), max_digits=5, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(0)],
    )
    sortierung = models.PositiveIntegerField(default=0)
    erledigt_am = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)  # optimistisches Sperren
    erstellt_von = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sortierung", "id"]
        verbose_name = _("Aufgabe")
        verbose_name_plural = _("Aufgaben")
        indexes = [
            models.Index(fields=["projekt", "abschnitt", "sortierung"]),
            models.Index(fields=["faellig_am"]),
        ]

    def __str__(self):
        return self.titel

    def get_absolute_url(self):
        return reverse("aufgabe", args=[self.pk])

    @property
    def ist_erledigt(self):
        return self.status.ist_erledigt

    def vorfahren(self):
        """Hauptaufgaben von oben nach unten (ohne die Aufgabe selbst)."""
        kette, aufgabe = [], self
        while aufgabe.eltern_id:
            aufgabe = aufgabe.eltern
            kette.append(aufgabe)
        return kette[::-1]

    @property
    def tiefe(self):
        """0 = Hauptaufgabe, 1 = Unteraufgabe, 2 und 3 = weitere Ebenen."""
        return len(self.vorfahren())


class Abhaengigkeit(models.Model):
    """„A vor B“: ``nachher`` soll erst beginnen, wenn ``vorher`` fertig ist.

    Auch zwischen Aufgaben verschiedener Projekte. Rückt A nach hinten, schiebt
    ``projekte.termine`` die geplanten Termine von B nach; Überschneidungen
    der tatsächlichen Einteilungen werden nur markiert.
    """

    vorher = models.ForeignKey("Aufgabe", on_delete=models.CASCADE, related_name="nachfolger_links")
    nachher = models.ForeignKey("Aufgabe", on_delete=models.CASCADE, related_name="vorgaenger_links")
    erstellt_von = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = _("Abhängigkeit")
        verbose_name_plural = _("Abhängigkeiten")
        constraints = [
            models.UniqueConstraint(fields=["vorher", "nachher"], name="abhaengigkeit_eindeutig"),
            models.CheckConstraint(condition=~models.Q(vorher=models.F("nachher")), name="abhaengigkeit_nicht_selbst"),
        ]

    def __str__(self):
        return f"{self.vorher} → {self.nachher}"
