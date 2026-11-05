"""Template-Helfer: Avatare, Status, Datumsangaben, Kommentartext mit Erwähnungen."""

import re
from datetime import date

from django import template
from django.utils.formats import date_format
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy

register = template.Library()


@register.simple_tag
def avatar(person, groesse=""):
    if person is None:
        return format_html('<span class="avatar avatar--leer{}" aria-hidden="true">–</span>',
                           f" avatar--{groesse}" if groesse else "")
    klassen = ["avatar"]
    if groesse:
        klassen.append(f"avatar--{groesse}")
    if person.ist_platzhalter:
        klassen.append("avatar--platzhalter")
    else:
        klassen.append(f"av-{person.pk % 8}")
    if person.archiviert:
        klassen.append("avatar--archiviert")
    titel = person.anzeigename + (_(" · Platzhalter") if person.ist_platzhalter else "")
    if person.foto:
        return format_html('<img class="{} avatar--foto" src="{}" alt="" title="{}">',
                           " ".join(klassen), person.foto_url, titel)
    return format_html('<span class="{}" title="{}" aria-hidden="true">{}</span>', " ".join(klassen), titel, person.initialen)


@register.simple_tag
def person_name(person):
    """Name mit Hinweis auf Platzhalter/Archiv."""
    if person is None:
        return _("Nicht zugewiesen")
    zusatz = []
    if person.ist_platzhalter:
        zusatz.append(_("Platzhalter"))
    if person.archiviert:
        zusatz.append(_("archiviert"))
    if zusatz:
        return format_html("{} <span class=\"gedaempft klein\">({})</span>", person.anzeigename, ", ".join(zusatz))
    return person.anzeigename


@register.filter
def status_klasse(status):
    return f"badge st-{status.farbe}" if status else "badge"


@register.filter
def datum_kurz(wert):
    if not wert:
        return ""
    return date_format(wert, "d.m.")


@register.filter
def datum_lang(wert):
    if not wert:
        return ""
    return date_format(wert, "D d.m.Y")


@register.filter
def ueberfaellig(wert):
    return bool(wert) and wert < date.today()


@register.filter
def personentage(wert):
    if wert is None:
        return ""
    zahl = float(wert)
    text = f"{zahl:g}".replace(".", ",")
    return f"{text} {_('Tag') if zahl == 1 else _('Tage')}"


ERWAEHNUNG = re.compile(r"@\[(\d+)\]")


@register.simple_tag
def kommentartext(kommentar, personen):
    """Ersetzt @[id] durch hervorgehobene Namen; ``personen`` ist {id: Person}."""
    teile = []
    letzte = 0
    text = kommentar.text
    for treffer in ERWAEHNUNG.finditer(text):
        teile.append(escape(text[letzte:treffer.start()]))
        person = personen.get(int(treffer.group(1)))
        if person is None:
            teile.append(escape(treffer.group(0)))
        else:
            klasse = "erwaehnung erwaehnung--platzhalter" if person.ist_platzhalter else "erwaehnung"
            teile.append(format_html('<span class="{}">@{}</span>', klasse, person.anzeigename))
        letzte = treffer.end()
    teile.append(escape(text[letzte:]))
    return mark_safe("".join(str(t) for t in teile))


@register.filter
def dateigroesse(wert):
    if wert is None:
        return ""
    for einheit in ["B", "KB", "MB", "GB"]:
        if wert < 1024 or einheit == "GB":
            return f"{wert:.0f} {einheit}" if einheit == "B" else f"{wert:.1f} {einheit}".replace(".", ",")
        wert /= 1024
    return ""


@register.filter
def dateiendung(name):
    """„Zeichnung.PDF“ → „PDF“ (Beschriftung der Anhang-Kachel ohne Vorschau)."""
    teile = (name or "").rsplit(".", 1)
    return teile[1].upper()[:5] if len(teile) == 2 else ""


OBJEKTE = {
    "konto": gettext_lazy("Konto"), "abwesenheit": gettext_lazy("Abwesenheit"), "platzhalter": gettext_lazy("Platzhalter"),
    "ansicht": gettext_lazy("Teamplaner-Ansicht"), "gantt_ansicht": gettext_lazy("Gantt-Ansicht"), "projekt": gettext_lazy("Projekt"), "status": gettext_lazy("Status"),
    "gewerk": gettext_lazy("Gewerk"), "bereich": gettext_lazy("Bereich"), "freiertag": gettext_lazy("Freier Tag"), "tag": gettext_lazy("Tag"),
    "notizordner": gettext_lazy("Notizordner"), "tagesfreigabe": gettext_lazy("Tagesfreigabe"), "freigabestufe": gettext_lazy("Freigabestufe"),
    "einstellungen": gettext_lazy("Einstellungen"), "bestellung": gettext_lazy("Bestellung"),
}
AKTIONEN = {
    "angelegt": gettext_lazy("angelegt"), "geaendert": gettext_lazy("geändert"), "geloescht": gettext_lazy("gelöscht"),
    "deaktiviert": gettext_lazy("deaktiviert"), "reaktiviert": gettext_lazy("reaktiviert"), "archivieren": gettext_lazy("archiviert"),
    "archiviert": gettext_lazy("archiviert"), "wiederherstellen": gettext_lazy("wiederhergestellt"), "wiederhergestellt": gettext_lazy("wiederhergestellt"),
    "link_erzeugt": gettext_lazy("Passwort-Link erzeugt"), "passwort_gesetzt": gettext_lazy("Passwort festgelegt"),
    "link_per_mail": gettext_lazy("Passwort-Link per E-Mail an die Person geschickt"),
    "passwort_zurueckgesetzt": gettext_lazy("Passwort zurückgesetzt"),
    "passwort_geaendert": gettext_lazy("Passwort geändert"),
    "aus_platzhalter": gettext_lazy("aus Platzhalter angelegt"),
    "foto_entfernt": gettext_lazy("Foto entfernt"),
    "zwei_faktor_eingerichtet": gettext_lazy("Zwei-Faktor-Anmeldung eingerichtet"),
    "zwei_faktor_ausgeschaltet": gettext_lazy("Zwei-Faktor-Anmeldung ausgeschaltet"),
    "zwei_faktor_zurueckgesetzt": gettext_lazy("Zwei-Faktor-Anmeldung zurückgesetzt"),
    "ersatzcodes_erneuert": gettext_lazy("Ersatzcodes erneuert"),
    "daten_entfernt": gettext_lazy("persönliche Daten nach der Frist entfernt"),
    "reset_angefordert": gettext_lazy("Passwort-Link per E-Mail angefordert"),
    "projekt_hinzugefuegt": gettext_lazy("Projekt hinzugefügt"),
    "projekt_entfernt": gettext_lazy("Projekt entfernt"),
}


@register.simple_tag
def protokoll_text(eintrag):
    """Lesbare Zusammenfassung eines Protokolleintrags."""
    from zusammenarbeit.views import _wert, _zeitraum, verlauf_text

    if eintrag.objekt_typ in {"aufgabe", "einteilung", "unteraufgabe", "anhang", "abhaengigkeit"}:
        text = verlauf_text(eintrag)
        if eintrag.aufgabe_id:
            text += f" (#{eintrag.aufgabe_id})"
        return text
    d = eintrag.daten
    kopf = f"{OBJEKTE.get(eintrag.objekt_typ, eintrag.objekt_typ)} {AKTIONEN.get(eintrag.aktion, eintrag.aktion)}"
    if eintrag.objekt_typ == "abwesenheit" and eintrag.aktion != "geaendert":
        return f"{kopf}: {_wert(d.get('person'))}, {_zeitraum(d)}"
    teile = []
    for schluessel, wert in d.items():
        if isinstance(wert, list) and len(wert) == 2 and eintrag.aktion == "geaendert":
            teile.append(f"{schluessel}: {_wert(wert[0])} → {_wert(wert[1])}")
        elif isinstance(wert, list):
            teile.append(f"{schluessel}: {', '.join(map(str, wert)) or '–'}")
        elif isinstance(wert, dict) and "name" not in wert:
            teile.append(f"{schluessel}: {', '.join(f'{k}={v}' for k, v in wert.items()) or '–'}")
        else:
            teile.append(f"{schluessel}: {_wert(wert)}")
    return f"{kopf}: {'; '.join(teile)}" if teile else kopf


@register.inclusion_tag("kern/_einst_nav.html", takes_context=True)
def einstellungen_nav(context):
    """Unternavigation des Einstellungsbereichs: nur Seiten, die das Konto öffnen darf."""
    from kern.einstellungen import unternavigation

    return {"gruppen": unternavigation(context["request"].user, context.get("einst_aktiv"))}
