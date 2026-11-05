from django import forms
from django.utils.translation import gettext_lazy as _

from kern.forms import PersonenAuswahl
from kern.models import Person

from .models import PRIORITAETEN, Abschnitt, Projekt, Tag


class PersonenMehrfachAuswahl(forms.ModelMultipleChoiceField):
    """Kästchenliste mit Suche (teile/personenauswahl.html); Beschriftung „Name · Bereich“."""

    widget = forms.CheckboxSelectMultiple

    def label_from_instance(self, person):
        teile = [person.anzeigename, str(person.bereich)]
        if person.ist_platzhalter:
            teile.append(str(_("Platzhalter")))
        return " · ".join(teile)


class TagsFeld(forms.CharField):
    """Kommagetrennte Tags; unbekannte werden angelegt."""

    def __init__(self, **kwargs):
        super().__init__(required=False, label=_("Tags"), **kwargs)

    def clean(self, value):
        namen = []
        for teil in (value or "").split(","):
            name = " ".join(teil.split())[:60]
            if name and name.lower() not in {n.lower() for n in namen}:
                namen.append(name)
        return namen


def tags_speichern(projekt, namen):
    tags = []
    for name in namen:
        tag = Tag.objects.filter(name__iexact=name).first() or Tag.objects.create(name=name)
        tags.append(tag)
    projekt.tags.set(tags)


class ProjektForm(forms.ModelForm):
    tags_text = TagsFeld()

    class Meta:
        model = Projekt
        fields = ["name", "farbe", "prioritaet", "projektleitung", "beginn", "ende", "mitglieder", "beschreibung"]
        widgets = {
            "beginn": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "ende": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "beschreibung": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        if self.instance.pk:
            self.initial["tags_text"] = ", ".join(t.name for t in self.instance.tags.all())

    def clean(self):
        daten = super().clean()
        if daten.get("beginn") and daten.get("ende") and daten["ende"] < daten["beginn"]:
            self.add_error("ende", _("Das Ende liegt vor dem Beginn."))
        return daten

    def save(self, commit=True):
        projekt = super().save(commit)
        if commit:
            tags_speichern(projekt, self.cleaned_data["tags_text"])
        return projekt


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
