"""Zentrale Rechteprüfung, immer auf dem Server.

Jede View und jeder API-Endpunkt fragt hier nach – nie direkt die Rolle. Die Tests in ``tests/test_rechte*.py``
prüfen sie für jede Rolle. Rechte im Teamplaner (wer wen sehen/einteilen darf)
stehen in ``planung.rechte``, weil sie zusätzlich von den Ansichtsfreigaben abhängen.
"""

from .models import ROLLEN_RANG, Rolle


def _aktiv(konto):
    return konto is not None and getattr(konto, "is_authenticated", False) and konto.is_active


def _mindestens(konto, rolle):
    return _aktiv(konto) and konto.rang >= ROLLEN_RANG[rolle]


def ist_admin(konto):
    return _aktiv(konto) and konto.rolle == Rolle.ADMIN


def sieht_alles_im_teamplaner(konto):
    """Admin und Bereichsleitung sehen und bearbeiten alle Personen."""
    return _mindestens(konto, Rolle.BEREICHSLEITUNG)


# --- System ---

def darf_systemeinstellungen(konto):
    """Feiertage/freie Tage, Status, Gewerke, Bereiche."""
    return ist_admin(konto)


def darf_konten_verwalten(konto):
    return _mindestens(konto, Rolle.BEREICHSLEITUNG)


def vergebbare_rollen(konto):
    """Rollen, die ``konto`` vergeben darf – Bereichsleitung bis zur eigenen Rolle."""
    if not darf_konten_verwalten(konto):
        return []
    return [r for r in Rolle if ROLLEN_RANG[r] <= konto.rang]


def darf_konto_bearbeiten(konto, ziel):
    """Ändern, deaktivieren, Links, Zwei-Faktor zurücksetzen: nur Konten mit niedrigerer Rolle –
    sonst könnten sich Kolleg:innen gleicher Rolle gegenseitig übernehmen. Dazu das eigene Konto
    (ohne Rolle). Admin-Konten anderer Admins nur über die Kommandozeile."""
    return darf_konten_verwalten(konto) and (ziel.rang < konto.rang or ziel.pk == konto.pk)


def darf_rolle_vergeben(konto, ziel, neue_rolle):
    if ziel.pk == konto.pk:
        return darf_konten_verwalten(konto) and neue_rolle == ziel.rolle
    return darf_konto_bearbeiten(konto, ziel) and neue_rolle in vergebbare_rollen(konto)


def darf_protokoll_sehen(konto):
    return _mindestens(konto, Rolle.BEREICHSLEITUNG)


def darf_erledigte_sehen(konto):
    """Protokoll gefiltert auf „wer hat wann welche Aufgabe erledigt“ – ab Planer:in."""
    return _mindestens(konto, Rolle.PLANER)


def darf_ansichten_verwalten(konto):
    return _mindestens(konto, Rolle.BEREICHSLEITUNG)


def darf_platzhalter_verwalten(konto):
    return _mindestens(konto, Rolle.PLANER)


def darf_planen(konto):
    """Rolle erlaubt grundsätzlich das Einteilen; für wen, regeln die Ansichtsfreigaben."""
    return _mindestens(konto, Rolle.PLANER)


# --- Projekte und Aufgaben ---

def darf_lesen(konto):
    """Projekte, Aufgaben und Kommentare lesen: alle angemeldeten Personen."""
    return _aktiv(konto)


def darf_projekte_verwalten(konto):
    """Projekte anlegen, bearbeiten, Tags vergeben, archivieren."""
    return _mindestens(konto, Rolle.PLANER)


def ist_projektmitglied(konto, projekt):
    if not _aktiv(konto):
        return False
    if projekt.projektleitung_id == konto.person_id:
        return True
    return projekt.mitglieder.filter(pk=konto.person_id).exists()


def darf_aufgaben_bearbeiten(konto, projekt):
    """Aufgaben anlegen und bearbeiten; Mitarbeiter:innen nur als Projektmitglied."""
    if _mindestens(konto, Rolle.PLANER):
        return True
    return (
        _aktiv(konto)
        and konto.rolle == Rolle.MITARBEITER
        and ist_projektmitglied(konto, projekt)
    )


def darf_bestellungen_bearbeiten(konto):
    """Bestellliste: lesen alle Angemeldeten, eintragen und ändern ab Mitarbeiter:in."""
    return _mindestens(konto, Rolle.MITARBEITER)


def darf_abschliessen_und_kommentieren(konto):
    return _mindestens(konto, Rolle.MITARBEITER)
