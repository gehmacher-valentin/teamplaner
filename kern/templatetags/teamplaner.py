"""Template-Helfer: Avatare, Status, Datumsangaben, Kommentartext mit Erwähnungen."""

import re
from datetime import date

from django import template
from django.utils.formats import date_format
from django.utils.html import escape, format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

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


