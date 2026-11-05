"""Wer welche Gantt-Ansicht sehen oder bearbeiten darf – gleiche Regeln wie im Teamplaner.

* Admin und Bereichsleitung: alle Ansichten sehen und bearbeiten, Ansichten verwalten.
* Alle anderen: nur freigegebene Ansichten; „bearbeiten“ wirkt erst ab Planer:in.
"""

from kern import rechte as kern_rechte
from planung.models import Recht

from .models import GanttAnsicht, GanttFreigabe


def freigaben(konto):
    """``{ansicht_id: recht}`` – effektives Recht je Gantt-Ansicht."""
    if kern_rechte.sieht_alles_im_teamplaner(konto):
        return {a: Recht.BEARBEITEN for a in GanttAnsicht.objects.values_list("id", flat=True)}
    if not kern_rechte.darf_lesen(konto):
        return {}
    darf_bearbeiten = kern_rechte.darf_planen(konto)
    return {
        ansicht_id: (Recht.BEARBEITEN if recht == Recht.BEARBEITEN and darf_bearbeiten else Recht.SEHEN)
        for ansicht_id, recht in GanttFreigabe.objects.filter(konto=konto).values_list("ansicht_id", "recht")
    }


def recht(konto, ansicht):
    return freigaben(konto).get(ansicht.pk)


def darf_verwalten(konto):
    """Gantt-Ansichten anlegen, Projekte hinzufügen/entfernen, freigeben."""
    return kern_rechte.darf_ansichten_verwalten(konto)


def hat_gantt(konto):
    return darf_verwalten(konto) or bool(freigaben(konto))
