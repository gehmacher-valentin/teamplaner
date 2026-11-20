"""Template-Helfer: Avatare, Status, Datumsangaben, Kommentartext mit Erwähnungen."""

import re

from django import template
from django.utils import timezone
from django.utils.formats import date_format
from django.utils.html import escape, format_html, format_html_join
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

register = template.Library()


@register.simple_tag
def avatar(person, groesse="", mit_titel=True):
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
    titel = format_html(' title="{}"', titel) if mit_titel else ""
    if person.foto:
        return format_html('<img class="{} avatar--foto" src="{}" alt=""{}>', " ".join(klassen), person.foto_url, titel)
    return format_html('<span class="{}"{} aria-hidden="true">{}</span>', " ".join(klassen), titel, person.initialen)


# Wie ANWESEND_HOECHSTENS in frontend/src/editor/gemeinsam.ts
STAPEL_HOECHSTENS = 5


@register.simple_tag
def avatarstapel(personen):
    """Überlappende runde Avatare wie „bearbeitet gerade“ bei Notizen (editor/gemeinsam.ts): der Name
    erscheint beim Zeigen oder Antippen, ab mehr als STAPEL_HOECHSTENS Personen fasst „+N“ den Rest zusammen."""
    personen = list(personen)
    zeigen = personen if len(personen) <= STAPEL_HOECHSTENS else personen[:STAPEL_HOECHSTENS - 1]

    def huelle(name, inhalt):
        return format_html('<span class="anwesend" tabindex="0" role="img" aria-label="{0}" data-name="{0}">{1}</span>',
                           name, inhalt)

    teile = [huelle(p.anzeigename, avatar(p, "klein", mit_titel=False)) for p in zeigen]
    rest = personen[len(zeigen):]
    if rest:
        teile.append(huelle(", ".join(p.anzeigename for p in rest),
                            format_html('<span class="avatar avatar--klein avatar--mehr" aria-hidden="true">+{}</span>',
                                        len(rest))))
    return format_html('<span class="avatarstapel">{}</span>', format_html_join("", "{}", ((t,) for t in teile)))


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
    return bool(wert) and wert < timezone.localdate()


@register.filter
def relativer_tag(wert):
    """„Gestern“, „Heute“ oder „Morgen“, sonst leer (Zeitzone der Anwendung)."""
    if not wert:
        return ""
    woerter = {-1: _("Gestern"), 0: _("Heute"), 1: _("Morgen")}
    return woerter.get((wert - timezone.localdate()).days, "")


@register.filter
def tag_relativ(wert, format="d.m."):
    """„Gestern“, „Heute“ oder „Morgen“, sonst das Datum im angegebenen Format."""
    if not wert:
        return ""
    return relativer_tag(wert) or date_format(wert, format)


@register.simple_tag
def faellig(wert, format="d.m.", leer="–"):
    """Fälligkeit als <time>: Gestern/Heute/Morgen oder Datum, das genaue Datum als Tooltip."""
    if not wert:
        return leer
    return format_html('<time datetime="{}" title="{}">{}</time>', wert.isoformat(),
                       date_format(wert, "D d.m.Y"), tag_relativ(wert, format))


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


