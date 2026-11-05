"""Daten für Teamplaner und Lesekalender zusammenstellen (Personen × Tage)."""

from collections import defaultdict
from datetime import date

from django.db.models import Count, Q
from django.urls import reverse
from django.utils.translation import gettext as _

from kern import rechte as kern_rechte
from kern.models import Bereich, Gewerk, Person, Systemeinstellungen
from projekte.models import Aufgabe, Projekt, Tag
from zusammenarbeit.models import Anhang

from . import rechte
from .kalender import (
    doppelbelegungen,
    freie_tage,
    freie_tage_mit_wochenende,
    kalenderwoche,
    tage,
    zaehlende_tage,
)
from .models import (
    Abwesenheit,
    Einteilung,
    FreigabeStufe,
    Tagesfreigabe,
    TagesInfo,
    TeamplanerAnsicht,
)

ANSICHT_ICH = "ich"
ANSICHT_ALLE = "alle"


class AnsichtNichtErlaubt(Exception):
    pass


def ansichten_fuer(konto):
    """Auswahl im Teamplaner: freigegebene Ansichten plus „Nur ich“ (und „Alle“ für BL/Admin)."""
    eintraege = []
    freigaben = rechte.freigaben(konto)
    if kern_rechte.sieht_alles_im_teamplaner(konto):
        eintraege.append({"id": ANSICHT_ALLE, "name": _("Alle Personen"), "recht": "bearbeiten", "filter": {}})
    for ansicht in TeamplanerAnsicht.objects.filter(pk__in=list(freigaben)):
        eintraege.append({
            "id": str(ansicht.pk),
            "name": ansicht.name,
            "recht": freigaben[ansicht.pk],
            "filter": ansicht.filter or {},
        })
    eintraege.append({
        "id": ANSICHT_ICH,
        "name": _("Nur ich"),
        "recht": "bearbeiten" if rechte.darf_einteilen(konto, konto.person) else "sehen",
        "filter": {},
    })
    return eintraege


def personen_der_ansicht(konto, ansicht_id):
    if ansicht_id == ANSICHT_ICH:
        return Person.objects.filter(pk=konto.person_id)
    if ansicht_id == ANSICHT_ALLE:
        if not kern_rechte.sieht_alles_im_teamplaner(konto):
            raise AnsichtNichtErlaubt
        return Person.objects.all()
    try:
        pk = int(ansicht_id)
    except (TypeError, ValueError):
        raise AnsichtNichtErlaubt from None
    if pk not in rechte.freigaben(konto):
        raise AnsichtNichtErlaubt
    return TeamplanerAnsicht.objects.get(pk=pk).personen_queryset()


def aufgaben_kennzahlen(aufgabe_ids):
    """Eingeteilte Personentage und Anzahl Personen je Aufgabe."""
    alle = list(
        Einteilung.objects.filter(aufgabe_id__in=aufgabe_ids)
        .order_by("aufgabe_id", "von", "id")
        .only("id", "aufgabe_id", "person_id", "von", "bis")
    )
    nach_aufgabe = defaultdict(list)
    for e in alle:
        nach_aufgabe[e.aufgabe_id].append(e)
    frei = freie_tage(min(e.von for e in alle), max(e.bis for e in alle)) if alle else {}
    pt, personen = {}, {}
    for aufgabe_id, liste in nach_aufgabe.items():
        pt[aufgabe_id] = sum(len(zaehlende_tage(e.von, e.bis, frei)) for e in liste)
        personen[aufgabe_id] = len({e.person_id for e in liste})
    return pt, personen


def anhang_anzahlen(aufgabe_ids):
    """Anzahl Anhänge je Aufgabe – für das Büroklammer-Symbol auf den Karten."""
    return dict(
        Anhang.objects.filter(aufgabe_id__in=aufgabe_ids).order_by()
        .values("aufgabe_id").annotate(n=Count("id")).values_list("aufgabe_id", "n")
    )


# Hauptaufgaben bis zur obersten Ebene in einer Abfrage (Unteraufgaben bis zu drei Ebenen)
ELTERN_KETTE = "eltern__eltern__eltern"


def eltern_pfad(aufgabe):
    """„Hauptaufgabe › Unteraufgabe“ über der Aufgabe, None für Hauptaufgaben."""
    return " › ".join(v.titel for v in aufgabe.vorfahren()) or None


def aufgabe_dict(aufgabe, pt=0, personen=0, anhaenge=0):
    return {
        "id": aufgabe.pk,
        "titel": aufgabe.titel,
        "eltern": eltern_pfad(aufgabe),
        "projekt_id": aufgabe.projekt_id,
        "gewerk": aufgabe.gewerk.name if aufgabe.gewerk_id else "",
        "gewerk_id": aufgabe.gewerk_id,
        "status": aufgabe.status.name,
        "erledigt": aufgabe.status.ist_erledigt,
        "schaetzung": float(aufgabe.schaetzung_personentage) if aufgabe.schaetzung_personentage is not None else None,
        "eingeteilt": pt,
        "personen": personen,
        "faellig_am": aufgabe.faellig_am.isoformat() if aufgabe.faellig_am else None,
        "anhaenge": anhaenge,
        "url": reverse("aufgabe", args=[aufgabe.pk]),
    }


def projekte_dict(projekt_ids):
    return {
        p.pk: {"id": p.pk, "name": p.name, "farbe": p.farbe, "tags": [t.pk for t in p.tags.all()]}
        for p in Projekt.objects.filter(pk__in=projekt_ids).prefetch_related("tags")
    }


def raster(konto, ansicht_id, von: date, bis: date, archivierte=False):
    sichtbar = rechte.sichtbare_personen_ids(konto)
    einteilbar = rechte.einteilbare_personen_ids(konto)

    personen_qs = personen_der_ansicht(konto, ansicht_id).select_related("bereich", "konto").prefetch_related("gewerke")
    if sichtbar is not None:
        personen_qs = personen_qs.filter(pk__in=sichtbar)
    if not archivierte:
        personen_qs = personen_qs.filter(archiviert_am__isnull=True)
    personen = list(personen_qs)
    person_ids = [p.pk for p in personen]

    einteilungen = list(
        Einteilung.objects.filter(person_id__in=person_ids, von__lte=bis, bis__gte=von)
        .select_related("aufgabe__status", "aufgabe__gewerk", f"aufgabe__{ELTERN_KETTE}")
    )
    abwesenheiten = list(Abwesenheit.objects.filter(person_id__in=person_ids, von__lte=bis, bis__gte=von))

    belegt = {e.person_id for e in einteilungen} | {a.person_id for a in abwesenheiten}
    if archivierte:
        # Archivierte Personen nur, wenn sie im Zeitraum Einträge haben
        personen = [p for p in personen if not p.archiviert or p.pk in belegt]
    # Systemkonten (z. B. Admin) nur, solange sie im Zeitraum noch Einträge haben – zum Umhängen
    personen = [p for p in personen if not p.systemkonto or p.pk in belegt]

    frei = freie_tage_mit_wochenende(von, bis)
    infos = dict(TagesInfo.objects.filter(datum__range=(von, bis)).values_list("datum", "text"))
    einstellungen = Systemeinstellungen.laden()
    freigabe_zeile = einstellungen.freigabe_zeile
    # Stufe und wer sie zuletzt gesetzt hat, auch archivierte Personen und Systemkonten mit Namen
    freigaben = {f.datum: (str(f.stufe_id), f.geaendert_von.anzeigename if f.geaendert_von else "")
                 for f in Tagesfreigabe.objects.filter(datum__range=(von, bis)).select_related("geaendert_von")
                 } if freigabe_zeile else {}
    aufgaben = {e.aufgabe_id: e.aufgabe for e in einteilungen}
    pt, anzahl_personen = aufgaben_kennzahlen(list(aufgaben))
    anhaenge = anhang_anzahlen(list(aufgaben))

    return {
        "von": von.isoformat(),
        "bis": bis.isoformat(),
        "heute": date.today().isoformat(),
        "info_bearbeitbar": rechte.hat_planungsansicht(konto),
        # Tagesfreigabe: Zeile nur, wenn ein Admin sie eingeschaltet hat; Bearbeiten wie die Info-Zeile
        "freigabe_zeile": freigabe_zeile,
        "freigabe_name": einstellungen.freigabe_bezeichnung,
        "freigabe_stufen": [{"wert": str(s.pk), "name": s.name} for s in FreigabeStufe.objects.all()] if freigabe_zeile else [],
        "tage": [
            {"datum": d.isoformat(), "wochentag": d.weekday(), "kw": kalenderwoche(d), "frei": frei.get(d),
             "info": infos.get(d, ""), "freigabe": freigaben.get(d, ("", ""))[0],
             "freigabe_von": freigaben.get(d, ("", ""))[1]}
            for d in tage(von, bis)
        ],
        "bereiche": [{"id": b.pk, "name": b.name} for b in Bereich.objects.all()],
        "personen": [
            {
                "id": p.pk,
                "name": p.anzeigename,
                "initialen": p.initialen,
                "foto": p.foto_url,
                "bereich_id": p.bereich_id,
                "gewerke": [g.name for g in p.gewerke.all()],
                "gewerk_ids": [g.pk for g in p.gewerke.all()],
                "platzhalter": p.ist_platzhalter,
                "archiviert": p.archiviert,
                "ich": p.pk == konto.person_id,
                "einteilbar": (einteilbar is None or p.pk in einteilbar) and not p.archiviert,
                # nur für neue Einteilungen wählbar, bestehende lassen sich auf andere Personen ziehen
                "auswaehlbar": p.auswaehlbar,
            }
            for p in personen
        ],
        "einteilungen": [
            {
                "id": e.pk, "aufgabe_id": e.aufgabe_id, "person_id": e.person_id,
                "von": e.von.isoformat(), "bis": e.bis.isoformat(), "version": e.version,
            }
            for e in einteilungen
        ],
        "abwesenheiten": [
            {"id": a.pk, "person_id": a.person_id, "von": a.von.isoformat(),
             "bis": a.bis.isoformat(), "version": a.version}
            for a in abwesenheiten
        ],
        "aufgaben": {
            a.pk: aufgabe_dict(a, pt.get(a.pk, 0), anzahl_personen.get(a.pk, 0), anhaenge.get(a.pk, 0))
            for a in aufgaben.values()
        },
        "projekte": projekte_dict({a.projekt_id for a in aufgaben.values()}),
        "doppelbelegungen": [
            {"person_id": pid, "datum": d.isoformat()}
            for pid, d in sorted(doppelbelegungen(einteilungen, abwesenheiten, frei))
        ],
    }


def palette(konto, *, modus="offen", projekt_id=None, gewerk_id=None, tag_id=None, suche=""):
    """Aufgaben zum Einteilen: offene Aufgaben, die noch nicht voll eingeteilt sind,
    oder – im Modus „projekt“ – alle offenen Aufgaben eines Projekts."""
    qs = (
        Aufgabe.objects.filter(status__ist_erledigt=False, projekt__archiviert_am__isnull=True)
        .select_related("projekt", "gewerk", "status", ELTERN_KETTE)
        .order_by("faellig_am", "titel")
    )
    if projekt_id:
        qs = qs.filter(projekt_id=projekt_id)
    if gewerk_id:
        qs = qs.filter(gewerk_id=gewerk_id)
    if tag_id:
        qs = qs.filter(projekt__tags=tag_id)
    if suche:
        qs = qs.filter(Q(titel__icontains=suche) | Q(projekt__name__icontains=suche) | Q(eltern__titel__icontains=suche)
                       | Q(eltern__eltern__titel__icontains=suche) | Q(eltern__eltern__eltern__titel__icontains=suche))
    aufgaben = list(qs[:500])
    pt, anzahl_personen = aufgaben_kennzahlen([a.pk for a in aufgaben])

    def noch_offen(a):
        eingeteilt = pt.get(a.pk, 0)
        if a.schaetzung_personentage is None:
            return eingeteilt == 0
        return eingeteilt < a.schaetzung_personentage

    if modus != "projekt":
        aufgaben = [a for a in aufgaben if noch_offen(a)]
    aufgaben = aufgaben[:200]
    anhaenge = anhang_anzahlen([a.pk for a in aufgaben])
    return {
        "aufgaben": [aufgabe_dict(a, pt.get(a.pk, 0), anzahl_personen.get(a.pk, 0), anhaenge.get(a.pk, 0))
                     for a in aufgaben],
        "projekte": projekte_dict({a.projekt_id for a in aufgaben}),
    }


def filteroptionen():
    return {
        "projekte": [
            {"id": p.pk, "name": p.name, "farbe": p.farbe, "tags": [t.pk for t in p.tags.all()]}
            for p in Projekt.objects.aktiv().prefetch_related("tags")
        ],
        "tags": [{"id": t.pk, "name": t.name} for t in Tag.objects.all()],
        "gewerke": [{"id": g.pk, "name": g.name} for g in Gewerk.objects.all()],
        "bereiche": [{"id": b.pk, "name": b.name} for b in Bereich.objects.all()],
    }
