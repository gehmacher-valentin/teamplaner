"""JSON-API des Gantt-Diagramms. Rechte prüft gantt.dienste bzw. gantt.rechte."""

from datetime import date

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework.decorators import api_view
from rest_framework.response import Response

from kern.hilfen import als_zahl
from kern.protokoll import protokollieren
from projekte.models import Abhaengigkeit, Aufgabe, Projekt

from . import dienste, rechte
from .daten import gantt_daten
from .models import GanttAnsicht


def _fehler(f):
    return Response({"code": f.code, "nachricht": f.nachricht, **f.daten}, status=f.status)


def _datum(wert):
    if not wert:
        return None
    try:
        return date.fromisoformat(wert)
    except (TypeError, ValueError):
        raise dienste.GanttFehler("ungueltig", _("Ungültiges Datum.")) from None


def _ansicht(request, wert):
    """Ansicht laden – 403, wenn sie dem Konto nicht freigegeben ist."""
    ansicht = get_object_or_404(GanttAnsicht, pk=wert)
    if rechte.recht(request.user, ansicht) is None:
        raise dienste.GanttFehler("keine_berechtigung", _("Diese Ansicht ist für Sie nicht freigegeben."), 403)
    return ansicht


@api_view(["GET"])
def ansichten(request):
    freigaben = rechte.freigaben(request.user)
    return Response({
        "ansichten": [{"id": a.pk, "name": a.name, "recht": freigaben[a.pk]}
                      for a in GanttAnsicht.objects.filter(pk__in=list(freigaben))],
        "darf_verwalten": rechte.darf_verwalten(request.user),
        "projekte": [{"id": p.pk, "name": p.name, "farbe": p.farbe} for p in Projekt.objects.aktiv()]
        if rechte.darf_verwalten(request.user) else [],
        "unteraufgaben_offen": request.user.gantt_unteraufgaben_offen,
    })


@api_view(["PATCH"])
def einstellungen(request):
    """Persönliche Gantt-Einstellung „Unteraufgaben aufgeklappt“ – immer nur das eigene Konto."""
    wert = request.data.get("unteraufgaben_offen")
    if not isinstance(wert, bool):
        return Response({"code": "ungueltig", "nachricht": _("Ungültiger Wert.")}, status=400)
    konto = request.user
    if konto.gantt_unteraufgaben_offen != wert:
        konto.gantt_unteraufgaben_offen = wert
        konto.save(update_fields=["gantt_unteraufgaben_offen"])
    return Response({"unteraufgaben_offen": wert})


@api_view(["GET"])
def daten(request, pk):
    try:
        return Response(gantt_daten(request.user, _ansicht(request, pk)))
    except dienste.GanttFehler as f:
        return _fehler(f)


@api_view(["PATCH"])
def aufgabe(request, pk, aufgabe_id):
    d = request.data
    try:
        ansicht = _ansicht(request, pk)
        a = get_object_or_404(Aufgabe, pk=aufgabe_id)
        a = dienste.aufgabe_termine(request.user, ansicht, a, beginn=_datum(d.get("beginn")),
                                    ende=_datum(d.get("ende")), version=d.get("version"))
    except dienste.GanttFehler as f:
        return _fehler(f)
    return Response({"id": a.pk, "version": a.version})


@api_view(["PATCH"])
def projekt(request, pk, projekt_id):
    d = request.data
    try:
        ansicht = _ansicht(request, pk)
        p = get_object_or_404(Projekt, pk=projekt_id)
        dienste.projekt_termine(request.user, ansicht, p, beginn=_datum(d.get("beginn")), ende=_datum(d.get("ende")))
    except dienste.GanttFehler as f:
        return _fehler(f)
    return Response({"id": p.pk})


@api_view(["POST"])
def abhaengigkeit_anlegen(request, pk):
    d = request.data
    try:
        ansicht = _ansicht(request, pk)
        abh = dienste.abhaengigkeit_anlegen(request.user, ansicht, get_object_or_404(Aufgabe, pk=als_zahl(d.get("vorher"))),
                                            get_object_or_404(Aufgabe, pk=als_zahl(d.get("nachher"))))
    except dienste.GanttFehler as f:
        return _fehler(f)
    return Response({"id": abh.pk}, status=201)


@api_view(["DELETE"])
def abhaengigkeit(request, pk, abh_id):
    try:
        ansicht = _ansicht(request, pk)
        abh = get_object_or_404(Abhaengigkeit.objects.select_related("vorher", "nachher"), pk=abh_id)
        dienste.abhaengigkeit_loeschen(request.user, ansicht, abh)
    except dienste.GanttFehler as f:
        return _fehler(f)
    return Response(status=204)


@api_view(["POST", "DELETE"])
def ansicht_projekt(request, pk, projekt_id):
    """Projekt nachträglich zur Ansicht hinzufügen oder entfernen – Admin/Bereichsleitung."""
    if not rechte.darf_verwalten(request.user):
        return Response({"code": "keine_berechtigung", "nachricht": _("Keine Berechtigung.")}, status=403)
    ansicht = get_object_or_404(GanttAnsicht, pk=pk)
    p = get_object_or_404(Projekt, pk=projekt_id)
    if request.method == "POST":
        ansicht.projekte.add(p)
        aktion = "projekt_hinzugefuegt"
    else:
        ansicht.projekte.remove(p)
        aktion = "projekt_entfernt"
    protokollieren(request.user, "gantt_ansicht", ansicht.pk, aktion, {"name": ansicht.name, "projekt": p})
    return Response(status=204)
