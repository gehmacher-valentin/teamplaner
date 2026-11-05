"""Notizen: persönliche Notizen je Person und Gruppenordner mit Freigabe an einzelne Personen.

Der Ordner „Persönliche Notizen“ ist kein Datensatz – persönliche Notizen haben einen
``besitzer`` und keinen ``ordner``. Gruppenordner legen Planer:innen und höher an und geben
sie einzelnen Konten frei; Rechte stehen in ``notizen.rechte``.
"""

import uuid
from pathlib import Path

from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from kern.models import Konto, Person

from .markdown import als_text


class Ordner(models.Model):
    name = models.CharField(_("Name"), max_length=120)
    mitglieder = models.ManyToManyField(
        Konto, blank=True, related_name="notizordner", verbose_name=_("Freigegeben für"),
    )
    erstellt_von = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    erstellt_am = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = [Lower("name"), "id"]
        verbose_name = _("Notizordner")
        verbose_name_plural = _("Notizordner")

    def __str__(self):
        return self.name


class Notiz(models.Model):
    """Einfacher Markdown-Text; entweder in einem Gruppenordner oder persönlich (``besitzer``)."""

    ordner = models.ForeignKey(Ordner, on_delete=models.CASCADE, null=True, blank=True, related_name="notizen")
    besitzer = models.ForeignKey(Person, on_delete=models.CASCADE, null=True, blank=True, related_name="notizen")
    titel = models.CharField(_("Titel"), max_length=200)
    text = models.TextField(_("Text"), blank=True)  # Markdown, im Editor als formatierter Text
    version = models.PositiveIntegerField(default=1)  # gleichzeitiges Bearbeiten in Gruppenordnern
    erstellt_von = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    erstellt_am = models.DateTimeField(auto_now_add=True)
    geaendert_von = models.ForeignKey(Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    geaendert_am = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-geaendert_am", "-id"]
        verbose_name = _("Notiz")
        verbose_name_plural = _("Notizen")
        constraints = [
            models.CheckConstraint(
                condition=Q(ordner__isnull=True, besitzer__isnull=False) | Q(ordner__isnull=False, besitzer__isnull=True),
                name="notiz_ordner_oder_besitzer",
            ),
        ]

    def __str__(self):
        return self.titel

    @property
    def auszug(self):
        return als_text(self.text)


def anhang_pfad(instanz, dateiname):
    # Speichername ohne Benutzereingabe; Originalname steht in ``dateiname``
    endung = Path(dateiname).suffix.lower()[:10]
    return f"notizen/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{endung}"


class NotizAnhang(models.Model):
    """Datei an einer Notiz; sichtbar für alle, die die Notiz sehen."""

    notiz = models.ForeignKey(Notiz, on_delete=models.CASCADE, related_name="anhaenge")
    datei = models.FileField(upload_to=anhang_pfad, max_length=200)
    dateiname = models.CharField(_("Dateiname"), max_length=255)
    groesse = models.PositiveBigIntegerField(_("Größe"))
    content_type = models.CharField(max_length=120, blank=True)
    hochgeladen_von = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="+")
    hochgeladen_am = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["hochgeladen_am", "id"]
        verbose_name = _("Anhang")
        verbose_name_plural = _("Anhänge")

    def __str__(self):
        return self.dateiname

    @property
    def ist_bild(self):
        return self.content_type.startswith("image/")

    @property
    def hat_vorschau(self):
        """Bildformate, die jeder Browser direkt anzeigt (HEIC u. ä. nicht)."""
        return self.content_type in {"image/png", "image/jpeg", "image/gif", "image/webp"}
