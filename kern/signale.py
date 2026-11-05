"""Reaktionen auf Anmeldung und Abmeldung (registriert in KernConfig.ready)."""

import time
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.signals import user_logged_in
from django.dispatch import receiver
from django.utils import timezone


@receiver(user_logged_in)
def sitzung_beginnen(sender, request, user, **kwargs):
    """Feste Frist ab der Anmeldung: einmal im Monat neu anmelden, egal wie oft man die Seite nutzt."""
    from .middleware import LETZTE_AKTIVITAET

    if request is None or not hasattr(request, "session"):
        return
    request.session.set_expiry(timezone.now() + timedelta(days=settings.TEAMPLANER_SITZUNG_TAGE))
    request.session[LETZTE_AKTIVITAET] = time.time()
