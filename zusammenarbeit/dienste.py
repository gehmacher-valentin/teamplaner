"""Benachrichtigungen erzeugen.

Der Text wird in der Sprache der empfangenden Person gespeichert. Ob zusätzlich eine
E-Mail verschickt wird, entscheidet deren Einstellung (Standard: aus).
"""

from django.utils import translation
from django.utils.formats import date_format
from django.utils.translation import gettext_lazy as _

from .models import Benachrichtigung, Benachrichtigungsart, MailStatus
from .verlauf import FELDNAMEN

A = Benachrichtigungsart


def _zeitraum(von, bis):
    if von == bis:
        return date_format(von, "D d.m.Y")
    return f"{date_format(von, 'd.m.')}–{date_format(bis, 'd.m.Y')}"


def benachrichtigen(empfaenger, art, vorlage, werte=None, *, aufgabe=None, ausloeser=None):
    """Legt eine Benachrichtigung an – nicht für Platzhalter, Archivierte oder sich selbst.

    ``vorlage`` ist ein übersetzbarer Text mit %(name)s-Platzhaltern; Werte dürfen
    Funktionen sein, die erst in der Sprache der empfangenden Person ausgewertet werden
    (z. B. Datumsangaben).
    """
    if empfaenger is None or empfaenger.ist_platzhalter or empfaenger.archiviert:
        return None
    if ausloeser is not None and empfaenger.pk == ausloeser.pk:
        return None
    konto = empfaenger.konto
    with translation.override(konto.sprache):
        aufgeloest = {k: (v() if callable(v) else v) for k, v in (werte or {}).items()}
        text = str(vorlage) % aufgeloest
    from .mail import mail_aktiv, mail_erwuenscht

    status = MailStatus.OFFEN if mail_erwuenscht(konto, art) and mail_aktiv() else MailStatus.KEINE
    return Benachrichtigung.objects.create(
        empfaenger=empfaenger, art=art, text=text[:500], aufgabe=aufgabe, ausloeser=ausloeser,
        mail_status=status,
    )


# --- Einteilung ---

def einteilung_benachrichtigen(konto, einteilung, aktion, alt_person=None):
    akteur = konto.person
    werte = {
        "akteur": akteur.anzeigename,
        "titel": einteilung.aufgabe.titel,
        "zeitraum": lambda: _zeitraum(einteilung.von, einteilung.bis),
    }
    arten = {
        "angelegt": (A.EINTEILUNG_NEU, _("%(akteur)s hat Sie für „%(titel)s“ eingeteilt: %(zeitraum)s.")),
        "geaendert": (A.EINTEILUNG_GEAENDERT, _("%(akteur)s hat Ihre Einteilung für „%(titel)s“ geändert: %(zeitraum)s.")),
        "geloescht": (A.EINTEILUNG_ENTFERNT, _("%(akteur)s hat Ihre Einteilung für „%(titel)s“ (%(zeitraum)s) entfernt.")),
    }
    art, vorlage = arten[aktion]
    if alt_person is not None and alt_person.pk != einteilung.person_id:
        # Auf eine andere Person verschoben: für die neue Person ist es eine neue Einteilung
        art, vorlage = arten["angelegt"]
        benachrichtigen(alt_person, A.EINTEILUNG_ENTFERNT,
                        _("%(akteur)s hat Ihre Einteilung für „%(titel)s“ an jemand anderen übergeben."),
                        werte, aufgabe=einteilung.aufgabe, ausloeser=akteur)
    benachrichtigen(einteilung.person, art, vorlage, werte, aufgabe=einteilung.aufgabe, ausloeser=akteur)


# --- Aufgaben ---

def zuweisung_benachrichtigen(konto, aufgabe):
    benachrichtigen(aufgabe.verantwortlich, A.ZUWEISUNG, _("%(akteur)s hat Ihnen „%(titel)s“ zugewiesen."),
                    {"akteur": konto.person.anzeigename, "titel": aufgabe.titel},
                    aufgabe=aufgabe, ausloeser=konto.person)


def aufgabe_geaendert_benachrichtigen(konto, aufgabe, felder):
    """Änderung durch jemand anderen an die verantwortliche Person; „erledigt“ zusätzlich
    an die Person, die die Aufgabe angelegt hat."""
    akteur = konto.person
    werte = {"akteur": akteur.anzeigename, "titel": aufgabe.titel}
    if "status" in felder and aufgabe.status.ist_erledigt:
        empfaenger = {p.pk: p for p in [aufgabe.verantwortlich, aufgabe.erstellt_von] if p is not None}
        for person in empfaenger.values():
            benachrichtigen(person, A.AUFGABE_ERLEDIGT, _("%(akteur)s hat „%(titel)s“ erledigt."), werte,
                            aufgabe=aufgabe, ausloeser=akteur)
        felder = [f for f in felder if f != "status"]
    felder = [f for f in felder if f != "verantwortlich"]  # dafür gibt es die Zuweisung
    if felder and aufgabe.verantwortlich_id:
        namen = lambda: ", ".join(str(FELDNAMEN.get(f, f)) for f in felder)  # noqa: E731
        benachrichtigen(aufgabe.verantwortlich, A.AUFGABE_GEAENDERT,
                        _("%(akteur)s hat „%(titel)s“ geändert (%(felder)s)."),
                        {**werte, "felder": namen}, aufgabe=aufgabe, ausloeser=akteur)


def projekt_aufgabe_benachrichtigen(konto, aufgabe):
    benachrichtigen(aufgabe.projekt.projektleitung, A.PROJEKT_AUFGABE_NEU,
                    _("%(akteur)s hat im Projekt „%(projekt)s“ die Aufgabe „%(titel)s“ angelegt."),
                    {"akteur": konto.person.anzeigename, "projekt": aufgabe.projekt.name, "titel": aufgabe.titel},
                    aufgabe=aufgabe, ausloeser=konto.person)


# --- Kommentare ---

def erwaehnung_benachrichtigen(konto, kommentar, personen):
    """Erwähnte Platzhalter: Benachrichtigung an die anlegende Person."""
    akteur = konto.person
    werte = {"akteur": akteur.anzeigename, "titel": kommentar.aufgabe.titel}
    for person in personen:
        if person.ist_platzhalter:
            benachrichtigen(person.erstellt_von, A.ERWAEHNUNG_PLATZHALTER,
                            _("%(akteur)s hat den Platzhalter %(platzhalter)s bei „%(titel)s“ erwähnt."),
                            {**werte, "platzhalter": person.anzeigename},
                            aufgabe=kommentar.aufgabe, ausloeser=akteur)
        else:
            benachrichtigen(person, A.ERWAEHNUNG, _("%(akteur)s hat Sie bei „%(titel)s“ erwähnt."), werte,
                            aufgabe=kommentar.aufgabe, ausloeser=akteur)


def kommentar_benachrichtigen(konto, kommentar, erwaehnte):
    """Neuer Kommentar an die verantwortliche Person – außer sie wurde ohnehin erwähnt."""
    verantwortlich = kommentar.aufgabe.verantwortlich
    if verantwortlich is None or verantwortlich.pk in {p.pk for p in erwaehnte}:
        return
    benachrichtigen(verantwortlich, A.KOMMENTAR, _("%(akteur)s hat „%(titel)s“ kommentiert."),
                    {"akteur": konto.person.anzeigename, "titel": kommentar.aufgabe.titel},
                    aufgabe=kommentar.aufgabe, ausloeser=konto.person)
