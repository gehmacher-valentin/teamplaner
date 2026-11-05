"""Freigaben von Teamplaner- und Gantt-Ansichten an einzelne Konten.

Gemeinsam für beide Arten und für die Personenseite: „—“, „Sehen“ oder „Bearbeiten“ je
Konto; „Bearbeiten“ wirkt erst ab Planer:in und wird darunter auf „Sehen“ gesetzt. Admin und
Bereichsleitung sehen und bearbeiten ohnehin alles und haben keine Freigabe-Einträge.
"""

from django.db import transaction

from . import rechte
from .models import Konto, Rolle
from .protokoll import protokollieren

KEINE, SEHEN, BEARBEITEN = "", "sehen", "bearbeiten"


def arten():
    """Art → (Ansicht-Modell, Freigabe-Modell, Protokoll-Typ, Recht zum Verwalten, URL-Name der Bearbeiten-Seite)."""
    from gantt import rechte as gantt_rechte
    from gantt.models import GanttAnsicht, GanttFreigabe
    from planung.models import AnsichtFreigabe, TeamplanerAnsicht

    return {
        "teamplaner": (TeamplanerAnsicht, AnsichtFreigabe, "ansicht", rechte.darf_ansichten_verwalten, "ansicht_bearbeiten"),
        "gantt": (GanttAnsicht, GanttFreigabe, "gantt_ansicht", gantt_rechte.darf_verwalten, "gantt_ansicht_bearbeiten"),
    }


def konten():
    """Aktive Konten in der Reihenfolge Bereich, Name."""
    return list(Konto.objects.select_related("person__bereich").filter(person__archiviert_am__isnull=True)
                .order_by("person__bereich__sortierung", "person__anzeigename"))


def erlaubt(konto, recht):
    """„Bearbeiten“ nur ab Planer:in, sonst höchstens „Sehen“."""
    if recht == BEARBEITEN and not konto.hat_mindestens(Rolle.PLANER):
        return SEHEN
    return recht if recht in (SEHEN, BEARBEITEN) else KEINE


def zeilen(liste, bisher, post=None):
    """Zeilen des Freigaben-Bauteils (teile/freigaben.html)."""
    return [{
        "konto": k,
        "immer": rechte.sieht_alles_im_teamplaner(k),
        "darf_bearbeiten": k.hat_mindestens(Rolle.PLANER),
        "recht": post.get(f"freigabe-{k.pk}", bisher.get(k.pk, KEINE)) if post is not None else bisher.get(k.pk, KEINE),
    } for k in liste]


def zusammenfassung(rechte_je_konto):
    werte = list(rechte_je_konto.values()) if isinstance(rechte_je_konto, dict) else list(rechte_je_konto)
    return {"sehen": werte.count(SEHEN), "bearbeiten": werte.count(BEARBEITEN)}


def aus_formular(liste, post):
    """Freigaben aus dem Formular der Ansicht (Felder freigabe-<Konto>)."""
    neu = {}
    for konto in liste:
        if rechte.sieht_alles_im_teamplaner(konto):
            continue
        wert = erlaubt(konto, post.get(f"freigabe-{konto.pk}", KEINE))
        if wert:
            neu[konto.pk] = wert
    return neu


def speichern(freigabe_modell, ansicht, neu, bisher):
    """Freigaben einer Ansicht ersetzen; gibt die Änderungen {Konto-ID: [alt, neu]} fürs Protokoll zurück."""
    freigabe_modell.objects.filter(ansicht=ansicht).exclude(konto_id__in=list(neu)).delete()
    for konto_id, recht in neu.items():
        freigabe_modell.objects.update_or_create(ansicht=ansicht, konto_id=konto_id, defaults={"recht": recht})
    return {str(k): [bisher.get(k), neu.get(k)] for k in set(bisher) | set(neu) if bisher.get(k) != neu.get(k)}


def setzen(akteur, art, ansicht, ziel, recht):
    """Eine Freigabe ändern (Personenseite) – protokolliert wie eine Änderung an der Ansicht.
    Gibt das tatsächlich gesetzte Recht zurück."""
    _ansicht_modell, freigabe_modell, typ, *_rest = arten()[art]
    recht = erlaubt(ziel, recht)
    with transaction.atomic():
        alt = freigabe_modell.objects.filter(ansicht=ansicht, konto=ziel).values_list("recht", flat=True).first()
        if recht:
            freigabe_modell.objects.update_or_create(ansicht=ansicht, konto=ziel, defaults={"recht": recht})
        else:
            freigabe_modell.objects.filter(ansicht=ansicht, konto=ziel).delete()
        if (alt or KEINE) != recht:
            protokollieren(akteur, typ, ansicht.pk, "geaendert",
                           {"name": ansicht.name, "freigaben": {str(ziel.pk): [alt, recht or None]}})
    return recht


def herabstufen(akteur, ziel):
    """Rolle unter Planer:in gesetzt: vorhandenes „Bearbeiten“ wird überall „Sehen“."""
    if ziel.hat_mindestens(Rolle.PLANER):
        return
    for art, (_a, freigabe_modell, _typ, *_rest) in arten().items():
        for f in freigabe_modell.objects.filter(konto=ziel, recht=BEARBEITEN).select_related("ansicht"):
            setzen(akteur, art, f.ansicht, ziel, SEHEN)
