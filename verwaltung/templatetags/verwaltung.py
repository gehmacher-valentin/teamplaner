"""Template-Helfer der Verwaltung: Protokolltext und Unternavigation der Einstellungen."""

from django import template
from django.utils.translation import gettext_lazy

from verwaltung.einstellungen import unternavigation
from zusammenarbeit.verlauf import verlauf_text, wert_text, zeitraum_text

register = template.Library()


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
    if eintrag.objekt_typ in {"aufgabe", "einteilung", "unteraufgabe", "anhang", "abhaengigkeit"}:
        text = verlauf_text(eintrag)
        if eintrag.aufgabe_id:
            text += f" (#{eintrag.aufgabe_id})"
        return text
    d = eintrag.daten
    kopf = f"{OBJEKTE.get(eintrag.objekt_typ, eintrag.objekt_typ)} {AKTIONEN.get(eintrag.aktion, eintrag.aktion)}"
    if eintrag.objekt_typ == "abwesenheit" and eintrag.aktion != "geaendert":
        return f"{kopf}: {wert_text(d.get('person'))}, {zeitraum_text(d)}"
    teile = []
    for schluessel, wert in d.items():
        if isinstance(wert, list) and len(wert) == 2 and eintrag.aktion == "geaendert":
            teile.append(f"{schluessel}: {wert_text(wert[0])} → {wert_text(wert[1])}")
        elif isinstance(wert, list):
            teile.append(f"{schluessel}: {', '.join(map(str, wert)) or '–'}")
        elif isinstance(wert, dict) and "name" not in wert:
            teile.append(f"{schluessel}: {', '.join(f'{k}={v}' for k, v in wert.items()) or '–'}")
        else:
            teile.append(f"{schluessel}: {wert_text(wert)}")
    return f"{kopf}: {'; '.join(teile)}" if teile else kopf


@register.inclusion_tag("kern/_einst_nav.html", takes_context=True)
def einstellungen_nav(context):
    """Unternavigation des Einstellungsbereichs: nur Seiten, die das Konto öffnen darf."""
    return {"gruppen": unternavigation(context["request"].user, context.get("einst_aktiv"))}
