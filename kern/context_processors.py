from django.db.models import Q
from django.utils.functional import SimpleLazyObject

from . import rechte
from .models import Systemeinstellungen


def navigation(request):
    """Daten für Kopf und Navigation – nur zum Ein-/Ausblenden, geprüft wird in den Views."""
    # erst beim Ausgeben gelesen: HTMX-Teilantworten zeigen den Kopf nicht
    organisation = SimpleLazyObject(lambda: Systemeinstellungen.laden().organisation)
    konto = getattr(request, "user", None)
    if konto is None or not konto.is_authenticated:
        return {"organisation": organisation}
    from gantt import rechte as gantt_rechte
    from kern.einstellungen import verwaltungsseite
    from planung.rechte import hat_planungsansicht
    from projekte.models import Projekt
    from zusammenarbeit.models import Benachrichtigung

    verwalten = rechte.darf_projekte_verwalten(konto)
    projekte = Projekt.objects.aktiv()
    if not verwalten:
        projekte = projekte.filter(Q(mitglieder=konto.person) | Q(projektleitung=konto.person)).distinct()

    return {
        "organisation": organisation,
        # einmalig nach dem Abhaken einer Aufgabe, siehe projekte.views.aufgabe_erledigt
        "feiern": request.session.pop("feiern", False) if hasattr(request, "session") else False,
        "nav": {
            "teamplaner": hat_planungsansicht(konto),
            "gantt": gantt_rechte.hat_gantt(konto),
            # „Einstellungen“ unter „Verwaltung“: erste erlaubte Team- oder System-Seite
            "verwaltung": verwaltungsseite(konto),
            "protokoll": rechte.darf_erledigte_sehen(konto),
            "projekte_verwalten": verwalten,
            "projekte": list(projekte.only("id", "name", "farbe")[:25]),
            "ungelesen": Benachrichtigung.objects.filter(empfaenger=konto.person, gelesen_am__isnull=True).count(),
        },
    }
