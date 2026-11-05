from django import forms
from django.utils.translation import gettext_lazy as _

from kern.forms import PersonenAuswahl

from .models import Bestellung

PERSONENFELDER = ["eingetragen_von", "bestellt_von"]


class BestellungForm(forms.ModelForm):
    class Meta:
        model = Bestellung
        fields = ["prio", "bedarf", "aufnahmedatum", "eingetragen_von", "projekt", "bestellt_am", "bestellt_von",
                  "lieferant", "liefertermin", "status"]
        widgets = {
            "aufnahmedatum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "bestellt_am": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "liefertermin": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for feld in PERSONENFELDER:
            aktuell = getattr(self.instance, feld) if self.instance.pk else None
            self.fields[feld] = PersonenAuswahl(aktuell=aktuell, required=False, label=Bestellung._meta.get_field(feld).verbose_name,
                                                empty_label=_("–"))
