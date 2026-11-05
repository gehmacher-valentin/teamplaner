"""Kommentare mit @-Erwähnung, Anhänge und Benachrichtigungen."""

import uuid
from pathlib import Path

from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from kern.models import Person
from projekte.models import Aufgabe


class Kommentar(models.Model):
    """Text mit Erwähnungs-Platzhaltern ``@[<person_id>]``; der Name wird beim Anzeigen
    eingesetzt, damit er auch nach Umbenennen oder Archivieren stimmt."""

    aufgabe = models.ForeignKey(Aufgabe, on_delete=models.CASCADE, related_name="kommentare")
    autor = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="+")
    text = models.TextField(_("Text"))
    erstellt_am = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["erstellt_am", "id"]
        verbose_name = _("Kommentar")
        verbose_name_plural = _("Kommentare")

    def __str__(self):
        return f"{self.autor}: {self.text[:40]}"


class Erwaehnung(models.Model):
    kommentar = models.ForeignKey(Kommentar, on_delete=models.CASCADE, related_name="erwaehnungen")
    person = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="erwaehnungen")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["kommentar", "person"], name="erwaehnung_eindeutig"),
        ]

    def __str__(self):
        return f"@{self.person}"


def anhang_pfad(instanz, dateiname):
    # Speichername ohne Benutzereingabe; Originalname steht in ``dateiname``
    endung = Path(dateiname).suffix.lower()[:10]
    return f"anhaenge/{timezone.now():%Y/%m}/{uuid.uuid4().hex}{endung}"


class Anhang(models.Model):
    aufgabe = models.ForeignKey(Aufgabe, on_delete=models.CASCADE, related_name="anhaenge")
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


class Benachrichtigungsart(models.TextChoices):
    """Ereignisse für Posteingang und E-Mail; Gruppierung in zusammenarbeit.mail.KATEGORIEN."""

    ZUWEISUNG = "zuweisung", _("Zuweisung")
    AUFGABE_GEAENDERT = "aufgabe_geaendert", _("Aufgabe geändert")
    AUFGABE_ERLEDIGT = "aufgabe_erledigt", _("Aufgabe erledigt")
    PROJEKT_AUFGABE_NEU = "projekt_aufgabe_neu", _("Neue Aufgabe im Projekt")
    ERWAEHNUNG = "erwaehnung", _("Erwähnung")
    ERWAEHNUNG_PLATZHALTER = "erwaehnung_platzhalter", _("Erwähnung eines Platzhalters")
    KOMMENTAR = "kommentar", _("Kommentar")
    EINTEILUNG_NEU = "einteilung_neu", _("Eingeteilt")
    EINTEILUNG_GEAENDERT = "einteilung_geaendert", _("Einteilung geändert")
    EINTEILUNG_ENTFERNT = "einteilung_entfernt", _("Einteilung entfernt")
    LIEFERTERMIN = "liefertermin", _("Liefertermin überschritten")


class MailStatus(models.TextChoices):
    KEINE = "", _("keine E-Mail")
    OFFEN = "offen", _("wird verschickt")
    GESENDET = "gesendet", _("verschickt")
    FEHLER = "fehler", _("Fehler")


class Benachrichtigung(models.Model):
    """Wird bei den Ereignissen in Benachrichtigungsart erzeugt (Posteingang).

    Platzhalter erhalten keine Benachrichtigungen; Erwähnungen gehen an die anlegende
    Person. Hat die empfangende Person das Ereignis für E-Mail eingeschaltet, steht
    ``mail_status`` auf „offen“ und der Dienst ``mails_versenden`` verschickt sie sofort.
    Der Text ist bereits in der Sprache der empfangenden Person gespeichert.
    """

    empfaenger = models.ForeignKey(Person, on_delete=models.PROTECT, related_name="benachrichtigungen")
    art = models.CharField(max_length=30, choices=Benachrichtigungsart.choices)
    aufgabe = models.ForeignKey(
        Aufgabe, on_delete=models.CASCADE, null=True, blank=True, related_name="+"
    )
    ausloeser = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    text = models.CharField(max_length=500)
    erstellt_am = models.DateTimeField(default=timezone.now)
    gelesen_am = models.DateTimeField(null=True, blank=True)
    mail_status = models.CharField(max_length=10, choices=MailStatus.choices, default=MailStatus.KEINE, blank=True)
    mail_versuche = models.PositiveSmallIntegerField(default=0)
    gesendet_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-erstellt_am", "-id"]
        verbose_name = _("Benachrichtigung")
        verbose_name_plural = _("Benachrichtigungen")
        indexes = [
            models.Index(fields=["empfaenger", "gelesen_am"]),
            models.Index(fields=["mail_status"]),
        ]

    def __str__(self):
        return self.text


class Postausgang(models.Model):
    """System-Mails (Einladung, Passwort-Link, Sicherheitshinweis), verschickt vom Dienst
    ``mails_versenden`` – nicht während der Anfrage, damit Antwortzeit und SMTP-Fehler nichts über
    Konten verraten. Nach dem Versand wird der Text geleert (er enthält Passwort-Links)."""

    class Art(models.TextChoices):
        EINLADUNG = "einladung", _("Einladung")
        RESET = "reset", _("Passwort zurücksetzen")
        SICHERHEIT = "sicherheit", _("Sicherheitshinweis")

    art = models.CharField(max_length=20, choices=Art.choices)
    empfaenger = models.EmailField()
    betreff = models.CharField(max_length=200)
    text = models.TextField(blank=True)
    erstellt_am = models.DateTimeField(default=timezone.now)
    status = models.CharField(max_length=10, choices=MailStatus.choices, default=MailStatus.OFFEN, blank=True)
    versuche = models.PositiveSmallIntegerField(default=0)
    gesendet_am = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["erstellt_am", "id"]
        verbose_name = _("System-Mail")
        verbose_name_plural = _("Postausgang")
        indexes = [models.Index(fields=["status"], name="postausgang_status")]

    def __str__(self):
        return f"{self.get_art_display()} an {self.empfaenger}"
