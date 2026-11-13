"""Versandverlauf der E-Mails: was wann an wen verschickt wurde, was offen ist, was fehlschlug.

    python manage.py mail_protokoll                     # die letzten 7 Tage
    python manage.py mail_protokoll --tage 30 --status fehler

Zeigt System-Mails (Einladung, Passwort zurücksetzen, Sicherheitshinweis) und Benachrichtigungen mit
E-Mail aus der Datenbank, nie Betreff oder Text. Der Verlauf reicht so weit zurück wie die
Aufbewahrungsfrist (TEAMPLANER_AUFBEWAHRUNG_TAGE). Dieselben Angaben stehen für Admins in der
Oberfläche unter Einstellungen, „E-Mail-Versand“.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from zusammenarbeit.mail import MAX_VERSUCHE, mail_aktiv, mail_eingerichtet
from zusammenarbeit.mailverlauf import STATUS, verlauf, zahlen


def _zeit(d):
    return timezone.localtime(d).strftime("%d.%m.%Y %H:%M") if d else "-"


class Command(BaseCommand):
    help = "Zeigt, welche E-Mails wann an wen verschickt wurden, offen sind oder fehlgeschlagen sind."

    def add_arguments(self, parser):
        parser.add_argument("--tage", type=int, default=7, help="Zeitraum in Tagen (Standard: 7)")
        parser.add_argument("--status", choices=[str(s) for s in STATUS], help="nur Einträge mit diesem Status")
        parser.add_argument("--limit", type=int, default=200, help="höchstens so viele Zeilen (Standard: 200)")

    def handle(self, *args, **o):
        if not mail_eingerichtet():
            self.stdout.write("Kein SMTP-Server eingerichtet (EMAIL_HOST): es wird nichts verschickt.")
        elif not mail_aktiv():
            self.stdout.write("Der E-Mail-Versand ist in den Einstellungen abgeschaltet.")
        eintraege = verlauf(tage=o["tage"], status=o["status"], limit=o["limit"])
        if eintraege:
            zeilen = [("Erstellt", "Verschickt", "Art", "Empfänger", "Status", "Versuche", "Eintrag")] + [
                (_zeit(e.erstellt_am), _zeit(e.gesendet_am), e.art, e.empfaenger or "-", e.status_text,
                 f"{e.versuche}/{MAX_VERSUCHE}" if e.versuche else "-", e.kennung)
                for e in eintraege
            ]
            breiten = [max(len(z[i]) for z in zeilen) for i in range(len(zeilen[0]))]
            for nr, z in enumerate(zeilen):
                self.stdout.write("  ".join(wert.ljust(breite) for wert, breite in zip(z, breiten, strict=True)).rstrip())
                if nr == 0:
                    self.stdout.write("  ".join("-" * breite for breite in breiten))
            if len(eintraege) == o["limit"]:
                self.stdout.write(f"(höchstens {o['limit']} Zeilen, mehr mit --limit)")
        else:
            self.stdout.write(f"Keine Einträge in den letzten {o['tage']} Tagen"
                              + (f" mit Status {o['status']}." if o["status"] else "."))
        z = zahlen()
        self.stdout.write("")
        self.stdout.write(f"Offen: {z['offen']}, aufgegeben: {z['fehler']}, in den letzten 24 Stunden verschickt: {z['gesendet_24h']}")
        if z["haengt"]:
            self.stdout.write(self.style.WARNING(
                f"Die älteste offene E-Mail wartet seit {_zeit(z['aelteste_offene'])}. "
                "Läuft der Dienst? sudo teamplaner status, sudo teamplaner logs mailer"))
