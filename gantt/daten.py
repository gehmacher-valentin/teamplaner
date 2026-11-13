"""Daten für das Gantt-Diagramm einer Ansicht zusammenstellen."""

from collections import defaultdict
from datetime import date, timedelta

from django.db.models import F
from django.urls import reverse

from planung.kalender import freie_tage
from planung.models import Einteilung
from projekte.models import Abhaengigkeit, Aufgabe, Projekt

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


def verletzung(vorher, nachher, ist):
    """„A vor B“ verletzt, wenn B spätestens an dem Tag beginnt, an dem A endet. Zwei Arten:

    - ``plan``: nach den geplanten Terminen beider Aufgaben. ``projekte.termine`` zieht Nachfolger
      nach, das bleibt also nur bei erledigten Nachfolgern stehen. Im Gantt-Diagramm zu sehen und
      dort zu beheben (roter Pfeil).
    - ``ist``: nach den tatsächlichen Einteilungen aus dem Teamplaner, die nie automatisch
      verschoben werden: beide Aufgaben sind eingeteilt und die Einteilungen überschneiden sich.
      Dazu der Mischfall: eine Aufgabe hat keine geplanten Termine, nur eine Einteilung, dann zählt
      für die andere ihr geplanter Termin. Sind beide geplant und nur eine eingeteilt, gibt es
      keine Warnung. Bei erledigten Nachfolgern entfällt sie. Ergebnis: ``None`` oder die beiden
      Tage mit ihrer Herkunft (``"ist"`` bzw. ``"plan"``), für den Hinweistext.
    """
    plan_ende_a = vorher.faellig_am
    plan_beginn_b = nachher.beginn_am or nachher.faellig_am
    plan = plan_ende_a is not None and plan_beginn_b is not None and plan_beginn_b <= plan_ende_a

    ist_a, ist_b = ist.get(vorher.pk), ist.get(nachher.pk)
    ohne_plan_a = vorher.beginn_am is None and vorher.faellig_am is None
    ohne_plan_b = nachher.beginn_am is None and nachher.faellig_am is None
    if ist_a and ist_b:
        ende_a, art_a, beginn_b, art_b = ist_a[1], "ist", ist_b[0], "ist"
    elif ist_a and ohne_plan_a:  # Mischfall: Vorgänger nur eingeteilt, Nachfolger nur geplant
        ende_a, art_a, beginn_b, art_b = ist_a[1], "ist", plan_beginn_b, "plan"
    elif ist_b and ohne_plan_b:  # Mischfall: Nachfolger nur eingeteilt, Vorgänger nur geplant
        ende_a, art_a, beginn_b, art_b = plan_ende_a, "plan", ist_b[0], "ist"
    else:
        ende_a = beginn_b = art_a = art_b = None
    warnung = None
    if ende_a is not None and beginn_b is not None and beginn_b <= ende_a and not nachher.status.ist_erledigt:
        warnung = {"vorher_bis": ende_a, "vorher_art": art_a, "nachher_von": beginn_b, "nachher_art": art_b}
    return {"plan": plan, "ist": warnung}


def verletzt(vorher, nachher, ist):
    """Verletzt nach den geplanten Terminen oder nach den Einteilungen (Aufgabendetail)."""
    ergebnis = verletzung(vorher, nachher, ist)
    return ergebnis["plan"] or ergebnis["ist"] is not None


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
    verletzungen = {abh.pk: verletzung(nach_id[abh.vorher_id], nach_id[abh.nachher_id], ist) for abh in abhaengigkeiten}
    projektnamen = {p.pk: p.name for p in projekte}
    fehlend = {nach_id[abh.vorher_id].projekt_id for abh in abhaengigkeiten if verletzungen[abh.pk]["ist"]} - set(projektnamen)
    projektnamen.update(Projekt.objects.filter(pk__in=fehlend).values_list("pk", "name"))

    def warnung(abh):
        """Hinweis für die Namensspalte: steht in der Zeile des Nachfolgers (bei tieferen Ebenen an
        der sichtbaren Unteraufgabe darüber) und nennt die tatsächlich betroffenen Aufgaben."""
        vorher, nachher, w = nach_id[abh.vorher_id], nach_id[abh.nachher_id], verletzungen[abh.pk]["ist"]
        return {
            "aufgabe": anzeige(abh.nachher_id),
            "nachher": {"id": nachher.pk, "titel": nachher.titel},
            "vorher": {"id": vorher.pk, "titel": vorher.titel, "projekt": projektnamen.get(vorher.projekt_id, "")},
            "nachher_von": _iso(w["nachher_von"]), "nachher_art": w["nachher_art"],
            "vorher_bis": _iso(w["vorher_bis"]), "vorher_art": w["vorher_art"],
        }

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
             "verletzt_plan": verletzungen[abh.pk]["plan"], "verletzt_ist": verletzungen[abh.pk]["ist"] is not None}
            for abh in abhaengigkeiten
            if anzeige(abh.vorher_id) != anzeige(abh.nachher_id)
        ],
        # Einteilungen aus dem Teamplaner verletzen eine Abhängigkeit: Warnzeichen in der Namensspalte.
        # Auch wenn beide Aufgaben in derselben sichtbaren Zeile liegen (dann gibt es keinen Pfeil).
        "warnungen": [warnung(abh) for abh in abhaengigkeiten if verletzungen[abh.pk]["ist"]],
    }
