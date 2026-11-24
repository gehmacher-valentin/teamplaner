"""Rolle ändern, Konten deaktivieren und reaktivieren – gemeinsam für Oberfläche und Kommandozeile.

``akteur=None`` steht für die Kommandozeile: keine Rechteprüfung, aber auch dort bleibt immer ein Admin übrig.
"""

from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.utils import timezone

from kern import rechte
from kern.models import Konto, Rolle
from kern.protokoll import protokollieren
from zusammenarbeit.mail import sicherheitshinweis

from .freigaben import herabstufen


class LetzterAdmin(Exception):
    """Ohne dieses Konto gäbe es keinen Admin mehr, der sich anmelden kann."""


def anderer_admin_vorhanden(ziel, konten=None):
    """Gibt es außer ``ziel`` einen aktiven Admin mit gesetztem Passwort, der sich schon einmal angemeldet
    hat? Bei einem nie benutzten Konto steht nicht fest, dass jemand hineinkommt."""
    if konten is None:
        konten = Konto.objects.select_related("person").filter(rolle=Rolle.ADMIN)
    return any(k.pk != ziel.pk and k.is_active and k.has_usable_password() and k.last_login is not None for k in konten)


def _sperren(akteur, ziel):
    """Alle Admin-Konten sperren und Akteur und Ziel danach frisch lesen – sonst könnten sich zwei
    Admins gleichzeitig gegenseitig entfernen. Nur innerhalb einer Transaktion."""
    admins = list(Konto.objects.select_for_update().select_related("person")
                  .filter(rolle=Rolle.ADMIN).order_by("pk"))
    frisch = Konto.objects.select_related("person")
    return admins, akteur and frisch.get(pk=akteur.pk), frisch.get(pk=ziel.pk)


@transaction.atomic
def rolle_setzen(akteur, ziel, rolle):
    """Gibt zurück, ob sich die Rolle geändert hat; aktualisiert auch ``ziel``."""
    admins, akteur, konto = _sperren(akteur, ziel)
    if akteur and not rechte.darf_rolle_vergeben(akteur, konto, rolle):
        raise PermissionDenied
    alt = konto.rolle
    if alt == rolle:
        return False
    war_admin = alt == Rolle.ADMIN
    if war_admin:
        if not anderer_admin_vorhanden(konto, admins):
            raise LetzterAdmin
        konto.admin_bis = timezone.now()
    konto.rolle = rolle
    konto.save(update_fields=["rolle", "admin_bis"])
    ziel.rolle, ziel.admin_bis = konto.rolle, konto.admin_bis
    protokollieren(akteur, "konto", konto.pk, "geaendert", {"person": konto.person, "rolle": [alt, rolle]})
    herabstufen(akteur, konto)  # unter Planer:in wird „Bearbeiten“ zu „Sehen“
    if war_admin:
        sicherheitshinweis(konto, "admin_entzogen")
    return True


@transaction.atomic
def deaktivieren(akteur, ziel):
    admins, akteur, konto = _sperren(akteur, ziel)
    if akteur and not rechte.darf_konto_deaktivieren(akteur, konto):
        raise PermissionDenied
    if not konto.is_active:
        return False
    if konto.rolle == Rolle.ADMIN and not anderer_admin_vorhanden(konto, admins):
        raise LetzterAdmin
    konto.person.archivieren()
    konto.zugang_stand += 1  # Sitzungen und offene Links gelten auch nach dem Reaktivieren nicht mehr
    konto.save(update_fields=["zugang_stand"])
    ziel.zugang_stand = konto.zugang_stand
    protokollieren(akteur, "konto", konto.pk, "deaktiviert", {"person": konto.person})
    if konto.rolle == Rolle.ADMIN:
        sicherheitshinweis(konto, "deaktiviert")
    return True


@transaction.atomic
def reaktivieren(akteur, ziel):
    _admins, akteur, konto = _sperren(akteur, ziel)
    if akteur and not rechte.darf_konto_deaktivieren(akteur, konto):
        raise PermissionDenied
    if konto.is_active:
        return False
    konto.person.wiederherstellen()
    if konto.daten_entfernt_am:  # bei einer späteren Deaktivierung wieder nach Frist bereinigen
        konto.daten_entfernt_am = None
        konto.save(update_fields=["daten_entfernt_am"])
    protokollieren(akteur, "konto", konto.pk, "reaktiviert", {"person": konto.person})
    return True
