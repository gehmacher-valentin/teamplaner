from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Max
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.http import require_POST

from kern import freigaben
from kern import rechte as kern_rechte
from kern.hilfen import einstellungsseite, erfordert
from kern.models import Bereich, Gewerk, Person
from kern.protokoll import protokollieren
from projekte.models import Projekt, Tag

from . import rechte
from .models import AnsichtFreigabe, TeamplanerAnsicht


@login_required
def teamplaner(request, lesen=False):
    """Teamplaner (Drag-and-drop) bzw. Lesekalender – beides dieselbe React-Oberfläche.

    Ob bearbeitet werden darf, entscheidet der Server je Person (``einteilbar``); die
    Seite blendet nur Werkzeuge ein oder aus.
    """
    planen = rechte.hat_planungsansicht(request.user) and not lesen
    return render(request, "planung/teamplaner.html", {"planen": planen, "aktiv": "teamplaner" if planen else "kalender"})


# ---------- Teamplaner-Ansichten verwalten ----------

class AnsichtForm(forms.ModelForm):
    wochen = forms.TypedChoiceField(label=gettext_lazy("Zeitraum"), coerce=int, choices=[(1, gettext_lazy("1 Woche")), (2, gettext_lazy("2 Wochen")), (4, gettext_lazy("4 Wochen"))], initial=2)
    gewerk = forms.ModelChoiceField(Gewerk.objects.all(), label=gettext_lazy("Gewerk"), required=False, empty_label=gettext_lazy("Alle Gewerke"))
    tag = forms.ModelChoiceField(Tag.objects.all(), label=gettext_lazy("Projekt-Tag"), required=False, empty_label=gettext_lazy("Alle Tags"))
    projekt = forms.ModelChoiceField(Projekt.objects.aktiv(), label=gettext_lazy("Projekt"), required=False, empty_label=gettext_lazy("Alle Projekte"))

    class Meta:
        model = TeamplanerAnsicht
        fields = ["name", "bereiche", "personen"]
        widgets = {"bereiche": forms.CheckboxSelectMultiple, "personen": forms.CheckboxSelectMultiple}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        auswahl = Person.objects.auswaehlbar()
        if self.instance.pk:
            auswahl = (auswahl | self.instance.personen.all()).distinct()
        self.fields["personen"].queryset = auswahl.select_related("bereich")
        self.fields["personen"].label_from_instance = lambda p: f"{p.anzeigename} · {p.bereich}"
        filter_ = (self.instance.filter or {}) if self.instance.pk else {}
        for feld in ["wochen", "gewerk", "tag", "projekt"]:
            if feld in filter_:
                self.initial[feld] = filter_[feld]

    def save(self, commit=True):
        d = self.cleaned_data
        self.instance.filter = {
            "wochen": d["wochen"],
            "gewerk": d["gewerk"].pk if d["gewerk"] else None,
            "tag": d["tag"].pk if d["tag"] else None,
            "projekt": d["projekt"].pk if d["projekt"] else None,
        }
        return super().save(commit)


def _zur_liste(art):
    return redirect(reverse("einst_ansichten") + f"?art={art}")


@erfordert(kern_rechte.darf_ansichten_verwalten)
def ansicht_bearbeiten(request, pk=None):
    """Teamplaner-Ansicht mit Freigaben; Freigaben-Logik gemeinsam mit Gantt (kern.freigaben)."""
    ansicht = get_object_or_404(TeamplanerAnsicht, pk=pk) if pk else None
    form = AnsichtForm(request.POST or None, instance=ansicht)
    konten = freigaben.konten()
    bisher = dict(AnsichtFreigabe.objects.filter(ansicht=ansicht).values_list("konto_id", "recht")) if ansicht else {}

    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            if ansicht is None:  # neue Ansichten ans Ende der Reihenfolge
                form.instance.sortierung = (TeamplanerAnsicht.objects.aggregate(m=Max("sortierung"))["m"] or 0) + 10
            gespeichert = form.save()
            neu = freigaben.aus_formular(konten, request.POST)
            geaendert = freigaben.speichern(AnsichtFreigabe, gespeichert, neu, bisher)
            protokollieren(request.user, "ansicht", gespeichert.pk, "geaendert" if ansicht else "angelegt", {
                "name": gespeichert.name,
                "bereiche": [b.name for b in gespeichert.bereiche.all()],
                "personen": [p.anzeigename for p in gespeichert.personen.all()],
                "freigaben": geaendert,
            })
        messages.success(request, _("Ansicht „%(name)s“ gespeichert.") % {"name": gespeichert.name})
        return _zur_liste("teamplaner")

    zeilen = freigaben.zeilen(konten, bisher, request.POST if request.method == "POST" else None)
    return einstellungsseite(request, "planung/ansicht_bearbeiten.html", "ansichten", ansicht=ansicht, form=form, zeilen=zeilen,
                             bereiche=Bereich.objects.all(), zusammenfassung=freigaben.zusammenfassung(z["recht"] for z in zeilen))


@require_POST
@erfordert(kern_rechte.darf_ansichten_verwalten)
def ansicht_loeschen(request, pk):
    ansicht = get_object_or_404(TeamplanerAnsicht, pk=pk)
    protokollieren(request.user, "ansicht", ansicht.pk, "geloescht", {"name": ansicht.name})
    ansicht.delete()
    messages.success(request, _("Ansicht gelöscht."))
    return _zur_liste("teamplaner")
