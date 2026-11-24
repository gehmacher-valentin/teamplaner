"""Vorschau der ersten Seite für PDF-Anhänge nachtragen, die noch keine haben (z. B. vor dem Update
hochgeladen). Neue PDFs bekommen sie beim Hochladen.

    sudo teamplaner verwalten pdf_vorschauen
"""

from django.core.management.base import BaseCommand

from notizen.models import NotizAnhang
from zusammenarbeit import pdf_vorschau
from zusammenarbeit.models import Anhang


class Command(BaseCommand):
    help = "Erzeugt die Vorschau der ersten Seite für PDF-Anhänge ohne Vorschau (Aufgaben und Notizen)."

    def add_arguments(self, parser):
        parser.add_argument("--neu", action="store_true",
                            help="auch vorhandene Vorschauen neu erzeugen")

    def handle(self, *args, **o):
        for bereich, modell in (("Aufgaben", Anhang), ("Notizen", NotizAnhang)):
            anhaenge = modell.objects.filter(content_type=pdf_vorschau.PDF).order_by("pk")
            if not o["neu"]:
                anhaenge = anhaenge.filter(vorschau="")
            erzeugt = ohne = 0
            for anhang in anhaenge.iterator():
                if pdf_vorschau.nachtragen(anhang):
                    erzeugt += 1
                else:
                    ohne += 1
            self.stdout.write(f"{bereich}: {erzeugt} Vorschauen erzeugt, {ohne} PDFs ohne Vorschau "
                              "(beschädigt, verschlüsselt oder zu aufwendig)")
