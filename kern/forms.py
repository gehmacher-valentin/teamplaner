from django import forms
from django.utils.translation import gettext_lazy as _

from .models import Person


class PersonenAuswahl(forms.ModelChoiceField):
    """Eine Person wählen, mit Tippsuche (data-personenwahl, frontend/src/lib/personenwahl.ts): auswählbare
    Personen inkl. Platzhalter (gekennzeichnet); die aktuell gesetzte bleibt wählbar, auch wenn sie
    archiviert oder ein Systemkonto ist."""

    def __init__(self, *args, aktuell=None, **kwargs):
        qs = Person.objects.auswaehlbar()
        if aktuell is not None:
            qs = Person.objects.filter(pk=aktuell.pk) | qs
        super().__init__(qs.select_related("konto").distinct().order_by("anzeigename"), *args, **kwargs)
        self.widget.attrs["data-personenwahl"] = ""

    def label_from_instance(self, person):
        return f"{person.anzeigename} ({_('Platzhalter')})" if person.ist_platzhalter else person.anzeigename
