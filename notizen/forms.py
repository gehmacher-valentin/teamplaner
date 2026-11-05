from django import forms
from django.utils.translation import gettext_lazy as _

from kern.models import Konto, Person

from .models import Ordner


class KontenAuswahl(forms.ModelMultipleChoiceField):
    """Kästchenliste mit Suche (teile/personenauswahl.html)."""

    widget = forms.CheckboxSelectMultiple

    def label_from_instance(self, konto):
        return f"{konto.person.anzeigename} · {konto.person.bereich}"


class OrdnerForm(forms.ModelForm):
    class Meta:
        model = Ordner
        fields = ["name", "mitglieder"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        konten = Konto.objects.filter(person__in=Person.objects.auswaehlbar())
        if self.instance.pk:
            konten = (konten | self.instance.mitglieder.all()).distinct()
        self.fields["mitglieder"] = KontenAuswahl(
            konten.select_related("person__bereich").order_by("person__anzeigename"), required=False,
            label=_("Freigegeben für"),
        )
