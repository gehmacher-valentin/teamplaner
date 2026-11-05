"""Zwei-Faktor-Anmeldung eines Kontos zurücksetzen, z. B. wenn ein Admin das Telefon verloren hat.

    sudo teamplaner verwalten zwei_faktor_zuruecksetzen admin@example.org

Admin-Konten lassen sich in der Oberfläche nicht von anderen Admins ändern; dafür gibt es diesen
Befehl. Für Admin und Bereichsleitung wird die Zwei-Faktor-Anmeldung bei der nächsten Anmeldung neu eingerichtet.
"""

from django.core.management.base import BaseCommand, CommandError

from kern import zwei_faktor
from kern.models import Konto
from kern.protokoll import protokollieren


class Command(BaseCommand):
    help = "Setzt die Zwei-Faktor-Anmeldung eines Kontos zurück."

    def add_arguments(self, parser):
        parser.add_argument("email")

    def handle(self, *args, **o):
        konto = Konto.objects.select_related("person").filter(email__iexact=o["email"].strip()).first()
        if konto is None:
            raise CommandError("Kein Konto mit dieser E-Mail.")
        zwei_faktor.zuruecksetzen(konto)
        protokollieren(None, "konto", konto.pk, "zwei_faktor_zurueckgesetzt", {"person": konto.person})
        self.stdout.write(self.style.SUCCESS(f"Zwei-Faktor-Anmeldung von {konto.email} zurückgesetzt."))
