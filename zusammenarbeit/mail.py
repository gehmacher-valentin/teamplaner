"""E-Mail-Benachrichtigungen und System-Mails (Einladung, Passwort-Reset).

* Jede Person schaltet einzelne Ereignisse ein; Standard ist alles aus.
* Benachrichtigungen mit ``mail_status = offen`` verschickt der Dienst
  ``python manage.py mails_versenden --dauerhaft`` sofort (alle paar Sekunden).
* Ohne konfigurierten SMTP-Server (``EMAIL_HOST`` leer) oder mit abgeschaltetem Versand
  (``Systemeinstellungen.mail_versand``) wird nichts verschickt.
* Jede verschickte oder fehlgeschlagene E-Mail ergibt eine Protokollzeile (Art, Empfänger, Eintrag),
  nie Betreff oder Text: der Betreff enthält Aufgabentitel, der Text Passwort-Links. Den Verlauf
  aus der Datenbank liefert ``zusammenarbeit.mailverlauf``.
"""

import logging
from collections import defaultdict
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.db import transaction
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import formats, timezone, translation
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
    Postausgang.objects.filter(status=MailStatus.OFFEN).update(status=MailStatus.KEINE, text="", html="")
    Benachrichtigung.objects.filter(mail_status=MailStatus.OFFEN).update(mail_status=MailStatus.KEINE)


def mail_erwuenscht(konto, art):
    return bool((konto.mail_einstellungen or {}).get(str(art)))


def absolute_url(pfad):
    return settings.TEAMPLANER_ADRESSE.rstrip("/") + pfad


def _marke():
    org = Systemeinstellungen.laden().organisation
    return _("Teamplaner · %(org)s") % {"org": org} if org else _("Teamplaner")


def _fusszeile():
    return "\n\n-- \n" + _marke() + "\n" + \
        _("E-Mail-Einstellungen ändern: %(link)s") % {"link": absolute_url(reverse("einst_benachrichtigungen"))}


def _html(betreff, bloecke, titel=""):
    """HTML-Teil im Stil des Teamplaners (Tabellen und Inline-Styles, keine Bilder oder Skripte):
    dunkler Kopf wie auf der Webseite, Inhalt als Karte mit optionalem ``titel``, Blau nur für den
    Hauptknopf und Links.

    ``bloecke``: Liste aus ``{"absatz": text}``, ``{"knopf": beschriftung, "url": url}``,
    ``{"link": url}`` (Adresse zum Kopieren) und ``{"ereignisse": [{"text", "zeit", "url", "beschriftung"}]}``.
    Alle Texte werden im Template escaped."""
    return render_to_string("mail/basis.html", {
        "betreff": betreff, "titel": titel, "marke": _marke(), "bloecke": bloecke,
        "organisation": Systemeinstellungen.laden().organisation,
        "einstellungen_url": absolute_url(reverse("einst_benachrichtigungen")),
        "sprache": translation.get_language(),
    })


def protokoll_adresse(email):
    """Empfängeradresse für das Protokoll: vollständig oder, wenn so eingestellt, gekürzt."""
    if settings.TEAMPLANER_PROTOKOLL_EMPFAENGER:
        return email
    name, _at, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


def _protokoll_verschickt(art, empfaenger, eintrag):
    log.info("E-Mail verschickt: %s an %s (%s)", art, protokoll_adresse(empfaenger), eintrag)


def _protokoll_fehler(art, empfaenger, eintrag, versuch, fehler):
    """Eine Zeile je Fehlversuch, ohne Traceback: bei einem Ausfall des SMTP-Servers wiederholt sich
    der Fehler alle paar Sekunden. Der vollständige Fehler steht mit TEAMPLANER_LOGLEVEL=DEBUG im Protokoll."""
    grund = " ".join(f"{type(fehler).__name__}: {fehler}".split())
    if versuch >= MAX_VERSUCHE:
        log.error("E-Mail aufgegeben nach %s Versuchen: %s an %s (%s): %s",
                  versuch, art, protokoll_adresse(empfaenger), eintrag, grund)
    else:
        log.warning("E-Mail fehlgeschlagen, Versuch %s von %s: %s an %s (%s): %s",
                    versuch, MAX_VERSUCHE, art, protokoll_adresse(empfaenger), eintrag, grund)
    log.debug("Fehler beim Versand (%s)", eintrag, exc_info=fehler)


def _senden(empfaenger_email, betreff, text, html=""):
    """Text-Teil immer, dazu der HTML-Teil als Alternative (multipart/alternative)."""
    betreff = " ".join(betreff.split())  # Zeilenumbrüche (z. B. im Aufgabentitel) sind im Betreff ungültig
    nachricht = EmailMultiAlternatives(subject=betreff[:200], body=text, to=[empfaenger_email])
    if html:
        nachricht.attach_alternative(html, "text/html")
    nachricht.send(fail_silently=False)


def _ziel(b):
    """Link zur Benachrichtigung: (Textzeile, Knopfbeschriftung, Adresse) oder None."""
    if b.aufgabe_id:
        url = absolute_url(b.aufgabe.get_absolute_url())
        return _("Zur Aufgabe: %(link)s") % {"link": url}, _("Zur Aufgabe"), url
    if b.art == A.LIEFERTERMIN:
        url = absolute_url(reverse("bestellungen"))
        return _("Zur Bestellliste: %(link)s") % {"link": url}, _("Zur Bestellliste"), url
    return None


def benachrichtigung_senden(b):
    """Verschickt eine Benachrichtigung in der Sprache der empfangenden Person."""
    konto = b.empfaenger.konto
    with translation.override(konto.sprache):
        betreff = f"[{_('Teamplaner')}] {b.text}"
        zeilen, bloecke = [b.text], [{"absatz": b.text}]
        ziel = _ziel(b)
        if ziel:
            zeilen += ["", ziel[0]]
            bloecke.append({"knopf": ziel[1], "url": ziel[2]})
        _senden(konto.email, betreff, "\n".join(zeilen) + _fusszeile(), _html(betreff, bloecke))


def sammelmail_senden(liste):
    """Mehrere Benachrichtigungen an dieselbe Person als eine Mail, in zeitlicher Reihenfolge."""
    konto = liste[0].empfaenger.konto
    with translation.override(konto.sprache):
        betreff = f"[{_('Teamplaner')}] " + _("%(n)s neue Benachrichtigungen") % {"n": len(liste)}
        posteingang = absolute_url(reverse("posteingang"))
        zeilen, ereignisse = [], []
        for b in liste:
            zeit = formats.date_format(timezone.localtime(b.erstellt_am), "H:i")
            ziel = _ziel(b)
            zeilen.append(f"- {zeit} {b.text}")
            if ziel:
                zeilen.append(f"  {ziel[0]}")
            ereignisse.append({"zeit": zeit, "text": b.text, "beschriftung": ziel[1] if ziel else "",
                               "url": ziel[2] if ziel else ""})
        zeilen += ["", _("Zum Posteingang: %(link)s") % {"link": posteingang}]
        bloecke = [{"ereignisse": ereignisse}, {"knopf": _("Zum Posteingang"), "url": posteingang}]
        titel = _("%(n)s neue Benachrichtigungen") % {"n": len(liste)}
        _senden(konto.email, betreff, "\n".join(zeilen) + _fusszeile(), _html(betreff, bloecke, titel))


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
                _senden(m.empfaenger, m.betreff, m.text, m.html)
            except Exception as fehler:  # noqa: BLE001 – SMTP-Fehler protokollieren, später erneut versuchen
                m.versuche += 1
                _protokoll_fehler(m.art, m.empfaenger, f"System-Mail {m.pk}", m.versuche, fehler)
                if m.versuche >= MAX_VERSUCHE:
                    m.status, m.text, m.html = MailStatus.FEHLER, "", ""
                m.save(update_fields=["versuche", "status", "text", "html"])
                continue
            # Text und HTML enthalten ggf. einen Passwort-Link – nach dem Versand nicht aufheben
            m.status, m.text, m.html, m.gesendet_am = MailStatus.GESENDET, "", "", timezone.now()
            m.save(update_fields=["status", "text", "html", "gesendet_am"])
            _protokoll_verschickt(m.art, m.empfaenger, f"System-Mail {m.pk}")
            gesendet += 1
    return gesendet


def _eintrag(liste):
    if len(liste) == 1:
        return f"Benachrichtigung {liste[0].pk}"
    return "Benachrichtigungen " + ", ".join(str(b.pk) for b in liste)


def _benachrichtigungen_versenden(limit):
    """Je Person eine Mail: Alle offenen Benachrichtigungen einer Person gehen zusammen raus, sobald
    die älteste ``TEAMPLANER_MAIL_SAMMELN_SEKUNDEN`` alt ist (0: sofort). ``limit`` zählt Personen."""
    fenster = settings.TEAMPLANER_MAIL_SAMMELN_SEKUNDEN
    bis = timezone.now() - timedelta(seconds=fenster)
    gesendet = 0
    with transaction.atomic():
        offen = list(
            Benachrichtigung.objects.select_for_update(skip_locked=True, of=("self",))
            .filter(mail_status=MailStatus.OFFEN)
            .select_related("empfaenger__konto", "aufgabe")
            .order_by("empfaenger_id", "erstellt_am", "id")
        )
        je_person = defaultdict(list)
        for b in offen:
            if b.empfaenger.archiviert or not hasattr(b.empfaenger, "konto"):
                b.mail_status = MailStatus.KEINE
                b.save(update_fields=["mail_status"])
                continue
            je_person[b.empfaenger_id].append(b)
        faellig = [liste for liste in je_person.values() if fenster <= 0 or liste[0].erstellt_am <= bis]
        for liste in faellig[:limit]:
            if fenster <= 0:  # bisheriges Verhalten: jede einzeln
                gesendet += sum(_mail_versenden([b]) for b in liste)
            else:
                gesendet += _mail_versenden(liste)
    return gesendet


def _mail_versenden(liste):
    """Eine Mail für ``liste`` (gleiche Person); Status und Versuche gelten für alle enthaltenen."""
    email, art = liste[0].empfaenger.konto.email, liste[0].art if len(liste) == 1 else "sammelmail"
    try:
        if len(liste) == 1:
            benachrichtigung_senden(liste[0])
        else:
            sammelmail_senden(liste)
    except Exception as fehler:  # noqa: BLE001 – SMTP-Fehler protokollieren, später erneut versuchen
        versuch = max(b.mail_versuche for b in liste) + 1
        _protokoll_fehler(art, email, _eintrag(liste), versuch, fehler)
        for b in liste:
            b.mail_versuche += 1
            if b.mail_versuche >= MAX_VERSUCHE:
                b.mail_status = MailStatus.FEHLER
            b.save(update_fields=["mail_versuche", "mail_status"])
        return 0
    jetzt = timezone.now()
    for b in liste:
        b.mail_status, b.gesendet_am = MailStatus.GESENDET, jetzt
        b.save(update_fields=["mail_status", "gesendet_am"])
    _protokoll_verschickt(art, email, _eintrag(liste))
    return 1


def _einreihen(art, empfaenger, betreff, text, html=""):
    Postausgang.objects.create(art=art, empfaenger=empfaenger, betreff=betreff[:200], text=text, html=html)


def einladung_senden(konto, link):
    """Einladung mit Link zum Passwort-Setzen. Gibt True zurück, wenn sie verschickt wird."""
    if not mail_aktiv():
        return False
    with translation.override(konto.sprache):
        gruss = _("Guten Tag %(name)s,") % {"name": konto.person.anzeigename}
        bitte = _("für Sie wurde ein Konto im Teamplaner angelegt. Bitte legen Sie über diesen Link Ihr Passwort fest:")
        gilt = _("Der Link gilt einige Tage und nur einmal. Ihre Anmeldung ist Ihre E-Mail-Adresse: %(email)s") % {
            "email": konto.email}
        text = "\n".join([gruss, "", bitte, link, "", gilt])
        betreff = f"[{_('Teamplaner')}] " + _("Einladung")
        html = _html(betreff, [{"absatz": gruss}, {"absatz": bitte}, {"knopf": _("Passwort festlegen"), "url": link},
                               {"link": link}, {"absatz": gilt}], _("Einladung"))
        _einreihen(Postausgang.Art.EINLADUNG, konto.email, betreff, text + _fusszeile(), html)
    return True


def reset_senden(konto, link):
    """Link zum Zurücksetzen – nur an die Person selbst. Gibt True zurück, wenn er verschickt wird."""
    if not mail_aktiv():
        return False
    with translation.override(konto.sprache):
        gruss = _("Guten Tag %(name)s,") % {"name": konto.person.anzeigename}
        bitte = _("über diesen Link legen Sie ein neues Passwort fest:")
        gilt = _("Der Link gilt %(n)s Stunden und nur einmal.") % {"n": settings.TEAMPLANER_RESET_GUELTIG_STUNDEN}
        ignorieren = _("Wenn Sie das nicht angefordert haben, können Sie diese E-Mail ignorieren.")
        text = "\n".join([gruss, "", bitte, link, "", gilt, ignorieren])
        betreff = f"[{_('Teamplaner')}] " + _("Passwort zurücksetzen")
        html = _html(betreff, [{"absatz": gruss}, {"absatz": bitte}, {"knopf": _("Passwort festlegen"), "url": link},
                               {"link": link}, {"absatz": gilt}, {"absatz": ignorieren}],
                     _("Passwort zurücksetzen"))
        _einreihen(Postausgang.Art.RESET, konto.email, betreff, text + _fusszeile(), html)
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
        gruss = _("Guten Tag %(name)s,") % {"name": konto.person.anzeigename}
        hinweis = str(SICHERHEITSHINWEISE[anlass]) % werte
        warnung = _("Waren Sie das nicht, wenden Sie sich bitte sofort an die Administration.")
        text = "\n".join([gruss, "", hinweis, "", warnung])
        betreff = f"[{_('Teamplaner')}] " + _("Sicherheitshinweis zu Ihrem Konto")
        html = _html(betreff, [{"absatz": gruss}, {"absatz": hinweis}, {"absatz": warnung, "wichtig": True},
                               {"knopf": _("Zur Anmeldung"), "url": absolute_url(reverse("login"))}],
                     _("Sicherheitshinweis zu Ihrem Konto"))
        _einreihen(Postausgang.Art.SICHERHEIT, an or konto.email, betreff, text + _fusszeile(), html)
