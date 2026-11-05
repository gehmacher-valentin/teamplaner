"""Bestellungsverfolgung. Lesen dürfen alle Angemeldeten, eintragen und ändern ab Mitarbeiter:in,
löschen nur, wer die Zeile angelegt hat, und Planer:innen aufwärts. Änderungen speichert jede Zeile per
HTMX sofort; jede Änderung steht im Protokoll."""

import unicodedata
from collections import Counter

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Case, IntegerField, Value, When
from django.forms.models import model_to_dict
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from kern import rechte
from kern.hilfen import erfordert
from kern.models import Person
from kern.protokoll import aenderungen, protokollieren

from .forms import BestellungForm
from .models import REIHENFOLGE, Bestellstatus, Bestellung


def darf_loeschen(konto, bestellung):
    return rechte.darf_planen(konto) or (rechte.darf_bestellungen_bearbeiten(konto)
                                         and bestellung.erstellt_von_id == konto.person_id)


def _sortiert():
    rang = Case(*[When(status=s, then=Value(i)) for i, s in enumerate(REIHENFOLGE)], output_field=IntegerField())
    return (Bestellung.objects.select_related("erstellt_von", "eingetragen_von", "bestellt_von")
            .annotate(rang=rang).order_by("rang", "-aufnahmedatum", "-id"))


def lieferanten(zeilen):
    """Vorschläge für das Feld „Lieferant“: alle bisherigen, alphabetisch, Schreibweisen ohne Rücksicht
    auf Groß-/Kleinschreibung zusammengefasst (es gilt die häufigste, bei Gleichstand eine mit großem
    Anfangsbuchstaben, sonst die zuerst gefundene)."""
    zaehler = {}
    for b in zeilen:
        name = " ".join(b.lieferant.split())
        if name:
            zaehler.setdefault(name.casefold(), Counter())[name] += 1
    beste = (max(c, key=lambda n, c=c: (c[n], n[:1].isupper())) for c in zaehler.values())
    return sorted(beste, key=lambda n: (_ohne_akzente(n), n))


def _ohne_akzente(text):
    """Sortierschlüssel: „Ärztebedarf“ steht bei A, nicht hinter Z."""
    return "".join(z for z in unicodedata.normalize("NFD", text.casefold()) if not unicodedata.combining(z))


def _kontext(request):
    zeilen = list(_sortiert())
    heute = timezone.localdate()
    for i, b in enumerate(zeilen):
        b.loeschbar = darf_loeschen(request.user, b)
        b.termin_ueberfaellig = b.ueberfaellig(heute)
        # Trennzeile vor den erhaltenen
        b.trenner = b.status == Bestellstatus.ERHALTEN and i > 0 and zeilen[i - 1].status != b.status
    return {
        "bestellungen": zeilen,
        "lieferanten": lieferanten(zeilen),
        "statusliste": Bestellstatus.choices,
        "offen": sum(b.status != Bestellstatus.ERHALTEN for b in zeilen),
        "darf_bearbeiten": rechte.darf_bestellungen_bearbeiten(request.user),
        "personenliste": list(Person.objects.auswaehlbar().select_related("konto")),
    }


def _antwort(request, fehler=None):
    if fehler:
        messages.error(request, fehler)  # bei HTMX als Toast (kern.middleware.HtmxMeldungenMiddleware)
    if request.htmx:
        antwort = render(request, "bestellungen/_liste.html", _kontext(request))
        if fehler:
            antwort["X-Fehler"] = "1"  # neue Zeile dann nicht leeren
        return antwort
    return redirect("bestellungen")


@erfordert(rechte.darf_lesen)
def liste(request):
    return render(request, "bestellungen/liste.html", {
        **_kontext(request), "neu": BestellungForm(prefix="neu", initial={"eingetragen_von": request.user.person}),
        "aktiv": "bestellungen",
    })


def _fehlertext(form):
    return "; ".join(f"{form.fields[f].label}: {', '.join(e)}" if f in form.fields else ", ".join(e)
                     for f, e in form.errors.items())


def _bestellt_ausfuellen(request, bestellung):
    """Status wechselt auf „bestellt“: leere Felder „Bestellt am“ und „Bestellt von“ füllen, vorhandene
    nie überschreiben. Systemkonten stehen in keiner Personenauswahl und werden nicht eingetragen."""
    if bestellung.bestellt_am is None:
        bestellung.bestellt_am = timezone.localdate()
    person = request.user.person
    if bestellung.bestellt_von_id is None and person.auswaehlbar:
        bestellung.bestellt_von = person


@require_POST
@erfordert(rechte.darf_bestellungen_bearbeiten)
def anlegen(request):
    form = BestellungForm(request.POST, prefix="neu")
    if not form.is_valid():
        return _antwort(request, _("Nicht gespeichert: %(fehler)s") % {"fehler": _fehlertext(form)})
    bestellung = form.save(commit=False)
    bestellung.erstellt_von = request.user.person
    if bestellung.status == Bestellstatus.BESTELLT:
        _bestellt_ausfuellen(request, bestellung)
    bestellung.save()
    protokollieren(request.user, "bestellung", bestellung.pk, "angelegt", {"name": bestellung.bedarf})
    return _antwort(request)


@require_POST
@erfordert(rechte.darf_bestellungen_bearbeiten)
def aendern(request, pk):
    bestellung = get_object_or_404(Bestellung, pk=pk)
    alt = {f: getattr(bestellung, f) for f in BestellungForm.Meta.fields}
    # Nur die mitgeschickten Felder übernehmen, die übrigen bleiben wie sie sind
    daten = model_to_dict(bestellung, fields=BestellungForm.Meta.fields)
    daten.update({f: request.POST[f] for f in BestellungForm.Meta.fields if f in request.POST})
    form = BestellungForm(daten, instance=bestellung)
    if not form.is_valid():
        return _antwort(request, _("Nicht gespeichert: %(fehler)s") % {"fehler": _fehlertext(form)})
    bestellung = form.save(commit=False)
    if bestellung.status == Bestellstatus.BESTELLT and alt["status"] != Bestellstatus.BESTELLT:
        _bestellt_ausfuellen(request, bestellung)
    bestellung.save()
    diff = aenderungen(alt, {f: getattr(bestellung, f) for f in BestellungForm.Meta.fields})
    if diff:
        protokollieren(request.user, "bestellung", bestellung.pk, "geaendert", {"name": bestellung.bedarf, **diff})
    return _antwort(request)


@require_POST
@erfordert(rechte.darf_bestellungen_bearbeiten)
def loeschen(request, pk):
    bestellung = get_object_or_404(Bestellung, pk=pk)
    if not darf_loeschen(request.user, bestellung):
        raise PermissionDenied
    protokollieren(request.user, "bestellung", bestellung.pk, "geloescht", {"name": bestellung.bedarf})
    bestellung.delete()
    return _antwort(request)
