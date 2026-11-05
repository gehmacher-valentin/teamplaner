from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from kern import rechte as kern_rechte
from kern.hilfen import erfordert
from kern.models import Bereich
from kern.protokoll import protokollieren
from projekte.models import Projekt

from . import rechte
from .models import GanttAnsicht, GanttFreigabe


@erfordert(kern_rechte.darf_lesen)
def gantt(request):
    if not rechte.hat_gantt(request.user):
        raise PermissionDenied
    return render(request, "gantt/gantt.html", {"aktiv": "gantt"})


class GanttAnsichtForm(forms.ModelForm):
    class Meta:
        model = GanttAnsicht
        fields = ["name", "neue_projekte_automatisch", "projekte"]
        widgets = {"projekte": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        aktive = Projekt.objects.aktiv()
        if self.instance.pk:
            aktive = (aktive | self.instance.projekte.all()).distinct()
        self.fields["projekte"].queryset = aktive


def _zur_liste():
    return redirect(reverse("einst_ansichten") + "?art=gantt")


@erfordert(rechte.darf_verwalten)
def ansicht_bearbeiten(request, pk=None):
    """Gleiche Freigabe-Logik wie bei den Teamplaner-Ansichten (kern.freigaben)."""
    from kern import freigaben
    from kern.einstellungen import seite

    ansicht = get_object_or_404(GanttAnsicht, pk=pk) if pk else None
    form = GanttAnsichtForm(request.POST or None, instance=ansicht)
    konten = freigaben.konten()
    bisher = dict(GanttFreigabe.objects.filter(ansicht=ansicht).values_list("konto_id", "recht")) if ansicht else {}

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if ansicht is None:
                form.instance.sortierung = (GanttAnsicht.objects.aggregate(m=Max("sortierung"))["m"] or 0) + 10
            gespeichert = form.save()
            neu = freigaben.aus_formular(konten, request.POST)
            geaendert = freigaben.speichern(GanttFreigabe, gespeichert, neu, bisher)
            protokollieren(request.user, "gantt_ansicht", gespeichert.pk, "geaendert" if ansicht else "angelegt", {
                "name": gespeichert.name, "projekte": [p.name for p in gespeichert.projekte.all()], "freigaben": geaendert,
            })
        messages.success(request, _("Gantt-Ansicht „%(name)s“ gespeichert.") % {"name": gespeichert.name})
        return _zur_liste()

    zeilen = freigaben.zeilen(konten, bisher, request.POST if request.method == "POST" else None)
    return seite(request, "gantt/ansicht_bearbeiten.html", "ansichten", ansicht=ansicht, form=form, zeilen=zeilen,
                 bereiche=Bereich.objects.all(), zusammenfassung=freigaben.zusammenfassung(z["recht"] for z in zeilen))


@require_POST
@erfordert(rechte.darf_verwalten)
def ansicht_loeschen(request, pk):
    ansicht = get_object_or_404(GanttAnsicht, pk=pk)
    protokollieren(request.user, "gantt_ansicht", ansicht.pk, "geloescht", {"name": ansicht.name})
    ansicht.delete()
    messages.success(request, _("Gantt-Ansicht gelöscht."))
    return _zur_liste()
