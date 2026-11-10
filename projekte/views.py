import json
import re
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchRank, SearchVector
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from gantt import dienste as gantt_dienste
from kern import rechte
from kern.hilfen import TEXT_MAX_ZEICHEN, als_zahl, erfordert
from kern.models import Gewerk, Person
from kern.protokoll import protokollieren
from planung import rechte as planungsrechte
from planung.kalender import freie_tage, montag, werktage, zaehlende_tage
from zusammenarbeit.models import Kommentar

from . import dienste, termine
from .ansicht import (
    aufgabe_laden,
    baum,
    block_laden,
    detail_kontext,
    detail_seite_kontext,
    kennzahlen_setzen,
    mit_unterzahlen,
    zeilen_kontext,
    zeilen_laden,
)
from .forms import (
    AbschnittForm,
    ProjektForm,
    SchnellAufgabeForm,
    UnteraufgabeForm,
    tags_speichern,
)
from .models import PRIORITAETEN, UNTERAUFGABEN_EBENEN, Abschnitt, Aufgabe, Projekt, Status, Tag
from .seitenleiste import liste_oob, offene_seitenleiste, seitenleiste_antwort


def _ids(request):
    """Liste von IDs aus dem JSON-Körper ({"ids": [...]}), None bei ungültigen Daten."""
    try:
        daten = json.loads(request.body)
    except ValueError:
        return None
    ids = [als_zahl(i) for i in daten.get("ids", [])] if isinstance(daten, dict) else [None]
    return None if None in ids else ids


def _darf_bearbeiten_oder_403(konto, projekt):
    if not rechte.darf_aufgaben_bearbeiten(konto, projekt):
        raise PermissionDenied


# ---------- Projekte ----------

@login_required
def projekte(request):
    tag_roh = request.GET.get("tag")
    tag_id = als_zahl(tag_roh) if tag_roh else None
    if tag_roh and tag_id is None:
        return HttpResponse(status=400)
    archiv = request.GET.get("archiv") == "1"
    liste = (Projekt.objects.filter(archiviert_am__isnull=not archiv)
             .select_related("projektleitung").prefetch_related("tags")
             .annotate(offen=Count("aufgaben", filter=Q(aufgaben__status__ist_erledigt=False), distinct=True),
                       anzahl_mitglieder=Count("mitglieder", distinct=True))
             .order_by(*Projekt._meta.ordering))  # Meta.ordering gilt bei GROUP BY nicht
    if tag_id:
        liste = liste.filter(tags=tag_id)
    return render(request, "projekte/projekte.html", {
        "projekte": liste, "tags": Tag.objects.all(), "tag_id": tag_id,
        "archiv": archiv, "aktiv": "projekte", "prioritaeten": PRIORITAETEN,
    })


@require_POST
@erfordert(rechte.darf_projekte_verwalten)
def projekt_prioritaet(request, pk):
    """Priorität direkt in der Projektliste wählen (leer = keine); die Liste sortiert danach."""
    projekt = get_object_or_404(Projekt, pk=pk)
    wert = request.POST.get("prioritaet", "")
    neu = int(wert) if wert.isdigit() and int(wert) in dict(PRIORITAETEN) else None
    if neu != projekt.prioritaet:
        alt, projekt.prioritaet = projekt.prioritaet, neu
        projekt.save(update_fields=["prioritaet"])
        protokollieren(request.user, "projekt", projekt.pk, "geaendert",
                       {"name": projekt.name, "prioritaet": [alt, neu]})
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        weiter = reverse("projekte")
    return redirect(weiter)


@erfordert(rechte.darf_projekte_verwalten)
def projekt_anlegen(request):
    form = ProjektForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            projekt = form.save(commit=False)
            projekt.erstellt_von = request.user.person
            projekt.save()
            form.save_m2m()
            tags_speichern(projekt, form.cleaned_data["tags_text"])  # neue Projekte sind leer, ohne Abschnitte
            gantt_dienste.neues_projekt_aufnehmen(projekt)
            protokollieren(request.user, "projekt", projekt.pk, "angelegt", {"name": projekt.name})
        messages.success(request, _("Projekt „%(name)s“ angelegt.") % {"name": projekt.name})
        return redirect(projekt)
    return render(request, "projekte/projekt_formular.html", {"form": form, "aktiv": "projekte", "tags": Tag.objects.all()})


@erfordert(rechte.darf_projekte_verwalten)
def projekt_bearbeiten(request, pk):
    projekt = get_object_or_404(Projekt, pk=pk)
    form = ProjektForm(request.POST or None, instance=projekt)
    if request.method == "POST":
        if "archivieren" in request.POST or "wiederherstellen" in request.POST:
            projekt.archiviert_am = timezone.now() if "archivieren" in request.POST else None
            projekt.save(update_fields=["archiviert_am"])
            protokollieren(request.user, "projekt", projekt.pk,
                           "archiviert" if projekt.archiviert_am else "wiederhergestellt", {"name": projekt.name})
            messages.success(request, _("Projekt archiviert.") if projekt.archiviert_am else _("Projekt wiederhergestellt."))
            return redirect(projekt)
        if form.is_valid():
            form.save()
            protokollieren(request.user, "projekt", projekt.pk, "geaendert", {"name": projekt.name})
            messages.success(request, _("Gespeichert."))
            return redirect(projekt)
    return render(request, "projekte/projekt_formular.html", {
        "form": form, "projekt": projekt, "aktiv": "projekte", "aktives_projekt": projekt.pk, "tags": Tag.objects.all(),
    })


SORTIERUNGEN = {
    "manuell": ["sortierung", "id"],
    "faellig": ["faellig_am", "sortierung"],
    "titel": ["titel"],
    "status": ["status__sortierung", "sortierung"],
}


@login_required
def projekt(request, pk):
    projekt = get_object_or_404(Projekt.objects.select_related("projektleitung").prefetch_related("tags", "mitglieder__konto"), pk=pk)
    g = request.GET
    filter_status = g.get("status", "offen")
    sortierung = g.get("sort", "manuell") if g.get("sort") in SORTIERUNGEN else "manuell"
    aufgaben = (mit_unterzahlen(projekt.aufgaben.select_related("verantwortlich__konto", "gewerk", "status", "eltern"))
                .order_by(*SORTIERUNGEN[sortierung]))
    if filter_status == "offen":
        aufgaben = aufgaben.filter(status__ist_erledigt=False)
    elif filter_status == "erledigt":
        aufgaben = aufgaben.filter(status__ist_erledigt=True)
    if g.get("verantwortlich") == "ich":
        aufgaben = aufgaben.filter(verantwortlich=request.user.person)
    elif g.get("verantwortlich", "").isdigit():
        aufgaben = aufgaben.filter(verantwortlich_id=int(g["verantwortlich"]))
    if g.get("gewerk", "").isdigit():
        aufgaben = aufgaben.filter(gewerk_id=int(g["gewerk"]))
    if g.get("q"):
        aufgaben = aufgaben.filter(titel__icontains=g["q"].strip())

    aufgaben = list(aufgaben)
    kennzahlen_setzen(aufgaben)
    oben = baum(aufgaben)
    abschnitte = list(projekt.abschnitte.all())
    for abschnitt in abschnitte:
        abschnitt.liste = [a for a in oben if a.abschnitt_id == abschnitt.pk]
    ohne_abschnitt = [a for a in oben if a.abschnitt_id is None or a.abschnitt_id not in {x.pk for x in abschnitte}]

    kontext = zeilen_kontext(request.user, projekt)
    # Am Filter-Knopf: wie viele Filter vom Standard („Offen“, sonst nichts) abweichen
    anzahl_filter = (filter_status != "offen") + sum(bool(g.get(k)) for k in ("verantwortlich", "gewerk", "q"))
    # ?aufgabe=<id>: Aufgabendetail als Seitenleiste; Aufgaben anderer Projekte zählen nicht
    aktive_aufgabe = projekt.aufgaben.filter(pk=als_zahl(g.get("aufgabe"))).values_list("pk", flat=True).first()
    return render(request, "projekte/projekt.html", {
        "projekt": projekt, "abschnitte": abschnitte, "ohne_abschnitt": ohne_abschnitt,
        "aktive_aufgabe": aktive_aufgabe,
        # Eigener Kontext: das Detail braucht teils gleichnamige Werte (abschnitte) in anderer Form
        "seitenleiste_html": render_to_string(
            "projekte/_seitenleiste_inhalt.html", detail_seite_kontext(request, aufgabe_laden(aktive_aufgabe)),
            request=request) if aktive_aufgabe else "",
        "filter_status": filter_status, "sortierung": sortierung,
        # Ziehen geht auch mit Filtern: ausgeblendete Aufgaben behalten ihren Platz (aufgabe_verschieben)
        "manuell_sortierbar": sortierung == "manuell" and kontext["darf_bearbeiten"],
        "anzahl_filter": anzahl_filter,
        "darf_verwalten": rechte.darf_projekte_verwalten(request.user),
        "darf_planen": planungsrechte.hat_planungsansicht(request.user),
        "aktiv": "projekt", "aktives_projekt": projekt.pk, **kontext,
    })


def _zeile_antwort(request, aufgabe, fehler=None):
    aufgabe = zeilen_laden([aufgabe.pk])[0]
    return render(request, "projekte/_aufgabe_zeile.html", {
        "a": aufgabe, "fehler": fehler, **zeilen_kontext(request.user, aufgabe.projekt),
    })


def _block_antwort(request, aufgabe):
    """Aufgabe mit allen Unteraufgaben (nach „alle mit erledigen“ oder neu angelegt)."""
    aufgabe = block_laden(aufgabe.pk)
    return render(request, "projekte/_aufgabe_block.html", {
        "a": aufgabe, **zeilen_kontext(request.user, aufgabe.projekt),
    })


def _geaendert_melden(antwort, aufgabe, *weitere):
    """Änderung in der Liste: Ist eine dieser Aufgaben in der Seitenleiste offen, lädt sie neu –
    sonst bliebe dort die alte Version stehen und das nächste Speichern meldete einen Konflikt."""
    ids = [i for i in (aufgabe.pk, aufgabe.eltern_id, *weitere) if i]
    antwort["HX-Trigger-After-Settle"] = json.dumps({"aufgabe-geaendert": {"ids": ids}})
    return antwort



# ---------- Abschnitte ----------

@require_POST
@login_required
def abschnitt_anlegen(request, pk):
    projekt = get_object_or_404(Projekt, pk=pk)
    _darf_bearbeiten_oder_403(request.user, projekt)
    form = AbschnittForm(request.POST)
    if form.is_valid():
        letzte = projekt.abschnitte.order_by("-sortierung").first()
        Abschnitt.objects.create(projekt=projekt, name=form.cleaned_data["name"],
                                 sortierung=(letzte.sortierung + 10) if letzte else 0)
    return redirect(projekt)


@require_POST
@login_required
def abschnitt_bearbeiten(request, pk):
    abschnitt = get_object_or_404(Abschnitt.objects.select_related("projekt"), pk=pk)
    _darf_bearbeiten_oder_403(request.user, abschnitt.projekt)
    if "loeschen" in request.POST:
        if abschnitt.aufgaben.exists():
            messages.error(request, _("Der Abschnitt enthält noch Aufgaben und kann nicht gelöscht werden."))
        else:
            abschnitt.delete()
    else:
        form = AbschnittForm(request.POST, instance=abschnitt)
        if form.is_valid():
            form.save()
    return redirect(abschnitt.projekt)


@require_POST
@login_required
def abschnitte_sortieren(request, pk):
    projekt = get_object_or_404(Projekt, pk=pk)
    _darf_bearbeiten_oder_403(request.user, projekt)
    ids = _ids(request)
    if ids is None:
        return HttpResponse(status=400)
    with transaction.atomic():
        for i, abschnitt_id in enumerate(ids):
            projekt.abschnitte.filter(pk=abschnitt_id).update(sortierung=i * 10)
    return HttpResponse(status=204)


# ---------- Aufgaben ----------

@require_POST
@login_required
def aufgabe_anlegen(request, pk, abschnitt_id=None):
    """Neue Aufgabe am Ende eines Abschnitts oder – ohne ``abschnitt_id`` – ohne Abschnitt."""
    projekt = get_object_or_404(Projekt, pk=pk)
    abschnitt = get_object_or_404(projekt.abschnitte, pk=abschnitt_id) if abschnitt_id else None
    _darf_bearbeiten_oder_403(request.user, projekt)
    form = SchnellAufgabeForm(request.POST)
    if not form.is_valid():
        return HttpResponse(status=400)
    aufgabe = dienste.aufgabe_anlegen(request.user, projekt, abschnitt, form.cleaned_data["titel"])
    if request.htmx:
        return _block_antwort(request, aufgabe)
    return redirect(aufgabe)


@require_POST
@login_required
def aufgabe_verschieben(request, pk):
    """Drag-and-drop in der Projektliste: Reihenfolge, Abschnitt und Ebene.

    JSON ``{"id", "eltern": ID|null, "abschnitt": ID|null, "vor": ID|null}`` – mit ``eltern`` wird
    die Aufgabe dessen Unteraufgabe, sonst Hauptaufgabe im Abschnitt; ``vor`` ist die sichtbare
    Aufgabe direkt danach.
    """
    projekt = get_object_or_404(Projekt, pk=pk)
    _darf_bearbeiten_oder_403(request.user, projekt)
    try:
        daten = json.loads(request.body)
    except ValueError:
        return HttpResponse(status=400)
    if not isinstance(daten, dict):
        return HttpResponse(status=400)
    werte = {k: daten.get(k) for k in ("id", "eltern", "abschnitt", "vor")}
    if any(v is not None and als_zahl(v) is None for v in werte.values()) or werte["id"] is None:
        return HttpResponse(status=400)
    aufgaben = projekt.aufgaben.all()
    aufgabe = get_object_or_404(aufgaben, pk=als_zahl(werte["id"]))
    eltern = get_object_or_404(aufgaben, pk=als_zahl(werte["eltern"])) if werte["eltern"] is not None else None
    abschnitt = (get_object_or_404(projekt.abschnitte, pk=als_zahl(werte["abschnitt"]))
                 if werte["abschnitt"] is not None else None)
    vor = aufgaben.filter(pk=als_zahl(werte["vor"])).first() if werte["vor"] is not None else None
    try:
        dienste.aufgabe_verschieben(request.user, aufgabe, eltern=eltern, abschnitt=abschnitt, vor=vor)
    except dienste.UngueltigesZiel:
        return HttpResponse(status=400)
    return HttpResponse(status=204)


INLINE_FELDER = {"verantwortlich", "gewerk", "faellig_am", "status"}
# Auf der Detailseite ist jedes Feld direkt bearbeitbar
DETAIL_FELDER = INLINE_FELDER | {"titel", "abschnitt", "beginn_am", "schaetzung_personentage", "beschreibung"}


class _Ungueltig(Exception):
    """Eingabe am Feld abgelehnt; die Meldung erscheint am Feld."""


def _feld_wert(aufgabe, feld, roh):
    """Prüft einen einzelnen Feldwert der Detailseite: Pflicht, Länge, Zahl ab 0, Fälligkeit nicht vor dem Beginn."""
    from decimal import Decimal, InvalidOperation

    roh = roh.strip() if feld != "beschreibung" else roh
    if feld == "titel":
        if not roh:
            raise _Ungueltig(_("Bitte einen Titel eingeben."))
        if len(roh) > 300:
            raise _Ungueltig(_("Höchstens 300 Zeichen."))
        return roh
    if feld == "beschreibung":
        if len(roh) > TEXT_MAX_ZEICHEN:
            raise _Ungueltig(_("Der Text ist zu lang (höchstens %(n)s Zeichen).") % {"n": TEXT_MAX_ZEICHEN})
        return roh
    try:
        if feld == "verantwortlich":
            if not roh:
                return None
            person = Person.objects.get(pk=roh)
            if not person.auswaehlbar and person.pk != aufgabe.verantwortlich_id:
                raise ValueError
            return person
        if feld == "abschnitt":
            return aufgabe.projekt.abschnitte.get(pk=roh) if roh else None
        if feld == "gewerk":
            return Gewerk.objects.get(pk=roh) if roh else None
        if feld == "status":
            return Status.objects.get(pk=roh)
        if feld == "schaetzung_personentage":
            if not roh:
                return None
            wert = Decimal(roh.replace(",", ".")).quantize(Decimal("0.1"))
            if wert < 0 or wert >= 10000:
                raise _Ungueltig(_("Bitte eine Zahl ab 0 eingeben."))
            return wert
        wert = date.fromisoformat(roh) if roh else None
    except (ValueError, InvalidOperation, Person.DoesNotExist, Gewerk.DoesNotExist, Status.DoesNotExist,
            Abschnitt.DoesNotExist) as fehler:
        raise _Ungueltig(_("Ungültige Eingabe.")) from fehler
    beginn = wert if feld == "beginn_am" else aufgabe.beginn_am
    faellig = wert if feld == "faellig_am" else aufgabe.faellig_am
    if beginn and faellig and faellig < beginn:
        raise _Ungueltig(_("Die Fälligkeit liegt vor dem geplanten Beginn.") if feld == "faellig_am"
                         else _("Der geplante Beginn liegt nach der Fälligkeit."))
    return wert


@require_POST
@login_required
def aufgabe_feld(request, pk):
    """Ein Feld speichern: Inline-Bearbeitung in der Listenansicht und auf der Detailseite."""
    aufgabe = get_object_or_404(Aufgabe.objects.select_related("projekt", "status"), pk=pk)
    _darf_bearbeiten_oder_403(request.user, aufgabe.projekt)
    detail = request.POST.get("ansicht") == "detail"
    feld = request.POST.get("feld")
    if (feld not in (DETAIL_FELDER if detail else INLINE_FELDER)
            or (feld in {"beginn_am", "faellig_am"} and termine.ist_sammelaufgabe(aufgabe))
            or (feld == "abschnitt" and aufgabe.eltern_id)):
        return HttpResponse(status=400)
    roh = request.POST.get("wert", "")
    if detail and request.POST.get("verwerfen"):  # Konflikt: die aktuelle Fassung übernehmen
        return _detail_feld_antwort(request, aufgabe, feld, ersetzen=True)
    try:
        wert = _feld_wert(aufgabe, feld, roh)
    except _Ungueltig as fehler:
        if detail:
            return _detail_feld_antwort(request, aufgabe, feld, fehler=str(fehler), eingabe=roh)
        return HttpResponse(status=400)
    war_erledigt = aufgabe.status.ist_erledigt
    alle = feld == "status" and wert.ist_erledigt and request.POST.get("unteraufgaben") == "alle"
    try:
        with transaction.atomic():
            aufgabe = dienste.aufgabe_speichern(request.user, aufgabe, {feld: wert}, request.POST.get("version"))
            if alle:
                dienste.unteraufgaben_erledigen(request.user, aufgabe)
    except dienste.Konflikt:
        meldung = _("Inzwischen von jemand anderem geändert – bitte erneut versuchen.")
        if detail:
            aufgabe.refresh_from_db()
            return _detail_feld_antwort(request, aufgabe, feld, konflikt=meldung,
                                        eingabe=roh if feld == "beschreibung" else None)
        return _zeile_antwort(request, aufgabe, fehler=meldung)
    feiern = request.user.feier_animation and aufgabe.status.ist_erledigt and not war_erledigt
    if detail and alle:
        # Unteraufgaben, Fortschritt und Verlauf ändern sich mit: ganze Seite neu laden
        if feiern:
            request.session["feiern"] = True
        antwort = HttpResponse(status=204)
        antwort["HX-Refresh"] = "true"
        return antwort
    if detail:
        antwort = _detail_feld_antwort(request, aufgabe, feld)
    elif alle and not aufgabe.eltern_id:
        antwort = _block_antwort(request, aufgabe)
        antwort["HX-Retarget"] = f"#aufgabe-block-{aufgabe.pk}"
        antwort["HX-Reswap"] = "outerHTML"
    else:
        antwort = _zeile_antwort(request, aufgabe)
    if not detail:
        _geaendert_melden(antwort, aufgabe, *(dienste.nachkommen(aufgabe.pk) if alle else ()))
    if feiern:
        antwort["HX-Trigger"] = "feiern"
    return antwort


def _detail_feld_antwort(request, aufgabe, feld, fehler=None, konflikt=None, eingabe=None, ersetzen=False):
    """Das geänderte Feld, dazu (out of band) Version, Kopf mit Status und Pfad; aus der Seitenleiste auch
    die Zeile der Liste, damit dort keine alte Version stehen bleibt."""
    aufgabe = (Aufgabe.objects.select_related("projekt", "abschnitt", "verantwortlich__konto", "verantwortlich__bereich",
                                              "gewerk", "status").get(pk=aufgabe.pk))
    seitenleiste = offene_seitenleiste(request)
    antwort = render(request, "projekte/_detail_antwort.html", {
        **(liste_oob(request.user, aufgabe.projekt, [aufgabe.pk]) if seitenleiste else {}),
        "aufgabe": aufgabe, "feld": feld, "fehler": fehler, "konflikt": konflikt, "eingabe": eingabe,
        "seitenleiste": bool(seitenleiste), "vorfahren": aufgabe.vorfahren(), **detail_kontext(request.user, aufgabe),
    })
    if feld in {"verantwortlich", "beschreibung"} and not (fehler or konflikt or ersetzen):
        # Tippsuche und Editor nicht austauschen, während man darin weiterarbeitet; nur Version und Kopf
        antwort["HX-Reswap"] = "none"
    return antwort


@login_required
def aufgabe(request, pk):
    aufgabe = aufgabe_laden(pk)
    kontext = detail_seite_kontext(request, aufgabe)
    if request.htmx and request.GET.get("seitenleiste"):
        return render(request, "projekte/_seitenleiste_inhalt.html", kontext)
    return render(request, "projekte/aufgabe.html", {
        **kontext, "aktiv": "projekt", "aktives_projekt": aufgabe.projekt_id,
    })


@require_POST
@login_required
def aufgabe_erledigt(request, pk):
    aufgabe = get_object_or_404(Aufgabe.objects.select_related("status", "projekt"), pk=pk)
    if not rechte.darf_abschliessen_und_kommentieren(request.user):
        raise PermissionDenied
    war_erledigt = aufgabe.status.ist_erledigt
    # Rückfrage im Browser: offene Unteraufgaben mit erledigen („alle“) oder nicht („keine“)
    alle = request.POST.get("unteraufgaben") == "alle"
    aufgabe = dienste.erledigt_setzen(request.user, aufgabe, request.POST.get("erledigt") == "1", unteraufgaben_mit=alle)
    feiern = request.user.feier_animation and aufgabe.status.ist_erledigt and not war_erledigt
    offen = offene_seitenleiste(request)
    if offen:  # Haken im Kopf oder an einer Unteraufgabe; in der Liste ändert sich auch der Zähler darüber
        antwort = seitenleiste_antwort(request, offen, zeilen=[aufgabe.pk, aufgabe.eltern_id, offen],
                                       block=aufgabe.pk if alle else None)
        if feiern:
            antwort["HX-Trigger"] = "feiern"
        return antwort
    if request.htmx and request.POST.get("zeile"):
        if alle and not aufgabe.eltern_id:
            antwort = _block_antwort(request, aufgabe)
            antwort["HX-Retarget"] = f"#aufgabe-block-{aufgabe.pk}"
            antwort["HX-Reswap"] = "outerHTML"
        else:
            antwort = _zeile_antwort(request, aufgabe)
        _geaendert_melden(antwort, aufgabe, *(dienste.nachkommen(aufgabe.pk) if alle else ()))
        if feiern:
            antwort["HX-Trigger"] = "feiern"
        return antwort
    if feiern:
        request.session["feiern"] = True  # nach der Weiterleitung abgespielt
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        weiter = aufgabe.get_absolute_url()
    return redirect(weiter)


@require_POST
@login_required
def aufgabe_loeschen(request, pk):
    aufgabe = get_object_or_404(Aufgabe.objects.select_related("projekt"), pk=pk)
    _darf_bearbeiten_oder_403(request.user, aufgabe.projekt)
    ziel = aufgabe.eltern if aufgabe.eltern_id else aufgabe.projekt
    weg, projekt, eltern_id = aufgabe.pk, aufgabe.projekt, aufgabe.eltern_id
    dienste.aufgabe_loeschen(request.user, aufgabe)  # samt Unteraufgaben aller Ebenen
    messages.success(request, _("Aufgabe gelöscht."))
    if offene_seitenleiste(request):
        antwort = render(request, "projekte/_seitenleiste_antwort.html",
                         liste_oob(request.user, projekt, [eltern_id], weg=weg))
        antwort["HX-Trigger-After-Settle"] = "seitenleiste-schliessen"
        return antwort
    return redirect(ziel)


# ---------- Unteraufgaben ----------

@require_POST
@login_required
def unteraufgabe_anlegen(request, pk):
    """Unteraufgabe = vollwertige Aufgabe mit Hauptaufgabe; bis zu UNTERAUFGABEN_EBENEN Ebenen."""
    aufgabe = get_object_or_404(Aufgabe.objects.select_related("projekt", "abschnitt"), pk=pk)
    _darf_bearbeiten_oder_403(request.user, aufgabe.projekt)
    form = UnteraufgabeForm(request.POST)
    if form.is_valid():
        d = form.cleaned_data
        try:
            dienste.aufgabe_anlegen(request.user, aufgabe.projekt, aufgabe.abschnitt, d["titel"], eltern=aufgabe,
                                    verantwortlich=d["verantwortlich"], faellig_am=d["faellig_am"])
        except dienste.KeineUnteraufgabe:
            messages.error(request, _("Unteraufgaben gibt es höchstens %(n)s Ebenen tief.") % {"n": UNTERAUFGABEN_EBENEN})
    if offen := offene_seitenleiste(request):
        return seitenleiste_antwort(request, offen, block=aufgabe.pk)
    return redirect(reverse("aufgabe", args=[aufgabe.pk]) + "#unteraufgaben")


# ---------- Meine Aufgaben ----------

@login_required
def meine_aufgaben(request):
    from planung.models import Abwesenheit, Einteilung

    person = request.user.person
    heute = timezone.localdate()
    beginn = heute if heute.weekday() < 5 else montag(heute) + timedelta(days=7)
    tage = werktage(beginn, beginn + timedelta(days=13))[:10]
    frei = freie_tage(tage[0], tage[-1])
    einteilungen = list(Einteilung.objects.filter(person=person, von__lte=tage[-1], bis__gte=tage[0])
                        .select_related("aufgabe__projekt", "aufgabe__status"))
    abwesend = set()
    for a in Abwesenheit.objects.filter(person=person, von__lte=tage[-1], bis__gte=tage[0]):
        abwesend.update(d for d in werktage(a.von, a.bis))
    tagesliste = []
    for d in tage:
        eintraege = [e for e in einteilungen if d in zaehlende_tage(e.von, e.bis, frei)]
        tagesliste.append({"datum": d, "frei": frei.get(d), "abwesend": d in abwesend, "einteilungen": eintraege,
                           "heute": d == heute})

    offene = list(mit_unterzahlen(Aufgabe.objects).filter(verantwortlich=person, status__ist_erledigt=False)
                  .select_related("projekt", "status", "eltern").order_by("faellig_am", "titel"))
    ende_woche = montag(heute) + timedelta(days=6)
    gruppen = [
        (_("Überfällig"), [a for a in offene if a.faellig_am and a.faellig_am < heute]),
        (_("Diese Woche"), [a for a in offene if a.faellig_am and heute <= a.faellig_am <= ende_woche]),
        (_("Später"), [a for a in offene if a.faellig_am and a.faellig_am > ende_woche]),
        (_("Ohne Termin"), [a for a in offene if not a.faellig_am]),
    ]
    erledigt = (Aufgabe.objects.filter(verantwortlich=person, status__ist_erledigt=True)
                .select_related("projekt", "status", "eltern").order_by("-erledigt_am")[:10])
    return render(request, "projekte/meine_aufgaben.html", {
        "tage": tagesliste, "gruppen": [(t, liste) for t, liste in gruppen if liste], "erledigt": erledigt,
        "anzahl_offen": len(offene), "aktiv": "meine", "heute": heute,
        "darf_abschliessen": rechte.darf_abschliessen_und_kommentieren(request.user),
    })


# ---------- Volltextsuche ----------

def _tsquery(text):
    woerter = re.findall(r"\w+", text, flags=re.UNICODE)[:8]
    if not woerter:
        return None
    return SearchQuery(" & ".join(f"{w}:*" for w in woerter), search_type="raw", config="german")


def _suchergebnisse(text, aufgaben=50, projekte=20, kommentare=30):
    """Treffer der Volltextsuche (Präfixe, deutsche Wortstämme, sonst Teilstring) je Art, bestbewertete zuerst."""
    ergebnisse = {"aufgaben": [], "projekte": [], "kommentare": []}
    anfrage = _tsquery(text)
    if anfrage is None:
        return ergebnisse
    vektor = SearchVector("titel", weight="A", config="german") + SearchVector("beschreibung", weight="B", config="german")
    ergebnisse["aufgaben"] = list(
        Aufgabe.objects.annotate(sv=vektor, rang=SearchRank(vektor, anfrage))
        .filter(Q(sv=anfrage) | Q(titel__icontains=text))
        .select_related("projekt", "status", "eltern").order_by("-rang", "titel")[:aufgaben]
    )
    pv = SearchVector("name", weight="A", config="german") + SearchVector("beschreibung", weight="B", config="german")
    ergebnisse["projekte"] = list(
        Projekt.objects.annotate(sv=pv).filter(Q(sv=anfrage) | Q(name__icontains=text))
        .prefetch_related("tags")[:projekte]
    )
    kv = SearchVector("text", config="german")
    treffer = list(
        Kommentar.objects.annotate(sv=kv).filter(Q(sv=anfrage) | Q(text__icontains=text))
        .select_related("aufgabe__projekt", "autor").order_by("-erstellt_am")[:kommentare]
    )
    ids = {int(i) for k in treffer for i in re.findall(r"@\[(\d+)\]", k.text)}
    namen = dict(Person.objects.filter(pk__in=ids).values_list("pk", "anzeigename"))
    for k in treffer:
        k.anzeige_text = re.sub(r"@\[(\d+)\]", lambda m: "@" + namen.get(int(m.group(1)), "?"), k.text)
    ergebnisse["kommentare"] = treffer
    return ergebnisse


@login_required
def suche(request):
    text = request.GET.get("q", "").strip()[:100]
    ergebnisse = {"aufgaben": [], "projekte": [], "kommentare": []}
    if text and rechte.darf_lesen(request.user):
        ergebnisse = _suchergebnisse(text)
    return render(request, "projekte/suche.html", {"text": text, **ergebnisse,
                                                   "anzahl": sum(len(v) for v in ergebnisse.values())})


# Vorschläge ab so vielen Zeichen – bei einem Zeichen passt fast alles
SUCHVORSCHLAEGE_AB = 2


@login_required
def suche_vorschlaege(request):
    """Vorschläge beim Tippen in der Suche der Kopfzeile (lib/suchvorschlaege.ts): wenige beste Treffer je Art
    und ein Link zur vollen Suche. Zu kurzer Text → leere Antwort, die Liste schließt sich."""
    text = request.GET.get("q", "").strip()[:100]
    if len(text) < SUCHVORSCHLAEGE_AB or not rechte.darf_lesen(request.user):
        return HttpResponse("")
    ergebnisse = _suchergebnisse(text, aufgaben=6, projekte=3, kommentare=3)
    return render(request, "projekte/_suchvorschlaege.html", {"text": text, **ergebnisse})
