"""JSON-API für Teamplaner und Lesekalender. Rechte prüft ``planung.dienste`` bzw. ``rechte``."""

from datetime import date, timedelta

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from rest_framework.decorators import api_view
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response

from kern import rechte as kern_rechte
from kern.hilfen import als_zahl
from kern.models import Person
from projekte.models import Aufgabe

from . import dienste, raster
from .kalender import montag

MAX_RASTER_TAGE = 7 * 8


def _fehler(fehler: dienste.PlanungsFehler):
    return Response({"code": fehler.code, "nachricht": fehler.nachricht, **fehler.daten}, status=fehler.status)


def _datum(wert, name):
    try:
        return date.fromisoformat(wert)
    except (TypeError, ValueError):
        raise dienste.PlanungsFehler("ungueltig", _("Ungültiges Datum: %(name)s") % {"name": name}) from None


def _client_id(request):
    return request.headers.get("X-Client-Id", "")[:64]


@api_view(["GET"])
def ansichten(request):
    return Response({
        "ansichten": raster.ansichten_fuer(request.user),
        "darf_planen": kern_rechte.darf_planen(request.user),
        **raster.filteroptionen(),
    })


@api_view(["GET"])
def raster_daten(request):
    try:
        von = _datum(request.GET.get("von") or montag(date.today()).isoformat(), "von")
        bis = _datum(request.GET.get("bis") or (von + timedelta(days=13)).isoformat(), "bis")
    except dienste.PlanungsFehler as fehler:
        return _fehler(fehler)
    if bis < von or (bis - von).days >= MAX_RASTER_TAGE:
        return Response({"code": "zeitraum", "nachricht": _("Ungültiger Zeitraum.")}, status=400)
    try:
        daten = raster.raster(
            request.user, request.GET.get("ansicht", raster.ANSICHT_ICH), von, bis,
            archivierte=request.GET.get("archivierte") == "1",
        )
    except raster.AnsichtNichtErlaubt:
        return Response({"code": "keine_berechtigung", "nachricht": _("Diese Ansicht ist für Sie nicht freigegeben.")}, status=403)
    return Response(daten)


def _filter_id(parameter, name):
    """Optionaler Filter auf eine ID: fehlt er, None; ist er keine ganze Zahl, 400 statt Fehler 500."""
    roh = parameter.get(name)
    if not roh:
        return None
    zahl = als_zahl(roh)
    if zahl is None:
        raise ValidationError({name: _("Ungültige Eingabe.")})
    return zahl


@api_view(["GET"])
def palette(request):
    if not kern_rechte.darf_planen(request.user):
        return Response({"code": "keine_berechtigung", "nachricht": _("Keine Berechtigung.")}, status=403)
    g = request.GET
    return Response(raster.palette(
        request.user,
        modus=g.get("modus", "offen"),
        projekt_id=_filter_id(g, "projekt"),
        gewerk_id=_filter_id(g, "gewerk"),
        tag_id=_filter_id(g, "tag"),
        suche=(g.get("q") or "").strip()[:100],
    ))


def _lade_person(person_id):
    return get_object_or_404(Person, pk=als_zahl(person_id))


@api_view(["POST"])
def einteilung_anlegen(request):
    d = request.data
    try:
        einteilung = dienste.einteilung_anlegen(
            request.user,
            aufgabe=get_object_or_404(Aufgabe, pk=als_zahl(d.get("aufgabe_id"))),
            person=_lade_person(d.get("person_id")),
            von=_datum(d.get("von"), "von"),
            bis=_datum(d.get("bis"), "bis"),
            feiertag_bestaetigt=bool(d.get("feiertag_bestaetigt")),
            client_id=_client_id(request),
        )
    except dienste.PlanungsFehler as fehler:
        return _fehler(fehler)
    return Response(dienste.als_dict(einteilung), status=201)


def _aenderungen(d):
    werte = {"version": d.get("version")}
    if d.get("person_id") is not None:
        werte["person"] = _lade_person(d["person_id"])
    if d.get("von"):
        werte["von"] = _datum(d["von"], "von")
    if d.get("bis"):
        werte["bis"] = _datum(d["bis"], "bis")
    return werte


@api_view(["PATCH", "DELETE"])
def einteilung(request, pk):
    try:
        if request.method == "DELETE":
            dienste.einteilung_loeschen(request.user, pk, version=request.GET.get("version"),
                                        client_id=_client_id(request))
            return Response(status=204)
        objekt = dienste.einteilung_aendern(
            request.user, pk, **_aenderungen(request.data),
            feiertag_bestaetigt=bool(request.data.get("feiertag_bestaetigt")),
            client_id=_client_id(request),
        )
    except dienste.PlanungsFehler as fehler:
        return _fehler(fehler)
    return Response(dienste.als_dict(objekt))


@api_view(["POST"])
def abwesenheit_anlegen(request):
    d = request.data
    try:
        abwesenheit = dienste.abwesenheit_anlegen(
            request.user,
            person=_lade_person(d.get("person_id")),
            von=_datum(d.get("von"), "von"),
            bis=_datum(d.get("bis"), "bis"),
            client_id=_client_id(request),
        )
    except dienste.PlanungsFehler as fehler:
        return _fehler(fehler)
    return Response(dienste.als_dict(abwesenheit), status=201)


@api_view(["PATCH", "DELETE"])
def abwesenheit(request, pk):
    try:
        if request.method == "DELETE":
            dienste.abwesenheit_loeschen(request.user, pk, version=request.GET.get("version"),
                                         client_id=_client_id(request))
            return Response(status=204)
        objekt = dienste.abwesenheit_aendern(request.user, pk, **_aenderungen(request.data),
                                             client_id=_client_id(request))
    except dienste.PlanungsFehler as fehler:
        return _fehler(fehler)
    return Response(dienste.als_dict(objekt))


@api_view(["PUT"])
def tagesinfo(request, datum):
    try:
        text = dienste.tagesinfo_setzen(request.user, _datum(datum, "datum"), request.data.get("text"),
                                        client_id=_client_id(request))
    except dienste.PlanungsFehler as fehler:
        return _fehler(fehler)
    return Response({"datum": datum, "text": text})


@api_view(["PUT"])
def tagesfreigabe(request, datum):
    try:
        stufe, von = dienste.tagesfreigabe_setzen(request.user, _datum(datum, "datum"), request.data.get("stufe"),
                                                  client_id=_client_id(request))
    except dienste.PlanungsFehler as fehler:
        return _fehler(fehler)
    return Response({"datum": datum, "stufe": stufe, "von": von})
