from django import forms
from django.conf import settings
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _

from kern import rechte
from kern.models import Bereich, Gewerk, Konto, Person, Rolle, Systemeinstellungen
from planung.models import FreierTag, FreigabeStufe
from projekte.forms import PersonenMehrfachAuswahl
from projekte.models import Status


class AnmeldeForm(AuthenticationForm):
    username = forms.EmailField(label=_("E-Mail"), widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))

    error_messages = {
        "invalid_login": _("E-Mail oder Passwort ist falsch."),
        "inactive": _("Dieses Konto ist deaktiviert."),
    }


class GewerkeFeld(forms.ModelMultipleChoiceField):
    widget = forms.CheckboxSelectMultiple

    def __init__(self, **kwargs):
        super().__init__(queryset=Gewerk.objects.all(), required=False, label=_("Gruppe / Funktion"), **kwargs)


class EinladenForm(forms.Form):
    anzeigename = forms.CharField(label=_("Name"), max_length=150)
    email = forms.EmailField(label=_("E-Mail"))
    bereich = forms.ModelChoiceField(Bereich.objects.all(), label=_("Bereich"))
    rolle = forms.ChoiceField(label=_("Rolle"))
    sprache = forms.ChoiceField(label=_("Sprache"), choices=settings.LANGUAGES, initial="de", required=False)
    gewerke = GewerkeFeld()

    def __init__(self, *args, konto, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rolle"].choices = [(r.value, r.label) for r in rechte.vergebbare_rollen(konto)]
        self.fields["rolle"].initial = Rolle.MITARBEITER

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Konto.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(_("Für diese E-Mail gibt es bereits ein Konto."))
        return email


class KontoBearbeitenForm(forms.Form):
    anzeigename = forms.CharField(label=_("Name"), max_length=150)
    email = forms.EmailField(label=_("E-Mail"))
    rolle = forms.ChoiceField(label=_("Rolle"))
    bereich = forms.ModelChoiceField(Bereich.objects.all(), label=_("Bereich"))
    gewerke = GewerkeFeld()
    systemkonto = forms.BooleanField(label=Konto._meta.get_field("systemkonto").verbose_name, required=False)
    darf_tagesfreigabe = forms.BooleanField(required=False)

    def __init__(self, *args, konto, ziel, **kwargs):
        super().__init__(*args, **kwargs)
        self.ziel = ziel
        self.fields["rolle"].choices = [(r.value, r.label) for r in rechte.vergebbare_rollen(konto)]
        feld = self.fields["darf_tagesfreigabe"]
        feld.label = _("Darf „%(name)s“ setzen") % {"name": Systemeinstellungen.laden().freigabe_bezeichnung}
        # Die Freigabe gilt für alle: den Haken vergibt nur, wer die Systemeinstellungen verwaltet (Admin)
        feld.disabled = not rechte.darf_systemeinstellungen(konto)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if Konto.objects.filter(email__iexact=email).exclude(pk=self.ziel.pk).exists():
            raise forms.ValidationError(_("Für diese E-Mail gibt es bereits ein Konto."))
        return email


class PlatzhalterForm(forms.ModelForm):
    gewerke = GewerkeFeld()

    class Meta:
        model = Person
        fields = ["anzeigename", "bereich", "notiz", "gewerke", "weiterleiten_an"]
        labels = {"anzeigename": _("Anzeigename (frei)"), "notiz": _("Notiz (optional)")}
        widgets = {
            "anzeigename": forms.TextInput(attrs={"placeholder": _("z. B. Aushilfe Montage")}),
            "notiz": forms.TextInput(attrs={"placeholder": _("z. B. ab November, 2 Tage pro Woche")}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Wie jede Personenauswahl: aktive Konten ohne Systemkonten, keine Platzhalter; bereits
        # eingetragene bleiben sichtbar (z. B. archiviert), damit sie sich austragen lassen
        konten = Person.objects.auswaehlbar().mit_konto()
        if self.instance.pk:
            konten = (konten | self.instance.weiterleiten_an.all()).distinct()
        self.fields["weiterleiten_an"] = PersonenMehrfachAuswahl(
            konten.select_related("konto", "bereich").order_by("anzeigename"), required=False,
            label=_("Benachrichtigungen weiterleiten an"),
            help_text=_("Diese Konten bekommen alle Benachrichtigungen des Platzhalters, z. B. Einteilungen, "
                        "Zuweisungen und Erwähnungen."),
        )


class UmwandelnForm(forms.Form):
    """Platzhalter in ein Benutzerkonto umwandeln."""

    email = forms.EmailField(label=_("E-Mail"))
    rolle = forms.ChoiceField(label=_("Rolle"))

    def __init__(self, *args, konto, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["rolle"].choices = [(r.value, r.label) for r in rechte.vergebbare_rollen(konto)]
        self.fields["rolle"].initial = Rolle.MITARBEITER

    clean_email = EinladenForm.clean_email


class ZweiFaktorCodeForm(forms.Form):
    code = forms.CharField(label=_("Code"), max_length=20, widget=forms.TextInput(attrs={
        "autofocus": True, "autocomplete": "one-time-code", "inputmode": "numeric", "spellcheck": "false"}))


class PasswortBestaetigenForm(forms.Form):
    passwort = forms.CharField(label=_("Ihr Passwort"), strip=False,
                               widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class ZweiFaktorEinrichtenForm(PasswortBestaetigenForm):
    code = forms.CharField(label=_("Code aus der App"), max_length=10, widget=forms.TextInput(attrs={
        "autocomplete": "one-time-code", "inputmode": "numeric", "spellcheck": "false"}))

    field_order = ["code", "passwort"]


class PasswortVergessenForm(forms.Form):
    email = forms.EmailField(label=_("E-Mail"), widget=forms.EmailInput(attrs={"autofocus": True, "autocomplete": "email"}))


# --- Einstellungen (nur Admin) ---

class StatusForm(forms.ModelForm):
    """Listen-Editor: die Reihenfolge setzt das Ziehen, nicht ein Zahlenfeld."""

    class Meta:
        model = Status
        fields = ["name", "ist_erledigt", "farbe"]
        widgets = {"farbe": forms.RadioSelect}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["farbe"].required = False  # die Hinzufügen-Zeile hat nur den Namen

    def clean_farbe(self):
        return self.cleaned_data.get("farbe") or self.instance.farbe or Status._meta.get_field("farbe").default


class FreigabeStufeForm(forms.ModelForm):
    class Meta:
        model = FreigabeStufe
        fields = ["name"]


class GewerkForm(forms.ModelForm):
    class Meta:
        model = Gewerk
        fields = ["name"]


class BereichForm(forms.ModelForm):
    class Meta:
        model = Bereich
        fields = ["name"]


class FreierTagForm(forms.ModelForm):
    class Meta:
        model = FreierTag
        fields = ["datum", "bezeichnung"]
        widgets = {"datum": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")}

