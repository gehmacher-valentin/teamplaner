import shutil
import time
from datetime import timedelta

from axes.handlers.proxy import AxesProxyHandler
from axes.helpers import get_client_ip_address
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.contrib.auth.signals import user_login_failed
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Max, Q, Sum
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.html import format_html
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from kern import fotos, rechte, zwei_faktor
from kern.auth import code_zugang, sperre_aufheben, zu_viele_fehlversuche_von_ip
from kern.hilfen import als_zahl, erfordert, link_qr_svg, passwort_link, passwort_links
from kern.models import (
    ENTFERNT_DOMAIN,
    Bereich,
    Konto,
    Person,
    Protokolleintrag,
    Resetanfrage,
    Rolle,
    Systemeinstellungen,
)
from kern.protokoll import aenderungen, protokollieren
from notizen.models import NotizAnhang
from planung.rechte import hat_planungsansicht
from projekte.models import Aufgabe, Status
from zusammenarbeit.mail import einladung_senden, mail_aktiv, reset_senden, sicherheitshinweis
from zusammenarbeit.models import Anhang

from . import konten
from .einstellungen import gespeichert, seite, zwei_faktor_kontext
from .forms import (
    AnmeldeForm,
    EinladenForm,
    EmailAendernForm,
    KontoBearbeitenForm,
    PasswortBestaetigenForm,
    PasswortVergessenForm,
    PlatzhalterForm,
    UmwandelnForm,
    ZweiFaktorCodeForm,
    ZweiFaktorEinrichtenForm,
)
from .freigaben import arten, setzen

# ---------- Anmeldung ----------

class AnmeldenView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = AnmeldeForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "mail_aktiv": mail_aktiv()}

    def post(self, request, *args, **kwargs):
        # Vor dem Passwortvergleich: abgewiesene Versuche kosten keine Argon2-Rechenzeit
        if zu_viele_fehlversuche_von_ip(request):
            return render(request, "registration/gesperrt.html", status=429)
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        konto = form.get_user()
        if not zwei_faktor.aktiv(konto):
            return super().form_valid(form)
        if _gesperrt(self.request, code_zugang(konto)):
            return render(self.request, "registration/gesperrt.html", status=429)
        # Passwort stimmt; angemeldet wird erst nach dem Code aus der App
        self.request.session[ANMELDUNG_OFFEN] = {
            "konto": konto.pk, "backend": konto.backend, "seit": time.time(), "stand": konto.zugang_stand,
            "weiter": self.get_success_url(), "fehler": 0,
        }
        return redirect("anmelden_code")


# ---------- Zwei-Faktor-Anmeldung ----------

ANMELDUNG_OFFEN = "anmeldung_offen"  # Passwort bestanden, Code fehlt noch
ANMELDUNG_OFFEN_SEKUNDEN = 300
CODE_VERSUCHE = 5
NEUES_GEHEIMNIS = "zwei_faktor_neu"


def _zugang(konto):
    return {settings.AXES_USERNAME_FORM_FIELD: konto.email}


def _fehlversuch(request, zugang):
    """Falscher Code oder falsches Passwort zählt wie ein Fehlversuch bei der Anmeldung (Sperre)."""
    user_login_failed.send(sender=__name__, credentials=zugang, request=request)


def _gesperrt(request, zugang):
    return AxesProxyHandler.is_locked(request, zugang) or zu_viele_fehlversuche_von_ip(request)


@never_cache
def anmelden_code(request):
    """Zweiter Schritt der Anmeldung: Code aus der App oder ein Ersatzcode."""
    offen = request.session.get(ANMELDUNG_OFFEN)
    konto = Konto.objects.select_related("person").filter(pk=offen["konto"]).first() if offen else None
    if (konto is None or time.time() - offen["seit"] > ANMELDUNG_OFFEN_SEKUNDEN
            or not konto.is_active or not zwei_faktor.aktiv(konto) or offen.get("stand", 0) != konto.zugang_stand):
        request.session.pop(ANMELDUNG_OFFEN, None)
        if offen:
            messages.info(request, _("Die Zeit für die Eingabe ist abgelaufen. Bitte erneut anmelden."))
        return redirect("login")
    form = ZweiFaktorCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _gesperrt(request, _zugang(konto)) or _gesperrt(request, code_zugang(konto)):
            request.session.pop(ANMELDUNG_OFFEN, None)
            return render(request, "registration/gesperrt.html", status=429)
        art = zwei_faktor.pruefen(konto, form.cleaned_data["code"])
        if art:
            del request.session[ANMELDUNG_OFFEN]
            sperre_aufheben(code_zugang(konto))
            login(request, konto, backend=offen["backend"])
            zwei_faktor.bestanden(request, konto)
            if art == "ersatz":
                konto.refresh_from_db(fields=["totp_ersatzcodes"])
                messages.warning(request, _("Sie haben einen Ersatzcode verwendet, noch %(n)s übrig. Neue Codes "
                                            "oder ein neues Telefon richten Sie unter „Mein Konto“ ein.")
                                 % {"n": zwei_faktor.ersatzcodes_uebrig(konto)})
            return redirect(offen["weiter"])
        _fehlversuch(request, code_zugang(konto))
        offen["fehler"] += 1
        if offen["fehler"] >= CODE_VERSUCHE:
            del request.session[ANMELDUNG_OFFEN]
            messages.error(request, _("Zu viele falsche Codes. Bitte erneut anmelden."))
            return redirect("login")
        request.session[ANMELDUNG_OFFEN] = offen
        form.add_error("code", _("Der Code stimmt nicht."))
    return render(request, "registration/anmelden_code.html", {"form": form})


@never_cache
@login_required
def zwei_faktor_einrichten(request):
    """Authenticator-App verbinden (auch: neues Telefon). Pflicht für Admin und Bereichsleitung."""
    konto = request.user
    geheimnis = request.session.get(NEUES_GEHEIMNIS) or zwei_faktor.neues_geheimnis()
    request.session[NEUES_GEHEIMNIS] = geheimnis
    form = ZweiFaktorEinrichtenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _gesperrt(request, _zugang(konto)):
            return render(request, "registration/gesperrt.html", status=429)
        schritt = zwei_faktor.passender_schritt(geheimnis, form.cleaned_data["code"])
        if not konto.check_password(form.cleaned_data["passwort"]):
            _fehlversuch(request, _zugang(konto))
            form.add_error("passwort", _("Das Passwort stimmt nicht."))
        elif schritt is None:
            form.add_error("code", _("Der Code passt nicht. Bitte den aktuellen Code aus der App eingeben; "
                                     "die Uhrzeit am Telefon muss stimmen."))
        else:
            codes = zwei_faktor.einrichten(konto, geheimnis, schritt)
            del request.session[NEUES_GEHEIMNIS]
            zwei_faktor.bestanden(request, konto)
            protokollieren(konto, "konto", konto.pk, "zwei_faktor_eingerichtet", {"person": konto.person})
            sicherheitshinweis(konto, "zwei_faktor_eingerichtet")
            return render(request, "kern/zwei_faktor_ersatzcodes.html", {"codes": codes, **_sicherheit_rahmen()})
    return render(request, "kern/zwei_faktor_einrichten.html", {
        "form": form, "qr": zwei_faktor.qr_svg(konto, geheimnis), "geheimnis": zwei_faktor.geheimnis_anzeigen(geheimnis),
        "pflicht": zwei_faktor.pflicht(konto), "eingerichtet": zwei_faktor.aktiv(konto), **_sicherheit_rahmen(),
    })


def _sicherheit_rahmen():
    """Zwei-Faktor-Seiten stehen im Einstellungsbereich unter „Anmeldung & Sicherheit“."""
    return {"einst_aktiv": "sicherheit", "aktiv": "konto"}


@never_cache
@require_POST
@login_required
def zwei_faktor_aendern(request, aktion):
    """Neue Ersatzcodes oder ausschalten (nur ohne Pflicht) – jeweils mit dem Passwort bestätigt."""
    konto = request.user
    if not zwei_faktor.aktiv(konto) or aktion not in {"ersatzcodes", "ausschalten"}:
        raise PermissionDenied
    if aktion == "ausschalten" and zwei_faktor.pflicht(konto):
        raise PermissionDenied
    if _gesperrt(request, _zugang(konto)):
        return render(request, "registration/gesperrt.html", status=429)
    form = PasswortBestaetigenForm(request.POST)
    if not form.is_valid() or not konto.check_password(form.cleaned_data["passwort"]):
        _fehlversuch(request, _zugang(konto))
        messages.error(request, _("Das Passwort stimmt nicht."))
        return redirect(reverse("einst_sicherheit") + "#zwei-faktor")
    if aktion == "ersatzcodes":
        codes = zwei_faktor.ersatzcodes_erzeugen(konto)
        konto.save(update_fields=["totp_ersatzcodes"])
        protokollieren(konto, "konto", konto.pk, "ersatzcodes_erneuert", {"person": konto.person})
        return render(request, "kern/zwei_faktor_ersatzcodes.html", {"codes": codes, **_sicherheit_rahmen()})
    zwei_faktor.zuruecksetzen(konto)
    request.session.pop(zwei_faktor.SITZUNG, None)
    protokollieren(konto, "konto", konto.pk, "zwei_faktor_ausgeschaltet", {"person": konto.person})
    sicherheitshinweis(konto, "zwei_faktor_ausgeschaltet")
    messages.success(request, _("Die Zwei-Faktor-Anmeldung ist ausgeschaltet."))
    return redirect("einst_sicherheit")


RESET_JE_IP_STUNDE = 10
RESET_ABSTAND_MINUTEN = 15


def passwort_vergessen(request):
    """Reset-Link per E-Mail. Die Antwort verrät nicht, ob es das Konto gibt: immer dieselbe
    Seite, verschickt wird im Hintergrund (Postausgang). Gedrosselt je Adresse (eine Mail je
    RESET_ABSTAND_MINUTEN) und je IP-Adresse (RESET_JE_IP_STUNDE Anfragen je Stunde)."""
    if not mail_aktiv():
        return redirect("login")
    form = PasswortVergessenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        email = form.cleaned_data["email"].strip().lower()
        jetzt = timezone.now()
        Resetanfrage.objects.filter(zeitpunkt__lt=jetzt - timedelta(days=1)).delete()
        ip = get_client_ip_address(request)
        letzte_stunde = Resetanfrage.objects.filter(zeitpunkt__gte=jetzt - timedelta(hours=1))
        if ip and letzte_stunde.filter(ip=ip).count() >= RESET_JE_IP_STUNDE:
            return render(request, "registration/passwort_vergessen.html", {"form": form, "zu_viele": True}, status=429)
        schluessel = salted_hmac("kern.resetanfrage", email).hexdigest()
        kuerzlich = letzte_stunde.filter(email_hash=schluessel,
                                         zeitpunkt__gte=jetzt - timedelta(minutes=RESET_ABSTAND_MINUTEN)).exists()
        Resetanfrage.objects.create(ip=ip, email_hash=schluessel)
        konto = Konto.objects.select_related("person").filter(email__iexact=email).first()
        if konto is not None and konto.is_active and not kuerzlich:
            reset_senden(konto, passwort_link(konto))
            protokollieren(None, "konto", konto.pk, "reset_angefordert", {"person": konto.person})
        return render(request, "registration/passwort_vergessen.html", {"gesendet": True})
    return render(request, "registration/passwort_vergessen.html", {"form": form})


class PasswortSetzenView(auth_views.PasswordResetConfirmView):
    """Einladung annehmen bzw. Passwort zurücksetzen (gleicher Ablauf)."""

    template_name = "registration/passwort_setzen.html"
    success_url = reverse_lazy("login")
    post_reset_login = False
    token_generator = passwort_links

    def get_user(self, uidb64):
        konto = super().get_user(uidb64)
        return konto if konto is not None and konto.is_active else None

    def form_valid(self, form):
        zuruecksetzen = self.user.has_usable_password()  # sonst: Einladung angenommen
        messages.success(self.request, _("Passwort gespeichert. Sie können sich jetzt anmelden."))
        protokollieren(self.user, "konto", self.user.pk, "passwort_gesetzt")
        antwort = super().form_valid(form)
        sperre_aufheben(_zugang(self.user))  # der zweite Faktor wird weiter verlangt
        if zuruecksetzen:
            sicherheitshinweis(self.user, "passwort_zurueckgesetzt")
        return antwort


class PasswortAendernView(auth_views.PasswordChangeView):
    """„Anmeldung & Sicherheit“: Passwort direkt auf der Seite, darunter die Zwei-Faktor-Anmeldung."""

    template_name = "kern/einst_sicherheit.html"
    success_url = reverse_lazy("einst_sicherheit")

    def get_context_data(self, **kwargs):
        return {**super().get_context_data(**kwargs), "zwei_faktor": zwei_faktor_kontext(self.request.user),
                **_sicherheit_rahmen()}

    def form_valid(self, form):
        messages.success(self.request, _("Passwort geändert."))
        antwort = super().form_valid(form)
        protokollieren(self.request.user, "konto", self.request.user.pk, "passwort_geaendert",
                       {"person": self.request.user.person})
        sicherheitshinweis(self.request.user, "passwort_geaendert")
        return antwort


@login_required
def start(request):
    """Startseite (/, Logo im Kopf): für alle Rollen „Meine Aufgaben“."""
    return redirect("meine_aufgaben")


# ---------- Personen & Rollen ----------

PERSONEN_ARTEN = ("alle", "konten", "platzhalter")


@erfordert(rechte.darf_platzhalter_verwalten)
def personen(request):
    """Konten und Platzhalter in einer Liste. Planer:innen sehen nur die Platzhalter."""
    konto = request.user
    mit_konten = rechte.darf_konten_verwalten(konto)
    suche = request.GET.get("q", "").strip()
    art = request.GET.get("art") if mit_konten and request.GET.get("art") in PERSONEN_ARTEN else "alle"
    inaktiv = request.GET.get("zustand") == "inaktiv"
    basis = Person.objects.select_related("bereich", "konto").prefetch_related("gewerke")
    if not mit_konten or art == "platzhalter":
        basis = basis.platzhalter()
    elif art == "konten":
        basis = basis.mit_konto()
    basis = basis.filter(archiviert_am__isnull=not inaktiv)
    if suche:
        basis = basis.filter(Q(anzeigename__icontains=suche) | Q(konto__email__icontains=suche))
    zahlen = dict(basis.order_by().values_list("bereich").annotate(n=Count("id")))
    bereich = als_zahl(request.GET.get("bereich"))
    liste = list((basis.filter(bereich_id=bereich) if bereich else basis).order_by("anzeigename", "id"))
    for p in liste:
        p.bearbeitbar = p.ist_platzhalter or rechte.darf_konto_oeffnen(konto, p.konto)
    bereiche = [{"bereich": b, "anzahl": zahlen.get(b.pk, 0)} for b in Bereich.objects.all()]
    return seite(request, "kern/personen.html", "personen", personen=liste, bereiche=bereiche,
                 gesamt=sum(zahlen.values()), filter_bereich=bereich, filter_art=art, inaktiv=inaktiv, suche=suche,
                 mit_konten=mit_konten)


@erfordert(rechte.darf_konten_verwalten)
def person_einladen(request):
    """„+ Person einladen“: Konto anlegen, danach die Seite der Person mit dem Einladungslink."""
    konto = request.user
    form = EinladenForm(request.POST or None, konto=konto)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        with transaction.atomic():
            neu = Konto.objects.anlegen(d["email"], anzeigename=d["anzeigename"], bereich=d["bereich"],
                                        rolle=d["rolle"], erstellt_von=konto.person)
            neu.person.gewerke.set(d["gewerke"])
            neu.sprache = d["sprache"] or settings.LANGUAGE_CODE
            neu.save(update_fields=["sprache"])
            protokollieren(konto, "konto", neu.pk, "angelegt",
                           {"person": neu.person, "email": neu.email, "rolle": neu.rolle, "bereich": d["bereich"]})
        messages.success(request, _("Konto für %(name)s angelegt.") % {"name": neu.person.anzeigename})
        return _nach_einladung(request, neu)
    return seite(request, "kern/person_einladen.html", "personen", form=form)


PASSWORT_LINK = "passwort_link"  # Sitzung: {"pk": Konto, "link": Adresse}, wird einmal angezeigt


def _link_merken(request, konto, link):
    """Der Link wird auf der nächsten Seite dieses Kontos einmal angezeigt – und nur dort."""
    request.session[PASSWORT_LINK] = {"pk": konto.pk, "link": link}


def _link_abholen(request, konto):
    gemerkt = request.session.get(PASSWORT_LINK)
    if not isinstance(gemerkt, dict) or gemerkt.get("pk") != konto.pk:
        return None
    del request.session[PASSWORT_LINK]
    return gemerkt.get("link")


def _link_nur_mailen(akteur, ziel):
    """Anderer Admin: der Link geht nur an die hinterlegte Adresse und wird nie angezeigt, auch nicht als
    QR-Code. Ein bestehendes Passwort bleibt gültig. Rückgabe: False ohne E-Mail-Versand."""
    senden = reset_senden if ziel.has_usable_password() else einladung_senden
    if not senden(ziel, passwort_link(ziel)):
        return False
    protokollieren(akteur, "konto", ziel.pk, "link_per_mail", {"person": ziel.person})
    return True


def _neu_einladen(request, ziel):
    """Nach dem Korrigieren der Adresse: neue Einladung dorthin, der alte Link gilt nicht mehr."""
    if ziel.is_active and _link_nur_mailen(request.user, ziel):
        messages.info(request, _("Eine neue Einladung geht per E-Mail an %(email)s. Der bisherige Link gilt nicht mehr.")
                      % {"email": ziel.email})
    else:
        messages.warning(request, _("Der bisherige Link gilt nicht mehr. Ein neuer lässt sich am Server erzeugen: %(befehl)s")
                         % {"befehl": f"sudo teamplaner konto-aendern {ziel.email} --passwort-link"})


def _nach_einladung(request, neu):
    """Link erzeugen und zur Seite, die ihn zeigt: die Seite der Person, wenn das Konto bearbeitet
    werden darf – sonst (gleiche Rolle) eine Bestätigungsseite, die kein Bearbeitungsrecht braucht."""
    link = passwort_link(neu)
    _link_merken(request, neu, link)
    _einladung_mitteilen(request, neu, link)
    if rechte.darf_konto_bearbeiten(request.user, neu):
        return redirect("einst_person", pk=neu.pk)
    return redirect("einst_person_eingeladen", pk=neu.pk)


@erfordert(rechte.darf_konten_verwalten)
def person_eingeladen(request, pk):
    """Bestätigung nach dem Einladen eines Kontos, das die einladende Person nicht bearbeiten darf
    (gleiche Rolle): zeigt einmal den Link, sonst nichts vom Konto."""
    ziel = get_object_or_404(Konto.objects.select_related("person__bereich"), pk=pk)
    link = _link_abholen(request, ziel)
    if rechte.darf_konto_bearbeiten(request.user, ziel):
        if link:
            _link_merken(request, ziel, link)
        return redirect("einst_person", pk=pk)
    if not link:
        return redirect("einst_personen")
    return seite(request, "kern/person_eingeladen.html", "personen",
                 ziel=ziel, link=link, link_qr=link_qr_svg(link), mail_aktiv=mail_aktiv())


def _einladung_mitteilen(request, konto, link):
    """Einladungslink zusätzlich per E-Mail verschicken, wenn SMTP eingerichtet ist."""
    if einladung_senden(konto, link):
        messages.info(request, _("Der Link geht zusätzlich per E-Mail an %(email)s.") % {"email": konto.email})


@erfordert(rechte.darf_platzhalter_verwalten)
def person_seite(request, pk):
    """Seite einer Person: Konto oder Platzhalter, gleich aufgebaut."""
    if Konto.objects.filter(pk=pk).exists():
        return person_bearbeiten(request, pk)
    return platzhalter_bearbeiten(request, pk)


def _freigaben_der_person(ziel):
    """Alle Teamplaner- und Gantt-Ansichten mit dem Recht der Person, nach Art gruppiert."""
    gruppen = []
    for art, (ansicht_modell, freigabe_modell, _typ, _recht, url_name) in arten().items():
        rechte_je_ansicht = dict(freigabe_modell.objects.filter(konto=ziel).values_list("ansicht_id", "recht"))
        gruppen.append({"art": art, "url_name": url_name, "ansichten": [
            {"ansicht": a, "recht": rechte_je_ansicht.get(a.pk, "")} for a in ansicht_modell.objects.all()
        ]})
    return gruppen


def _hinweis_freigabe_ohne_teamplaner(konto, ziel):
    """Der Haken allein reicht nicht: Die Tagesfreigabe setzt nur, wer auch den Teamplaner sieht."""
    name = Systemeinstellungen.laden().freigabe_bezeichnung
    text = _("%(name)s sieht den Teamplaner nicht und kann „%(freigabe)s“ deshalb nicht setzen. Dazu braucht "
             "es mindestens Planer:in und „Bearbeiten“ auf einer Teamplaner-Ansicht.") % {
        "name": ziel.person.anzeigename, "freigabe": name}
    if not arten()["teamplaner"][3](konto):
        return text
    return format_html('{} <a href="{}">{}</a>', text, reverse("einst_ansichten") + "?art=teamplaner",
                       _("Freigaben der Teamplaner-Ansichten"))


def _hinweis_planer_ohne_ansicht(konto, ziel):
    """Die Rolle allein zeigt den Teamplaner noch nicht: dazu braucht es „Bearbeiten“ auf einer Ansicht."""
    if arten()["teamplaner"][3](konto):
        ziel_url = reverse("einst_ansichten") + "?art=teamplaner"
    else:
        ziel_url = reverse("einst_person", args=[ziel.pk]) + "#freigaben"
    return format_html(
        '{} <a href="{}">{}</a>',
        _("%(name)s ist jetzt Planer:in. Den Teamplaner sieht sie erst, wenn sie auf mindestens einer "
          "Teamplaner-Ansicht „Bearbeiten“ hat.") % {"name": ziel.person.anzeigename},
        ziel_url, _("Freigaben der Teamplaner-Ansichten"),
    )


LETZTER_ADMIN = gettext_lazy("Nicht möglich: Es muss ein weiterer aktiver Admin bleiben, der sich schon einmal angemeldet hat.")


@erfordert(rechte.darf_konten_verwalten)
def person_bearbeiten(request, pk):
    konto = request.user
    ziel = get_object_or_404(Konto.objects.select_related("person__bereich"), pk=pk)
    if not rechte.darf_konto_oeffnen(konto, ziel):
        raise PermissionDenied
    bearbeitbar = rechte.darf_konto_bearbeiten(konto, ziel)  # sonst anderer Admin: nur die Rolle
    anmeldung_verwaltbar = rechte.darf_anmeldung_verwalten(konto, ziel)
    person = ziel.person
    form = KontoBearbeitenForm(
        request.POST or None, konto=konto, ziel=ziel,
        initial={"anzeigename": person.anzeigename, "email": ziel.email, "rolle": ziel.rolle, "bereich": person.bereich,
                 "gewerke": person.gewerke.all(), "systemkonto": ziel.systemkonto,
                 "darf_tagesfreigabe": ziel.darf_tagesfreigabe},
    )
    eigene_rolle_aenderbar = ziel.pk == konto.pk and rechte.ist_admin(konto) and konten.anderer_admin_vorhanden(ziel)
    if ziel.pk == konto.pk and not eigene_rolle_aenderbar:
        form.fields["rolle"].disabled = True  # ohne weiteren Admin bleibt die eigene Rolle
    adresse_korrigierbar = rechte.darf_adresse_korrigieren(konto, ziel)
    if not bearbeitbar:
        for feld in ("anzeigename", "email", "bereich", "gewerke", "systemkonto", "darf_tagesfreigabe"):
            if feld != "email" or not adresse_korrigierbar:
                del form.fields[feld]
    elif ziel.pk == konto.pk or not anmeldung_verwaltbar:
        form.fields["email"].disabled = True  # die eigene nur mit Passwort (email_aendern)
    if request.method == "POST" and form.is_valid():
        d = form.cleaned_data
        if not rechte.darf_rolle_vergeben(konto, ziel, d["rolle"]):
            raise PermissionDenied
        alt = {"anzeigename": person.anzeigename, "bereich": person.bereich, "email": ziel.email,
               "systemkonto": ziel.systemkonto, "darf_tagesfreigabe": ziel.darf_tagesfreigabe}
        diff = {}
        try:
            with transaction.atomic():
                korrigiert = adresse_korrigierbar and d["email"] != ziel.email
                if korrigiert:
                    konten.adresse_korrigieren(konto, ziel, d["email"])
                rolle_neu = konten.rolle_setzen(konto, ziel, d["rolle"])
                if bearbeitbar:
                    person.anzeigename, person.bereich = d["anzeigename"], d["bereich"]
                    person.save(update_fields=["anzeigename", "bereich"])
                    person.gewerke.set(d["gewerke"])
                    ziel.email, ziel.systemkonto = d["email"], d["systemkonto"]
                    ziel.darf_tagesfreigabe = d["darf_tagesfreigabe"]  # deaktiviertes Feld: bleibt beim alten Wert
                    ziel.save(update_fields=["email", "systemkonto", "darf_tagesfreigabe"])
                    diff = aenderungen(alt, {"anzeigename": person.anzeigename, "bereich": person.bereich,
                                             "email": ziel.email, "systemkonto": ziel.systemkonto,
                                             "darf_tagesfreigabe": ziel.darf_tagesfreigabe})
                    if diff:
                        protokollieren(konto, "konto", ziel.pk, "geaendert", {"person": person, **diff})
        except konten.LetzterAdmin:
            messages.error(request, LETZTER_ADMIN)
            return redirect("einst_person", pk=pk)
        if "email" in diff and not alt["email"].endswith(ENTFERNT_DOMAIN):
            # An die bisherige Adresse: die Person merkt es, auch wenn jemand anderes ihr Konto übernehmen will
            sicherheitshinweis(ziel, "email_geaendert", an=alt["email"], neu=ziel.email)
        messages.success(request, _("Gespeichert."))
        if korrigiert:
            _neu_einladen(request, ziel)
        ich = ziel if ziel.pk == konto.pk else konto
        if not rechte.darf_konto_oeffnen(ich, ziel):
            # Sich selbst herabgestuft oder die Person auf die eigene Rolle angehoben
            return redirect(settings.LOGIN_REDIRECT_URL if ich is ziel else "einst_personen")
        if rolle_neu and ziel.rolle == Rolle.PLANER and not hat_planungsansicht(ziel):
            messages.info(request, _hinweis_planer_ohne_ansicht(konto, ziel))
        elif ziel.darf_tagesfreigabe and not hat_planungsansicht(ziel) and (
                "darf_tagesfreigabe" in diff or rolle_neu):
            messages.info(request, _hinweis_freigabe_ohne_teamplaner(konto, ziel))
        return redirect("einst_person", pk=pk)
    darf_freigaben = {art: recht(konto) for art, (_a, _f, _t, recht, _u) in arten().items()}
    link = _link_abholen(request, ziel)
    return seite(request, "kern/person_bearbeiten.html", "personen",
                 ziel=ziel, form=form, freigabe_zeile_aus=not Systemeinstellungen.laden().freigabe_zeile,
                 freigabe_ohne_teamplaner=ziel.darf_tagesfreigabe and not hat_planungsansicht(ziel), link=link, link_qr=link_qr_svg(link) if link else None, mail_aktiv=mail_aktiv(),
                 zwei_faktor_aktiv=zwei_faktor.aktiv(ziel),
                 immer_bearbeiten=rechte.sieht_alles_im_teamplaner(ziel), ab_planer=ziel.hat_mindestens(Rolle.PLANER),
                 bearbeitbar=bearbeitbar, adresse_korrigierbar=adresse_korrigierbar, anmeldung_zuruecksetzbar=rechte.darf_anmeldung_zuruecksetzen(konto, ziel),
                 link_nur_per_mail=rechte.darf_link_mailen(konto, ziel),
                 eigene_rolle_aenderbar=eigene_rolle_aenderbar,
                 email_wechsel=konten.offener_email_wechsel(ziel) if ziel.pk == konto.pk else None,
                 schutz_bis=ziel.admin_bis + rechte.ADMIN_SCHUTZFRIST if rechte.in_schutzfrist(ziel) else None,
                 freigaben=[g for g in _freigaben_der_person(ziel) if bearbeitbar and darf_freigaben[g["art"]]])


EMAIL_VERGEBEN = gettext_lazy("Für diese E-Mail gibt es bereits ein Konto.")
EMAIL_GEAENDERT = gettext_lazy("E-Mail-Adresse geändert. Sie melden sich ab jetzt mit %(email)s an.")


@never_cache
@erfordert(rechte.darf_konten_verwalten)
def email_aendern(request):
    """Eigene E-Mail-Adresse, immer mit dem Passwort. Mit E-Mail-Versand gilt sie erst nach der Bestätigung
    über den Link an die neue Adresse, ohne wird sie zweimal eingegeben und gilt sofort."""
    konto = request.user
    mit_link = mail_aktiv()
    form = EmailAendernForm(request.POST or None, konto=konto, wiederholen=not mit_link)
    if request.method == "POST" and form.is_valid():
        if _gesperrt(request, _zugang(konto)):
            return render(request, "registration/gesperrt.html", status=429)
        email = form.cleaned_data["email"]
        if not konto.check_password(form.cleaned_data["passwort"]):
            _fehlversuch(request, _zugang(konto))
            form.add_error("passwort", _("Das Passwort stimmt nicht."))
        elif mit_link:
            if not konten.email_wechsel_beginnen(konto, email):
                return redirect("email_aendern")  # Versand eben abgeschaltet: jetzt mit Wiederholung
            messages.info(request, _("Ein Link zum Bestätigen geht per E-Mail an %(email)s. Bis dahin gilt die "
                                     "bisherige Adresse.") % {"email": email})
            return redirect("einst_person", pk=konto.pk)
        else:
            try:
                konten.eigene_email_setzen(konto, email)
            except konten.EmailVergeben:
                form.add_error("email", EMAIL_VERGEBEN)
            else:
                messages.success(request, EMAIL_GEAENDERT % {"email": email})
                return redirect("einst_person", pk=konto.pk)
    return seite(request, "kern/email_aendern.html", "personen", form=form, mit_link=mit_link,
                 stunden=settings.TEAMPLANER_RESET_GUELTIG_STUNDEN)


@require_POST
@erfordert(rechte.darf_konten_verwalten)
def email_wechsel_abbrechen(request):
    if konten.email_wechsel_abbrechen(request.user):
        messages.success(request, _("Wechsel der E-Mail-Adresse abgebrochen. Der Link gilt nicht mehr."))
    return redirect("einst_person", pk=request.user.pk)


@never_cache
@erfordert(rechte.darf_konten_verwalten)
def email_bestaetigen(request, schluessel):
    """Link aus der E-Mail an die neue Adresse. Nur angemeldet im eigenen Konto: Wer die E-Mail wegen eines
    Tippfehlers bekommt, kann damit nichts anfangen. Geändert wird erst mit dem Knopf (POST), damit das
    Vorabladen von Links nichts auslöst."""
    konto = request.user
    if request.method == "POST":
        try:
            if konten.email_wechsel_bestaetigen(konto, schluessel):
                messages.success(request, EMAIL_GEAENDERT % {"email": konto.email})
                return redirect("einst_person", pk=konto.pk)
        except konten.EmailVergeben:
            messages.error(request, EMAIL_VERGEBEN)
            return redirect("einst_person", pk=konto.pk)
    return seite(request, "kern/email_bestaetigen.html", "personen",
                 wechsel=konten.passender_email_wechsel(konto, schluessel))


@require_POST
@erfordert(rechte.darf_konten_verwalten)
def person_freigabe(request, pk):
    """Eine Freigabe auf der Seite der Person ändern, sofort gespeichert."""
    ziel = get_object_or_404(Konto.objects.select_related("person"), pk=pk)
    art = request.POST.get("art")
    if art not in arten() or not rechte.darf_konto_bearbeiten(request.user, ziel):
        raise PermissionDenied
    ansicht_modell, _f, _t, darf, _u = arten()[art]
    if not darf(request.user):
        raise PermissionDenied
    ansicht = get_object_or_404(ansicht_modell, pk=als_zahl(request.POST.get("ansicht")))
    gewuenscht = request.POST.get("recht", "")
    if rechte.sieht_alles_im_teamplaner(ziel) or gewuenscht not in ("", "sehen", "bearbeiten"):
        return HttpResponse(status=400)
    if setzen(request.user, art, ansicht, ziel, gewuenscht) != gewuenscht:
        return HttpResponse(status=400)  # „Bearbeiten“ erst ab Planer:in
    return gespeichert(request)


@require_POST
@erfordert(rechte.darf_konten_verwalten)
def person_aktion(request, pk, aktion):
    konto = request.user
    ziel = get_object_or_404(Konto.objects.select_related("person"), pk=pk)
    nur_per_mail = aktion == "link" and rechte.darf_link_mailen(konto, ziel)
    darf = {"deaktivieren": rechte.darf_konto_oeffnen, "reaktivieren": rechte.darf_konto_deaktivieren,
            "link": rechte.darf_anmeldung_zuruecksetzen,
            "zwei_faktor_zuruecksetzen": rechte.darf_anmeldung_zuruecksetzen,
            "foto_entfernen": rechte.darf_konto_bearbeiten}.get(aktion)
    if darf is None or not (nur_per_mail or darf(konto, ziel)):
        raise PermissionDenied
    if aktion == "link" and ziel.email_entfernt:
        messages.error(request, _("Bitte zuerst eine neue E-Mail-Adresse eintragen."))
    elif nur_per_mail:
        if not _link_nur_mailen(konto, ziel):
            raise PermissionDenied  # ohne E-Mail-Versand nur am Server
        messages.success(request, _("Ein neuer Link geht per E-Mail an %(email)s.") % {"email": ziel.email})
    elif aktion == "link":
        if ziel.has_usable_password():
            # Link zum Zurücksetzen nur an die Person selbst – sonst könnte die Verwaltung das Konto
            # übernehmen. Ohne Mailversand: bisheriges Passwort sperren, dann wie eine Einladung.
            if reset_senden(ziel, passwort_link(ziel)):
                protokollieren(konto, "konto", ziel.pk, "link_per_mail", {"person": ziel.person})
                messages.success(request, _("Ein Link zum Zurücksetzen geht per E-Mail an %(email)s.") % {"email": ziel.email})
                return redirect("einst_person", pk=pk)
            ziel.set_unusable_password()
            ziel.save(update_fields=["password"])
            protokollieren(konto, "konto", ziel.pk, "passwort_zurueckgesetzt", {"person": ziel.person})
            messages.warning(request, _("Das bisherige Passwort gilt nicht mehr. Bitte den Link an die Person weitergeben."))
        link = passwort_link(ziel)
        _link_merken(request, ziel, link)
        protokollieren(konto, "konto", ziel.pk, "link_erzeugt", {"person": ziel.person})
        _einladung_mitteilen(request, ziel, link)
    elif aktion == "deaktivieren":
        if ziel.pk == konto.pk:
            messages.error(request, _("Sie können Ihr eigenes Konto nicht deaktivieren."))
        else:
            try:
                konten.deaktivieren(konto, ziel)
            except konten.LetzterAdmin:
                messages.error(request, LETZTER_ADMIN)
            else:
                messages.success(request, _("Konto deaktiviert. Aufgaben und Einteilungen bleiben erhalten."))
    elif aktion == "reaktivieren":
        konten.reaktivieren(konto, ziel)
        messages.success(request, _("Konto reaktiviert."))
    elif aktion == "foto_entfernen":
        fotos.entfernen(ziel.person)
        protokollieren(konto, "konto", ziel.pk, "foto_entfernt", {"person": ziel.person})
        messages.success(request, _("Foto entfernt."))
    elif aktion == "zwei_faktor_zuruecksetzen":
        zwei_faktor.zuruecksetzen(ziel)
        protokollieren(konto, "konto", ziel.pk, "zwei_faktor_zurueckgesetzt", {"person": ziel.person})
        sicherheitshinweis(ziel, "zwei_faktor_zurueckgesetzt")
        messages.success(request, _("Zwei-Faktor-Anmeldung zurückgesetzt.") + " " + (
            _("Bei der nächsten Anmeldung wird sie neu eingerichtet.") if zwei_faktor.pflicht(ziel) else ""))
    else:
        raise PermissionDenied
    return redirect("einst_person", pk=pk)


# ---------- Platzhalter ----------

@erfordert(rechte.darf_platzhalter_verwalten)
def platzhalter_neu(request):
    """„+ Platzhalter“."""
    form = PlatzhalterForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        person = form.save(commit=False)
        person.erstellt_von = request.user.person
        person.save()
        form.save_m2m()
        protokollieren(request.user, "platzhalter", person.pk, "angelegt", {"person": person, "bereich": person.bereich})
        messages.success(request, _("Platzhalter „%(name)s“ angelegt.") % {"name": person.anzeigename})
        return redirect("einst_personen")
    return seite(request, "kern/platzhalter_neu.html", "personen", form=form)


@erfordert(rechte.darf_platzhalter_verwalten)
def platzhalter_bearbeiten(request, pk, umwandeln=None):
    person = get_object_or_404(Person.objects.platzhalter().select_related("bereich"), pk=pk)
    alt = {"anzeigename": person.anzeigename, "bereich": person.bereich, "notiz": person.notiz,
           "weiterleiten_an": _weiterleitung(person)}
    form = PlatzhalterForm(request.POST or None if umwandeln is None else None, instance=person)
    if umwandeln is None and rechte.darf_konten_verwalten(request.user):
        umwandeln = UmwandelnForm(konto=request.user)
    if request.method == "POST" and form.is_bound and form.is_valid():
        form.save()
        protokollieren(request.user, "platzhalter", person.pk, "geaendert",
                       aenderungen(alt, {"anzeigename": person.anzeigename, "bereich": person.bereich, "notiz": person.notiz,
                                         "weiterleiten_an": _weiterleitung(person)}))
        messages.success(request, _("Gespeichert."))
        return redirect("einst_person", pk=pk)
    eingeteilt_bis = person.einteilungen.aggregate(m=Max("bis"))["m"]
    return seite(request, "kern/platzhalter_bearbeiten.html", "personen",
                 person=person, form=form, umwandeln=umwandeln, eingeteilt_bis=eingeteilt_bis)


def _weiterleitung(platzhalter):
    return sorted(platzhalter.weiterleiten_an.values_list("anzeigename", flat=True))


@require_POST
@erfordert(rechte.darf_platzhalter_verwalten)
def platzhalter_aktion(request, pk, aktion):
    person = get_object_or_404(Person.objects.platzhalter(), pk=pk)
    if aktion == "archivieren":
        person.archivieren()
        messages.success(request, _("„%(name)s“ archiviert.") % {"name": person.anzeigename})
    elif aktion == "wiederherstellen":
        person.wiederherstellen()
        messages.success(request, _("„%(name)s“ wiederhergestellt.") % {"name": person.anzeigename})
    else:
        raise PermissionDenied
    protokollieren(request.user, "platzhalter", person.pk, aktion, {"person": person})
    return redirect("einst_person", pk=pk)


@require_POST
@erfordert(rechte.darf_konten_verwalten)
def platzhalter_umwandeln(request, pk):
    """Platzhalter bekommt ein Konto; Zuweisungen, Einteilungen, Erwähnungen bleiben."""
    person = get_object_or_404(Person.objects.platzhalter(), pk=pk)
    form = UmwandelnForm(request.POST, konto=request.user)
    if not form.is_valid():
        return platzhalter_bearbeiten(request, pk, umwandeln=form)
    neu = Konto.objects.anlegen(form.cleaned_data["email"], anzeigename=person.anzeigename,
                                bereich=person.bereich, rolle=form.cleaned_data["rolle"], person=person)
    person.weiterleiten_an.clear()  # mit eigenem Konto bekommt die Person ihre Benachrichtigungen selbst
    protokollieren(request.user, "konto", neu.pk, "aus_platzhalter", {"person": person, "rolle": neu.rolle})
    messages.success(request, _("„%(name)s“ hat jetzt ein Konto.") % {"name": person.anzeigename})
    return _nach_einladung(request, neu)


# ---------- Protokoll ----------

def erledigt_eintraege():
    """Protokolleinträge, in denen eine Aufgabe auf einen erledigten Status gesetzt wurde."""
    erledigt_ids = list(Status.objects.filter(ist_erledigt=True).values_list("id", flat=True))
    return Protokolleintrag.objects.filter(objekt_typ="aufgabe", aktion="geaendert",
                                           daten__status__1__id__in=erledigt_ids)


@erfordert(rechte.darf_erledigte_sehen)
def protokoll(request):
    voll = rechte.darf_protokoll_sehen(request.user)
    # Planer:innen sehen nur, wer wann welche Aufgabe erledigt hat
    erledigt = not voll or request.GET.get("ansicht") == "erledigt"
    typ = "" if erledigt else request.GET.get("typ", "")
    eintraege = (erledigt_eintraege() if erledigt else Protokolleintrag.objects.all()).select_related("akteur")
    if typ:
        eintraege = eintraege.filter(objekt_typ=typ)
    seite = Paginator(eintraege, 50).get_page(request.GET.get("seite"))
    if erledigt:
        aufgaben = Aufgabe.objects.select_related("projekt", "eltern").in_bulk([e.aufgabe_id for e in seite])
        for e in seite:
            e.aufgabe = aufgaben.get(e.aufgabe_id)
    typen = Protokolleintrag.objects.order_by().values_list("objekt_typ", flat=True).distinct() if voll else []
    parameter = "ansicht=erledigt" if erledigt and voll else f"typ={typ}"
    return render(request, "kern/protokoll.html", {
        "seite": seite, "typ": typ, "typen": sorted(typen), "erledigt": erledigt, "voll": voll,
        "parameter": parameter, "aktiv": "protokoll",
    })


# ---------- Einstellungen (nur Admin) ----------

ANHANG_SORTIERUNG = {
    "groesse": ["-groesse", "-id"],
    "neu": ["-hochgeladen_am", "-id"],
    "alt": ["hochgeladen_am", "id"],
}


@erfordert(rechte.darf_systemeinstellungen)
def anhaenge(request):
    """Anhänge der Aufgaben nach Größe oder Datum, zum Aufräumen. Notiz-Anhänge nur als Summe:
    Gruppenordner sieht nur, wem sie freigegeben sind, persönliche Notizen niemand sonst."""
    sortierung = request.GET.get("sort") if request.GET.get("sort") in ANHANG_SORTIERUNG else "groesse"
    nur_archiv = request.GET.get("archiv") == "1"
    liste = Anhang.objects.select_related("aufgabe__projekt", "hochgeladen_von").order_by(*ANHANG_SORTIERUNG[sortierung])
    if nur_archiv:
        liste = liste.filter(aufgabe__projekt__archiviert_am__isnull=False)
    try:
        platz = shutil.disk_usage(settings.MEDIA_ROOT)
    except OSError:
        platz = None

    def summe(qs):
        return qs.aggregate(anzahl=Count("id"), groesse=Sum("groesse"))

    return seite(request, "kern/anhaenge.html", "speicherplatz", **{
        "seite": Paginator(liste, 50).get_page(request.GET.get("seite")),
        "sortierung": sortierung, "nur_archiv": nur_archiv,
        "parameter": f"sort={sortierung}" + ("&archiv=1" if nur_archiv else ""),
        "summen": [
            (_("Aufgaben"), summe(Anhang.objects.all())),
            (_("Notizen in Gruppenordnern"), summe(NotizAnhang.objects.filter(notiz__ordner__isnull=False))),
            (_("Persönliche Notizen"), summe(NotizAnhang.objects.filter(notiz__ordner__isnull=True))),
        ],
        "platz": platz,
    })


@require_POST
@erfordert(rechte.darf_systemeinstellungen)
def anhang_entfernen(request, pk):
    anhang = get_object_or_404(Anhang, pk=pk)
    protokollieren(request.user, "anhang", anhang.pk, "geloescht", {"name": anhang.dateiname},
                   aufgabe_id=anhang.aufgabe_id)
    anhang.delete()  # Datei und Vorschau löscht zusammenarbeit.anhaenge.dateien_entfernen
    messages.success(request, _("„%(name)s“ gelöscht.") % {"name": anhang.dateiname})
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        weiter = reverse("einst_speicherplatz")
    return redirect(weiter)


