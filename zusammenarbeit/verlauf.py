"""Verlauf einer Aufgabe: Kommentare und protokollierte Änderungen als lesbare Einträge."""

import re

from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

from kern import rechte
from kern.models import Person, Protokolleintrag
from planung import rechte as planungsrechte

ERWAEHNUNG = re.compile(r"@\[(\d+)\]")

FELDNAMEN = {
    "titel": gettext_lazy("Titel"), "abschnitt": gettext_lazy("Abschnitt"), "verantwortlich": gettext_lazy("Verantwortlich"),
    "gewerk": gettext_lazy("Gewerk"), "beginn_am": gettext_lazy("Beginn"), "faellig_am": gettext_lazy("Fällig"),
    "status": gettext_lazy("Status"),
    "schaetzung_personentage": gettext_lazy("Schätzung"), "eltern": gettext_lazy("Hauptaufgabe"),
}


def wert_text(wert):
    if wert in (None, ""):
        return "–"
    if isinstance(wert, dict):
        return wert.get("name", "")
    if isinstance(wert, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", wert):
        return f"{wert[8:10]}.{wert[5:7]}.{wert[:4]}"
    return str(wert)


def zeitraum_text(daten):
    von, bis = wert_text(daten.get("von")), wert_text(daten.get("bis"))
    return von if von == bis else f"{von[:6]}–{bis}"


def verlauf_text(eintrag):
    d = eintrag.daten
    if eintrag.objekt_typ == "aufgabe":
        if eintrag.aktion == "angelegt":
            return _("hat die Aufgabe angelegt.")
        if eintrag.aktion == "geaendert":
            teile = []
            for feld, (alt, neu) in d.items():
                if feld == "beschreibung":
                    teile.append(_("Beschreibung bearbeitet"))
                elif feld in FELDNAMEN:
                    teile.append(f"{FELDNAMEN[feld]}: {wert_text(alt)} → {wert_text(neu)}")
            return _("hat geändert: %(teile)s") % {"teile": "; ".join(teile)}
    if eintrag.objekt_typ == "einteilung":
        person = wert_text(d.get("person"))
        if eintrag.aktion == "angelegt":
            return _("hat die Aufgabe auf %(person)s, %(zeitraum)s eingeplant.") % {"person": person, "zeitraum": zeitraum_text(d)}
        if eintrag.aktion == "geloescht":
            return _("hat die Einteilung von %(person)s (%(zeitraum)s) entfernt.") % {"person": person, "zeitraum": zeitraum_text(d)}
        teile = [f"{wert_text(a)} → {wert_text(n)}" for _feld, (a, n) in d.items()]
        return _("hat eine Einteilung geändert: %(teile)s") % {"teile": "; ".join(teile)}
    if eintrag.objekt_typ == "unteraufgabe":
        texte = {"angelegt": _("hat die Unteraufgabe „%(t)s“ angelegt."), "erledigt": _("hat „%(t)s“ erledigt."),
                 "wieder_offen": _("hat „%(t)s“ wieder geöffnet."), "geloescht": _("hat die Unteraufgabe „%(t)s“ gelöscht."),
                 "hierher": _("hat „%(t)s“ hierher als Unteraufgabe verschoben."),
                 "weg": _("hat die Unteraufgabe „%(t)s“ woandershin verschoben.")}
        return texte.get(eintrag.aktion, eintrag.aktion) % {"t": d.get("titel", "")}
    if eintrag.objekt_typ == "abhaengigkeit":
        werte = {"vorher": wert_text(d.get("vorher")), "nachher": wert_text(d.get("nachher"))}
        if eintrag.aktion == "angelegt":
            return _("hat festgelegt: „%(vorher)s“ vor „%(nachher)s“.") % werte
        return _("hat die Abhängigkeit „%(vorher)s“ vor „%(nachher)s“ entfernt.") % werte
    if eintrag.objekt_typ == "anhang":
        if eintrag.aktion == "angelegt":
            return _("hat „%(name)s“ angehängt.") % {"name": d.get("name", "")}
        return _("hat den Anhang „%(name)s“ entfernt.") % {"name": d.get("name", "")}
    return f"{eintrag.objekt_typ} {eintrag.aktion}"


def _einteilung_sichtbar(konto, eintrag, sichtbar):
    if eintrag.objekt_typ != "einteilung":
        return True
    if sichtbar is None:
        return True
    person = eintrag.daten.get("person") or {}
    return isinstance(person, dict) and person.get("id") in sichtbar


def verlauf_eintraege(konto, aufgabe):
    """Kommentare und Änderungen chronologisch. Einteilungen von Personen,
    die das Konto im Teamplaner nicht sehen darf, werden ausgelassen."""
    sichtbar = planungsrechte.sichtbare_personen_ids(konto)
    kommentare = list(aufgabe.kommentare.select_related("autor__konto"))
    erwaehnte_ids = {int(i) for k in kommentare for i in ERWAEHNUNG.findall(k.text)}
    personen = {p.pk: p for p in Person.objects.filter(pk__in=erwaehnte_ids).select_related("konto", "erstellt_von")}
    eintraege = []
    for k in kommentare:
        platzhalter = [personen[int(i)] for i in dict.fromkeys(ERWAEHNUNG.findall(k.text))
                       if int(i) in personen and personen[int(i)].ist_platzhalter]
        eintraege.append({"art": "kommentar", "zeit": k.erstellt_am, "kommentar": k, "personen": personen,
                          "platzhalter": platzhalter,
                          "darf_loeschen": k.autor_id == konto.person_id or rechte.ist_admin(konto)})
    for p in Protokolleintrag.objects.filter(aufgabe_id=aufgabe.pk).select_related("akteur"):
        if _einteilung_sichtbar(konto, p, sichtbar):
            eintraege.append({"art": "verlauf", "zeit": p.zeitpunkt, "akteur": p.akteur, "text": verlauf_text(p)})
    return sorted(eintraege, key=lambda e: e["zeit"])
