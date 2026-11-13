"""E-Mail-Benachrichtigungen verschicken.

    python manage.py mails_versenden              # einmal alle offenen
    python manage.py mails_versenden --dauerhaft  # Dienst: prüft alle paar Sekunden

Als Dienst räumt er außerdem einmal am Tag nach den Lösch- und Aufbewahrungsfristen auf
(verwaltung.aufraeumen) und warnt bei überschrittenen Lieferterminen (bestellungen.warnungen, einmal je
Kalendertag) – so braucht es dafür keinen eigenen Zeitplan auf dem Server.

Der Dienst meldet über ``logging`` (ungepuffert nach stderr, also ins Journal), nicht über stdout:
ohne Terminal puffert Python stdout blockweise, und die wenigen Zeilen am Tag kämen nie an. Je
E-Mail schreibt ``zusammenarbeit.mail`` eine Zeile. Was wann an wen ging, zeigt ``mail_protokoll``.
"""

import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from bestellungen.warnungen import liefertermine_pruefen
from verwaltung.aufraeumen import aufraeumen
from zusammenarbeit.mail import mail_aktiv, offene_versenden
from zusammenarbeit.mailverlauf import zahlen

log = logging.getLogger(__name__)
AUFRAEUMEN_SEKUNDEN = 24 * 3600


class Command(BaseCommand):
    help = "Verschickt offene E-Mail-Benachrichtigungen."

    def add_arguments(self, parser):
        parser.add_argument("--dauerhaft", action="store_true", help="als Dienst laufen lassen")
        parser.add_argument("--intervall", type=float, default=5.0, help="Sekunden zwischen zwei Durchläufen")

    def handle(self, *args, **o):
        if not o["dauerhaft"]:
            self.einmal()
            return
        log.info("Versanddienst gestartet, Durchlauf alle %g Sekunden.", o["intervall"])
        aktiv = None
        naechstes_aufraeumen = 0.0
        geprueft_am = None
        while True:
            close_old_connections()
            if mail_aktiv() != aktiv:  # beim Start und wenn der Versand in den Einstellungen umgeschaltet wird
                aktiv = mail_aktiv()
                if aktiv:
                    log.info("E-Mail-Versand ist eingeschaltet.")
                else:
                    log.warning("Versand abgeschaltet oder kein SMTP-Server eingerichtet (EMAIL_HOST): "
                                "es wird nichts verschickt.")
            if timezone.localdate() != geprueft_am:
                try:
                    anzahl = liefertermine_pruefen()
                    geprueft_am = timezone.localdate()
                    if anzahl:
                        log.info("Liefertermin-Warnungen: %s", anzahl)
                except Exception:  # noqa: BLE001 – Versand soll trotzdem weiterlaufen
                    log.exception("Prüfung der Liefertermine fehlgeschlagen")
            if time.monotonic() >= naechstes_aufraeumen:
                naechstes_aufraeumen = time.monotonic() + AUFRAEUMEN_SEKUNDEN
                try:
                    log.info("Aufgeräumt: %s", aufraeumen())
                except Exception:  # noqa: BLE001 – Versand soll trotzdem weiterlaufen
                    log.exception("Aufräumen fehlgeschlagen")
            offene_versenden()  # je E-Mail eine Protokollzeile (zusammenarbeit.mail)
            time.sleep(o["intervall"])

    def einmal(self):
        """Ein Versandlauf, kein Protokoll: verschickt, was noch offen ist. Läuft der Dienst, ist meist
        nichts mehr offen."""
        if not mail_aktiv():
            self.stdout.write("Versand abgeschaltet oder kein SMTP-Server konfiguriert (EMAIL_HOST) – es wird nichts verschickt.")
            return
        anzahl = offene_versenden()
        offen = zahlen()["offen"]
        if anzahl:
            self.stdout.write(f"{anzahl} E-Mail(s) verschickt.")
        elif not offen:
            self.stdout.write("Keine offenen E-Mails, nichts zu verschicken.")
        if offen:
            self.stdout.write(f"{offen} E-Mail(s) noch offen (Versand fehlgeschlagen, wird erneut versucht).")
        self.stdout.write("Was wann an wen verschickt wurde: mail_protokoll")
