"""Personen, Bereiche, Konten und Rollen.

Jede einteilbare Person ist eine ``Person``. Personen mit Zugang haben zusätzlich ein
``Konto`` (1 : 0..1). Platzhalter sind Personen ohne Konto – es gibt dafür kein eigenes
Flag, damit kein widersprüchlicher Zustand entstehen kann. Alle fachlichen Verweise
(Verantwortliche:r, Einteilung, Abwesenheit, Erwähnung) zeigen auf ``Person``.
"""

import re

from django.conf import settings
from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class Bereich(models.Model):
    """Organisationseinheit; dient nur zum Gruppieren und Filtern, vergibt keine Rechte."""

    name = models.CharField(_("Name"), max_length=100, unique=True)
    sortierung = models.PositiveIntegerField(_("Sortierung"), default=0)

    class Meta:
        ordering = ["sortierung", "name"]
        verbose_name = _("Bereich")
        verbose_name_plural = _("Bereiche")

    def __str__(self):
        return self.name


class Gewerk(models.Model):
    name = models.CharField(_("Name"), max_length=100, unique=True)

    class Meta:
        ordering = ["name"]
        verbose_name = _("Gewerk")
        verbose_name_plural = _("Gewerke")

    def __str__(self):
        return self.name


class PersonQuerySet(models.QuerySet):
    def aktiv(self):
        return self.filter(archiviert_am__isnull=True)

    def auswaehlbar(self):
        """Für alle Personenauswahlen (Teamplaner, Verantwortlich, Mitglieder, Erwähnungen …): aktiv und
        kein Systemkonto. Die Konten- und Personenverwaltung zeigt weiterhin alle."""
        return self.aktiv().exclude(konto__systemkonto=True)

    def platzhalter(self):
        return self.filter(konto__isnull=True)

    def mit_konto(self):
        return self.filter(konto__isnull=False)


def initialen(name):
    """Kürzel für Avatare: „Person 01“ → „P1“, „Aushilfe Montage“ → „AM“."""
    teile = [re.sub(r"\W", "", t) for t in re.split(r"[\s\-]+", name or "")]
    teile = [t for t in teile if t]
    if not teile:
        return "?"
    erster = teile[0][0].upper()
    if len(teile) == 1:
        return (teile[0][:2]).upper()
    zweiter = teile[1]
    if zweiter.isdigit():
        return erster + str(int(zweiter))[:2]
    return erster + zweiter[0].upper()


class Person(models.Model):
    anzeigename = models.CharField(_("Anzeigename"), max_length=150)
    bereich = models.ForeignKey(
        Bereich, on_delete=models.PROTECT, related_name="personen", verbose_name=_("Bereich")
    )
    gewerke = models.ManyToManyField(
        Gewerk, blank=True, related_name="personen", verbose_name=_("Gewerke")
    )
    notiz = models.CharField(_("Notiz"), max_length=500, blank=True)
    # Profilfoto (nur Personen mit Konto; Platzhalter nur mit Anzeigename)
    foto = models.ImageField(_("Foto"), upload_to="fotos/", blank=True)
    archiviert_am = models.DateTimeField(_("archiviert am"), null=True, blank=True)
    erstellt_von = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    erstellt_am = models.DateTimeField(auto_now_add=True)

    objects = PersonQuerySet.as_manager()

    class Meta:
        ordering = ["anzeigename", "id"]
        verbose_name = _("Person")
        verbose_name_plural = _("Personen")

    def __str__(self):
        return self.anzeigename

    @property
    def ist_platzhalter(self):
        return not hasattr(self, "konto")

    @property
    def archiviert(self):
        return self.archiviert_am is not None

    @property
    def systemkonto(self):
        konto = getattr(self, "konto", None)  # Platzhalter haben keins
        return bool(konto and konto.systemkonto)

    @property
    def auswaehlbar(self):
        """Wie ``Person.objects.auswaehlbar()`` für eine einzelne Person."""
        return not self.archiviert and not self.systemkonto

    @property
    def initialen(self):
        return initialen(self.anzeigename)

    @property
    def foto_url(self):
        """Adresse des Fotos (nur für Angemeldete) mit Version gegen veraltete Caches."""
        if not self.foto:
            return None
        from django.urls import reverse

        version = self.foto.name.rsplit("/", 1)[-1].split(".")[0][:8]
        return f"{reverse('person_foto', args=[self.pk])}?v={version}"

    def archivieren(self):
        if self.archiviert_am is None:
            self.archiviert_am = timezone.now()
            self.save(update_fields=["archiviert_am"])

    def wiederherstellen(self):
        if self.archiviert_am is not None:
            self.archiviert_am = None
            self.save(update_fields=["archiviert_am"])


class Rolle(models.TextChoices):
    """Fest vorgegebene, systemweite Rollen. Die Rechte stehen in ``kern.rechte``."""

    ADMIN = "admin", _("Admin")
    BEREICHSLEITUNG = "bereichsleitung", _("Bereichsleitung")
    PLANER = "planer", _("Planer:in")
    MITARBEITER = "mitarbeiter", _("Mitarbeiter:in")
    LESEND = "lesend", _("Lesend")


ROLLEN_RANG = {
    Rolle.ADMIN: 50,
    Rolle.BEREICHSLEITUNG: 40,
    Rolle.PLANER: 30,
    Rolle.MITARBEITER: 20,
    Rolle.LESEND: 10,
}


class KontoManager(BaseUserManager):
    def get_by_natural_key(self, email):
        return self.get(email__iexact=email)

    def anlegen(self, email, *, anzeigename, bereich, rolle=Rolle.MITARBEITER, password=None,
                erstellt_von=None, person=None):
        """Legt Konto (und, falls nicht übergeben, die Person) an."""
        if person is None:
            person = Person.objects.create(
                anzeigename=anzeigename, bereich=bereich, erstellt_von=erstellt_von
            )
        konto = self.model(person=person, email=self.normalize_email(email).lower(), rolle=rolle)
        if password:
            konto.set_password(password)
        else:
            konto.set_unusable_password()
        konto.save()
        return konto


class Konto(AbstractBaseUser):
    """Anmeldedaten und Rolle einer Person. Platzhalter haben strukturell kein Konto."""

    person = models.OneToOneField(
        Person, on_delete=models.PROTECT, primary_key=True, related_name="konto"
    )
    email = models.EmailField(_("E-Mail"), unique=True)
    rolle = models.CharField(_("Rolle"), max_length=20, choices=Rolle.choices)
    # E-Mail je Ereignis (Schlüssel = zusammenarbeit.models.Benachrichtigungsart); leer = alles aus
    mail_einstellungen = models.JSONField(_("E-Mail-Benachrichtigungen"), default=dict, blank=True)
    sprache = models.CharField(_("Sprache"), max_length=5, choices=settings.LANGUAGES, default="de")
    feier_animation = models.BooleanField(_("Feieranimation beim Abhaken"), default=False)
    # Gantt: Unteraufgaben immer aufgeklappt; Maßstab, Pfeile usw. bleiben im Browser
    gantt_unteraufgaben_offen = models.BooleanField(_("Unteraufgaben im Gantt aufgeklappt"), default=False)
    # Technisches Konto: behält alle Rechte seiner Rolle, steht aber in keiner Personenauswahl
    systemkonto = models.BooleanField(_("Systemkonto – nicht als Person auswählbar"), default=False)
    # Zwei-Faktor-Anmeldung (kern.zwei_faktor); leer = nicht eingerichtet
    totp_geheimnis = models.CharField(max_length=64, blank=True, editable=False)
    totp_seit = models.DateTimeField(null=True, blank=True, editable=False)
    totp_letzter_schritt = models.BigIntegerField(null=True, blank=True, editable=False)
    totp_ersatzcodes = models.JSONField(default=list, blank=True, editable=False)
    # Persönliche Daten nach der Frist für deaktivierte Konten entfernt (kern.aufraeumen)
    daten_entfernt_am = models.DateTimeField(null=True, blank=True, editable=False)

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = KontoManager()

    class Meta:
        verbose_name = _("Konto")
        verbose_name_plural = _("Konten")
        constraints = [
            models.UniqueConstraint(Lower("email"), name="konto_email_eindeutig_ci"),
        ]

    def __str__(self):
        return f"{self.person.anzeigename} <{self.email}>"

    @property
    def is_active(self):
        # Deaktivierte Konten = archivierte Personen
        return self.person.archiviert_am is None

    @property
    def rang(self):
        return ROLLEN_RANG[self.rolle]

    def hat_mindestens(self, rolle):
        return self.rang >= ROLLEN_RANG[rolle]

    # Keine Django-Administrationsoberfläche und keine Django-Permissions: Rechte stehen in
    # kern.rechte. Die Attribute gibt es nur, weil Django-Teile danach fragen können.
    is_staff = False
    is_superuser = False

    def has_perm(self, perm, obj=None):
        return False

    def has_module_perms(self, app_label):
        return False


class Protokolleintrag(models.Model):
    """Revisionssicheres Änderungsprotokoll und Verlauf je Aufgabe.

    Nur Einfügen: UPDATE und DELETE werden per Datenbank-Trigger abgewiesen.
    Objekte werden per ID referenziert (keine Fremdschlüssel), damit Einträge auch nach
    dem Löschen des Objekts unverändert bestehen bleiben.
    """

    zeitpunkt = models.DateTimeField(default=timezone.now, db_index=True)
    akteur = models.ForeignKey(
        Person, on_delete=models.PROTECT, null=True, blank=True, related_name="+"
    )
    objekt_typ = models.CharField(max_length=40)
    objekt_id = models.BigIntegerField(null=True, blank=True)
    aufgabe_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    aktion = models.CharField(max_length=40)
    daten = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-zeitpunkt", "-id"]
        verbose_name = _("Protokolleintrag")
        verbose_name_plural = _("Protokoll")
        indexes = [models.Index(fields=["objekt_typ", "objekt_id"])]

    def __str__(self):
        return f"{self.zeitpunkt:%d.%m.%Y %H:%M} {self.objekt_typ} {self.aktion}"


class Systemeinstellungen(models.Model):
    """Globale Schalter für alle (eine Zeile, pk=1); ändern darf nur Admin."""

    freigabe_zeile = models.BooleanField(_("Tagesfreigabe"), default=False)
    freigabe_name = models.CharField(_("Name der Tagesfreigabe"), max_length=40, blank=True)
    organisation = models.CharField(_("Organisationsname"), max_length=100, blank=True)
    mail_versand = models.BooleanField(_("E-Mail-Versand"), default=True)

    class Meta:
        verbose_name = _("Systemeinstellungen")
        verbose_name_plural = _("Systemeinstellungen")

    def __str__(self):
        return str(_("Systemeinstellungen"))

    @classmethod
    def laden(cls):
        return cls.objects.get_or_create(pk=1)[0]

    @property
    def freigabe_bezeichnung(self):
        return self.freigabe_name or str(_("Tagesfreigabe"))


class Resetanfrage(models.Model):
    """„Passwort vergessen“-Anfragen für die Drosselung je Adresse und je IP.

    Statt der E-Mail nur ihr Hash; Einträge älter als ein Tag werden beim nächsten Aufruf gelöscht.
    """

    zeitpunkt = models.DateTimeField(default=timezone.now, db_index=True)
    ip = models.GenericIPAddressField(null=True, blank=True)
    email_hash = models.CharField(max_length=64)

    def __str__(self):
        return f"{self.zeitpunkt:%d.%m.%Y %H:%M} {self.ip or '–'}"
