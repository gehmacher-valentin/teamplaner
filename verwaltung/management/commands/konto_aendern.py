"""Vorhandenes Konto auf dem Server ändern, auch Admin-Konten.

    sudo teamplaner konto-aendern admin@example.org                          # nur anzeigen
    sudo teamplaner konto-aendern admin@example.org --rolle bereichsleitung
    sudo teamplaner konto-aendern admin@example.org --deaktivieren
    sudo teamplaner konto-aendern admin@example.org --reaktivieren
    sudo teamplaner konto-aendern admin@example.org --neue-email neu@example.org
    sudo teamplaner konto-aendern admin@example.org --passwort-link

Anders als in der Oberfläche gilt hier keine Schutzfrist für ehemalige Admins. Der letzte Admin
bleibt auch hier geschützt: Es muss ein weiterer aktiver Admin bleiben, der sich schon einmal angemeldet hat.
Zwei-Faktor-Anmeldung zurücksetzen: zwei_faktor_zuruecksetzen.
"""

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from kern.hilfen import passwort_link
from kern.models import Konto, Rolle
from kern.protokoll import protokollieren
from verwaltung import konten
from zusammenarbeit.mail import sicherheitshinweis


class Command(BaseCommand):
    help = "Ändert Rolle, E-Mail oder Zustand eines Kontos; ohne Option wird es nur angezeigt."

    def add_arguments(self, parser):
        parser.add_argument("email")
        parser.add_argument("--rolle", choices=[r.value for r in Rolle])
        zustand = parser.add_mutually_exclusive_group()
        zustand.add_argument("--deaktivieren", action="store_true")
        zustand.add_argument("--reaktivieren", action="store_true")
        parser.add_argument("--neue-email")
        parser.add_argument("--passwort-link", action="store_true",
                            help="Link zum Setzen eines neuen Passworts ausgeben (es geht keine E-Mail hinaus)")

    @transaction.atomic
    def handle(self, *args, **o):
        konto = Konto.objects.select_related("person").filter(email__iexact=o["email"].strip()).first()
        if konto is None:
            raise CommandError("Kein Konto mit dieser E-Mail.")
        try:
            if o["reaktivieren"]:
                konten.reaktivieren(None, konto)
            if o["rolle"]:
                konten.rolle_setzen(None, konto, o["rolle"])
            if o["deaktivieren"]:
                konten.deaktivieren(None, konto)
        except konten.LetzterAdmin:
            raise CommandError("Das ist der letzte Admin. Es muss ein weiterer aktiver Admin bleiben, der sich "
                               "schon einmal angemeldet hat: zuerst mit konto-anlegen anlegen und damit anmelden.") from None
        if o["neue_email"]:
            self._email_aendern(konto, o["neue_email"].strip().lower())
        konto = Konto.objects.select_related("person").get(pk=konto.pk)
        zustand = "aktiv" if konto.is_active else "deaktiviert"
        self.stdout.write(self.style.SUCCESS(
            f"{konto.person.anzeigename} <{konto.email}>: {konto.get_rolle_display()}, {zustand}"))
        if o["passwort_link"]:
            if not konto.is_active:
                raise CommandError("Das Konto ist deaktiviert – zuerst --reaktivieren.")
            protokollieren(None, "konto", konto.pk, "link_erzeugt", {"person": konto.person})
            self.stdout.write(f"Link zum Setzen des Passworts:\n{passwort_link(konto)}")

    def _email_aendern(self, konto, neu):
        try:
            validate_email(neu)
        except ValidationError:
            raise CommandError("Keine gültige E-Mail-Adresse.") from None
        if Konto.objects.filter(email__iexact=neu).exclude(pk=konto.pk).exists():
            raise CommandError("Für diese E-Mail gibt es bereits ein Konto.")
        alt = konto.email
        if alt == neu:
            return
        konto.email = neu
        konto.save(update_fields=["email"])
        protokollieren(None, "konto", konto.pk, "geaendert", {"person": konto.person, "email": [alt, neu]})
        sicherheitshinweis(konto, "email_geaendert", an=alt, neu=neu)
