"""Wer im Teamplaner wen sehen und einteilen darf.

* Admin und Bereichsleitung: alle Personen sehen und einteilen.
* Alle anderen: Personen aus Ansichten, die ihnen freigegeben sind („sehen“ oder
  „bearbeiten“). Die eigene Einteilung ist immer sichtbar.
* Einteilen: Rolle ab Planer:in **und** Freigabe „bearbeiten“ auf eine Ansicht, die die
  Person enthält. Es gilt das höchste Recht über alle Ansichten.
* Archivierte Personen bekommen keine neuen oder geänderten Einteilungen.
"""

from django.db.models import Q

from kern import rechte
from kern.models import Person

from .models import AnsichtFreigabe, Recht, TeamplanerAnsicht


def _personen_in_ansichten(ansicht_ids):
    if not ansicht_ids:
        return set()
    return set(
        Person.objects.filter(
            Q(ansichten__in=ansicht_ids) | Q(bereich__ansichten__in=ansicht_ids)
        ).values_list("id", flat=True)
    )


def freigaben(konto):
    """``{ansicht_id: recht}`` – effektives Recht je Ansicht für dieses Konto."""
    if rechte.sieht_alles_im_teamplaner(konto):
        return {a: Recht.BEARBEITEN for a in TeamplanerAnsicht.objects.values_list("id", flat=True)}
    if not rechte.darf_lesen(konto):
        return {}
    darf_bearbeiten = rechte.darf_planen(konto)
    return {
        ansicht_id: (Recht.BEARBEITEN if recht == Recht.BEARBEITEN and darf_bearbeiten else Recht.SEHEN)
        for ansicht_id, recht in AnsichtFreigabe.objects.filter(konto=konto).values_list(
            "ansicht_id", "recht"
        )
    }


def sichtbare_personen_ids(konto):
    """Menge der Personen-IDs oder ``None`` für „alle“."""
    if rechte.sieht_alles_im_teamplaner(konto):
        return None
    if not rechte.darf_lesen(konto):
        return set()
    ids = _personen_in_ansichten(list(freigaben(konto)))
    ids.add(konto.person_id)
    return ids


def einteilbare_personen_ids(konto):
    """Menge der Personen-IDs oder ``None`` für „alle“ (Archivierung separat prüfen)."""
    if rechte.sieht_alles_im_teamplaner(konto):
        return None
    if not rechte.darf_planen(konto):
        return set()
    bearbeitbar = [a for a, r in freigaben(konto).items() if r == Recht.BEARBEITEN]
    return _personen_in_ansichten(bearbeitbar)


def darf_sehen(konto, person):
    ids = sichtbare_personen_ids(konto)
    return ids is None or person.pk in ids


def darf_einteilen(konto, person):
    """Ohne Archivprüfung – die macht der Dienst mit eigener Fehlermeldung."""
    ids = einteilbare_personen_ids(konto)
    return ids is None or person.pk in ids


def hat_planungsansicht(konto):
    """Bekommt den Teamplaner (Bearbeiten) statt nur des Lesekalenders angezeigt."""
    ids = einteilbare_personen_ids(konto)
    return ids is None or bool(ids)


def sichtbare_ansichten(konto):
    return TeamplanerAnsicht.objects.filter(pk__in=list(freigaben(konto)))
