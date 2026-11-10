"""Freigaben über beide Arten von Ansichten hinweg (Personenseite, Liste der Ansichten).
Die gemeinsame Logik je Ansicht liegt in kern.freigaben."""

from django.db import transaction

from gantt import rechte as gantt_rechte
from gantt.models import GanttAnsicht, GanttFreigabe
from kern import rechte
from kern.freigaben import BEARBEITEN, KEINE, SEHEN, erlaubt
from kern.models import Rolle
from kern.protokoll import protokollieren
from planung.models import AnsichtFreigabe, TeamplanerAnsicht


def arten():
    """Art → (Ansicht-Modell, Freigabe-Modell, Protokoll-Typ, Recht zum Verwalten, URL-Name der Bearbeiten-Seite)."""
    return {
        "teamplaner": (TeamplanerAnsicht, AnsichtFreigabe, "ansicht", rechte.darf_ansichten_verwalten, "ansicht_bearbeiten"),
        "gantt": (GanttAnsicht, GanttFreigabe, "gantt_ansicht", gantt_rechte.darf_verwalten, "gantt_ansicht_bearbeiten"),
    }


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
