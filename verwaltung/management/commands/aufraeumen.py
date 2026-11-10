"""Lösch- und Aufbewahrungsfristen sofort anwenden (läuft sonst täglich im Dienst mails_versenden).

    sudo teamplaner verwalten aufraeumen
"""

from django.core.management.base import BaseCommand

from verwaltung.aufraeumen import aufraeumen


class Command(BaseCommand):
    help = "Löscht Protokolle, Benachrichtigungen und Daten deaktivierter Konten nach den Fristen."

    def handle(self, *args, **o):
        for bereich, anzahl in aufraeumen().items():
            self.stdout.write(f"{bereich}: {anzahl}")
