"""Wer welche Notizen sehen und bearbeiten darf (serverseitig).

* Persönliche Notizen: nur die eigene Person – auch Admins sehen sie nicht.
* Gruppenordner: nur die Konten, denen der Ordner freigegeben ist, und Admins (sie stehen als
  Systemkonto evtl. in keiner Mitgliederauswahl). Lesen dürfen alle freigegebenen Konten, schreiben
  ab Mitarbeiter:in.
* Ordner anlegen, umbenennen, freigeben, löschen: ab Planer:in, für Ordner, die ihnen freigegeben sind.
"""

from kern import rechte as kern_rechte

from .models import Ordner


def _mitglied(konto, ordner):
    return kern_rechte.ist_admin(konto) or ordner.mitglieder.filter(pk=konto.pk).exists()


def sichtbare_ordner(konto):
    if not kern_rechte.darf_lesen(konto):
        return Ordner.objects.none()
    if kern_rechte.ist_admin(konto):
        return Ordner.objects.all()
    return Ordner.objects.filter(mitglieder=konto)


def darf_ordner_anlegen(konto):
    return kern_rechte.darf_planen(konto)


def darf_ordner_verwalten(konto, ordner):
    return kern_rechte.darf_planen(konto) and _mitglied(konto, ordner)


def darf_ordner_lesen(konto, ordner):
    return kern_rechte.darf_lesen(konto) and _mitglied(konto, ordner)


def darf_ordner_schreiben(konto, ordner):
    return kern_rechte.darf_abschliessen_und_kommentieren(konto) and darf_ordner_lesen(konto, ordner)


def darf_notiz_lesen(konto, notiz):
    if notiz.ordner_id is None:
        return kern_rechte.darf_lesen(konto) and notiz.besitzer_id == konto.person_id
    return darf_ordner_lesen(konto, notiz.ordner)


def darf_notiz_schreiben(konto, notiz):
    if notiz.ordner_id is None:
        return kern_rechte.darf_lesen(konto) and notiz.besitzer_id == konto.person_id
    return darf_ordner_schreiben(konto, notiz.ordner)
