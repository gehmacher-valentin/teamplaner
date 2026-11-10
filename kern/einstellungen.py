"""Einstellungsbereich: ein Rahmen mit Unternavigation für persönliche Einstellungen, Team und System.

Jede Seite steht nur in der Unternavigation, wenn das Konto sie öffnen darf; geprüft wird zusätzlich
in jeder View. Kleine Einstellungen speichern sofort per HTMX, Rückmeldung als Toast.
"""

import json

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, ProtectedError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import translation
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy, ngettext
from django.views.decorators.http import require_POST

from . import rechte, zwei_faktor
from .hilfen import erfordert
from .models import Systemeinstellungen
from .protokoll import aenderungen, protokollieren


def _darf_personen(konto):
    return rechte.darf_platzhalter_verwalten(konto) or rechte.darf_konten_verwalten(konto)


def _darf_ansichten(konto):
    from gantt import rechte as gantt_rechte

    return rechte.darf_ansichten_verwalten(konto) or gantt_rechte.darf_verwalten(konto)


def _alle(konto):
    return True


# (Gruppe, Kennung, Beschriftung, URL-Name, Recht); die Reihenfolge ist die der Unternavigation
SEITEN = [
    ("persoenlich", "profil", gettext_lazy("Profil"), "einst_profil", _alle),
    ("persoenlich", "sicherheit", gettext_lazy("Anmeldung & Sicherheit"), "einst_sicherheit", _alle),
    ("persoenlich", "benachrichtigungen", gettext_lazy("Benachrichtigungen"), "einst_benachrichtigungen", _alle),
    ("persoenlich", "darstellung", gettext_lazy("Darstellung"), "einst_darstellung", _alle),
    ("team", "personen", gettext_lazy("Personen"), "einst_personen", _darf_personen),
    ("team", "ansichten", gettext_lazy("Ansichten & Freigaben"), "einst_ansichten", _darf_ansichten),
    ("team", "rollen", gettext_lazy("Rollen & Rechte"), "einst_rollen", rechte.darf_konten_verwalten),
    ("system", "allgemein", gettext_lazy("Allgemein"), "einst_allgemein", rechte.darf_systemeinstellungen),
    ("system", "listen", gettext_lazy("Listen"), "einst_listen", rechte.darf_systemeinstellungen),
    ("system", "kalender", gettext_lazy("Kalender"), "einst_kalender", rechte.darf_systemeinstellungen),
    ("system", "speicherplatz", gettext_lazy("Speicherplatz"), "einst_speicherplatz", rechte.darf_systemeinstellungen),
    ("ueber", "ueber", gettext_lazy("Über"), "einst_ueber", _alle),
]
GRUPPEN = {"persoenlich": gettext_lazy("Persönlich"), "team": gettext_lazy("Team"), "system": gettext_lazy("System"),
           "ueber": ""}


def unternavigation(konto, aktiv):
    """Gruppen mit den erlaubten Seiten; „Über“ steht ohne Titel unter einer Trennlinie am Ende."""
    gruppen = []
    for gruppe, kennung, beschriftung, url_name, recht in SEITEN:
        if not recht(konto):
            continue
        if not gruppen or gruppen[-1]["kennung"] != gruppe:
            gruppen.append({"kennung": gruppe, "titel": GRUPPEN[gruppe], "eintraege": []})
        gruppen[-1]["eintraege"].append({"kennung": kennung, "beschriftung": beschriftung,
                                         "url": reverse(url_name), "aktiv": kennung == aktiv})
    return gruppen


def verwaltungsseite(konto):
    """Ziel von „Einstellungen“ unter „Verwaltung“: die erste erlaubte Team- oder System-Seite."""
    for gruppe, _kennung, _beschriftung, url_name, recht in SEITEN:
        if gruppe in {"team", "system"} and recht(konto):
            return reverse(url_name)
    return None


def seite(request, vorlage, aktiv, **kontext):
    """Seite im Einstellungsrahmen; Team- und System-Seiten markieren „Einstellungen“ unter „Verwaltung“."""
    gruppe = next(g for g, k, *_rest in SEITEN if k == aktiv)
    return render(request, vorlage, {
        "einst_aktiv": aktiv, "aktiv": "einstellungen" if gruppe in {"team", "system"} else "konto", **kontext,
    })


def gespeichert(request, antwort=None):
    """Antwort auf das sofortige Speichern: nichts austauschen, „Gespeichert“ als Toast."""
    messages.success(request, _("Gespeichert"))
    return antwort or HttpResponse(status=204)


@login_required
def start(request):
    return redirect("einst_profil")


# ---------- Persönlich ----------

@login_required
def profil(request):
    return seite(request, "kern/einst_profil.html", "profil")


def zwei_faktor_kontext(konto):
    return {"eingerichtet": zwei_faktor.aktiv(konto), "pflicht": zwei_faktor.pflicht(konto),
            "seit": konto.totp_seit, "uebrig": zwei_faktor.ersatzcodes_uebrig(konto)}


@login_required
def benachrichtigungen(request):
    from zusammenarbeit.mail import KATEGORIEN, mail_aktiv, mail_eingerichtet

    werte = request.user.mail_einstellungen or {}
    kategorien = [
        {"schluessel": schluessel, "titel": titel,
         "ereignisse": [{"art": str(art), "beschreibung": beschreibung, "an": bool(werte.get(str(art)))}
                        for art, beschreibung in arten]}
        for schluessel, titel, arten in KATEGORIEN
    ]
    for k in kategorien:
        k["alle"] = all(e["an"] for e in k["ereignisse"])
        k["teilweise"] = not k["alle"] and any(e["an"] for e in k["ereignisse"])
    return seite(request, "kern/einst_benachrichtigungen.html", "benachrichtigungen",
                 kategorien=kategorien, mail_aktiv=mail_aktiv(), kein_smtp=not mail_eingerichtet())


@require_POST
@login_required
def benachrichtigung_speichern(request):
    """Ein Ereignis oder eine ganze Kategorie an/aus – immer nur für das eigene Konto.
    Ohne Mailversand gibt es nichts einzustellen; gespeicherte Werte bleiben für später erhalten."""
    from zusammenarbeit.mail import KATEGORIEN, mail_aktiv

    if not mail_aktiv():
        return HttpResponse(status=400)
    konto = request.user
    an = request.POST.get("an") == "1"
    arten = {str(art) for _s, _t, liste in KATEGORIEN for art, _b in liste}
    kategorie = request.POST.get("kategorie")
    if kategorie:
        betroffen = next(([str(a) for a, _b in liste] for s, _t, liste in KATEGORIEN if s == kategorie), None)
    else:
        betroffen = [request.POST.get("art")] if request.POST.get("art") in arten else None
    if not betroffen:
        return HttpResponse(status=400)
    werte = dict(konto.mail_einstellungen or {})
    for art in betroffen:
        if an:
            werte[art] = True
        else:
            werte.pop(art, None)
    konto.mail_einstellungen = werte
    konto.save(update_fields=["mail_einstellungen"])
    return gespeichert(request)


@login_required
def darstellung(request):
    return seite(request, "kern/einst_darstellung.html", "darstellung", sprachen=settings.LANGUAGES)


DARSTELLUNG_SCHALTER = {"feier_animation", "gantt_unteraufgaben_offen"}


@require_POST
@login_required
def darstellung_speichern(request):
    """Sprache, Feieranimation, Unteraufgaben im Gantt – sofort, nur das eigene Konto."""
    konto = request.user
    feld = request.POST.get("feld")
    if feld == "sprache":
        sprache = request.POST.get("wert")
        if sprache not in dict(settings.LANGUAGES):
            return HttpResponse(status=400)
        konto.sprache = sprache
        konto.save(update_fields=["sprache"])
        translation.activate(sprache)  # Meldung schon in der neuen Sprache
        messages.success(request, _("Gespeichert"))
        antwort = HttpResponse(status=204)
        antwort["HX-Refresh"] = "true"  # die ganze Oberfläche gleich in der neuen Sprache
        return antwort
    if feld not in DARSTELLUNG_SCHALTER:
        return HttpResponse(status=400)
    setattr(konto, feld, request.POST.get("an") == "1")
    konto.save(update_fields=[feld])
    return gespeichert(request)


# ---------- System ----------

@erfordert(rechte.darf_systemeinstellungen)
def allgemein(request):
    """Globale Einstellungen, alle speichern sofort: Organisationsname, Tagesfreigabe, E-Mail-Versand."""
    from zusammenarbeit.mail import mail_aktiv, mail_eingerichtet, wartende_verwerfen

    objekt = Systemeinstellungen.laden()
    if request.method == "POST":
        feld = request.POST.get("feld")
        if feld in {"organisation", "freigabe_name"}:
            wert = " ".join(request.POST.get("wert", "").split())
            if len(wert) > Systemeinstellungen._meta.get_field(feld).max_length:
                return HttpResponse(status=400)
        elif feld == "freigabe_zeile" or (feld == "mail_versand" and mail_eingerichtet()):
            wert = request.POST.get("an") == "1"
        else:
            return HttpResponse(status=400)
        alt = {feld: getattr(objekt, feld)}
        with transaction.atomic():
            setattr(objekt, feld, wert)
            objekt.save(update_fields=[feld])
            if feld == "mail_versand" and not wert:
                wartende_verwerfen()
            diff = aenderungen(alt, {feld: wert})
            if diff:
                protokollieren(request.user, "einstellungen", objekt.pk, "geaendert", diff)
        return gespeichert(request)
    return seite(request, "kern/einst_allgemein.html", "allgemein", einstellungen=objekt,
                 freigabestufen=_liste_kontext("freigabestufe"),
                 mail_aktiv=mail_aktiv(), kein_smtp=not mail_eingerichtet())


@login_required
def ueber(request):
    return seite(request, "kern/einst_ueber.html", "ueber", version=settings.TEAMPLANER_VERSION,
                 quellcode=settings.TEAMPLANER_QUELLCODE)


@erfordert(rechte.darf_konten_verwalten)
def rollen(request):
    from .models import Rolle
    from .views import RECHTEMATRIX

    return seite(request, "kern/einst_rollen.html", "rollen", rechtematrix=RECHTEMATRIX, rollen=list(Rolle))


# ---------- Listen: Status, Gewerke, Projekt-Tags, Bereiche, Freigabestufen ----------

def _listen():
    from planung.models import FreigabeStufe
    from projekte.models import Aufgabe, Status, Tag

    from .forms import BereichForm, FreigabeStufeForm, GewerkForm, StatusForm, TagForm
    from .models import Bereich, Gewerk

    def status_verwendung():
        anzahl = dict(Aufgabe.objects.values_list("status").annotate(n=Count("id")).values_list("status", "n"))
        return lambda obj: anzahl.get(obj.pk, 0)

    return {
        # Art: Modell, Formular, Titel, ziehbar, Verwendung (Zähler), Text zur Verwendung, Löschen gesperrt
        "status": (Status, StatusForm, gettext_lazy("Status"), True, status_verwendung,
                   lambda n: ngettext("%(n)s Aufgabe", "%(n)s Aufgaben", n) % {"n": n}, True),
        "gewerk": (Gewerk, GewerkForm, gettext_lazy("Gewerke"), False,
                   lambda: (lambda obj: obj.personen.count()),
                   lambda n: ngettext("%(n)s Person", "%(n)s Personen", n) % {"n": n}, False),
        "tag": (Tag, TagForm, gettext_lazy("Projekt-Tags"), False,
                lambda: (lambda obj: obj.projekte.count()),
                lambda n: ngettext("%(n)s Projekt", "%(n)s Projekte", n) % {"n": n}, False),
        "bereich": (Bereich, BereichForm, gettext_lazy("Bereiche"), True,
                    lambda: (lambda obj: obj.personen.count()),
                    lambda n: ngettext("%(n)s Person", "%(n)s Personen", n) % {"n": n}, True),
        "freigabestufe": (FreigabeStufe, FreigabeStufeForm, gettext_lazy("Freigabestufen"), True,
                          lambda: (lambda obj: obj.tage.count()),
                          lambda n: ngettext("%(n)s Tag", "%(n)s Tage", n) % {"n": n}, True),
    }


def _frage(art, objekt, anzahl):
    """Rückfrage beim Löschen mit der Verwendung."""
    namen = {"status": _("Status „%(name)s“ löschen?"), "gewerk": _("Gewerk „%(name)s“ löschen?"),
             "tag": _("Tag „%(name)s“ löschen?"), "bereich": _("Bereich „%(name)s“ löschen?"),
             "freigabestufe": _("Freigabestufe „%(name)s“ löschen?")}
    text = namen[art] % {"name": objekt}
    if anzahl and art == "gewerk":
        text += " " + ngettext("Es ist %(n)s Person zugeordnet.", "Es ist %(n)s Personen zugeordnet.", anzahl) % {"n": anzahl}
    elif anzahl and art == "tag":
        text += " " + ngettext("Er hängt an %(n)s Projekt.", "Er hängt an %(n)s Projekten.", anzahl) % {"n": anzahl}
    return text


def _liste_kontext(art, neu_form=None, fokus=False):
    modell, formklasse, titel, ziehbar, verwendung, verwendung_text, gesperrt = _listen()[art]
    zaehlen = verwendung()
    eintraege = []
    for obj in modell.objects.all():
        anzahl = zaehlen(obj)
        eintraege.append({"objekt": obj, "anzahl": anzahl, "verwendung": verwendung_text(anzahl),
                          "gesperrt": gesperrt and anzahl > 0})
    return {"art": art, "titel": titel, "ziehbar": ziehbar, "eintraege": eintraege,
            "neu_form": neu_form or formklasse(prefix="neu"), "fokus": fokus, "farben": _farben(art)}


def _farben(art):
    from projekte.models import Statusfarbe

    return list(Statusfarbe.choices) if art == "status" else []


def _art_oder_404(art):
    if art not in _listen():
        raise Http404
    return _listen()[art]


@erfordert(rechte.darf_systemeinstellungen)
def listen(request):
    return seite(request, "kern/einst_listen.html", "listen", listen=[_liste_kontext(art) for art in _listen() if art != "freigabestufe"])


def _eintrag_kontext(art, objekt, **extra):
    kontext = _liste_kontext(art)
    eintrag = next(e for e in kontext["eintraege"] if e["objekt"].pk == objekt.pk)
    return {"art": art, "e": eintrag, "ziehbar": kontext["ziehbar"], "farben": kontext["farben"], **extra}


@erfordert(rechte.darf_systemeinstellungen)
def liste_eintrag(request, art, pk):
    """Eine Zeile anzeigen (GET ?ansicht=zeile|bearbeiten|frage) oder speichern (POST, sofort)."""
    modell, formklasse, *_rest = _art_oder_404(art)
    objekt = get_object_or_404(modell, pk=pk)
    if request.method == "POST":
        alt = str(objekt)
        form = formklasse(request.POST, instance=objekt, prefix=f"e{pk}")
        if not form.is_valid():
            objekt.refresh_from_db()
            antwort = render(request, "kern/_listen_bearbeiten.html", _eintrag_kontext(art, objekt, form=form))
            antwort["HX-Retarget"] = f"#eintrag-{art}-{pk}"
            antwort["HX-Reswap"] = "outerHTML"
            antwort["X-Fehler"] = "1"
            return antwort
        if form.has_changed():
            gespeichert_obj = form.save()
            daten = {"name": str(gespeichert_obj)}
            if alt != str(gespeichert_obj):
                daten["vorher"] = alt
            protokollieren(request.user, art, pk, "geaendert", daten)
            return gespeichert(request)
        return HttpResponse(status=204)
    ansicht = request.GET.get("ansicht")
    if ansicht == "bearbeiten":
        return render(request, "kern/_listen_bearbeiten.html",
                      _eintrag_kontext(art, objekt, form=formklasse(instance=objekt, prefix=f"e{pk}")))
    kontext = _eintrag_kontext(art, objekt)
    if ansicht == "frage" and not kontext["e"]["gesperrt"]:
        kontext["frage"] = _frage(art, objekt, kontext["e"]["anzahl"])
    return render(request, "kern/_listen_zeile.html", kontext)


@require_POST
@erfordert(rechte.darf_systemeinstellungen)
def liste_neu(request, art):
    _modell, formklasse, *_rest = _art_oder_404(art)
    form = formklasse(request.POST, prefix="neu")
    if form.is_valid():
        objekt = form.save(commit=False)
        if hasattr(objekt, "sortierung"):  # neue Einträge ans Ende der Reihenfolge
            letzte = type(objekt).objects.aggregate(m=Max("sortierung"))["m"] or 0
            objekt.sortierung = letzte + 10
        objekt.save()
        protokollieren(request.user, art, objekt.pk, "angelegt", {"name": str(objekt)})
        return gespeichert(request, render(request, "kern/_listen.html", {"l": _liste_kontext(art, fokus=True)}))
    antwort = render(request, "kern/_listen.html", {"l": _liste_kontext(art, neu_form=form, fokus=True)})
    antwort["X-Fehler"] = "1"
    return antwort


@require_POST
@erfordert(rechte.darf_systemeinstellungen)
def liste_loeschen(request, art, pk):
    modell, *_rest = _art_oder_404(art)
    objekt = get_object_or_404(modell, pk=pk)
    if _eintrag_kontext(art, objekt)["e"]["gesperrt"]:
        messages.error(request, _("„%(name)s“ wird noch verwendet und kann nicht gelöscht werden.") % {"name": objekt})
    else:
        try:
            with transaction.atomic():
                objekt.delete()
            protokollieren(request.user, art, pk, "geloescht", {"name": str(objekt)})
            messages.success(request, _("„%(name)s“ gelöscht.") % {"name": objekt})
        except (ProtectedError, IntegrityError):
            messages.error(request, _("„%(name)s“ wird noch verwendet und kann nicht gelöscht werden.") % {"name": objekt})
    return render(request, "kern/_listen.html", {"l": _liste_kontext(art)})


@require_POST
@erfordert(rechte.darf_systemeinstellungen)
def liste_sortieren(request, art):
    """Neue Reihenfolge von Status oder Bereichen (gezogen bzw. per Pfeiltasten); wirkt überall."""
    modell, _formklasse, _titel, ziehbar, *_rest = _art_oder_404(art)
    try:
        ids = [int(i) for i in json.loads(request.body).get("ids", [])]
    except (ValueError, TypeError, AttributeError):
        return HttpResponse(status=400)
    if not ziehbar or sorted(ids) != sorted(modell.objects.values_list("pk", flat=True)):
        return HttpResponse(status=400)
    with transaction.atomic():
        for i, pk in enumerate(ids):
            modell.objects.filter(pk=pk).update(sortierung=(i + 1) * 10)
    protokollieren(request.user, art, None, "sortiert", {"reihenfolge": [str(o) for o in modell.objects.all()]})
    return gespeichert(request)


# ---------- Ansichten & Freigaben ----------

@login_required
def ansichten(request):
    """Teamplaner- und Gantt-Ansichten auf einer Seite mit Reitern, je nur mit dem passenden Recht."""
    from . import freigaben

    erlaubt = {art: werte for art, werte in freigaben.arten().items() if werte[3](request.user)}
    if not erlaubt:
        raise PermissionDenied
    art = request.GET.get("art") if request.GET.get("art") in erlaubt else next(iter(erlaubt))
    ansicht_modell, freigabe_modell, _typ, _recht, url_name = erlaubt[art]
    vorrang = {"teamplaner": ("bereiche", "personen"), "gantt": ("projekte",)}[art]
    liste = list(ansicht_modell.objects.prefetch_related(*vorrang, "freigaben__konto__person"))
    for a in liste:
        a.freigegeben = [f for f in a.freigaben.all() if f.recht in (freigaben.SEHEN, freigaben.BEARBEITEN)]
        a.zusammenfassung = freigaben.zusammenfassung(f.recht for f in a.freigegeben)
        a.inhalt = ([b.name for b in a.bereiche.all()] + [p.anzeigename for p in a.personen.all()]
                    if art == "teamplaner" else [p.name for p in a.projekte.all()])
    reiter = [{"art": k, "titel": _("Teamplaner") if k == "teamplaner" else _("Gantt-Diagramm"),
               "anzahl": werte[0].objects.count(), "aktiv": k == art} for k, werte in erlaubt.items()]
    neu_url = reverse("ansicht_neu" if art == "teamplaner" else "gantt_ansicht_neu")
    return seite(request, "kern/einst_ansichten.html", "ansichten", art=art, reiter=reiter, ansichten=liste,
                 url_name=url_name, neu_url=neu_url)


@require_POST
@login_required
def ansichten_sortieren(request, art):
    """Reihenfolge der Ansichten per Ziehen statt über eine Zahl."""
    from . import freigaben

    if art not in freigaben.arten():
        raise Http404
    ansicht_modell, _f, typ, recht, _u = freigaben.arten()[art]
    if not recht(request.user):
        raise PermissionDenied
    try:
        ids = [int(i) for i in json.loads(request.body).get("ids", [])]
    except (ValueError, TypeError, AttributeError):
        return HttpResponse(status=400)
    if sorted(ids) != sorted(ansicht_modell.objects.values_list("pk", flat=True)):
        return HttpResponse(status=400)
    with transaction.atomic():
        for i, pk in enumerate(ids):
            ansicht_modell.objects.filter(pk=pk).update(sortierung=(i + 1) * 10)
    protokollieren(request.user, typ, None, "sortiert", {"reihenfolge": [a.name for a in ansicht_modell.objects.all()]})
    return gespeichert(request)


# ---------- Kalender: freie Tage als Zeitraum, mit den Feiertagen in einer Jahresliste ----------

HOECHSTENS_TAGE = 366


def _jahresliste(heute):
    from planung.kalender import gesetzliche_feiertage, zeitraeume
    from planung.models import FreierTag

    freie = list(FreierTag.objects.all())
    alle = {heute.year, heute.year + 1} | {t.datum.year for t in freie}
    # Laufendes und nächstes Jahr zuerst, dann spätere, dann vergangene (neueste zuerst)
    jahre = sorted(j for j in alle if j >= heute.year) + sorted((j for j in alle if j < heute.year), reverse=True)
    liste = []
    for jahr in jahre:
        zeilen = [{"art": "gesetzlich", "von": d, "bis": d, "bezeichnung": name}
                  for d, name in gesetzliche_feiertage(jahr).items()]
        eigene = zeitraeume([t for t in freie if t.datum.year == jahr])
        zeilen += [{"art": "frei", **z} for z in eigene]
        zeilen.sort(key=lambda z: (z["von"], z["art"] != "gesetzlich"))
        for z in zeilen:
            z["vorbei"] = z["bis"] < heute
        liste.append({"jahr": jahr, "zeilen": zeilen, "offen": jahr >= heute.year,
                      "gesetzlich": len(gesetzliche_feiertage(jahr)), "frei": sum(len(z["tage"]) for z in eigene)})
    return liste


@erfordert(rechte.darf_systemeinstellungen)
def kalender(request):
    """Freie Tage eintragen: von, bis (leer = ein Tag), Bezeichnung."""
    from datetime import date

    from django.utils import timezone

    from planung.kalender import neue_freie_tage
    from planung.models import FreierTag

    eingabe = {"von": "", "bis": "", "bezeichnung": ""}
    fehler = None
    if request.method == "POST":
        eingabe = {k: request.POST.get(k, "").strip() for k in eingabe}
        try:
            von = date.fromisoformat(eingabe["von"])
            bis = date.fromisoformat(eingabe["bis"]) if eingabe["bis"] else von
        except ValueError:
            von = bis = None
        if von is None:
            fehler = _("Bitte ein gültiges Datum eingeben.")
        elif bis < von:
            fehler = _("„Bis“ liegt vor „Von“.")
        elif (bis - von).days >= HOECHSTENS_TAGE:
            fehler = _("Höchstens ein Jahr auf einmal.")
        elif not eingabe["bezeichnung"]:
            fehler = _("Bitte eine Bezeichnung eingeben.")
        if fehler is None:
            vorhanden = set(FreierTag.objects.filter(datum__range=(von, bis)).values_list("datum", flat=True))
            neu = neue_freie_tage(von, bis, vorhanden)
            FreierTag.objects.bulk_create(FreierTag(datum=d, bezeichnung=eingabe["bezeichnung"][:100]) for d in neu)
            if neu:
                protokollieren(request.user, "freiertag", None, "angelegt", {
                    "von": von, "bis": bis, "bezeichnung": eingabe["bezeichnung"], "tage": len(neu)})
                messages.success(request, ngettext("%(n)s freier Tag eingetragen.", "%(n)s freie Tage eingetragen.",
                                                   len(neu)) % {"n": len(neu)})
            else:
                messages.info(request, _("Keine neuen Tage – im Zeitraum ist schon alles frei."))
            return redirect("einst_kalender")
    return seite(request, "kern/einst_kalender.html", "kalender", jahre=_jahresliste(timezone.localdate()),
                 eingabe=eingabe, fehler=fehler)


@require_POST
@erfordert(rechte.darf_systemeinstellungen)
def kalender_zeitraum(request):
    """Einen Zeitraum als Ganzes umbenennen oder löschen."""
    from datetime import date

    from planung.models import FreierTag

    try:
        von, bis = date.fromisoformat(request.POST.get("von", "")), date.fromisoformat(request.POST.get("bis", ""))
    except ValueError:
        return HttpResponse(status=400)
    tage = FreierTag.objects.filter(datum__range=(von, bis), bezeichnung=request.POST.get("alt", ""))
    anzahl = tage.count()
    if not anzahl:
        return redirect("einst_kalender")
    if request.POST.get("aktion") == "loeschen":
        tage.delete()
        protokollieren(request.user, "freiertag", None, "geloescht",
                       {"von": von, "bis": bis, "bezeichnung": request.POST.get("alt"), "tage": anzahl})
        messages.success(request, ngettext("%(n)s freier Tag gelöscht.", "%(n)s freie Tage gelöscht.", anzahl) % {"n": anzahl})
    else:
        neu = request.POST.get("bezeichnung", "").strip()[:100]
        if not neu:
            messages.error(request, _("Bitte eine Bezeichnung eingeben."))
        else:
            tage.update(bezeichnung=neu)
            protokollieren(request.user, "freiertag", None, "geaendert",
                           {"von": von, "bis": bis, "bezeichnung": [request.POST.get("alt"), neu]})
            messages.success(request, _("Gespeichert."))
    return redirect("einst_kalender")


@require_POST
@erfordert(rechte.darf_systemeinstellungen)
def kalender_tag(request, pk):
    """Einen einzelnen freien Tag aus einem Zeitraum entfernen."""
    from planung.models import FreierTag

    tag = get_object_or_404(FreierTag, pk=pk)
    tag.delete()
    protokollieren(request.user, "freiertag", pk, "geloescht", {"name": str(tag)})
    messages.success(request, _("„%(name)s“ gelöscht.") % {"name": tag})
    return redirect("einst_kalender")
