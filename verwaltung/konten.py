"""Rolle ändern, Konten deaktivieren und reaktivieren – gemeinsam für Oberfläche und Kommandozeile.

``akteur=None`` steht für die Kommandozeile: keine Rechteprüfung, aber auch dort bleibt immer ein Admin übrig.
"""

from django.core.exceptions import PermissionDenied
from django.db import IntegrityError, transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from kern import rechte
from kern.models import EmailWechsel, Konto, Rolle
from kern.protokoll import protokollieren
from zusammenarbeit.mail import email_bestaetigung_senden, sicherheitshinweis

from .freigaben import herabstufen


class LetzterAdmin(Exception):
    """Ohne dieses Konto gäbe es keinen Admin mehr, der sich anmelden kann."""


class EmailVergeben(Exception):
    """Die Adresse gehört inzwischen zu einem anderen Konto."""


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
        if not rechte.nie_benutzt(konto):  # sonst gibt es nichts zu schützen
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
def adresse_korrigieren(akteur, ziel, email):
    """Falsche Adresse eines noch nie benutzten Admin-Kontos. Der alte Einladungslink wird dadurch ungültig.
    Kein Sicherheitshinweis an die bisherige Adresse: sie gehört womöglich jemand Fremdem."""
    _admins, akteur, konto = _sperren(akteur, ziel)
    if not rechte.darf_adresse_korrigieren(akteur, konto):
        raise PermissionDenied
    alt, konto.email = konto.email, email
    konto.save(update_fields=["email"])
    ziel.email = email
    protokollieren(akteur, "konto", konto.pk, "geaendert", {"person": konto.person, "email": [alt, email]})


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


# ---------- Eigene E-Mail-Adresse (das Passwort prüft die View) ----------

def offener_email_wechsel(konto):
    wechsel = EmailWechsel.objects.filter(konto=konto).first()
    return wechsel if wechsel is not None and wechsel.offen(konto) else None


def passender_email_wechsel(konto, schluessel):
    """Offener Wechsel dieses Kontos, zu dem der Link gehört, sonst None."""
    wechsel = offener_email_wechsel(konto)
    return wechsel if wechsel is not None and constant_time_compare(wechsel.schluessel, schluessel) else None


@transaction.atomic
def email_wechsel_beginnen(konto, email):
    """Die neue Adresse gilt erst nach der Bestätigung. Ein früherer offener Wechsel wird ersetzt.
    Gibt False zurück, wenn der E-Mail-Versand inzwischen abgeschaltet ist."""
    wechsel = EmailWechsel.objects.update_or_create(konto=konto, defaults={
        "email": email, "angefordert_am": timezone.now(), "stand": EmailWechsel.stand_von(konto)})[0]
    if not email_bestaetigung_senden(konto, wechsel):
        wechsel.delete()
        return False
    protokollieren(konto, "konto", konto.pk, "email_wechsel_angefordert", {"person": konto.person, "email": email})
    return True


@transaction.atomic
def email_wechsel_abbrechen(konto):
    konto = _eigenes_sperren(konto)  # nicht gleichzeitig mit dem Bestätigen
    wechsel = offener_email_wechsel(konto)
    if wechsel is None:
        return False
    wechsel.delete()
    protokollieren(konto, "konto", konto.pk, "email_wechsel_abgebrochen", {"person": konto.person, "email": wechsel.email})
    return True


@transaction.atomic
def email_wechsel_bestaetigen(konto, schluessel):
    """Gibt False zurück, wenn der Link nicht (mehr) gilt."""
    wechsel = passender_email_wechsel(_eigenes_sperren(konto), schluessel)
    if wechsel is None:
        return False
    eigene_email_setzen(konto, wechsel.email)
    return True


@transaction.atomic
def eigene_email_setzen(konto, email):
    """Aktualisiert auch ``konto``. Der Hinweis geht an die bisherige Adresse."""
    frisch = _eigenes_sperren(konto)
    alt, frisch.email = frisch.email, email
    try:
        with transaction.atomic():
            frisch.save(update_fields=["email"])
    except IntegrityError:
        raise EmailVergeben from None
    EmailWechsel.objects.filter(konto=frisch).delete()
    protokollieren(konto, "konto", frisch.pk, "geaendert", {"person": frisch.person, "email": [alt, email]})
    sicherheitshinweis(frisch, "email_geaendert", an=alt, neu=email)
    konto.email = email


def _eigenes_sperren(konto):
    return Konto.objects.select_for_update(of=("self",)).select_related("person").get(pk=konto.pk)
