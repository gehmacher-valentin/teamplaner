"""Daten für das Gantt-Diagramm einer Ansicht zusammenstellen."""

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import F
from django.urls import reverse

from planung.kalender import freie_tage
from planung.models import Einteilung
from projekte.models import Abhaengigkeit, Aufgabe

from . import rechte


def _iso(d):
    return d.isoformat() if d else None


def ist_zeitraeume(einteilungen):
    """Tatsächlich eingeteilter Zeitraum je Aufgabe: frühester Beginn bis spätestes Ende."""
    ist = {}
    for e in einteilungen:
        von, bis = ist.get(e.aufgabe_id, (e.von, e.bis))
        ist[e.aufgabe_id] = (min(von, e.von), max(bis, e.bis))
    return ist


def verletzt(vorher, nachher, ist):
    """„A vor B“ verletzt, wenn B spätestens an dem Tag beginnt, an dem A endet – nach den geplanten
    Terminen (die projekte.termine nachzieht, also nur noch bei erledigten Nachfolgern) oder nach den
    tatsächlichen Einteilungen, die nie automatisch verschoben werden."""
    ende_a = vorher.faellig_am or ist.get(vorher.pk, (None, None))[1]
    beginn_b = nachher.beginn_am or ist.get(nachher.pk, (None, None))[0] or nachher.faellig_am
    geplant = ende_a is not None and beginn_b is not None and beginn_b <= ende_a
    ist_a, ist_b = ist.get(vorher.pk), ist.get(nachher.pk)
    return geplant or (ist_a is not None and ist_b is not None and ist_b[0] <= ist_a[1])


# Im Gantt-Diagramm nur Hauptaufgaben und die erste Ebene Unteraufgaben
GANTT_EBENEN = 1


def aufgabe_dict(a, ist, extern=False, kinder=(), sammel=False):
    ist_von, ist_bis = ist.get(a.pk, (None, None))
    return {
        "id": a.pk,
        "projekt_id": a.projekt_id,
        "titel": a.titel,
        "eltern": a.eltern_id,
        # Unteraufgaben in dieser Ansicht; „sammel“: Termine ergeben sich aus den Unteraufgaben
        "kinder": list(kinder),
        "sammel": sammel,
        "abschnitt": a.abschnitt.name if a.abschnitt_id else "",
        "beginn": _iso(a.beginn_am),
        "ende": _iso(a.faellig_am),
        "ist_von": _iso(ist_von),
        "ist_bis": _iso(ist_bis),
        "erledigt": a.status.ist_erledigt,
        "status": a.status.name,
        "status_farbe": a.status.farbe,
        "version": a.version,
        "extern": extern,
        "url": reverse("aufgabe", args=[a.pk]),
    }


def gantt_daten(konto, ansicht):
    projekte = list(ansicht.projekte.all().order_by("beginn", "name"))
    alle = list(
        Aufgabe.objects.filter(projekt__in=projekte)
        .select_related("status", "abschnitt")
        .order_by("projekt_id", F("abschnitt__sortierung").asc(nulls_first=True), "sortierung", "id")
    )
    nach_id = {a.pk: a for a in alle}

    def tiefe(a):
        n = 0
        while a.eltern_id:
            a = a.eltern if a.eltern_id not in nach_id else nach_id[a.eltern_id]
            n += 1
        return n

    def sichtbar_fuer(a):
        """Die Aufgabe selbst oder ihre Unteraufgabe der ersten Ebene, unter der sie liegt."""
        while tiefe(a) > GANTT_EBENEN:
            a = nach_id.get(a.eltern_id) or a.eltern
        return a

    aufgaben = [a for a in alle if tiefe(a) <= GANTT_EBENEN]
    ids = {a.pk for a in aufgaben}
    alle_ids = set(nach_id)
    abhaengigkeiten = list(
        Abhaengigkeit.objects.filter(vorher_id__in=alle_ids) | Abhaengigkeit.objects.filter(nachher_id__in=alle_ids)
    )
    # Aufgaben anderer Projekte, die über Abhängigkeiten verbunden sind (tiefere Ebenen über ihrer
    # Unteraufgabe der ersten Ebene)
    fremd_ids = {x for abh in abhaengigkeiten for x in (abh.vorher_id, abh.nachher_id)} - alle_ids
    for a in Aufgabe.objects.filter(pk__in=fremd_ids).select_related("status", "eltern__eltern__eltern"):
        nach_id[a.pk] = a
        kette = a
        while kette.eltern_id:
            kette = kette.eltern
            nach_id.setdefault(kette.pk, kette)
    extern_ids = {sichtbar_fuer(nach_id[pk]).pk for pk in fremd_ids} - ids
    extern = {a.pk: a for a in Aufgabe.objects.filter(pk__in=extern_ids).select_related("status", "abschnitt", "projekt")}
    nach_id.update(extern)
    alle_aufgaben = {a.pk: a for a in [*aufgaben, *extern.values()]}

    einteilungen = list(Einteilung.objects.filter(aufgabe_id__in=nach_id))
    ist = ist_zeitraeume(einteilungen)
    # Tatsächlicher Zeitraum einer sichtbaren Aufgabe schließt ihre tieferen Unteraufgaben ein
    ist_sichtbar = dict(ist)
    for pk, (von_, bis_) in ist.items():
        a = nach_id.get(pk)
        if a is None:
            continue
        ziel = sichtbar_fuer(a).pk
        if ziel != pk:
            alt = ist_sichtbar.get(ziel, (von_, bis_))
            ist_sichtbar[ziel] = (min(alt[0], von_), max(alt[1], bis_))

    # Zeilen: Hauptaufgaben in Listenreihenfolge, jeweils gefolgt von ihren Unteraufgaben
    kinder = defaultdict(list)
    for a in aufgaben:
        if a.eltern_id in ids:
            kinder[a.eltern_id].append(a)
    mit_terminen = {a.eltern_id for a in nach_id.values() if a.eltern_id and (a.beginn_am or a.faellig_am)}
    je_projekt = defaultdict(list)
    for a in aufgaben:
        if a.eltern_id in ids:
            continue
        je_projekt[a.projekt_id].append(a.pk)
        je_projekt[a.projekt_id].extend(k.pk for k in kinder[a.pk])

    termine = [d for p in projekte for d in (p.beginn, p.ende)]
    termine += [d for a in alle_aufgaben.values() for d in (a.beginn_am, a.faellig_am)]
    termine += [d for zeitraum in ist.values() for d in zeitraum]
    termine = [d for d in termine if d]
    heute = date.today()
    von = min([*termine, heute]) - timedelta(days=14)
    bis = max([*termine, heute]) + timedelta(days=42)

    def projekt_ist(p):
        bereiche = [ist_sichtbar[a] for a in je_projekt[p.pk] if a in ist_sichtbar]
        if not bereiche:
            return None, None
        return min(b[0] for b in bereiche), max(b[1] for b in bereiche)

    def projekt_plan(p):
        """Zeitraum der geplanten Aufgabentermine – reicht er über Beginn/Ende hinaus, wächst der
        Projektbalken mit und der Überzug wird markiert."""
        tage = [d for a in alle if a.projekt_id == p.pk for d in (a.beginn_am, a.faellig_am) if d]
        return (min(tage), max(tage)) if tage else (None, None)

    def anzeige(pk):
        return sichtbar_fuer(nach_id[pk]).pk

    externe_projekte = {a.projekt_id: a.projekt for a in extern.values()}
    return {
        "ansicht": {"id": ansicht.pk, "name": ansicht.name, "recht": rechte.recht(konto, ansicht)},
        "heute": heute.isoformat(),
        "von": von.isoformat(),
        "bis": bis.isoformat(),
        "frei": {d.isoformat(): str(name) for d, name in freie_tage(von, bis).items()},
        "projekte": [
            {
                "id": p.pk, "name": p.name, "farbe": p.farbe, "archiviert": p.archiviert,
                "beginn": _iso(p.beginn), "ende": _iso(p.ende),
                "plan_von": _iso(projekt_plan(p)[0]), "plan_bis": _iso(projekt_plan(p)[1]),
                "ist_von": _iso(projekt_ist(p)[0]), "ist_bis": _iso(projekt_ist(p)[1]),
                "aufgaben": je_projekt[p.pk],
                "url": p.get_absolute_url(),
            }
            for p in projekte
        ],
        "externe_projekte": {pid: {"id": pid, "name": p.name, "farbe": p.farbe} for pid, p in externe_projekte.items()},
        "aufgaben": {
            a.pk: aufgabe_dict(a, ist_sichtbar, extern=a.pk not in ids, kinder=[k.pk for k in kinder[a.pk]],
                               sammel=a.pk in mit_terminen)
            for a in alle_aufgaben.values()
        },
        # Endpunkte tieferer Ebenen zeigen auf ihre Unteraufgabe der ersten Ebene
        "abhaengigkeiten": [
            {"id": abh.pk, "vorher": anzeige(abh.vorher_id), "nachher": anzeige(abh.nachher_id),
             "verletzt": verletzt(nach_id[abh.vorher_id], nach_id[abh.nachher_id], ist)}
            for abh in abhaengigkeiten
            if anzeige(abh.vorher_id) != anzeige(abh.nachher_id)
        ],
    }
