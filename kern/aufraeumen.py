"""Lösch- und Aufbewahrungsfristen – läuft täglich im Dienst ``mails_versenden``.

* Allgemein nach TEAMPLANER_AUFBEWAHRUNG_TAGE (365): Änderungsprotokoll (frühestens nach einem Jahr,
  das erzwingt der Datenbank-Trigger), Anmeldeprotokoll mit IP-Adressen (django-axes),
  Benachrichtigungen und Postausgang.
* Deaktivierte Personen nach TEAMPLANER_DEAKTIVIERT_TAGE (90): E-Mail, Passwort, Zwei-Faktor,
  E-Mail-Einstellungen, Foto, persönliche Notizen und Freigaben werden entfernt. Der Name bleibt – in
  alten Einteilungen, Aufgaben und Kommentaren; Kommentare und Anhänge werden nie gelöscht.
  Archivierte Platzhalter verlieren ihre Notiz.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import fotos, zwei_faktor
from .models import Konto, Person, Protokolleintrag, Resetanfrage
from .protokoll import protokollieren

PROTOKOLL_MINDESTENS_TAGE = 365  # wie im Trigger kern_protokoll_nur_einfuegen


def aufraeumen(jetzt=None):
    """Gibt {Bereich: Anzahl gelöschter bzw. bereinigter Einträge} zurück."""
    from axes.models import AccessAttempt, AccessFailureLog, AccessLog

    from zusammenarbeit.models import Benachrichtigung, Postausgang

    jetzt = jetzt or timezone.now()
    grenze = jetzt - timedelta(days=settings.TEAMPLANER_AUFBEWAHRUNG_TAGE)
    protokoll_grenze = min(grenze, jetzt - timedelta(days=PROTOKOLL_MINDESTENS_TAGE))
    anmeldungen = sum(modell.objects.filter(attempt_time__lt=grenze).delete()[0]
                      for modell in (AccessLog, AccessFailureLog, AccessAttempt))
    Resetanfrage.objects.filter(zeitpunkt__lt=jetzt - timedelta(days=1)).delete()
    return {
        "protokoll": Protokolleintrag.objects.filter(zeitpunkt__lt=protokoll_grenze).delete()[0],
        "anmeldeprotokoll": anmeldungen,
        "benachrichtigungen": Benachrichtigung.objects.filter(erstellt_am__lt=grenze).delete()[0],
        "postausgang": Postausgang.objects.filter(erstellt_am__lt=grenze).delete()[0],
        "deaktivierte_konten": deaktivierte_bereinigen(jetzt),
        "platzhalter_notizen": (Person.objects.platzhalter()
                                .filter(archiviert_am__lt=jetzt - timedelta(days=settings.TEAMPLANER_DEAKTIVIERT_TAGE))
                                .exclude(notiz="").update(notiz="")),
    }


def deaktivierte_bereinigen(jetzt):
    from notizen.models import Notiz, NotizAnhang

    grenze = jetzt - timedelta(days=settings.TEAMPLANER_DEAKTIVIERT_TAGE)
    konten = Konto.objects.select_related("person").filter(person__archiviert_am__lt=grenze,
                                                          daten_entfernt_am__isnull=True)
    anzahl = 0
    for konto in konten:
        person = konto.person
        with transaction.atomic():
            for anhang in NotizAnhang.objects.filter(notiz__besitzer=person):
                anhang.datei.delete(save=False)
            Notiz.objects.filter(besitzer=person).delete()
            konto.notizordner.clear()
            konto.ansicht_freigaben.all().delete()
            konto.gantt_freigaben.all().delete()
            fotos.entfernen(person)
            zwei_faktor.zuruecksetzen(konto)
            konto.email = f"entfernt-{konto.pk}@konto.invalid"
            konto.set_unusable_password()
            konto.mail_einstellungen = {}
            konto.daten_entfernt_am = jetzt
            konto.save(update_fields=["email", "password", "mail_einstellungen", "daten_entfernt_am"])
            protokollieren(None, "konto", konto.pk, "daten_entfernt", {"person": person})
        anzahl += 1
    return anzahl
