"""Aufgaben für die Anzeige laden und aufbereiten: Zeilen der Projektliste und das Aufgabendetail
(eigene Seite oder Seitenleiste). Ohne View-Code, damit auch andere Apps es nutzen können."""

import re
from datetime import date, timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.formats import date_format

from kern import rechte
from kern.models import Gewerk, Person
from planung import rechte as planungsrechte
from planung.kalender import arbeitstage, freie_tage, werktage, zaehlende_tage
from planung.raster import aufgaben_kennzahlen
from zusammenarbeit.verlauf import verlauf_eintraege

from . import dienste, termine
from .forms import UnteraufgabeForm
from .models import UNTERAUFGABEN_EBENEN, Aufgabe, Status


def mit_unterzahlen(qs):
    """Anzahl Unteraufgaben gesamt/erledigt für die Anzeige „2 / 5“."""
    return qs.annotate(
        unter_gesamt=Count("unteraufgaben", distinct=True),
        unter_erledigt=Count("unteraufgaben", filter=Q(unteraufgaben__status__ist_erledigt=True), distinct=True),
        unter_offen=Count("unteraufgaben", filter=Q(unteraufgaben__status__ist_erledigt=False), distinct=True),
        # Sammelaufgabe: Termine ergeben sich aus den Unteraufgaben (projekte.termine)
        unter_termine=Count("unteraufgaben", filter=Q(unteraufgaben__beginn_am__isnull=False)
                            | Q(unteraufgaben__faellig_am__isnull=False), distinct=True),
    )


def kennzahlen_setzen(aufgaben):
    pt, personen = aufgaben_kennzahlen([a.pk for a in aufgaben])
    for a in aufgaben:
        a.eingeteilt_pt = pt.get(a.pk, 0)
        a.eingeteilt_personen = personen.get(a.pk, 0)


def zeilen_kontext(konto, projekt):
    return {
        "darf_bearbeiten": rechte.darf_aufgaben_bearbeiten(konto, projekt),
        "darf_abschliessen": rechte.darf_abschliessen_und_kommentieren(konto),
        "statusliste": list(Status.objects.all()),
        "erledigt_status": ",".join(str(s.pk) for s in Status.objects.filter(ist_erledigt=True)),
        "gewerke": list(Gewerk.objects.all()),
        "personenliste": list(Person.objects.auswaehlbar().select_related("konto")),
        "heute": timezone.localdate(),
        "max_ebenen": UNTERAUFGABEN_EBENEN,
    }


def baum(aufgaben):
    """Unteraufgaben (``kinder``) unter ihre Hauptaufgabe hängen; gibt die oberste Ebene zurück.

    Ist eine Hauptaufgabe weggefiltert, steht die Unteraufgabe für sich (``waise``, mit Hinweis auf
    die Hauptaufgabe) im Abschnitt. ``tiefe`` und ``hoehe`` braucht das Ziehen im Browser, um zu
    tiefe Ebenen gar nicht erst anzubieten.
    """
    sichtbar = {a.pk: a for a in aufgaben}
    for a in aufgaben:
        a.kinder = sorted((k for k in aufgaben if k.eltern_id == a.pk), key=lambda k: (k.sortierung, k.pk))
        a.waise = bool(a.eltern_id) and a.eltern_id not in sichtbar

    def setzen(a, tiefe):
        a.tiefe_liste = tiefe
        a.hoehe = max((setzen(k, tiefe + 1) + 1 for k in a.kinder), default=0)
        return a.hoehe

    oben = sorted((a for a in aufgaben if a.eltern_id is None or a.waise), key=lambda a: (a.sortierung, a.pk))
    for a in oben:
        setzen(a, a.tiefe if a.waise else 0)
    return oben


def zeilen_laden(ids):
    """Aufgaben wie in der Projektliste: mit Zählern für die Unteraufgaben und Kennzahlen der Einteilung."""
    zeilen = list(mit_unterzahlen(Aufgabe.objects.select_related("verantwortlich__konto", "gewerk", "status",
                                                                  "projekt", "eltern")).filter(pk__in=ids))
    kennzahlen_setzen(zeilen)
    return zeilen


def block_laden(pk):
    """Aufgabe mit allen Unteraufgaben als Baum."""
    liste = zeilen_laden([pk, *dienste.nachkommen(pk)])
    baum(liste)
    aufgabe = next(a for a in liste if a.pk == pk)
    aufgabe.waise = False
    aufgabe.tiefe_liste = aufgabe.tiefe
    return aufgabe


def detail_kontext(konto, aufgabe):
    """Was die bearbeitbaren Felder der Detailseite brauchen."""
    personen = Person.objects.auswaehlbar().select_related("konto")
    return {
        "personenliste": personen,
        "abschnitte": aufgabe.projekt.abschnitte.all(),
        "statusliste": Status.objects.all(),
        "erledigt_status": ",".join(str(s.pk) for s in Status.objects.filter(ist_erledigt=True)),
        "gewerke": Gewerk.objects.all(),
        "sammelaufgabe": termine.ist_sammelaufgabe(aufgabe),
        "darf_bearbeiten": rechte.darf_aufgaben_bearbeiten(konto, aufgabe.projekt),
        "darf_abschliessen": rechte.darf_abschliessen_und_kommentieren(konto),
        "offene_unteraufgaben": dienste.offene_unteraufgaben(aufgabe),
    }


def aufgabe_laden(pk):
    return get_object_or_404(
        Aufgabe.objects.select_related("projekt", "abschnitt", "verantwortlich__konto", "verantwortlich__bereich",
                                       "gewerk", "status").prefetch_related("projekt__tags"),
        pk=pk,
    )


def detail_seite_kontext(request, aufgabe):
    """Alles für das Aufgabendetail, ob als eigene Seite oder in der Seitenleiste."""
    return {"aufgabe": aufgabe, **aufgabe_kontext(request, aufgabe), **detail_kontext(request.user, aufgabe)}


def aufgabe_kontext(request, aufgabe):
    """Unteraufgaben, Anhänge, Kommentare/Verlauf und Arbeitstage-Widget."""
    konto = request.user
    einteilungen = list(aufgabe.einteilungen.all())
    frei = freie_tage(min(e.von for e in einteilungen), max(e.bis for e in einteilungen)) if einteilungen else {}
    eingeteilt = sum(len(zaehlende_tage(e.von, e.bis, frei)) for e in einteilungen)
    verlauf = verlauf_eintraege(konto, aufgabe)
    kommentare = sum(1 for e in verlauf if e["art"] == "kommentar")
    return {
        "vorfahren": aufgabe.vorfahren(),
        "unteraufgaben": list(aufgabe.unteraufgaben.select_related("verantwortlich__konto", "status")),
        "unteraufgabe_form": UnteraufgabeForm() if dienste.darf_unteraufgaben_haben(aufgabe) else None,
        "anhaenge": aufgabe.anhaenge.select_related("hochgeladen_von"),
        "verlauf": verlauf,
        "kommentare_anzahl": kommentare,
        "verlauf_anzahl": len(verlauf) - kommentare,
        "eingeteilt_pt": eingeteilt,
        "widget": arbeitstage_widget(aufgabe, einteilungen, request.GET.get("monat")),
        "darf_abschliessen": rechte.darf_abschliessen_und_kommentieren(konto),
        "darf_planen": planungsrechte.hat_planungsansicht(konto),
        **abhaengigkeiten_kontext(aufgabe),
    }


def abhaengigkeiten_kontext(aufgabe):
    """Vorgänger/Nachfolger „A vor B“ mit Verletzungs-Hinweis."""
    from gantt.daten import ist_zeitraeume, verletzt
    from planung.models import Einteilung

    vorgaenger = list(aufgabe.vorgaenger_links.select_related("vorher__projekt"))
    nachfolger = list(aufgabe.nachfolger_links.select_related("nachher__projekt"))
    beteiligte = {aufgabe.pk, *(a.vorher_id for a in vorgaenger), *(a.nachher_id for a in nachfolger)}
    ist = ist_zeitraeume(Einteilung.objects.filter(aufgabe_id__in=beteiligte))
    for abh in vorgaenger:
        abh.verletzt = verletzt(abh.vorher, aufgabe, ist)
    for abh in nachfolger:
        abh.verletzt = verletzt(aufgabe, abh.nachher, ist)
    return {
        "vorgaenger": vorgaenger, "nachfolger": nachfolger,
        "abhaengigkeiten_anzahl": len(vorgaenger) + len(nachfolger),
        # eingeklappt soll eine Überschneidung trotzdem auffallen
        "abhaengigkeit_verletzt": any(abh.verletzt for abh in [*vorgaenger, *nachfolger]),
    }


def arbeitstage_widget(aufgabe, einteilungen, monat_param=None):
    """Monatsraster Mo–Fr: an welchen Tagen arbeitet mindestens eine Person."""
    heute = timezone.localdate()
    # Nur echte Monate und Jahre mit Abstand zu den Grenzen von ``date`` (das Raster rechnet einen
    # Monat vor und zurück), alles andere fällt auf den Vorgabemonat zurück
    monat = re.fullmatch(r"(\d{4})-(0[1-9]|1[0-2])", monat_param or "")
    if monat and 1900 <= int(monat[1]) <= 2200:
        erster = date(int(monat[1]), int(monat[2]), 1)
    elif einteilungen and not any(e.von <= heute <= e.bis for e in einteilungen) and min(e.von for e in einteilungen) > heute:
        erster = min(e.von for e in einteilungen).replace(day=1)
    else:
        erster = heute.replace(day=1)
    letzter = (erster.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    frei = freie_tage(erster, letzter)
    an = arbeitstage(einteilungen, freie_tage(min((e.von for e in einteilungen), default=erster),
                                              max((e.bis for e in einteilungen), default=letzter)))
    zellen = [None] * erster.weekday() if erster.weekday() < 5 else []
    for d in werktage(erster, letzter):
        zellen.append({"datum": d, "an": d in an, "frei": frei.get(d), "heute": d == heute})
    vorher = (erster - timedelta(days=1)).replace(day=1)
    nachher = letzter + timedelta(days=1)
    return {
        "titel": date_format(erster, "F Y"),
        "zellen": zellen,
        "vorher": vorher.strftime("%Y-%m"),
        "nachher": nachher.strftime("%Y-%m"),
        "anzahl": len(an),
        "farbe": aufgabe.projekt.farbe,
    }
