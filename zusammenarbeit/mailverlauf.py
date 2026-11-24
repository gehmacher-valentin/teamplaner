"""Versandverlauf der E-Mails aus der Datenbank: System-Mails (``Postausgang``) und
Benachrichtigungen mit E-Mail (``Benachrichtigung``), gemeinsam für den Befehl ``mail_protokoll`` und
die Seite „E-Mail-Versand“ in den Einstellungen.

Betreff und Text gehören nie in den Verlauf: der Betreff enthält Aufgabentitel, der Text
Passwort-Links. Der Verlauf reicht so weit zurück wie die Aufbewahrungsfrist (``verwaltung.aufraeumen``).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta

from django.utils import timezone

from kern.models import Konto

from .models import Benachrichtigung, MailStatus, Postausgang

STATUS = (MailStatus.OFFEN, MailStatus.GESENDET, MailStatus.FEHLER)
# Offene Mails verschickt der Dienst alle paar Sekunden. Liegt eine länger, läuft er vermutlich nicht.
HAENGT_NACH = timedelta(minutes=15)
MIT_LINK = (Postausgang.Art.EINLADUNG, Postausgang.Art.RESET)


@dataclass(frozen=True)
class Eintrag:
    quelle: str  # "system" (Postausgang) oder "benachrichtigung"
    id: int
    erstellt_am: datetime
    art: str  # lesbar, z. B. „Einladung“
    empfaenger: str  # E-Mail-Adresse, leer wenn das Konto fehlt
    status: str  # MailStatus
    status_text: str
    versuche: int
    gesendet_am: datetime | None
    # Aufgegeben, aber der Text ist noch da (Benachrichtigung, Sicherheitshinweis): lässt sich erneut einreihen
    wiederholbar: bool = False
    # Konto zu einer aufgegebenen Einladung oder einem Passwort-Link: der Text ist gelöscht, es hilft nur ein neuer Link
    neuer_link_fuer: Konto | None = None

    @property
    def kennung(self):
        return f"{'System-Mail' if self.quelle == 'system' else 'Benachrichtigung'} {self.id}"


def _zeitraum(abfrage, tage):
    return abfrage.filter(erstellt_am__gte=timezone.now() - timedelta(days=tage)) if tage else abfrage


def verlauf(tage=None, status=None, limit=None):
    """Einträge beider Quellen, neueste zuerst. ``status``: offen, gesendet oder fehler (sonst alle drei);
    ``tage``: nur Einträge der letzten N Tage; ``limit``: höchstens so viele."""
    gewaehlt = [status] if status in STATUS else list(STATUS)
    system = (_zeitraum(Postausgang.objects.filter(status__in=gewaehlt), tage)
              .select_related("konto__person").order_by("-erstellt_am", "-id"))
    hinweise = (_zeitraum(Benachrichtigung.objects.filter(mail_status__in=gewaehlt), tage)
                .select_related("empfaenger__konto").order_by("-erstellt_am", "-id"))
    if limit:
        system, hinweise = system[:limit], hinweise[:limit]
    eintraege = [
        Eintrag("system", m.pk, m.erstellt_am, m.get_art_display(), m.empfaenger, m.status,
                m.get_status_display(), m.versuche, m.gesendet_am,
                wiederholbar=m.status == MailStatus.FEHLER and m.art == Postausgang.Art.SICHERHEIT and bool(m.text),
                neuer_link_fuer=m.konto if m.status == MailStatus.FEHLER and m.art in MIT_LINK else None)
        for m in system
    ] + [
        Eintrag("benachrichtigung", b.pk, b.erstellt_am, b.get_art_display(),
                getattr(getattr(b.empfaenger, "konto", None), "email", ""), b.mail_status,
                b.get_mail_status_display(), b.mail_versuche, b.gesendet_am,
                wiederholbar=b.mail_status == MailStatus.FEHLER)
        for b in hinweise
    ]
    eintraege.sort(key=lambda e: (e.erstellt_am, e.id), reverse=True)
    return eintraege[:limit] if limit else eintraege


def zahlen():
    """Überblick: offene und aufgegebene E-Mails, in den letzten 24 Stunden verschickte, und ob der
    Versand hängt (älteste offene E-Mail liegt länger als ``HAENGT_NACH``)."""
    jetzt = timezone.now()
    seit = jetzt - timedelta(hours=24)

    def anzahl(status, **zeit):
        return (Postausgang.objects.filter(status=status, **zeit).count()
                + Benachrichtigung.objects.filter(mail_status=status, **zeit).count())

    aelteste = [d for d in (
        Postausgang.objects.filter(status=MailStatus.OFFEN).order_by("erstellt_am").values_list("erstellt_am", flat=True).first(),
        Benachrichtigung.objects.filter(mail_status=MailStatus.OFFEN).order_by("erstellt_am")
        .values_list("erstellt_am", flat=True).first(),
    ) if d]
    aelteste_offene = min(aelteste) if aelteste else None
    return {
        "offen": anzahl(MailStatus.OFFEN),
        "fehler": anzahl(MailStatus.FEHLER),
        "gesendet_24h": anzahl(MailStatus.GESENDET, gesendet_am__gte=seit),
        "aelteste_offene": aelteste_offene,
        "haengt": aelteste_offene is not None and jetzt - aelteste_offene > HAENGT_NACH,
    }


def erneut_versuchen(benachrichtigung_id):
    """Aufgegebene Benachrichtigung wieder einreihen. Gibt die Benachrichtigung zurück oder None,
    wenn sie nicht (mehr) aufgegeben ist."""
    geaendert = Benachrichtigung.objects.filter(pk=benachrichtigung_id, mail_status=MailStatus.FEHLER).update(
        mail_status=MailStatus.OFFEN, mail_versuche=0)
    return Benachrichtigung.objects.select_related("empfaenger").get(pk=benachrichtigung_id) if geaendert else None


def hinweis_erneut_versuchen(system_mail_id):
    """Aufgegebenen Sicherheitshinweis wieder einreihen, solange sein Text da ist. Gibt die System-Mail
    zurück oder None, wenn sie nicht (mehr) aufgegeben ist oder sich nicht wiederholen lässt."""
    geaendert = (Postausgang.objects
                 .filter(pk=system_mail_id, art=Postausgang.Art.SICHERHEIT, status=MailStatus.FEHLER).exclude(text="")
                 .update(status=MailStatus.OFFEN, versuche=0))
    return Postausgang.objects.select_related("konto__person").get(pk=system_mail_id) if geaendert else None
