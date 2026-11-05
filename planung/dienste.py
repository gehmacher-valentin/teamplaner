"""Anlegen, Ändern und Löschen von Einteilungen und Abwesenheiten.

Alle Schreibzugriffe aus API und Oberfläche laufen hier durch: Rechteprüfung,
Feiertagsbestätigung, Schutz vor stillem Überschreiben, Protokoll
und Live-Benachrichtigung der anderen Clients (``pg_notify``).
"""

import json

from django.db import connection, transaction
from django.utils.formats import date_format
from django.utils.translation import gettext as _

from kern.hilfen import als_zahl
from kern.protokoll import aenderungen, protokollieren

from . import rechte
from .kalender import freie_tage_mit_wochenende
from .models import Abwesenheit, Einteilung, FreigabeStufe, Tagesfreigabe, TagesInfo

MAX_TAGE = 366
MAX_INFO_ZEICHEN = 120
KANAL = "planung"


class PlanungsFehler(Exception):
    def __init__(self, code, nachricht, status=400, daten=None):
        super().__init__(nachricht)
        self.code = code
        self.nachricht = nachricht
        self.status = status
        self.daten = daten or {}


def als_dict(objekt):
    daten = {
        "id": objekt.pk,
        "person_id": objekt.person_id,
        "von": objekt.von.isoformat(),
        "bis": objekt.bis.isoformat(),
        "version": objekt.version,
    }
    if isinstance(objekt, Einteilung):
        daten["aufgabe_id"] = objekt.aufgabe_id
    return daten


def _melden(art, aktion, objekt, personen_ids, von, bis, akteur, client_id, alle=False, extra=None):
    """Nach dem Commit an alle verbundenen Clients melden (Live-Aktualisierung).

    ``alle``: betrifft keine bestimmten Personen (Tagesinfo) und geht an jede offene Seite.
    ``extra``: zusätzliche Angaben für alle, z. B. Stufe und Name bei der Tagesfreigabe.
    """
    nutzlast = json.dumps({
        **(extra or {}),
        "art": art,
        "aktion": aktion,
        "id": objekt.pk,
        "person_ids": sorted(set(personen_ids)),
        "alle": alle,
        "von": von.isoformat(),
        "bis": bis.isoformat(),
        "akteur_id": akteur.person_id,
        "client": client_id or "",
    })

    def senden():
        with connection.cursor() as cursor:
            cursor.execute("SELECT pg_notify(%s, %s)", [KANAL, nutzlast])

    transaction.on_commit(senden)


def einteilungen_entfernt_melden(konto, einteilungen):
    """Für Löschungen außerhalb dieses Moduls (z. B. Aufgabe gelöscht): Clients aktualisieren."""
    for e in einteilungen:
        _melden("einteilung", "geloescht", e, [e.person_id], e.von, e.bis, konto, None)


def _pruefe_zeitraum(von, bis):
    if von is None or bis is None:
        raise PlanungsFehler("zeitraum", _("Beginn und Ende sind erforderlich."))
    if bis < von:
        raise PlanungsFehler("zeitraum", _("Das Ende liegt vor dem Beginn."))
    if (bis - von).days >= MAX_TAGE:
        raise PlanungsFehler("zu_lang", _("Ein Zeitraum darf höchstens ein Jahr lang sein."))


def _pruefe_recht(konto, person):
    if not rechte.darf_einteilen(konto, person):
        raise PlanungsFehler(
            "keine_berechtigung",
            _("Sie dürfen %(name)s nicht einteilen.") % {"name": person.anzeigename},
            status=403,
        )


def _pruefe_auswaehlbar(person):
    """Systemkonten (z. B. Admin) bekommen keine neuen Einträge; bestehende lassen sich umhängen."""
    if person.systemkonto:
        raise PlanungsFehler(
            "systemkonto", _("%(name)s ist ein Systemkonto und kann nicht eingeteilt werden.") % {"name": person.anzeigename},
        )


def _pruefe_nicht_archiviert(person):
    if person.archiviert:
        raise PlanungsFehler(
            "archiviert",
            _("%(name)s ist archiviert und kann nicht mehr eingeteilt werden.")
            % {"name": person.anzeigename},
        )


def _pruefe_feiertag(von, bis, bestaetigt):
    """Eintägige Einteilung genau auf einem Feiertag oder Wochenendtag nur nach Bestätigung."""
    if von != bis or bestaetigt:
        return
    frei = freie_tage_mit_wochenende(von, bis)
    if von in frei:
        raise PlanungsFehler(
            "feiertag_bestaetigung",
            _("%(datum)s ist ein freier Tag (%(name)s). Trotzdem einteilen?")
            % {"datum": date_format(von, "D d.m.Y"), "name": frei[von]},
            status=409,
            daten={"feiertag": frei[von], "datum": von.isoformat()},
        )


def _sperren_und_pruefen(modell, konto, objekt_id, version):
    objekt = modell.objects.select_for_update().select_related("person").filter(pk=objekt_id).first()
    if objekt is None:
        raise PlanungsFehler("geloescht", _("Der Eintrag wurde inzwischen gelöscht."), status=409)
    _pruefe_recht(konto, objekt.person)
    if als_zahl(version) != objekt.version:
        raise PlanungsFehler(
            "konflikt",
            _("Der Eintrag wurde inzwischen von jemand anderem geändert. Die Ansicht wurde aktualisiert."),
            status=409,
            daten={"aktuell": als_dict(objekt)},
        )
    return objekt


def _protokolldaten(objekt):
    daten = {"person": objekt.person, "von": objekt.von, "bis": objekt.bis}
    if isinstance(objekt, Einteilung):
        daten["aufgabe"] = objekt.aufgabe_id
    return daten


# --- Einteilungen ---

def einteilung_anlegen(konto, *, aufgabe, person, von, bis, feiertag_bestaetigt=False, client_id=None):
    _pruefe_recht(konto, person)
    _pruefe_nicht_archiviert(person)
    _pruefe_auswaehlbar(person)
    _pruefe_zeitraum(von, bis)
    _pruefe_feiertag(von, bis, feiertag_bestaetigt)
    with transaction.atomic():
        einteilung = Einteilung.objects.create(
            aufgabe=aufgabe, person=person, von=von, bis=bis, erstellt_von=konto.person
        )
        protokollieren(konto, "einteilung", einteilung.pk, "angelegt",
                       _protokolldaten(einteilung), aufgabe_id=aufgabe.pk)
        _melden("einteilung", "angelegt", einteilung, [person.pk], von, bis, konto, client_id)
        _benachrichtigen(konto, einteilung, "angelegt")
    return einteilung


def _aendern(modell, art, konto, objekt_id, *, version, person=None, von=None, bis=None,
             feiertag_bestaetigt=False, client_id=None):
    with transaction.atomic():
        objekt = _sperren_und_pruefen(modell, konto, objekt_id, version)
        alt_person, alt_von, alt_bis = objekt.person, objekt.von, objekt.bis
        neue_person = person or alt_person
        neu_von = von or alt_von
        neu_bis = bis or alt_bis
        if neue_person.pk != alt_person.pk:
            _pruefe_recht(konto, neue_person)
            _pruefe_auswaehlbar(neue_person)
        _pruefe_nicht_archiviert(neue_person)
        _pruefe_zeitraum(neu_von, neu_bis)
        if modell is Einteilung and (neu_von, neu_bis) != (alt_von, alt_bis):
            _pruefe_feiertag(neu_von, neu_bis, feiertag_bestaetigt)

        alt = _protokolldaten(objekt)
        objekt.person, objekt.von, objekt.bis = neue_person, neu_von, neu_bis
        objekt.version += 1
        objekt.save()
        protokollieren(konto, art, objekt.pk, "geaendert", aenderungen(alt, _protokolldaten(objekt)),
                       aufgabe_id=getattr(objekt, "aufgabe_id", None))
        _melden(art, "geaendert", objekt, [alt_person.pk, neue_person.pk],
                min(alt_von, neu_von), max(alt_bis, neu_bis), konto, client_id)
        if modell is Einteilung:
            _benachrichtigen(konto, objekt, "geaendert", alt_person=alt_person)
    return objekt


def _loeschen(modell, art, konto, objekt_id, *, version, client_id=None):
    with transaction.atomic():
        objekt = _sperren_und_pruefen(modell, konto, objekt_id, version)
        daten = _protokolldaten(objekt)
        aufgabe_id = getattr(objekt, "aufgabe_id", None)
        if modell is Einteilung:
            _benachrichtigen(konto, objekt, "geloescht")
        _melden(art, "geloescht", objekt, [objekt.person_id], objekt.von, objekt.bis, konto, client_id)
        objekt_pk = objekt.pk
        objekt.delete()
        protokollieren(konto, art, objekt_pk, "geloescht", daten, aufgabe_id=aufgabe_id)


def einteilung_aendern(konto, einteilung_id, **kwargs):
    return _aendern(Einteilung, "einteilung", konto, einteilung_id, **kwargs)


def einteilung_loeschen(konto, einteilung_id, **kwargs):
    _loeschen(Einteilung, "einteilung", konto, einteilung_id, **kwargs)


# --- Abwesenheiten (ohne Feiertagsbestätigung, ohne Aufgabenbezug) ---

def abwesenheit_anlegen(konto, *, person, von, bis, client_id=None):
    _pruefe_recht(konto, person)
    _pruefe_nicht_archiviert(person)
    _pruefe_auswaehlbar(person)
    _pruefe_zeitraum(von, bis)
    with transaction.atomic():
        abwesenheit = Abwesenheit.objects.create(person=person, von=von, bis=bis, erstellt_von=konto.person)
        protokollieren(konto, "abwesenheit", abwesenheit.pk, "angelegt", _protokolldaten(abwesenheit))
        _melden("abwesenheit", "angelegt", abwesenheit, [person.pk], von, bis, konto, client_id)
    return abwesenheit


def abwesenheit_aendern(konto, abwesenheit_id, **kwargs):
    kwargs.pop("feiertag_bestaetigt", None)
    return _aendern(Abwesenheit, "abwesenheit", konto, abwesenheit_id, **kwargs)


def abwesenheit_loeschen(konto, abwesenheit_id, **kwargs):
    _loeschen(Abwesenheit, "abwesenheit", konto, abwesenheit_id, **kwargs)


# --- Tagesinfo (Info-Zeile unter den Wochentagen, für alle sichtbar) ---

def tagesinfo_setzen(konto, datum, text, client_id=None):
    """Setzt den Freitext eines Tages; leerer Text entfernt ihn. Gibt den gespeicherten Text zurück."""
    if not rechte.hat_planungsansicht(konto):
        raise PlanungsFehler("keine_berechtigung", _("Sie dürfen die Info-Zeile nicht bearbeiten."), status=403)
    text = " ".join((text or "").split())
    if len(text) > MAX_INFO_ZEICHEN:
        raise PlanungsFehler(
            "zu_lang", _("Die Info darf höchstens %(n)s Zeichen lang sein.") % {"n": MAX_INFO_ZEICHEN}
        )
    with transaction.atomic():
        info = TagesInfo.objects.select_for_update().filter(datum=datum).first()
        alt = info.text if info else ""
        if alt == text:
            return text
        if not text:
            info_pk = info.pk
            info.delete()
            protokollieren(konto, "tagesinfo", info_pk, "geloescht", {"datum": datum, "text": alt})
            info.pk = info_pk
        elif info:
            info.text, info.geaendert_von = text, konto.person
            info.save()
            protokollieren(konto, "tagesinfo", info.pk, "geaendert", {"datum": datum, "text": [alt, text]})
        else:
            info = TagesInfo.objects.create(datum=datum, text=text, geaendert_von=konto.person)
            protokollieren(konto, "tagesinfo", info.pk, "angelegt", {"datum": datum, "text": text})
        _melden("tagesinfo", "geaendert", info, [], datum, datum, konto, client_id, alle=True)
    return text


def tagesfreigabe_setzen(konto, datum, stufe_id, client_id=None):
    """Tagesfreigabe eines Tags setzen; leer („keine Freigabe“) entfernt sie. Gibt die Kennung der Stufe und den
    Namen der Person zurück, die sie gesetzt hat (bei „keine Freigabe“ beide leer)."""
    if not rechte.hat_planungsansicht(konto):
        raise PlanungsFehler("keine_berechtigung", _("Sie dürfen die Tagesfreigabe nicht bearbeiten."), status=403)
    stufe = None
    if stufe_id:
        try:
            stufe = FreigabeStufe.objects.get(pk=int(stufe_id))
        except (FreigabeStufe.DoesNotExist, TypeError, ValueError):
            raise PlanungsFehler("ungueltig", _("Unbekannte Freigabestufe.")) from None
    with transaction.atomic():
        eintrag = Tagesfreigabe.objects.select_for_update(of=("self",)).select_related("stufe", "geaendert_von").filter(
            datum=datum).first()
        alt = eintrag.stufe if eintrag else None
        if alt == stufe:
            von = eintrag.geaendert_von.anzeigename if eintrag and eintrag.geaendert_von else ""
            return (str(stufe.pk) if stufe else ""), von
        if stufe is None:
            eintrag_pk = eintrag.pk
            eintrag.delete()
            eintrag.pk = eintrag_pk
            protokollieren(konto, "tagesfreigabe", eintrag_pk, "geloescht", {"datum": datum, "stufe": alt.name})
        elif eintrag:
            eintrag.stufe, eintrag.geaendert_von = stufe, konto.person
            eintrag.save()
            protokollieren(konto, "tagesfreigabe", eintrag.pk, "geaendert",
                           {"datum": datum, "stufe": [alt.name, stufe.name]})
        else:
            eintrag = Tagesfreigabe.objects.create(datum=datum, stufe=stufe, geaendert_von=konto.person)
            protokollieren(konto, "tagesfreigabe", eintrag.pk, "angelegt", {"datum": datum, "stufe": stufe.name})
        wert = str(stufe.pk) if stufe else ""
        von = konto.person.anzeigename if stufe else ""
        _melden("tagesfreigabe", "geaendert", eintrag, [], datum, datum, konto, client_id, alle=True,
                extra={"stufe": wert, "freigabe_von": von})
    return wert, von


def _benachrichtigen(konto, einteilung, aktion, alt_person=None):
    """Benachrichtigung „Einteilung geändert“ an die betroffene(n) Person(en)."""
    from zusammenarbeit.dienste import einteilung_benachrichtigen

    einteilung_benachrichtigen(konto, einteilung, aktion, alt_person=alt_person)
