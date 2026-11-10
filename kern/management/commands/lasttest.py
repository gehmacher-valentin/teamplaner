"""Lasttest: Teamplaner mit 50 Personen × 20 Arbeitstagen.

    python manage.py lasttest

Legt in einer Transaktion 50 Personen mit je 6 Einteilungen und einer Abwesenheit an,
misst Laden des Rasters (4 Wochen) und Speichern einer Verschiebung über die API und
rollt danach alles zurück – die Datenbank bleibt unverändert.
"""

import statistics
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.test import Client
from django.utils import timezone

from kern.models import Bereich, Konto, Person, Rolle
from planung.kalender import montag
from planung.models import Abwesenheit, Einteilung
from projekte.models import Abschnitt, Aufgabe, Projekt, Status


class Rueckrollen(Exception):
    pass


class Command(BaseCommand):
    help = "Misst Ladezeit des Teamplaners (50 Personen × 20 Tage) und Speicherzeit."

    def handle(self, *args, **opts):
        try:
            with transaction.atomic():
                self.messen()
                raise Rueckrollen
        except Rueckrollen:
            self.stdout.write("Testdaten zurückgerollt.")

    def messen(self):
        bereiche = list(Bereich.objects.all())
        status = Status.objects.first()
        projekt = Projekt.objects.create(name="Lasttest")
        abschnitt = Abschnitt.objects.create(projekt=projekt, name="Lasttest")
        aufgaben = [Aufgabe.objects.create(projekt=projekt, abschnitt=abschnitt, titel=f"Lastaufgabe {i}", status=status,
                                           schaetzung_personentage=10) for i in range(40)]
        start = montag(timezone.localdate())
        personen = []
        for i in range(50):
            person = Person.objects.create(anzeigename=f"Person L{i:02d}", bereich=bereiche[i % len(bereiche)])
            personen.append(person)
            for j in range(6):
                von = start + timedelta(days=j * 4 + (i % 3))
                while von.weekday() >= 5:
                    von += timedelta(days=1)
                bis = von + timedelta(days=2 if von.weekday() < 3 else 0)
                Einteilung.objects.create(aufgabe=aufgaben[(i + j) % 40], person=person, von=von, bis=bis)
            Abwesenheit.objects.create(person=person, von=start + timedelta(days=21), bis=start + timedelta(days=22))
        admin = Konto.objects.filter(rolle=Rolle.ADMIN).first() or Konto.objects.anlegen(
            "lasttest@example.test", anzeigename="Person L99", bereich=bereiche[0], rolle=Rolle.ADMIN)
        client = Client(SERVER_NAME="localhost")
        client.force_login(admin)
        bis = start + timedelta(days=27)
        url = f"/api/planung/raster?ansicht=alle&von={start}&bis={bis}"

        laden = []
        for _ in range(5):
            t0 = time.perf_counter()
            antwort = client.get(url)
            laden.append(time.perf_counter() - t0)
        daten = antwort.json()
        self.stdout.write(f"Raster: {len(daten['personen'])} Personen × {len(daten['tage'])} Tage, "
                          f"{len(daten['einteilungen'])} Einteilungen")

        einteilung = Einteilung.objects.filter(person__in=personen).first()
        speichern = []
        for k in range(5):
            einteilung.refresh_from_db()
            neu = einteilung.von + timedelta(days=7 if k % 2 == 0 else -7)
            t0 = time.perf_counter()
            antwort = client.patch(f"/api/planung/einteilungen/{einteilung.pk}",
                                   {"von": neu.isoformat(), "bis": (neu + (einteilung.bis - einteilung.von)).isoformat(),
                                    "version": einteilung.version}, content_type="application/json")
            speichern.append(time.perf_counter() - t0)
            assert antwort.status_code == 200, antwort.content

        def text(werte):
            return f"Median {statistics.median(werte) * 1000:.0f} ms, Maximum {max(werte) * 1000:.0f} ms"

        self.stdout.write(f"Laden (Ziel < 2000 ms):     {text(laden)}")
        self.stdout.write(f"Speichern (Ziel < 500 ms):  {text(speichern)}")
