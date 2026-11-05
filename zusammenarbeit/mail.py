"""E-Mail-Benachrichtigungen und System-Mails (Einladung, Passwort-Reset).

* Jede Person schaltet einzelne Ereignisse ein; Standard ist alles aus.
* Benachrichtigungen mit ``mail_status = offen`` verschickt der Dienst
  ``python manage.py mails_versenden --dauerhaft`` sofort (alle paar Sekunden).
* Ohne konfigurierten SMTP-Server (``EMAIL_HOST`` leer) oder mit abgeschaltetem Versand
  (``Systemeinstellungen.mail_versand``) wird nichts verschickt.
"""

import logging

from django.conf import settings
from django.core.mail import EmailMessage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone, translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from kern.models import Systemeinstellungen

from .models import Benachrichtigung, Benachrichtigungsart, MailStatus, Postausgang

log = logging.getLogger(__name__)
A = Benachrichtigungsart

KATEGORIEN = [
    ("aufgaben", gettext_lazy("Aufgaben"), [
        (A.ZUWEISUNG, gettext_lazy("Mir wird eine Aufgabe zugewiesen")),
        (A.AUFGABE_GEAENDERT, gettext_lazy("Jemand ändert eine Aufgabe, für die ich verantwortlich bin")),
        (A.AUFGABE_ERLEDIGT, gettext_lazy("Eine Aufgabe, die ich verantworte oder angelegt habe, wird erledigt")),
        (A.PROJEKT_AUFGABE_NEU, gettext_lazy("Neue Aufgabe in einem Projekt, das ich leite")),
    ]),
    ("kommentare", gettext_lazy("Kommentare & Erwähnungen"), [
        (A.ERWAEHNUNG, gettext_lazy("Ich werde in einem Kommentar erwähnt")),
        (A.ERWAEHNUNG_PLATZHALTER, gettext_lazy("Ein von mir angelegter Platzhalter wird erwähnt")),
        (A.KOMMENTAR, gettext_lazy("Neuer Kommentar zu einer Aufgabe, für die ich verantwortlich bin")),
    ]),
    ("einteilung", gettext_lazy("Einteilung im Teamplaner"), [
        (A.EINTEILUNG_NEU, gettext_lazy("Ich werde eingeteilt")),
        (A.EINTEILUNG_GEAENDERT, gettext_lazy("Meine Einteilung wird geändert")),
        (A.EINTEILUNG_ENTFERNT, gettext_lazy("Meine Einteilung wird entfernt")),
    ]),
    ("bestellungen", gettext_lazy("Bestellungen"), [
        (A.LIEFERTERMIN, gettext_lazy("Der Liefertermin einer Bestellung, die ich bestellt habe, ist überschritten")),
    ]),
]
ALLE_ARTEN = [art for _k, _t, arten in KATEGORIEN for art, _b in arten]
MAX_VERSUCHE = 5


def mail_eingerichtet():
    return bool(settings.EMAIL_HOST)


def mail_aktiv():
    return mail_eingerichtet() and Systemeinstellungen.laden().mail_versand


def wartende_verwerfen():
    """Beim Abschalten des Versands: Wartendes ginge sonst beim Wiedereinschalten verspätet
    raus, auch abgelaufene oder ersetzte Passwort-Links – deshalb auch den Text leeren."""
    Postausgang.objects.filter(status=MailStatus.OFFEN).update(status=MailStatus.KEINE, text="")
    Benachrichtigung.objects.filter(mail_status=MailStatus.OFFEN).update(mail_status=MailStatus.KEINE)


def mail_erwuenscht(konto, art):
    return bool((konto.mail_einstellungen or {}).get(str(art)))


def absolute_url(pfad):
    return settings.TEAMPLANER_ADRESSE.rstrip("/") + pfad


def _fusszeile():
    org = Systemeinstellungen.laden().organisation
    marke = _("Teamplaner · %(org)s") % {"org": org} if org else _("Teamplaner")
    return "\n\n-- \n" + marke + "\n" + \
        _("E-Mail-Einstellungen ändern: %(link)s") % {"link": absolute_url(reverse("einst_benachrichtigungen"))}


def _senden(empfaenger_email, betreff, text):
    betreff = " ".join(betreff.split())  # Zeilenumbrüche (z. B. im Aufgabentitel) sind im Betreff ungültig
    EmailMessage(subject=betreff[:200], body=text, to=[empfaenger_email]).send(fail_silently=False)


def benachrichtigung_senden(b):
    """Verschickt eine Benachrichtigung in der Sprache der empfangenden Person."""
    konto = b.empfaenger.konto
    with translation.override(konto.sprache):
        betreff = f"[{_('Teamplaner')}] {b.text}"
        zeilen = [b.text]
        if b.aufgabe_id:
            zeilen.append("")
            zeilen.append(_("Zur Aufgabe: %(link)s") % {"link": absolute_url(b.aufgabe.get_absolute_url())})
        elif b.art == A.LIEFERTERMIN:
            zeilen.append("")
            zeilen.append(_("Zur Bestellliste: %(link)s") % {"link": absolute_url(reverse("bestellungen"))})
        _senden(konto.email, betreff, "\n".join(zeilen) + _fusszeile())


def offene_versenden(limit=50):
    """Verschickt offene System-Mails und Benachrichtigungen; gibt die Zahl der verschickten zurück."""
    if not mail_aktiv():
        return 0
    return _postausgang_versenden(limit) + _benachrichtigungen_versenden(limit)


def _postausgang_versenden(limit):
    gesendet = 0
    with transaction.atomic():
        for m in Postausgang.objects.select_for_update(skip_locked=True).filter(status=MailStatus.OFFEN)[:limit]:
            try:
                _senden(m.empfaenger, m.betreff, m.text)
            except Exception:  # noqa: BLE001 – SMTP-Fehler protokollieren, später erneut versuchen
                log.exception("System-Mail %s fehlgeschlagen", m.pk)
                m.versuche += 1
                if m.versuche >= MAX_VERSUCHE:
                    m.status, m.text = MailStatus.FEHLER, ""
                m.save(update_fields=["versuche", "status", "text"])
                continue
            # Text enthält ggf. einen Passwort-Link – nach dem Versand nicht aufheben
            m.status, m.text, m.gesendet_am = MailStatus.GESENDET, "", timezone.now()
            m.save(update_fields=["status", "text", "gesendet_am"])
            gesendet += 1
    return gesendet


def _benachrichtigungen_versenden(limit):
    gesendet = 0
    with transaction.atomic():
        offen = list(
            Benachrichtigung.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(mail_status=MailStatus.OFFEN)
            .select_related("empfaenger__konto", "aufgabe")[:limit]
        )
        for b in offen:
            if b.empfaenger.archiviert or not hasattr(b.empfaenger, "konto"):
                b.mail_status = MailStatus.KEINE
                b.save(update_fields=["mail_status"])
                continue
            try:
                benachrichtigung_senden(b)
            except Exception:  # noqa: BLE001 – SMTP-Fehler protokollieren, später erneut versuchen
                log.exception("E-Mail an %s fehlgeschlagen", b.empfaenger_id)
                b.mail_versuche += 1
                if b.mail_versuche >= MAX_VERSUCHE:
                    b.mail_status = MailStatus.FEHLER
                b.save(update_fields=["mail_versuche", "mail_status"])
                continue
            b.mail_status = MailStatus.GESENDET
            b.gesendet_am = timezone.now()
            b.save(update_fields=["mail_status", "gesendet_am"])
            gesendet += 1
    return gesendet


def _einreihen(art, empfaenger, betreff, text):
    Postausgang.objects.create(art=art, empfaenger=empfaenger, betreff=betreff[:200], text=text)


def einladung_senden(konto, link):
    """Einladung mit Link zum Passwort-Setzen. Gibt True zurück, wenn sie verschickt wird."""
    if not mail_aktiv():
        return False
    with translation.override(konto.sprache):
        text = "\n".join([
            _("Guten Tag %(name)s,") % {"name": konto.person.anzeigename},
            "",
            _("für Sie wurde ein Konto im Teamplaner angelegt. Bitte legen Sie über diesen Link Ihr Passwort fest:"),
            link,
            "",
            _("Der Link gilt einige Tage und nur einmal. Ihre Anmeldung ist Ihre E-Mail-Adresse: %(email)s") % {"email": konto.email},
        ])
        _einreihen(Postausgang.Art.EINLADUNG, konto.email, f"[{_('Teamplaner')}] " + _("Einladung"), text + _fusszeile())
    return True


def reset_senden(konto, link):
    """Link zum Zurücksetzen – nur an die Person selbst. Gibt True zurück, wenn er verschickt wird."""
    if not mail_aktiv():
        return False
    with translation.override(konto.sprache):
        text = "\n".join([
            _("Guten Tag %(name)s,") % {"name": konto.person.anzeigename},
            "",
            _("über diesen Link legen Sie ein neues Passwort fest:"),
            link,
            "",
            _("Der Link gilt %(n)s Stunden und nur einmal.") % {"n": settings.TEAMPLANER_RESET_GUELTIG_STUNDEN},
            _("Wenn Sie das nicht angefordert haben, können Sie diese E-Mail ignorieren."),
        ])
        _einreihen(Postausgang.Art.RESET, konto.email, f"[{_('Teamplaner')}] " + _("Passwort zurücksetzen"),
                   text + _fusszeile())
    return True


SICHERHEITSHINWEISE = {
    "passwort_geaendert": gettext_lazy("das Passwort Ihres Teamplaner-Kontos wurde geändert."),
    "passwort_zurueckgesetzt": gettext_lazy("das Passwort Ihres Teamplaner-Kontos wurde über einen Link neu festgelegt."),
    "email_geaendert": gettext_lazy("die Anmelde-E-Mail Ihres Teamplaner-Kontos wurde auf %(neu)s geändert."),
    "zwei_faktor_eingerichtet": gettext_lazy("für Ihr Teamplaner-Konto wurde die Zwei-Faktor-Anmeldung eingerichtet "
                                             "(bzw. ein neues Telefon verbunden)."),
    "zwei_faktor_ausgeschaltet": gettext_lazy("die Zwei-Faktor-Anmeldung Ihres Teamplaner-Kontos wurde ausgeschaltet."),
    "zwei_faktor_zurueckgesetzt": gettext_lazy("die Zwei-Faktor-Anmeldung Ihres Teamplaner-Kontos wurde von der "
                                               "Verwaltung zurückgesetzt."),
}


def sicherheitshinweis(konto, anlass, an=None, **werte):
    """Hinweis an die Person bei Änderungen an ihrer Anmeldung – immer, unabhängig von den
    E-Mail-Einstellungen. ``an``: andere Adresse, z. B. die bisherige nach einer Änderung der E-Mail."""
    if not mail_aktiv():
        return
    with translation.override(konto.sprache):
        text = "\n".join([
            _("Guten Tag %(name)s,") % {"name": konto.person.anzeigename},
            "",
            str(SICHERHEITSHINWEISE[anlass]) % werte,
            "",
            _("Waren Sie das nicht, wenden Sie sich bitte sofort an die Administration."),
        ])
        _einreihen(Postausgang.Art.SICHERHEIT, an or konto.email,
                   f"[{_('Teamplaner')}] " + _("Sicherheitshinweis zu Ihrem Konto"), text + _fusszeile())
