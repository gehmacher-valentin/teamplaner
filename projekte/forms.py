import random

from django import forms
from django.db.models import Count
from django.utils.translation import gettext_lazy as _

from kern.forms import PersonenAuswahl
from kern.hilfen import TEXT_MAX_ZEICHEN
from kern.models import Person

from .models import PRIORITAETEN, Abschnitt, Projekt, Projektfarbe


def seltenste_farbe():
    """Vorauswahl für neue Projekte: die unter den aktiven Projekten seltenste Farbe, bei Gleichstand
    zufällig. Alle Farben der Palette kommen in Frage, auch Grau."""
    anzahl = dict(Projekt.objects.filter(archiviert_am__isnull=True)
                  .order_by().values("farbe").annotate(n=Count("pk")).values_list("farbe", "n"))
    wenigste = min(anzahl.get(f, 0) for f in Projektfarbe.values)
    return random.choice([f for f in Projektfarbe.values if anzahl.get(f, 0) == wenigste])


class PersonenMehrfachAuswahl(forms.ModelMultipleChoiceField):
    """Kästchenliste mit Suche (teile/personenauswahl.html); Beschriftung „Name · Bereich“."""

    widget = forms.CheckboxSelectMultiple

    def label_from_instance(self, person):
        teile = [person.anzeigename, str(person.bereich)]
        if person.ist_platzhalter:
            teile.append(str(_("Platzhalter")))
        return " · ".join(teile)


class ProjektForm(forms.ModelForm):
    """Projekt-Tags (Projekt.tags) bleiben im Datenmodell, erscheinen aber nicht mehr in der Oberfläche."""

    class Meta:
        model = Projekt
        fields = ["name", "farbe", "prioritaet", "projektleitung", "beginn", "ende", "mitglieder", "beschreibung"]
        widgets = {
            "beginn": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "ende": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "beschreibung": forms.Textarea(attrs={"rows": 3}),
        }

    def clean_beschreibung(self):
        text = self.cleaned_data["beschreibung"]
        if len(text) > TEXT_MAX_ZEICHEN:
            raise forms.ValidationError(_("Der Text ist zu lang (höchstens %(n)s Zeichen).") % {"n": TEXT_MAX_ZEICHEN})
        return text

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and "farbe" not in (kwargs.get("initial") or {}):
            self.initial["farbe"] = seltenste_farbe()  # statt immer Blau aus dem Modell
        aktive = Person.objects.auswaehlbar()
        if self.instance.pk:
            aktive = (aktive | self.instance.mitglieder.all()).distinct()
        self.fields["mitglieder"] = PersonenMehrfachAuswahl(
            aktive.select_related("konto", "bereich").order_by("anzeigename"), required=False,
            label=_("Mitglieder"),
        )
        self.fields["prioritaet"].choices = [("", "–"), *PRIORITAETEN]
        self.fields["projektleitung"] = PersonenAuswahl(
            aktuell=self.instance.projektleitung if self.instance.pk else None, required=False,
            label=_("Projektleitung"), empty_label=_("– keine –"),
        )

    def clean(self):
        daten = super().clean()
        if daten.get("beginn") and daten.get("ende") and daten["ende"] < daten["beginn"]:
            self.add_error("ende", _("Das Ende liegt vor dem Beginn."))
        return daten


class SchnellAufgabeForm(forms.Form):
    titel = forms.CharField(max_length=300, label=_("Titel"))


class AbschnittForm(forms.ModelForm):
    class Meta:
        model = Abschnitt
        fields = ["name"]


class UnteraufgabeForm(forms.Form):
    """Schnell anlegen im Aufgabendetail; alles Weitere auf der Detailseite der Unteraufgabe."""

    titel = forms.CharField(max_length=300, label=_("Titel"))
    faellig_am = forms.DateField(required=False, label=_("Fällig am"),
                                 widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["verantwortlich"] = PersonenAuswahl(required=False, label=_("Verantwortlich"),
                                                        empty_label=_("Nicht zugewiesen"))
