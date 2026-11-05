"""Erstes Admin-Konto (oder weitere Konten) auf der Kommandozeile anlegen.

    docker compose exec app python manage.py konto_anlegen --email admin@example.org \
        --name "Vorname Nachname" --bereich Allgemein --rolle admin [--systemkonto]

--systemkonto: Konto steht in keiner Personenauswahl (z. B. ein technisches Admin-Konto).

Ohne --passwort wird ein Einladungslink ausgegeben, mit dem die Person ihr Passwort setzt.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from kern.hilfen import passwort_links
from kern.models import Bereich, Konto, Rolle
from kern.protokoll import protokollieren


class Command(BaseCommand):
    help = "Legt ein Konto an und gibt einen Link zum Setzen des Passworts aus."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True)
        parser.add_argument("--bereich", required=True, help="Name des Bereichs, z. B. Allgemein")
        parser.add_argument("--rolle", default=Rolle.ADMIN, choices=[r.value for r in Rolle])
        parser.add_argument("--passwort", help="Nur für Tests – sonst Einladungslink verwenden")
        parser.add_argument("--systemkonto", action="store_true",
                            help="Nicht als Person auswählbar (Teamplaner, Verantwortlich, Mitglieder …)")
        parser.add_argument("--adresse", default=None,
                            help="Basisadresse für den ausgegebenen Link (Standard: TEAMPLANER_ADRESSE)")

    def handle(self, *args, **o):
        if Konto.objects.filter(email__iexact=o["email"]).exists():
            raise CommandError("Für diese E-Mail gibt es bereits ein Konto.")
        try:
            bereich = Bereich.objects.get(name__iexact=o["bereich"])
        except Bereich.DoesNotExist:
            namen = ", ".join(Bereich.objects.values_list("name", flat=True))
            raise CommandError(f"Unbekannter Bereich. Vorhanden: {namen}") from None
        konto = Konto.objects.anlegen(o["email"], anzeigename=o["name"], bereich=bereich,
                                      rolle=o["rolle"], password=o["passwort"])
        if o["systemkonto"]:
            konto.systemkonto = True
            konto.save(update_fields=["systemkonto"])
        protokollieren(None, "konto", konto.pk, "angelegt", {"person": konto.person, "rolle": konto.rolle})
        self.stdout.write(self.style.SUCCESS(f"Konto {konto.email} ({konto.get_rolle_display()}) angelegt."))
        if not o["passwort"]:
            uid = urlsafe_base64_encode(force_bytes(konto.pk))
            pfad = reverse("passwort_setzen", args=[uid, passwort_links.make_token(konto)])
            adresse = o["adresse"] or settings.TEAMPLANER_ADRESSE
            self.stdout.write(f"Link zum Setzen des Passworts:\n{adresse.rstrip('/')}{pfad}")
