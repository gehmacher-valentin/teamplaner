from collections import defaultdict

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Count, F, Q
from django.db.models.functions import Lower
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from kern import rechte as kern_rechte
from kern.heic import heic_umwandeln
from kern.hilfen import als_zahl, erfordert
from kern.protokoll import protokollieren
from zusammenarbeit.views import INLINE_TYPEN, dateityp

from . import rechte
from .forms import OrdnerForm
from .markdown import als_html
from .models import Notiz, NotizAnhang, Ordner


def _ordner_oder_403(konto, pk):
    ordner = get_object_or_404(Ordner, pk=pk)
    if not rechte.darf_ordner_lesen(konto, ordner):
        raise PermissionDenied
    return ordner


def _ziel(notiz_oder_ordner):
    """Ordnerseite, zu der nach dem Speichern/Löschen zurückgekehrt wird."""
    ordner_id = getattr(notiz_oder_ordner, "ordner_id", None)
    return reverse("notizordner", args=[ordner_id]) if ordner_id else reverse("notizen")


def _notizbaum(konto, ordner, notiz_pk):
    """Ordnerspalte als Baum: persönliche Notizen und sichtbare Gruppenordner mit ihren Titeln.

    Nur was man auch öffnen darf: eigene persönliche Notizen (auch Admins keine fremden) und Notizen
    der sichtbaren Ordner. Titel alphabetisch, damit beim automatischen Speichern nichts springt.
    """
    ordnerliste = rechte.sichtbare_ordner(konto)
    titel = defaultdict(list)
    notizen = (Notiz.objects.filter(Q(besitzer=konto.person, ordner__isnull=True) | Q(ordner__in=ordnerliste))
               .order_by(Lower("titel"), "pk").values_list("pk", "titel", "ordner_id"))
    for pk, notiztitel, ordner_id in notizen:
        titel[ordner_id].append({"pk": pk, "titel": notiztitel, "aktuell": pk == notiz_pk})
    baum = [{"schluessel": "persoenlich", "name": _("Persönliche Notizen"), "url": reverse("notizen"),
             "persoenlich": True, "aktuell": ordner is None, "notizen": titel[None]}]
    for o in ordnerliste:
        baum.append({"schluessel": str(o.pk), "name": o.name, "url": reverse("notizordner", args=[o.pk]),
                     "aktuell": ordner is not None and ordner.pk == o.pk, "notizen": titel[o.pk]})
    return baum


def _kontext(request, ordner=None, notiz_pk=None):
    konto = request.user
    return {
        "notizbaum": _notizbaum(konto, ordner, notiz_pk),
        "ordner": ordner,
        "darf_ordner_anlegen": rechte.darf_ordner_anlegen(konto),
        "aktiv": "notizen",
    }


@erfordert(kern_rechte.darf_lesen)
def uebersicht(request, pk=None):
    """Liste der Notizen eines Ordners; ohne ``pk`` die persönlichen Notizen."""
    konto = request.user
    if pk is None:
        ordner = None
        notizen = Notiz.objects.filter(besitzer=konto.person, ordner__isnull=True)
        darf_schreiben = True
    else:
        ordner = _ordner_oder_403(konto, pk)
        notizen = ordner.notizen.all()
        darf_schreiben = rechte.darf_ordner_schreiben(konto, ordner)
    suche = request.GET.get("q", "").strip()
    if suche:
        notizen = notizen.filter(titel__icontains=suche) | notizen.filter(text__icontains=suche)
    return render(request, "notizen/uebersicht.html", {
        **_kontext(request, ordner),
        "notizen": notizen.select_related("geaendert_von").annotate(anzahl_anhaenge=Count("anhaenge")),
        "suche": suche,
        "darf_schreiben": darf_schreiben,
        "darf_verwalten": ordner is not None and rechte.darf_ordner_verwalten(konto, ordner),
        "mitglieder": ordner.mitglieder.select_related("person").order_by("person__anzeigename") if ordner else [],
    })


def _notiz_kontext(request, eintrag):
    return {
        **_kontext(request, eintrag.ordner, eintrag.pk),
        "notiz_offen": True,
        "notiz": eintrag,
        "html": als_html(eintrag.text),
        "darf_schreiben": eintrag.pk is None or rechte.darf_notiz_schreiben(request.user, eintrag),
        "anhaenge": eintrag.anhaenge.all() if eintrag.pk else [],
    }


@erfordert(kern_rechte.darf_lesen)
def notiz(request, pk):
    """Notiz ansehen und – mit Schreibrecht – direkt bearbeiten."""
    eintrag = get_object_or_404(Notiz.objects.select_related("ordner", "erstellt_von", "geaendert_von"), pk=pk)
    if not rechte.darf_notiz_lesen(request.user, eintrag):
        raise PermissionDenied
    return render(request, "notizen/notiz.html", _notiz_kontext(request, eintrag))


def _neue_notiz(konto, ordner_id):
    ordner = _ordner_oder_403(konto, ordner_id) if ordner_id else None
    if ordner is not None and not rechte.darf_ordner_schreiben(konto, ordner):
        raise PermissionDenied
    return Notiz(ordner=ordner, besitzer=None if ordner else konto.person, erstellt_von=konto.person)


@erfordert(kern_rechte.darf_lesen)
def notiz_neu(request):
    """Leere Notiz in derselben Ansicht; angelegt wird sie erst beim ersten Speichern (notiz_speichern)."""
    eintrag = _neue_notiz(request.user, als_zahl(request.GET.get("ordner")))
    return render(request, "notizen/notiz.html", _notiz_kontext(request, eintrag))


@require_POST
@erfordert(kern_rechte.darf_lesen)
def notiz_speichern(request):
    """Titel und Text speichern, sobald man ein Feld verlässt oder kurz nicht tippt.

    Jede Anfrage schickt beide Felder und die Version; eine neue Notiz entsteht beim ersten Speichern.
    Ist die Notiz inzwischen von jemand anderem geändert worden, wird nichts überschrieben: Die
    Antwort zeigt die aktuelle Fassung, der eigene Text bleibt im Editor stehen.
    """
    konto = request.user
    pk = als_zahl(request.POST.get("notiz"))
    if pk:
        eintrag = get_object_or_404(Notiz.objects.select_related("ordner"), pk=pk)
        if not rechte.darf_notiz_schreiben(konto, eintrag):
            raise PermissionDenied
    else:
        eintrag = _neue_notiz(konto, als_zahl(request.POST.get("ordner")))
    titel = request.POST.get("titel", "").strip()
    text = request.POST.get("text", "")
    if not titel or len(titel) > 200:
        fehler = _("Bitte einen Titel eingeben.") if not titel else _("Höchstens 200 Zeichen.")
        antwort = render(request, "notizen/_titel.html", {**_notiz_kontext(request, eintrag), "titel_eingabe": titel,
                                                          "fehler": fehler})
        antwort["HX-Retarget"] = "#notiz-titel"
        antwort["HX-Reswap"] = "outerHTML"
        return antwort
    neu = eintrag.pk is None
    with transaction.atomic():
        if not neu:
            aktuell = Notiz.objects.select_for_update().get(pk=eintrag.pk)
            if request.POST.get("version") != str(aktuell.version):
                antwort = render(request, "notizen/_konflikt.html", {
                    "notiz": aktuell, "aktuell_html": als_html(aktuell.text),
                })
                antwort["HX-Retarget"] = "#notiz-konflikt"
                antwort["HX-Reswap"] = "innerHTML"
                return antwort
            eintrag = aktuell
            if (eintrag.titel, eintrag.text) == (titel, text):
                return render(request, "notizen/_gespeichert.html", _notiz_kontext(request, eintrag))
            eintrag.version = F("version") + 1
        eintrag.titel, eintrag.text = titel, text
        eintrag.geaendert_von = konto.person
        eintrag.save()
        eintrag.refresh_from_db()
    antwort = render(request, "notizen/_gespeichert.html", {**_notiz_kontext(request, eintrag), "neu": neu})
    if neu:
        antwort["HX-Replace-Url"] = reverse("notiz", args=[eintrag.pk])
    return antwort


@require_POST
@erfordert(kern_rechte.darf_lesen)
def notiz_loeschen(request, pk):
    eintrag = get_object_or_404(Notiz, pk=pk)
    if not rechte.darf_notiz_schreiben(request.user, eintrag):
        raise PermissionDenied
    ziel = _ziel(eintrag)
    _dateien_loeschen(eintrag.anhaenge.all())
    eintrag.delete()
    messages.success(request, _("Notiz „%(titel)s“ gelöscht.") % {"titel": eintrag.titel})
    return redirect(ziel)


@erfordert(rechte.darf_ordner_anlegen)
def ordner_bearbeiten(request, pk=None):
    konto = request.user
    ordner = get_object_or_404(Ordner, pk=pk) if pk else None
    if ordner is not None and not rechte.darf_ordner_verwalten(konto, ordner):
        raise PermissionDenied
    form = OrdnerForm(request.POST or None, instance=ordner,
                      initial=None if ordner else {"mitglieder": [konto.pk]})
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            gespeichert = form.save(commit=False)
            if ordner is None:
                gespeichert.erstellt_von = konto.person
            gespeichert.save()
            form.save_m2m()
            protokollieren(konto, "notizordner", gespeichert.pk, "geaendert" if ordner else "angelegt", {
                "name": gespeichert.name,
                "mitglieder": [k.person.anzeigename for k in gespeichert.mitglieder.select_related("person")],
            })
        messages.success(request, _("Ordner „%(name)s“ gespeichert.") % {"name": gespeichert.name})
        if not rechte.darf_ordner_lesen(konto, gespeichert):
            return redirect("notizen")
        return redirect("notizordner", pk=gespeichert.pk)
    return render(request, "notizen/ordner.html", {**_kontext(request, ordner), "form": form, "bearbeitet": ordner})


@require_POST
@erfordert(rechte.darf_ordner_anlegen)
def ordner_loeschen(request, pk):
    ordner = get_object_or_404(Ordner, pk=pk)
    if not rechte.darf_ordner_verwalten(request.user, ordner):
        raise PermissionDenied
    protokollieren(request.user, "notizordner", ordner.pk, "geloescht",
                   {"name": ordner.name, "notizen": ordner.notizen.count()})
    _dateien_loeschen(NotizAnhang.objects.filter(notiz__ordner=ordner))
    ordner.delete()
    messages.success(request, _("Ordner „%(name)s“ gelöscht.") % {"name": ordner.name})
    return redirect("notizen")


# ---------- Anhänge ----------

def _dateien_loeschen(anhaenge):
    for anhang in anhaenge:
        anhang.datei.delete(save=False)


@require_POST
@erfordert(kern_rechte.darf_lesen)
def anhang_hochladen(request, pk):
    eintrag = get_object_or_404(Notiz, pk=pk)
    if not rechte.darf_notiz_schreiben(request.user, eintrag):
        raise PermissionDenied
    datei = request.FILES.get("datei")
    max_mb = settings.TEAMPLANER_ANHANG_MAX_MB
    if datei is not None and datei.size > max_mb * 1024 * 1024:
        messages.error(request, _("Die Datei ist zu groß (höchstens %(mb)s MB).") % {"mb": max_mb})
    elif datei is not None:
        datei = heic_umwandeln(datei) or datei  # iPhone-Fotos als JPEG
        NotizAnhang.objects.create(
            notiz=eintrag, datei=datei, dateiname=datei.name[:255], groesse=datei.size,
            content_type=dateityp(datei), hochgeladen_von=request.user.person,
        )
    return redirect(reverse("notiz", args=[eintrag.pk]) + "#anhaenge")


@erfordert(kern_rechte.darf_lesen)
def anhang_herunterladen(request, pk):
    anhang = get_object_or_404(NotizAnhang.objects.select_related("notiz"), pk=pk)
    if not rechte.darf_notiz_lesen(request.user, anhang.notiz):
        raise PermissionDenied
    try:
        datei = anhang.datei.open("rb")
    except FileNotFoundError:
        raise Http404 from None
    inline = anhang.content_type in INLINE_TYPEN
    antwort = FileResponse(datei, as_attachment=not inline, filename=anhang.dateiname,
                           content_type=anhang.content_type if inline else "application/octet-stream")
    antwort["X-Content-Type-Options"] = "nosniff"
    antwort["Content-Security-Policy"] = "default-src 'none'; img-src 'self'; style-src 'unsafe-inline'"
    antwort["Cache-Control"] = "private"
    return antwort


@require_POST
@erfordert(kern_rechte.darf_lesen)
def anhang_loeschen(request, pk):
    anhang = get_object_or_404(NotizAnhang.objects.select_related("notiz"), pk=pk)
    if not rechte.darf_notiz_schreiben(request.user, anhang.notiz):
        raise PermissionDenied
    _dateien_loeschen([anhang])
    anhang.delete()
    return redirect(reverse("notiz", args=[anhang.notiz_id]) + "#anhaenge")
