"""Zentrale Rechteprüfung, immer auf dem Server.

Jede View und jeder API-Endpunkt fragt hier nach – nie direkt die Rolle. Die Tests in ``tests/test_rechte*.py``
prüfen sie für jede Rolle. Rechte im Teamplaner (wer wen sehen/einteilen darf)
stehen in ``planung.rechte``, weil sie zusätzlich von den Ansichtsfreigaben abhängen.
"""

from datetime import timedelta

from django.utils import timezone

from .models import ROLLEN_RANG, Rolle

# So lange nach dem Ende der Admin-Rolle bleibt die Anmeldung des Kontos für die Verwaltung gesperrt
ADMIN_SCHUTZFRIST = timedelta(days=7)


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


def _anderer_admin(konto, ziel):
    return ist_admin(konto) and ziel.rolle == Rolle.ADMIN and ziel.pk != konto.pk


def darf_konto_bearbeiten(konto, ziel):
    """Stammdaten, Freigaben, Foto: nur Konten mit niedrigerer Rolle – sonst könnten sich Kolleg:innen
    gleicher Rolle gegenseitig übernehmen. Dazu das eigene Konto."""
    return darf_konten_verwalten(konto) and (ziel.rang < konto.rang or ziel.pk == konto.pk)


def in_schutzfrist(ziel):
    return ziel.admin_bis is not None and timezone.now() < ziel.admin_bis + ADMIN_SCHUTZFRIST


def darf_anmeldung_verwalten(konto, ziel):
    """E-Mail, Passwort-Link und Zwei-Faktor-Anmeldung. Bei ehemaligen Admins erst nach der
    Schutzfrist – sonst ließe sich ein Admin-Konto herabstufen und gleich danach übernehmen."""
    return darf_konto_bearbeiten(konto, ziel) and (ziel.pk == konto.pk or not in_schutzfrist(ziel))


def darf_anmeldung_zuruecksetzen(konto, ziel):
    """Passwort-Link und Zurücksetzen der Zwei-Faktor-Anmeldung durch die Verwaltung. Nie für das eigene
    Konto: das geht nur mit dem Passwort unter „Anmeldung & Sicherheit“."""
    return ziel.pk != konto.pk and darf_anmeldung_verwalten(konto, ziel)


def nie_benutzt(ziel):
    """Noch nie ein Passwort gesetzt und nie angemeldet, z. B. eine Einladung an eine falsche Adresse. Ein
    fehlendes Passwort allein reicht nicht: das entsteht auch beim Zurücksetzen ohne E-Mail-Versand."""
    return not ziel.has_usable_password() and ziel.last_login is None


def darf_adresse_korrigieren(konto, ziel):
    """E-Mail-Adresse eines anderen Admins, solange das Konto nie benutzt wurde – es gibt noch nichts zu übernehmen."""
    return _anderer_admin(konto, ziel) and nie_benutzt(ziel)


def darf_link_mailen(konto, ziel):
    """Anderen aktiven Admins einen Einladungs- oder Passwort-Link an ihre hinterlegte Adresse schicken,
    ohne ihn zu sehen. Alles andere an ihrer Anmeldung bleibt gesperrt."""
    return _anderer_admin(konto, ziel) and ziel.is_active


def darf_konto_deaktivieren(konto, ziel):
    """Deaktivieren und reaktivieren; Admins auch andere Admins, niemand sich selbst."""
    if ziel.pk == konto.pk:
        return False
    return darf_konto_bearbeiten(konto, ziel) or _anderer_admin(konto, ziel)


def darf_konto_oeffnen(konto, ziel):
    """Seite der Person in den Einstellungen. Bei anderen Admins nur Rolle und Deaktivieren."""
    return darf_konto_bearbeiten(konto, ziel) or _anderer_admin(konto, ziel)


def darf_rolle_vergeben(konto, ziel, neue_rolle):
    """Die eigene Rolle ändern nur Admins. Dass ein Admin übrig bleibt, prüft ``verwaltung.konten``."""
    if ziel.pk == konto.pk and not ist_admin(konto):
        return darf_konten_verwalten(konto) and neue_rolle == ziel.rolle
    return darf_konto_oeffnen(konto, ziel) and neue_rolle in vergebbare_rollen(konto)


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
    """Projekte anlegen, bearbeiten, archivieren."""
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
