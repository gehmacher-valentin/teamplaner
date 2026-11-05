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
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from projekte.models import Status

from . import fotos, rechte, version, zwei_faktor
from .auth import zu_viele_fehlversuche_von_ip
from .forms import (
    AnmeldeForm,
    EinladenForm,
    KontoBearbeitenForm,
    PasswortBestaetigenForm,
    PasswortVergessenForm,
    PlatzhalterForm,
    UmwandelnForm,
    ZweiFaktorCodeForm,
    ZweiFaktorEinrichtenForm,
)
from .hilfen import als_zahl, erfordert, link_qr_svg, passwort_link, passwort_links
from .models import (
    Bereich,
    Konto,
    Person,
    Protokolleintrag,
    Resetanfrage,
    Rolle,
)
from .protokoll import aenderungen, protokollieren

# ---------- Anmeldung ----------

class AnmeldenView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = AnmeldeForm
    redirect_authenticated_user = True

    def get_context_data(self, **kwargs):
        from zusammenarbeit.mail import mail_aktiv

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
        # Passwort stimmt; angemeldet wird erst nach dem Code aus der App
        self.request.session[ANMELDUNG_OFFEN] = {
            "konto": konto.pk, "backend": konto.backend, "seit": time.time(),
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


def _fehlversuch(request, konto):
    """Falscher Code oder falsches Passwort zählt wie ein Fehlversuch bei der Anmeldung (Sperre)."""
    user_login_failed.send(sender=__name__, credentials=_zugang(konto), request=request)


def _gesperrt(request, konto):
    return AxesProxyHandler.is_locked(request, _zugang(konto)) or zu_viele_fehlversuche_von_ip(request)


@never_cache
def anmelden_code(request):
    """Zweiter Schritt der Anmeldung: Code aus der App oder ein Ersatzcode."""
    offen = request.session.get(ANMELDUNG_OFFEN)
    konto = Konto.objects.select_related("person").filter(pk=offen["konto"]).first() if offen else None
    if (konto is None or time.time() - offen["seit"] > ANMELDUNG_OFFEN_SEKUNDEN
            or not konto.is_active or not zwei_faktor.aktiv(konto)):
        request.session.pop(ANMELDUNG_OFFEN, None)
        if offen:
            messages.info(request, _("Die Zeit für die Eingabe ist abgelaufen. Bitte erneut anmelden."))
        return redirect("login")
    form = ZweiFaktorCodeForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _gesperrt(request, konto):
            request.session.pop(ANMELDUNG_OFFEN, None)
            return render(request, "registration/gesperrt.html", status=429)
        art = zwei_faktor.pruefen(konto, form.cleaned_data["code"])
        if art:
            del request.session[ANMELDUNG_OFFEN]
            login(request, konto, backend=offen["backend"])
            zwei_faktor.bestanden(request, konto)
            if art == "ersatz":
                konto.refresh_from_db(fields=["totp_ersatzcodes"])
                messages.warning(request, _("Sie haben einen Ersatzcode verwendet, noch %(n)s übrig. Neue Codes "
                                            "oder ein neues Telefon richten Sie unter „Mein Konto“ ein.")
                                 % {"n": zwei_faktor.ersatzcodes_uebrig(konto)})
            return redirect(offen["weiter"])
        _fehlversuch(request, konto)
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
    from zusammenarbeit.mail import sicherheitshinweis

    konto = request.user
    geheimnis = request.session.get(NEUES_GEHEIMNIS) or zwei_faktor.neues_geheimnis()
    request.session[NEUES_GEHEIMNIS] = geheimnis
    form = ZweiFaktorEinrichtenForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        if _gesperrt(request, konto):
            return render(request, "registration/gesperrt.html", status=429)
        schritt = zwei_faktor.passender_schritt(geheimnis, form.cleaned_data["code"])
        if not konto.check_password(form.cleaned_data["passwort"]):
            _fehlversuch(request, konto)
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
    from zusammenarbeit.mail import sicherheitshinweis

    konto = request.user
    if not zwei_faktor.aktiv(konto) or aktion not in {"ersatzcodes", "ausschalten"}:
        raise PermissionDenied
    if aktion == "ausschalten" and zwei_faktor.pflicht(konto):
        raise PermissionDenied
    if _gesperrt(request, konto):
        return render(request, "registration/gesperrt.html", status=429)
    form = PasswortBestaetigenForm(request.POST)
    if not form.is_valid() or not konto.check_password(form.cleaned_data["passwort"]):
        _fehlversuch(request, konto)
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
    from zusammenarbeit.mail import mail_aktiv, reset_senden

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
        from zusammenarbeit.mail import sicherheitshinweis

        zuruecksetzen = self.user.has_usable_password()  # sonst: Einladung angenommen
        messages.success(self.request, _("Passwort gespeichert. Sie können sich jetzt anmelden."))
        protokollieren(self.user, "konto", self.user.pk, "passwort_gesetzt")
        antwort = super().form_valid(form)
        if zuruecksetzen:
            sicherheitshinweis(self.user, "passwort_zurueckgesetzt")
        return antwort


class PasswortAendernView(auth_views.PasswordChangeView):
    """„Anmeldung & Sicherheit“: Passwort direkt auf der Seite, darunter die Zwei-Faktor-Anmeldung."""

    template_name = "kern/einst_sicherheit.html"
    success_url = reverse_lazy("einst_sicherheit")

    def get_context_data(self, **kwargs):
        from .einstellungen import zwei_faktor_kontext

        return {**super().get_context_data(**kwargs), "zwei_faktor": zwei_faktor_kontext(self.request.user),
                **_sicherheit_rahmen()}

    def form_valid(self, form):
        from zusammenarbeit.mail import sicherheitshinweis

        messages.success(self.request, _("Passwort geändert."))
        antwort = super().form_valid(form)
        protokollieren(self.request.user, "konto", self.request.user.pk, "passwort_geaendert",
                       {"person": self.request.user.person})
        sicherheitshinweis(self.request.user, "passwort_geaendert")
        return antwort


@login_required
def start(request):
    from planung.rechte import hat_planungsansicht

    return redirect("teamplaner" if hat_planungsansicht(request.user) else "meine_aufgaben")


# ---------- Personen & Rollen ----------

PERSONEN_ARTEN = ("alle", "konten", "platzhalter")


@erfordert(rechte.darf_platzhalter_verwalten)
def personen(request):
    """Konten und Platzhalter in einer Liste. Planer:innen sehen nur die Platzhalter."""
    from .einstellungen import seite

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
        p.bearbeitbar = p.ist_platzhalter or rechte.darf_konto_bearbeiten(konto, p.konto)
    bereiche = [{"bereich": b, "anzahl": zahlen.get(b.pk, 0)} for b in Bereich.objects.all()]
    return seite(request, "kern/personen.html", "personen", personen=liste, bereiche=bereiche,
                 gesamt=sum(zahlen.values()), filter_bereich=bereich, filter_art=art, inaktiv=inaktiv, suche=suche,
                 mit_konten=mit_konten)


@erfordert(rechte.darf_konten_verwalten)
def person_einladen(request):
    """„+ Person einladen“: Konto anlegen, danach die Seite der Person mit dem Einladungslink."""
    from .einstellungen import seite

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
        link = passwort_link(neu)
        request.session["passwort_link"] = link
        messages.success(request, _("Konto für %(name)s angelegt.") % {"name": neu.person.anzeigename})
        _einladung_mitteilen(request, neu, link)
        return redirect("einst_person", pk=neu.pk)
    return seite(request, "kern/person_einladen.html", "personen", form=form)


def _einladung_mitteilen(request, konto, link):
    """Einladungslink zusätzlich per E-Mail verschicken, wenn SMTP eingerichtet ist."""
    from zusammenarbeit.mail import einladung_senden

    if einladung_senden(konto, link):
        messages.info(request, _("Der Link geht zusätzlich per E-Mail an %(email)s.") % {"email": konto.email})


# Anzeige der Rechtematrix (gleich wie tests/test_rechte.py)
RECHTEMATRIX = [
    (gettext_lazy("Feiertage, Status, Systemeinstellungen"), "ja nein nein nein nein", ""),
    (gettext_lazy("Benutzerkonten anlegen und deaktivieren"), "ja ja nein nein nein",
     gettext_lazy("Bestehende Konten nur mit niedrigerer Rolle als der eigenen; Admin-Konten über die Kommandozeile")),
    (gettext_lazy("Rollen vergeben"), "ja ja nein nein nein", gettext_lazy("Bereichsleitung bis maximal zur eigenen Rolle")),
    (gettext_lazy("Projekte anlegen, Tags vergeben, archivieren"), "ja ja ja nein nein", ""),
    (gettext_lazy("Aufgaben anlegen und bearbeiten"), "ja ja ja eigene nein", gettext_lazy("Mitarbeiter:innen: in Projekten, in denen sie Mitglied sind")),
    (gettext_lazy("Aufgaben abschließen, kommentieren"), "ja ja ja ja nein", ""),
    (gettext_lazy("Teamplaner-Ansichten anlegen und freigeben"), "ja ja nein nein nein", ""),
    (gettext_lazy("Teamplaner: einteilen, Abwesenheiten"), "ja ja freigabe nein nein", gettext_lazy("Planer:innen: in Ansichten mit Freigabe „bearbeiten“")),
    (gettext_lazy("Platzhalter anlegen, bearbeiten, archivieren"), "ja ja ja nein nein", ""),
    (gettext_lazy("Lesekalender"), "ja ja freigabe freigabe freigabe", gettext_lazy("freigegebene Ansichten; die eigene Einteilung immer")),
    (gettext_lazy("Änderungsprotokoll einsehen"), "ja ja nein nein nein", ""),
    (gettext_lazy("Protokoll: erledigte Aufgaben einsehen"), "ja ja ja nein nein", ""),
    (gettext_lazy("Tagesfreigabe einrichten"), "ja nein nein nein nein", ""),
    (gettext_lazy("Bestellungen eintragen und ändern"), "ja ja ja ja nein", gettext_lazy("Löschen: eigene Zeilen, ab Planer:in alle")),
]


@erfordert(rechte.darf_platzhalter_verwalten)
def person_seite(request, pk):
    """Seite einer Person: Konto oder Platzhalter, gleich aufgebaut."""
    if Konto.objects.filter(pk=pk).exists():
        return person_bearbeiten(request, pk)
    return platzhalter_bearbeiten(request, pk)


def _freigaben_der_person(ziel):
    """Alle Teamplaner- und Gantt-Ansichten mit dem Recht der Person, nach Art gruppiert."""
    from .freigaben import arten

    gruppen = []
    for art, (ansicht_modell, freigabe_modell, _typ, _recht, url_name) in arten().items():
        rechte_je_ansicht = dict(freigabe_modell.objects.filter(konto=ziel).values_list("ansicht_id", "recht"))
        gruppen.append({"art": art, "url_name": url_name, "ansichten": [
            {"ansicht": a, "recht": rechte_je_ansicht.get(a.pk, "")} for a in ansicht_modell.objects.all()
        ]})
    return gruppen


@erfordert(rechte.darf_konten_verwalten)
def person_bearbeiten(request, pk):
    from zusammenarbeit.mail import mail_aktiv

    from .einstellungen import seite
    from .freigaben import arten, herabstufen

    konto = request.user
    ziel = get_object_or_404(Konto.objects.select_related("person__bereich"), pk=pk)
    if not rechte.darf_konto_bearbeiten(konto, ziel):
        raise PermissionDenied
    person = ziel.person
    form = KontoBearbeitenForm(
        request.POST or None, konto=konto, ziel=ziel,
        initial={"anzeigename": person.anzeigename, "email": ziel.email, "rolle": ziel.rolle,
                 "gewerke": person.gewerke.all(), "systemkonto": ziel.systemkonto},
    )
    if ziel.pk == konto.pk:
        form.fields["rolle"].disabled = True  # die eigene Rolle ändert eine höhere Rolle
    if request.method == "POST" and form.is_valid():
        from zusammenarbeit.mail import sicherheitshinweis

        d = form.cleaned_data
        if not rechte.darf_rolle_vergeben(konto, ziel, d["rolle"]):
            raise PermissionDenied
        alt = {"anzeigename": person.anzeigename, "email": ziel.email, "rolle": ziel.rolle, "systemkonto": ziel.systemkonto}
        with transaction.atomic():
            person.anzeigename = d["anzeigename"]
            person.save(update_fields=["anzeigename"])
            person.gewerke.set(d["gewerke"])
            ziel.email, ziel.rolle, ziel.systemkonto = d["email"], d["rolle"], d["systemkonto"]
            ziel.save(update_fields=["email", "rolle", "systemkonto"])
            diff = aenderungen(alt, {"anzeigename": person.anzeigename, "email": ziel.email, "rolle": ziel.rolle,
                                     "systemkonto": ziel.systemkonto})
            if diff:
                protokollieren(konto, "konto", ziel.pk, "geaendert", {"person": person, **diff})
            if "rolle" in diff:
                herabstufen(konto, ziel)  # unter Planer:in wird „Bearbeiten“ zu „Sehen“
        if "email" in diff:
            # An die bisherige Adresse: die Person merkt es, auch wenn jemand anderes ihr Konto übernehmen will
            sicherheitshinweis(ziel, "email_geaendert", an=alt["email"], neu=ziel.email)
        messages.success(request, _("Gespeichert."))
        return redirect("einst_person", pk=pk)
    darf_freigaben = {art: recht(konto) for art, (_a, _f, _t, recht, _u) in arten().items()}
    link = request.session.pop("passwort_link", None)
    return seite(request, "kern/person_bearbeiten.html", "personen",
                 ziel=ziel, form=form, link=link, link_qr=link_qr_svg(link) if link else None, mail_aktiv=mail_aktiv(),
                 zwei_faktor_aktiv=zwei_faktor.aktiv(ziel),
                 immer_bearbeiten=rechte.sieht_alles_im_teamplaner(ziel), ab_planer=ziel.hat_mindestens(Rolle.PLANER),
                 freigaben=[g for g in _freigaben_der_person(ziel) if darf_freigaben[g["art"]]])


@require_POST
@erfordert(rechte.darf_konten_verwalten)
def person_freigabe(request, pk):
    """Eine Freigabe auf der Seite der Person ändern, sofort gespeichert."""
    from .einstellungen import gespeichert
    from .freigaben import arten, setzen

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
    if not rechte.darf_konto_bearbeiten(konto, ziel):
        raise PermissionDenied
    if aktion == "link":
        from zusammenarbeit.mail import reset_senden

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
        request.session["passwort_link"] = link
        protokollieren(konto, "konto", ziel.pk, "link_erzeugt", {"person": ziel.person})
        _einladung_mitteilen(request, ziel, link)
    elif aktion == "deaktivieren":
        if ziel.pk == konto.pk:
            messages.error(request, _("Sie können Ihr eigenes Konto nicht deaktivieren."))
        else:
            ziel.person.archivieren()
            protokollieren(konto, "konto", ziel.pk, "deaktiviert", {"person": ziel.person})
            messages.success(request, _("Konto deaktiviert. Aufgaben und Einteilungen bleiben erhalten."))
    elif aktion == "reaktivieren":
        ziel.person.wiederherstellen()
        if ziel.daten_entfernt_am:  # bei einer späteren Deaktivierung wieder nach Frist bereinigen
            ziel.daten_entfernt_am = None
            ziel.save(update_fields=["daten_entfernt_am"])
        protokollieren(konto, "konto", ziel.pk, "reaktiviert", {"person": ziel.person})
        messages.success(request, _("Konto reaktiviert."))
    elif aktion == "foto_entfernen":
        fotos.entfernen(ziel.person)
        protokollieren(konto, "konto", ziel.pk, "foto_entfernt", {"person": ziel.person})
        messages.success(request, _("Foto entfernt."))
    elif aktion == "zwei_faktor_zuruecksetzen":
        from zusammenarbeit.mail import sicherheitshinweis

        zwei_faktor.zuruecksetzen(ziel)
        protokollieren(konto, "konto", ziel.pk, "zwei_faktor_zurueckgesetzt", {"person": ziel.person})
        sicherheitshinweis(ziel, "zwei_faktor_zurueckgesetzt")
        messages.success(request, _("Zwei-Faktor-Anmeldung zurückgesetzt.") + " " + (
            _("Bei der nächsten Anmeldung wird sie neu eingerichtet.") if zwei_faktor.pflicht(ziel) else ""))
    else:
        raise PermissionDenied
    return redirect("einst_person", pk=pk)


# ---------- Profilfoto ----------

@require_POST
@login_required
def konto_foto(request):
    """Eigenes Foto hochladen oder entfernen; ohne Foto zeigt der Avatar die Initialen."""
    person = request.user.person
    if "entfernen" in request.POST:
        fotos.entfernen(person)
        messages.success(request, _("Foto entfernt."))
    elif request.FILES.get("foto"):
        try:
            fotos.setzen(person, request.FILES["foto"])
            messages.success(request, _("Foto gespeichert."))
        except fotos.FotoFehler as fehler:
            messages.error(request, str(fehler))
    return redirect("einst_profil")


@login_required
def person_foto(request, pk):
    """Fotos sind personenbezogen und nur für angemeldete Personen abrufbar."""
    person = get_object_or_404(Person, pk=pk)
    if not person.foto:
        raise Http404
    try:
        datei = person.foto.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    antwort = FileResponse(datei, content_type="image/jpeg")
    antwort["Cache-Control"] = "private, max-age=604800"
    antwort["X-Content-Type-Options"] = "nosniff"
    return antwort


# ---------- Platzhalter ----------

@erfordert(rechte.darf_platzhalter_verwalten)
def platzhalter_neu(request):
    """„+ Platzhalter“."""
    from .einstellungen import seite

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
    from .einstellungen import seite

    person = get_object_or_404(Person.objects.platzhalter().select_related("bereich"), pk=pk)
    alt = {"anzeigename": person.anzeigename, "notiz": person.notiz}
    form = PlatzhalterForm(request.POST or None if umwandeln is None else None, instance=person)
    form.fields["bereich"].disabled = True  # Bereich ändert sich nicht
    if umwandeln is None and rechte.darf_konten_verwalten(request.user):
        umwandeln = UmwandelnForm(konto=request.user)
    if request.method == "POST" and form.is_bound and form.is_valid():
        form.save()
        protokollieren(request.user, "platzhalter", person.pk, "geaendert",
                       aenderungen(alt, {"anzeigename": person.anzeigename, "notiz": person.notiz}))
        messages.success(request, _("Gespeichert."))
        return redirect("einst_person", pk=pk)
    eingeteilt_bis = person.einteilungen.aggregate(m=Max("bis"))["m"]
    return seite(request, "kern/platzhalter_bearbeiten.html", "personen",
                 person=person, form=form, umwandeln=umwandeln, eingeteilt_bis=eingeteilt_bis)


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
    protokollieren(request.user, "konto", neu.pk, "aus_platzhalter", {"person": person, "rolle": neu.rolle})
    link = passwort_link(neu)
    request.session["passwort_link"] = link
    messages.success(request, _("„%(name)s“ hat jetzt ein Konto.") % {"name": person.anzeigename})
    _einladung_mitteilen(request, neu, link)
    return redirect("einst_person", pk=neu.pk)


@login_required
def personen_vorschlaege(request):
    """Vorschläge für @-Erwähnung und Auswahllisten: nur auswählbare Personen (ohne Systemkonten)."""
    suche = request.GET.get("q", "").strip()
    personen = Person.objects.auswaehlbar().select_related("konto")
    if suche:
        personen = personen.filter(anzeigename__icontains=suche)
    return JsonResponse({"personen": [
        {"id": p.pk, "name": p.anzeigename, "initialen": p.initialen, "platzhalter": p.ist_platzhalter,
         "foto": p.foto_url}
        for p in personen[:8]
    ]})


# ---------- Protokoll ----------

def erledigt_eintraege():
    """Protokolleinträge, in denen eine Aufgabe auf einen erledigten Status gesetzt wurde."""
    erledigt_ids = list(Status.objects.filter(ist_erledigt=True).values_list("id", flat=True))
    return Protokolleintrag.objects.filter(objekt_typ="aufgabe", aktion="geaendert",
                                           daten__status__1__id__in=erledigt_ids)


@erfordert(rechte.darf_erledigte_sehen)
def protokoll(request):
    from projekte.models import Aufgabe

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
    import shutil

    from notizen.models import NotizAnhang
    from zusammenarbeit.models import Anhang

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

    from .einstellungen import seite

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
    from django.utils.http import url_has_allowed_host_and_scheme

    from zusammenarbeit.models import Anhang

    anhang = get_object_or_404(Anhang, pk=pk)
    protokollieren(request.user, "anhang", anhang.pk, "geloescht", {"name": anhang.dateiname},
                   aufgabe_id=anhang.aufgabe_id)
    anhang.datei.delete(save=False)
    anhang.delete()
    messages.success(request, _("„%(name)s“ gelöscht.") % {"name": anhang.dateiname})
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        weiter = reverse("einst_speicherplatz")
    return redirect(weiter)


@erfordert(rechte.darf_systemeinstellungen)
def einstellungen_version(request):
    """Hinweis auf eine neuere Version – per HTMX nachgeladen, damit die Seite nicht auf die Registry wartet."""
    stand, neu = version.update_stand()
    return render(request, "kern/version_hinweis.html", {"stand": stand, "neu": neu})


# ---------- Posteingang ----------

@login_required
def posteingang(request):
    from zusammenarbeit.models import Benachrichtigung

    eintraege = Benachrichtigung.objects.filter(empfaenger=request.user.person).select_related("aufgabe", "ausloeser")
    if request.method == "POST":
        eintraege.filter(gelesen_am__isnull=True).update(gelesen_am=timezone.now())
        return redirect("posteingang")
    return render(request, "kern/posteingang.html", {"eintraege": eintraege[:200], "aktiv": "posteingang"})


@never_cache
@login_required
def sitzung_frist(request):
    """Restzeit der Admin-Sitzung: GET als Hintergrundabfrage prüft nur (die Frist steht in der Kopfzeile
    ``X-Sitzung-Ablauf``, kern.middleware.SitzungMiddleware), POST zählt als Aktivität und setzt sie zurück."""
    if request.method not in ("GET", "POST"):
        return HttpResponse(status=405)
    return HttpResponse(status=204)


@login_required
def posteingang_feld(request):
    """Mitteilungszentrale im Kopf (HTMX): die letzten Benachrichtigungen; POST markiert alle als gelesen."""
    from zusammenarbeit.models import Benachrichtigung

    eintraege = Benachrichtigung.objects.filter(empfaenger=request.user.person).select_related("aufgabe", "ausloeser")
    if request.method == "POST":
        eintraege.filter(gelesen_am__isnull=True).update(gelesen_am=timezone.now())
    ungelesen = eintraege.filter(gelesen_am__isnull=True).count()
    return render(request, "kern/_posteingang_feld.html", {"eintraege": eintraege[:15], "ungelesen": ungelesen})


@login_required
def posteingang_zahl(request):
    """Zahl der ungelesenen Benachrichtigungen am Glockensymbol (wird minütlich nachgeladen)."""
    from zusammenarbeit.models import Benachrichtigung

    ungelesen = Benachrichtigung.objects.filter(empfaenger=request.user.person, gelesen_am__isnull=True).count()
    return render(request, "kern/_ungelesen.html", {"ungelesen": ungelesen})


@login_required
def benachrichtigung_oeffnen(request, pk):
    from zusammenarbeit.models import Benachrichtigung, Benachrichtigungsart

    eintrag = get_object_or_404(Benachrichtigung, pk=pk, empfaenger=request.user.person)
    if eintrag.gelesen_am is None:
        eintrag.gelesen_am = timezone.now()
        eintrag.save(update_fields=["gelesen_am"])
    if eintrag.aufgabe_id:
        return redirect(eintrag.aufgabe.get_absolute_url())
    if eintrag.art == Benachrichtigungsart.LIEFERTERMIN:
        return redirect("bestellungen")
    return redirect("posteingang")


def gesund(request):
    """Für Docker-Healthcheck und Monitoring: Anwendung und Datenbank erreichbar?"""
    from django.db import connection

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        return JsonResponse({"status": "ok"})
    except Exception:  # noqa: BLE001
        return JsonResponse({"status": "fehler"}, status=503)
