"""E-Mail-Benachrichtigungen verschicken.

    python manage.py mails_versenden              # einmal alle offenen
    python manage.py mails_versenden --dauerhaft  # Dienst: prüft alle paar Sekunden

Als Dienst räumt er außerdem einmal am Tag nach den Lösch- und Aufbewahrungsfristen auf
(kern.aufraeumen) und warnt bei überschrittenen Lieferterminen (bestellungen.warnungen, einmal je
Kalendertag) – so braucht es dafür keinen eigenen Zeitplan auf dem Server.
"""

import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from bestellungen.warnungen import liefertermine_pruefen
from kern.aufraeumen import aufraeumen
from zusammenarbeit.mail import mail_aktiv, offene_versenden

log = logging.getLogger(__name__)
AUFRAEUMEN_SEKUNDEN = 24 * 3600


class Command(BaseCommand):
    help = "Verschickt offene E-Mail-Benachrichtigungen."

    def add_arguments(self, parser):
        parser.add_argument("--dauerhaft", action="store_true", help="als Dienst laufen lassen")
        parser.add_argument("--intervall", type=float, default=5.0, help="Sekunden zwischen zwei Durchläufen")

    def handle(self, *args, **o):
        if not mail_aktiv():
            self.stdout.write("Versand abgeschaltet oder kein SMTP-Server konfiguriert (EMAIL_HOST) – es wird nichts verschickt.")
        if not o["dauerhaft"]:
            self.stdout.write(f"{offene_versenden()} E-Mail(s) verschickt.")
            return
        naechstes_aufraeumen = 0.0
        geprueft_am = None
        while True:
            close_old_connections()
            if timezone.localdate() != geprueft_am:
                try:
                    anzahl = liefertermine_pruefen()
                    geprueft_am = timezone.localdate()
                    if anzahl:
                        self.stdout.write(f"Liefertermin-Warnungen: {anzahl}")
                except Exception:  # noqa: BLE001 – Versand soll trotzdem weiterlaufen
                    log.exception("Prüfung der Liefertermine fehlgeschlagen")
            if time.monotonic() >= naechstes_aufraeumen:
                naechstes_aufraeumen = time.monotonic() + AUFRAEUMEN_SEKUNDEN
                try:
                    self.stdout.write(f"Aufgeräumt: {aufraeumen()}")
                except Exception:  # noqa: BLE001 – Versand soll trotzdem weiterlaufen
                    log.exception("Aufräumen fehlgeschlagen")
            anzahl = offene_versenden()
            if anzahl:
                self.stdout.write(f"{anzahl} E-Mail(s) verschickt.")
            time.sleep(o["intervall"])
