"""Demodaten für die lokale Entwicklung (nur Platzhalternamen, keine echten Personen).

    docker compose exec app python manage.py demodaten          # nur in leerer Datenbank
    docker compose exec app python manage.py demodaten --neu    # vorher ALLES löschen

Alle Demokonten haben das Passwort aus DEMO_PASSWORT (Standard siehe unten).
Die Einteilungen beziehen sich auf die aktuelle Woche, damit der Teamplaner sofort etwas zeigt.
"""

import os
from datetime import timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from bestellungen.models import Bestellung
from kern.models import Bereich, Gewerk, Konto, Person, Rolle, Systemeinstellungen
from notizen.models import Notiz, Ordner
from planung.kalender import montag
from planung.models import (
    Abwesenheit,
    AnsichtFreigabe,
    Einteilung,
    FreigabeStufe,
    Recht,
    Tagesfreigabe,
    TeamplanerAnsicht,
)
from projekte import termine
from projekte.models import Abschnitt, Aufgabe, Projekt, Status, Tag
from zusammenarbeit.models import Kommentar

DEMO_PASSWORT = os.environ.get("DEMO_PASSWORT", "Teamplaner-Demo-2026")


def notizen_anlegen(p):
    """Persönliche Notizen für die Demokonten und freigegebene Gruppenordner (nur Platzhalternamen).

    ``p`` ordnet die Nummer aus „Person NN“ der Person zu; fehlende Personen werden übersprungen.
    """
    def persoenlich(nr, titel, text):
        if nr in p:
            Notiz.objects.create(besitzer=p[nr], titel=titel, text=text, erstellt_von=p[nr], geaendert_von=p[nr])

    def ordner(name, nummern, notizen):
        o = Ordner.objects.create(name=name, erstellt_von=p.get(nummern[0]))
        o.mitglieder.set([p[nr].konto for nr in nummern if nr in p])
        for nr, titel, text in notizen:
            Notiz.objects.create(ordner=o, titel=titel, text=text, erstellt_von=p.get(nr), geaendert_von=p.get(nr))

    persoenlich(5, "Zu klären diese Woche",
                "- Prüftermin Hebebühne fixieren\n- Urlaubsplanung **Dezember** einsammeln\n- Angebote vergleichen")
    persoenlich(5, "Ideen Palette", "Aufgaben ohne Schätzung *farbig* markieren?\n\nMit Person 00 besprechen.")
    persoenlich(0, "Mitarbeitergespräche", "| Person | Termin |\n| --- | --- |\n| Person 01 | Di 9:00 |\n"
                "| Person 03 | Do 13:30 |\n| Person 07 | offen |")
    persoenlich(0, "Budget Produktion 2027", "## Größere Anschaffungen\n1. Neue Hebebühne\n2. Regale Halle B\n\n"
                "> Bis Ende November an die Geschäftsführung")
    persoenlich(1, "Maße Hallenboden", "- Länge 24,50 m\n- Breite 12,00 m\n- Stärke 18 cm\n\n`Beschichtung zweilagig`")
    persoenlich(1, "Einkaufsliste", "- Klebeband\n- Dübel 8 mm\n- ~~Handschuhe~~ erledigt")
    persoenlich(0, "Urlaubsplanung Produktion", "## Dezember\n- Person 02: 22.–31.12.\n- Person 04: 27.–31.12.\n"
                "- Person 07: noch offen\n\n> Mindestens **zwei** Personen anwesend")
    persoenlich(0, "Notizen Leitungsrunde", "- Auslastung im **November** hoch → Neubau Lagerhalle priorisieren\n"
                "- Neue Platzhalter für Aushilfen anlegen\n- Prüftermin Hebebühne mit Person 02 abstimmen")
    persoenlich(0, "Einschulung neue Kolleg:innen", "1. Sicherheitsunterweisung\n2. Konto im Teamplaner anlegen\n"
                "3. Ausrüstung ausgeben\n4. Erste Woche mit Person 03 einteilen")
    persoenlich(1, "Werkzeug ausgeliehen", "| Werkzeug | an | seit |\n| --- | --- | --- |\n| Bohrmaschine | Person 03 | Mo |\n"
                "| Messgerät | Person 22 | letzte Woche |")
    persoenlich(1, "Ideen Lager", "- Wandhalter bauen\n- Kleinteile *nach Größe* sortieren\n- Beschriftung erneuern")
    persoenlich(1, "Arbeitsschritte Hallenboden", "1. Untergrund vorbereiten\n2. Grundierung, **24 h** trocknen\n"
                "3. Beschichtung auftragen\n4. Abnahme mit Person 11")
    persoenlich(90, "Betrieb", "- Zertifikat läuft im **März** ab\n- Wöchentliche Sicherung prüfen (Sonntag)\n- Update-Termin abstimmen")
    persoenlich(90, "Konten und Rollen", "## Diese Woche\n- Konto für Person 22 auf *Planer:in* hochstufen?\n"
                "- Aushilfenkonto im Februar deaktivieren\n\n## Erinnerung\nAlle mit Leitungsrolle brauchen die "
                "Zwei-Faktor-Anmeldung.")
    persoenlich(90, "Speicherplatz", "- Anhänge über **20 MB** aus archivierten Projekten löschen\n"
                "- Freien Platz einmal im Monat in den Einstellungen ansehen")
    persoenlich(30, "Fragen zum Prototyp", "1. Welche Geschwindigkeit?\n2. Wer testet am Freitag?")
    persoenlich(21, "Testplan Prototyp", "| Lauf | Last [kg] | Tag |\n| --- | --- | --- |\n| 1 | 50 | Mo |\n"
                "| 2 | 80 | Di |\n| 3 | 120 | Mi |")
    persoenlich(15, "Checkliste Einsatz", "- Akkus geladen\n- Ersatzteile\n- Laptop\n- Warnwesten")

    ordner("Besprechung Produktion", [0, 1, 2, 3, 4, 5, 7], [
        (0, "Besprechung Montag", "## Themen\n1. Hallenboden – Stand Beschichtung\n2. Materialbestellung\n\n"
                                  "> Nächste Besprechung: Montag 8:00"),
        (3, "Werkzeugausgabe", "| Werkzeug | bei |\n| --- | --- |\n| Akkuschrauber 2 | Person 04 |\n| Laser | Person 05 |"),
        (2, "Wartung Maschinen", "- Förderband: Riemen tauschen (**KW 45**)\n- Kompressor: Öl prüfen\n- Hebebühne: jährliche Prüfung"),
    ])
    ordner("Entwicklung", [20, 21, 11, 22, 30, 5], [
        (20, "Regeln Testbereich", "## Wichtig\n- Prototyp nach dem Test **abschalten**\n- Not-Aus vor jedem Lauf prüfen\n"
                                   "- Daten täglich sichern"),
        (21, "Testprotokoll Vorlage", "**Datum:** \n**Last:** \n**Dauer:** \n\n### Beobachtungen\n- "),
        (11, "Datenblatt Motor", "Neues Datenblatt liegt als PDF im Projektordner."),
    ])
    ordner("Kundendienst Süd", [15, 8, 10, 5], [
        (15, "Standorte", "1. Standort Nord\n2. Standort Mitte\n3. Standort Süd"),
        (8, "Anfahrt und Schlüssel", "Schlüssel beim Empfang abholen, Parkplatz hinter dem Gebäude."),
    ])
    ordner("Leitungsrunde", [90, 0, 15, 20], [
        (90, "Protokoll Leitungsrunde", "## Beschlüsse\n- Bestellungen laufen über die Liste\n\n"
                                        "## Offen\n- Urlaubssperre Dezember?"),
    ])


class Command(BaseCommand):
    help = "Legt Demodaten an (Platzhalternamen, Einteilungen ab der aktuellen Woche)."

    def add_arguments(self, parser):
        parser.add_argument("--neu", action="store_true", help="Datenbank vorher vollständig leeren")
        parser.add_argument("--notizen", action="store_true",
                            help="Nur die Beispiel-Notizen neu anlegen (ersetzt alle Notizen), übrige Daten bleiben")

    def handle(self, *args, **opts):
        # Leert auf Wunsch die Datenbank und legt Konten mit bekanntem Passwort an: nie im Produktivbetrieb
        if not (settings.DEBUG or settings.TEAMPLANER_DEMO):
            raise CommandError("Demodaten nur in der Entwicklung (DJANGO_DEBUG=1) oder mit TEAMPLANER_DEMO=1.")
        if opts["notizen"]:
            personen = {int(x.anzeigename.split()[1]): x
                        for x in Person.objects.mit_konto().filter(anzeigename__regex=r"^Person \d+$")}
            with transaction.atomic():
                Notiz.objects.all().delete()
                Ordner.objects.all().delete()
                notizen_anlegen(personen)
            self.stdout.write(self.style.SUCCESS("Beispiel-Notizen angelegt."))
            return
        if opts["neu"]:
            call_command("flush", interactive=False, verbosity=0)
        elif Person.objects.exists():
            raise CommandError("Es gibt bereits Personen. Mit --neu wird die Datenbank vorher geleert.")
        with transaction.atomic():
            self.anlegen()
        self.stdout.write(self.style.SUCCESS("Demodaten angelegt."))
        self.stdout.write(f"Anmeldung z. B. mit bereichsleitung@example.test / planer@example.test / "
                          f"mitarbeiter@example.test / lesend@example.test, Passwort: {DEMO_PASSWORT}")

    def anlegen(self):
        bereiche = {}
        for i, name in enumerate(["Produktion", "Service", "Entwicklung"]):
            bereiche[name], _x = Bereich.objects.get_or_create(name=name, defaults={"sortierung": i})
        for i, (name, erledigt, farbe) in enumerate([("Offen", False, "grau"), ("Eingeplant", False, "blau"),
                                                    ("In Arbeit", False, "gelb"), ("Wartet", False, "orange"),
                                                    ("Erledigt", True, "gruen")]):
            Status.objects.get_or_create(name=name, defaults={"sortierung": i, "ist_erledigt": erledigt, "farbe": farbe})
        status = {s.name: s for s in Status.objects.all()}
        gewerke = {n: Gewerk.objects.create(name=n) for n in [
            "Montage", "Fertigung", "Elektrik", "Steuerung", "Konstruktion", "Einkauf", "Außendienst", "Prüfung"]}
        Bereich.objects.filter(name="Allgemein", personen__isnull=True).delete()
        W, F, L = bereiche["Produktion"], bereiche["Service"], bereiche["Entwicklung"]

        def konto(nr, bereich, rolle, gew=(), email=None):
            name = f"Person {nr:02d}"
            k = Konto.objects.anlegen(email or f"person{nr:02d}@example.test", anzeigename=name, bereich=bereich,
                                      rolle=rolle, password=DEMO_PASSWORT)
            k.person.gewerke.set([gewerke[g] for g in gew])
            return k.person

        admin = konto(90, W, Rolle.ADMIN, email="admin@example.test")
        admin.konto.systemkonto = True  # technisches Admin-Konto: in keiner Personenauswahl
        admin.konto.save(update_fields=["systemkonto"])
        p = {
            0: konto(0, W, Rolle.BEREICHSLEITUNG, email="bereichsleitung@example.test"),
            1: konto(1, W, Rolle.MITARBEITER, ["Montage"], email="mitarbeiter@example.test"),
            2: konto(2, W, Rolle.MITARBEITER, ["Montage"]),
            3: konto(3, W, Rolle.MITARBEITER, ["Fertigung"]),
            4: konto(4, W, Rolle.MITARBEITER, ["Fertigung", "Elektrik"]),
            5: konto(5, W, Rolle.PLANER, ["Steuerung"], email="planer@example.test"),
            7: konto(7, W, Rolle.MITARBEITER, ["Konstruktion", "Einkauf"]),
            8: konto(8, F, Rolle.MITARBEITER, ["Außendienst"]),
            10: konto(10, F, Rolle.MITARBEITER, ["Außendienst"]),
            15: konto(15, F, Rolle.BEREICHSLEITUNG, ["Außendienst"]),
            11: konto(11, L, Rolle.MITARBEITER, ["Prüfung"]),
            20: konto(20, L, Rolle.BEREICHSLEITUNG, ["Prüfung"]),
            21: konto(21, L, Rolle.PLANER, ["Prüfung"]),
            22: konto(22, L, Rolle.MITARBEITER, ["Prüfung"]),
            30: konto(30, L, Rolle.LESEND, [], email="lesend@example.test"),
        }
        ws = Person.objects.create(anzeigename="Aushilfe Montage", bereich=W, notiz="Neubau Lagerhalle, Di–Do", erstellt_von=p[21])
        hl = Person.objects.create(anzeigename="Leihkraft Prüfung", bereich=L, notiz="Testreihe 3", erstellt_von=p[11])
        Person.objects.create(anzeigename="Aushilfe Service", bereich=F, erstellt_von=p[8])
        alt = Person.objects.create(anzeigename="Saisonkraft Sommer", bereich=W, notiz="Juli–August", erstellt_von=p[0])
        alt.archivieren()

        tags = {n: Tag.objects.create(name=n) for n in ["Produktion", "Entwicklung", "Service", "Kunde A", "Prototyp"]}

        def projekt(name, farbe, leitung, tagnamen, mitglieder, abschnitte):
            pr = Projekt.objects.create(name=name, farbe=farbe, projektleitung=leitung, erstellt_von=admin)
            pr.tags.set([tags[t] for t in tagnamen])
            pr.mitglieder.set(mitglieder)
            return pr, {n: Abschnitt.objects.create(projekt=pr, name=n, sortierung=i * 10) for i, n in enumerate(abschnitte)}

        A, a_ab = projekt("Neubau Lagerhalle", "bernstein", p[21], ["Produktion", "Entwicklung", "Kunde A"],
                          [p[1], p[3], p[4], p[7], ws, p[22]], ["Planung", "Fertigung", "Montage & Inbetriebnahme"])
        B, b_ab = projekt("Prototyp Förderband", "blau", p[21], ["Produktion", "Prototyp"],
                          [p[3], p[5], p[11], hl], ["Planung", "Fertigung", "Tests"])
        C, c_ab = projekt("Kundendienst Süd", "gruen", p[15], ["Service"], [p[8], p[10]], ["Vorbereitung", "Einsätze", "Abschluss"])
        D, d_ab = projekt("Betrieb intern", "violett", p[0], ["Produktion"], [p[1], p[2], p[3]], ["Wartung", "Einrichtung"])
        for pr, prio in [(A, 1), (B, 2), (C, 3)]:  # „Betrieb intern“ ohne Priorität
            pr.prioritaet = prio
            pr.save(update_fields=["prioritaet"])

        heute = timezone.localdate()
        mo = montag(heute)

        def tag(spalte):
            return mo + timedelta(days=(spalte // 5) * 7 + spalte % 5)

        reihen = {}

        def aufgabe(pr, abschnitt, titel, gewerk=None, pt=None, faellig=None, st="Offen", verantwortlich=None, eltern=None):
            if eltern is not None:
                abschnitt = eltern.abschnitt
            schluessel = (abschnitt.pk, eltern.pk if eltern else None)
            reihen[schluessel] = reihen.get(schluessel, 0) + 10
            return Aufgabe.objects.create(
                projekt=pr, abschnitt=abschnitt, eltern=eltern, titel=titel, gewerk=gewerke.get(gewerk) if gewerk else None,
                schaetzung_personentage=Decimal(pt) if pt is not None else None,
                faellig_am=tag(faellig) if faellig is not None else None, status=status[st],
                verantwortlich=verantwortlich, sortierung=reihen[schluessel], erstellt_von=admin,
                erledigt_am=timezone.now() if status[st].ist_erledigt else None,
            )

        # Größere Arbeitspakete als Hauptaufgaben, die einzuteilenden Aufgaben als ihre Unteraufgaben.
        # Termine der Hauptaufgaben ergeben sich unten aus den Unteraufgaben.
        h = {
            "planung_a": aufgabe(A, a_ab["Planung"], "Planung Halle", verantwortlich=p[21]),
            "fertigung_a": aufgabe(A, a_ab["Fertigung"], "Halle ausbauen", verantwortlich=p[0]),
            "boden": aufgabe(A, a_ab["Montage & Inbetriebnahme"], "Boden fertigstellen", verantwortlich=p[1]),
            "inbetrieb_a": aufgabe(A, a_ab["Montage & Inbetriebnahme"], "Übergabe Halle", verantwortlich=p[22]),
            "antrieb": aufgabe(B, b_ab["Fertigung"], "Antrieb bauen", verantwortlich=p[3]),
            "steuerschrank": aufgabe(B, b_ab["Fertigung"], "Steuerschrank", verantwortlich=p[5]),
            "band_b": aufgabe(B, b_ab["Fertigung"], "Band aufbauen", verantwortlich=p[2]),
            "tests_b": aufgabe(B, b_ab["Tests"], "Testreihen", verantwortlich=p[11]),
            "bericht_b": aufgabe(B, b_ab["Tests"], "Auswertung und Bericht", verantwortlich=p[21]),
            "ausruestung": aufgabe(C, c_ab["Vorbereitung"], "Ausrüstung vorbereiten", verantwortlich=p[10]),
            "einsaetze": aufgabe(C, c_ab["Einsätze"], "Serviceeinsätze", verantwortlich=p[8]),
            "wartung_d": aufgabe(D, d_ab["Wartung"], "Maschinenwartung Herbst", verantwortlich=p[2]),
        }

        t = {
            "hallenboden": aufgabe(A, None, "Hallenboden verlegen", "Montage", 10, 9, "In Arbeit", p[1], h["fertigung_a"]),
            "materialbestellung": aufgabe(A, None, "Materialbestellung", "Einkauf", 1, 2, "Eingeplant", p[7], h["planung_a"]),
            "stuecklisten": aufgabe(A, None, "Stücklisten Montage", "Konstruktion", 2, 8, "Eingeplant", p[7], h["planung_a"]),
            "regalsystem": aufgabe(A, None, "Regalsystem", "Fertigung", 4, 9, "Eingeplant", p[4], h["fertigung_a"]),
            "rolltor": aufgabe(A, None, "Rolltor einbauen", "Fertigung", 2, 4, eltern=h["fertigung_a"]),
            "sensorik": aufgabe(A, None, "Sensorik einrichten", "Prüfung", 2, 11, "Eingeplant", p[22], h["inbetrieb_a"]),
            "beschichten": aufgabe(A, None, "Hallenboden beschichten", "Montage", 2, 12, verantwortlich=p[2], eltern=h["boden"]),
            "abnahme": aufgabe(A, None, "Abnahme", None, None, 13, "Wartet", eltern=h["boden"]),
            "gehaeuse": aufgabe(B, None, "Gehäuse Band", "Montage", 4, 9, "Eingeplant", p[2], h["band_b"]),
            "rahmen": aufgabe(B, None, "Rahmen Antrieb", "Fertigung", 7, 4, "In Arbeit", p[3], h["antrieb"]),
            "halterung": aufgabe(B, None, "Halterung Steuerschrank", "Fertigung", 1, 3, "Eingeplant", p[4], h["steuerschrank"]),
            "steuerung": aufgabe(B, None, "Steuerung verdrahten", "Steuerung", 5, 4, "In Arbeit", p[5], h["steuerschrank"]),
            "sensoren": aufgabe(B, None, "Sensorkalibrierung", "Steuerung", 2, 8, "Eingeplant", p[5], h["tests_b"]),
            "zeichnungen": aufgabe(B, b_ab["Planung"], "Zeichnungen Antrieb", "Konstruktion", 2, 1, "Eingeplant", p[7]),
            "bohrungen": aufgabe(B, None, "Bohrungen Rahmen", "Fertigung", 3, 9, "Eingeplant", ws, h["antrieb"]),
            "kabelbaum": aufgabe(B, None, "Kabelbaum Antrieb", "Steuerung", 3, 9, eltern=h["antrieb"]),
            "abdeckung": aufgabe(B, None, "Abdeckung zuschneiden", "Montage", 1, 7, eltern=h["band_b"]),
            "testreihe": aufgabe(B, None, "Testreihe 3", "Prüfung", 7, 14, "Eingeplant", p[11], h["tests_b"]),
            "servicewagen": aufgabe(C, None, "Servicewagen ausrüsten", "Elektrik", 3, 4, "Eingeplant", p[4], h["ausruestung"]),
            "wartungseinsatz": aufgabe(C, None, "Wartungseinsatz", "Außendienst", 8, 4, "In Arbeit", p[8], h["einsaetze"]),
            "einsatzberichte": aufgabe(C, c_ab["Abschluss"], "Einsatzberichte", "Außendienst", 3, 9, "Eingeplant", p[8]),
            "geraete": aufgabe(C, None, "Geräte prüfen", "Außendienst", 1, 6, "Eingeplant", p[10], h["ausruestung"]),
            "kisten": aufgabe(C, None, "Transportkisten", "Montage", 2, 14, eltern=h["ausruestung"]),
            "regal": aufgabe(D, d_ab["Einrichtung"], "Regal Lager", "Montage", 1, 6, "Eingeplant", p[1]),
            "werkbank": aufgabe(D, None, "Werkbank Wartung", "Montage", 1, 6, "Eingeplant", p[2], h["wartung_d"]),
            "gelaender": aufgabe(D, d_ab["Einrichtung"], "Geländer Galerie", "Fertigung", 4, 9, "Eingeplant", p[3]),
            "filter": aufgabe(D, None, "Filter reinigen", None, 1, None, eltern=h["wartung_d"]),
        }
        # Spätere Schritte, damit die Projekte im Gantt-Diagramm realistisch lang laufen
        t.update({
            "inbetriebnahme": aufgabe(A, None, "Inbetriebnahme Halle", "Prüfung", 4, 20, eltern=h["inbetrieb_a"]),
            "probebetrieb": aufgabe(A, None, "Probebetrieb", "Prüfung", 8, 30, eltern=h["inbetrieb_a"]),
            "dokumentation": aufgabe(A, a_ab["Montage & Inbetriebnahme"], "Dokumentation Neubau", None, 3, 38),
            "testreihe4": aufgabe(B, None, "Testreihe 4", "Prüfung", 8, 30, eltern=h["tests_b"]),
            "testdaten": aufgabe(B, None, "Auswertung Testdaten", "Prüfung", 6, 40, eltern=h["bericht_b"]),
            "bericht_b": aufgabe(B, None, "Abschlussbericht Prototyp", None, 3, 44, eltern=h["bericht_b"]),
            "einsatz2": aufgabe(C, None, "Zweiter Einsatz", "Außendienst", 8, 20, eltern=h["einsaetze"]),
            "bericht_c": aufgabe(C, c_ab["Abschluss"], "Bericht Kundendienst", "Außendienst", 4, 32),
            "hubwagen": aufgabe(D, None, "Service Hubwagen", "Fertigung", 2, 19, eltern=h["wartung_d"]),
            "inventur": aufgabe(D, d_ab["Einrichtung"], "Inventur Werkzeuge", None, 2, 27),
        })
        aufgabe(A, None, "Konstruktionszeichnung Halle", "Konstruktion", 2, -5, "Erledigt", p[7], h["planung_a"])

        def ein(aufg, person, von, bis=None):
            Einteilung.objects.create(aufgabe=t[aufg], person=person, von=tag(von), bis=tag(bis if bis is not None else von), erstellt_von=p[0])

        def weg(person, von, bis=None):
            Abwesenheit.objects.create(person=person, von=tag(von), bis=tag(bis if bis is not None else von), erstellt_von=p[0])

        ein("hallenboden", p[1], 0, 1); ein("gehaeuse", p[1], 2); ein("hallenboden", p[1], 3); ein("regal", p[1], 6); ein("hallenboden", p[1], 7, 9)  # noqa: E702
        weg(p[2], 0, 4); ein("werkbank", p[2], 6); ein("gehaeuse", p[2], 7, 9)  # noqa: E702
        ein("rahmen", p[3], 0, 4); ein("gelaender", p[3], 6, 9)  # noqa: E702
        ein("rahmen", p[4], 0, 1); ein("servicewagen", p[4], 2, 4); ein("regalsystem", p[4], 6, 9); ein("halterung", p[4], 3)  # noqa: E702
        ein("steuerung", p[5], 0, 4); ein("sensoren", p[5], 7, 8)  # noqa: E702
        ein("materialbestellung", p[7], -4, -3); ein("zeichnungen", p[7], 0, 2); weg(p[7], 3, 4); ein("stuecklisten", p[7], 6, 7)  # noqa: E702
        ein("hallenboden", ws, 1, 2); weg(ws, 3, 4); ein("bohrungen", ws, 6, 8)  # noqa: E702
        weg(p[8], 0); ein("wartungseinsatz", p[8], 1, 4); ein("einsatzberichte", p[8], 6, 8)  # noqa: E702
        ein("wartungseinsatz", p[10], 1, 4); ein("geraete", p[10], 6); weg(p[10], 7, 9)  # noqa: E702
        ein("sensorik", p[11], 2, 3); ein("testreihe", p[11], 6, 9)  # noqa: E702
        ein("testreihe", hl, 7, 9); ein("kisten", p[1], 12)  # noqa: E702

        t["hallenboden"].beschreibung = ("<p>Untergrund vorbereiten, Grundierung auftragen und Fugen nach Plan setzen.</p>"
                                         "<ul><li>Maße und Toleranzen siehe Anhang</li></ul>")
        t["hallenboden"].save(update_fields=["beschreibung"])
        Kommentar.objects.create(aufgabe=t["hallenboden"], autor=p[1],
                                 text=f"Untergrund ist fertig. @[{p[7].pk}] fehlt noch Material aus der Bestellung? "
                                      f"@[{ws.pk}] hilft Mi beim Verlegen.")

        def ansicht(name, sortierung, bereiche_, freigaben):
            a = TeamplanerAnsicht.objects.create(name=name, sortierung=sortierung, erstellt_von=p[0], filter={"wochen": 2})
            a.bereiche.set(bereiche_)
            for person, recht in freigaben:
                AnsichtFreigabe.objects.create(ansicht=a, konto=person.konto, recht=recht)
            return a

        ansicht("Produktion", 10, [W], [(p[5], Recht.BEARBEITEN), (p[1], Recht.SEHEN), (p[2], Recht.SEHEN),
                                       (p[3], Recht.SEHEN), (p[4], Recht.SEHEN), (p[7], Recht.SEHEN)])
        ansicht("Service", 20, [F], [(p[8], Recht.SEHEN), (p[10], Recht.SEHEN), (p[5], Recht.SEHEN)])
        ansicht("Entwicklung", 30, [L], [(p[21], Recht.BEARBEITEN), (p[11], Recht.SEHEN), (p[22], Recht.SEHEN), (p[30], Recht.SEHEN)])
        ansicht("Alle Bereiche", 40, [W, F, L], [(p[21], Recht.SEHEN)])

        # --- Gantt: Zeiträume, geplante Beginne, Abhängigkeiten, Ansichten ---
        from gantt.models import GanttAnsicht, GanttFreigabe
        from projekte.models import Abhaengigkeit

        # Projektzeiträume über rund zwei bis drei Monate (Werktag-Spalten ab Montag dieser Woche)
        for pr, (von, bis) in {A: (-10, 40), B: (-15, 45), C: (0, 34), D: (-5, 30)}.items():
            pr.beginn, pr.ende = tag(von), tag(bis)
            pr.save(update_fields=["beginn", "ende"])
        # Geplanter Beginn und Fälligkeit, passend zu den Einteilungen oben
        plan = {
            "materialbestellung": (-5, -3), "hallenboden": (0, 9), "stuecklisten": (5, 8), "rolltor": (2, 4),
            "regalsystem": (6, 10), "sensorik": (1, 3), "beschichten": (11, 12), "abnahme": (14, 15),
            "inbetriebnahme": (16, 20), "probebetrieb": (21, 30), "dokumentation": (31, 38),
            "zeichnungen": (-4, 2), "rahmen": (-3, 4), "halterung": (3, 3), "steuerung": (-2, 4),
            "kabelbaum": (3, 6), "bohrungen": (6, 9), "abdeckung": (5, 7), "gehaeuse": (2, 10), "sensoren": (7, 8),
            "testreihe": (6, 14), "testreihe4": (20, 30), "testdaten": (31, 40), "bericht_b": (41, 44),
            "servicewagen": (2, 5), "wartungseinsatz": (1, 4), "geraete": (5, 6), "einsatzberichte": (6, 9), "kisten": (10, 12),
            "einsatz2": (15, 20), "bericht_c": (25, 32),
            "werkbank": (6, 6), "regal": (5, 6), "gelaender": (6, 10), "hubwagen": (18, 19), "inventur": (25, 27),
        }
        for schluessel, (von, bis) in plan.items():
            t[schluessel].beginn_am, t[schluessel].faellig_am = tag(von), tag(bis)
            t[schluessel].save(update_fields=["beginn_am", "faellig_am"])
        for aufgabe_ in Aufgabe.objects.filter(projekt__in=[A, B, C, D], faellig_am__isnull=False, beginn_am__isnull=True):
            dauer = int(aufgabe_.schaetzung_personentage or 1)
            aufgabe_.beginn_am = aufgabe_.faellig_am - timedelta(days=dauer + dauer // 5 * 2)
            aufgabe_.save(update_fields=["beginn_am"])
        for vorher, nachher in [
            ("materialbestellung", "hallenboden"), ("hallenboden", "beschichten"), ("beschichten", "abnahme"),
            ("abnahme", "inbetriebnahme"), ("inbetriebnahme", "probebetrieb"), ("probebetrieb", "dokumentation"),
            ("rolltor", "regalsystem"),
            ("zeichnungen", "bohrungen"), ("rahmen", "bohrungen"), ("steuerung", "sensoren"), ("kabelbaum", "sensoren"),
            ("testreihe", "testreihe4"), ("testreihe4", "testdaten"), ("testdaten", "bericht_b"),
            ("wartungseinsatz", "einsatzberichte"), ("einsatzberichte", "einsatz2"), ("einsatz2", "bericht_c"),
            ("sensorik", "testreihe"),    # projektübergreifend: Sensorik vor Testreihe
            ("rahmen", "servicewagen"),        # projektübergreifend: Rahmen vor dem Servicewagen –
                                                 # die Einteilungen überschneiden sich (als verletzt markiert)
            ("abdeckung", "testreihe"),
        ]:
            Abhaengigkeit.objects.create(vorher=t[vorher], nachher=t[nachher], erstellt_von=p[0])
        # Geplante Termine wie in der Oberfläche nachziehen: Nachfolger nach ihren Vorgängern, Hauptaufgaben
        # über ihre Unteraufgaben (ohne Verlauf und Benachrichtigungen)
        plan = termine.Plan()
        termine.nachziehen(plan, list(Aufgabe.objects.filter(projekt__in=[A, B, C, D]).values_list("pk", flat=True)))
        for pk, (beginn, faellig) in plan.neu.items():
            Aufgabe.objects.filter(pk=pk).update(beginn_am=beginn, faellig_am=faellig)

        gesamt = GanttAnsicht.objects.create(name="Alle Projekte", sortierung=10, erstellt_von=p[0],
                                             neue_projekte_automatisch=True)
        gesamt.projekte.set(Projekt.objects.aktiv())
        produktion_gantt = GanttAnsicht.objects.create(name="Produktion", sortierung=20, erstellt_von=p[0])
        produktion_gantt.projekte.set([A, B, D])
        for ansicht_, person, recht in [
            (gesamt, p[5], Recht.BEARBEITEN), (gesamt, p[21], Recht.BEARBEITEN), (gesamt, p[1], Recht.SEHEN),
            (gesamt, p[30], Recht.SEHEN), (produktion_gantt, p[5], Recht.BEARBEITEN), (produktion_gantt, p[1], Recht.SEHEN),
        ]:
            GanttFreigabe.objects.create(ansicht=ansicht_, konto=person.konto, recht=recht)

        # Tagesfreigabe, Bestellungen, Notizen
        Systemeinstellungen.objects.update_or_create(pk=1, defaults={"freigabe_zeile": True})
        stufen = {name: FreigabeStufe.objects.create(name=name, sortierung=i * 10)
                  for i, name in enumerate(["Komplett", "Halle A", "Halle B"])}
        for spalte, stufe in [(0, "Komplett"), (1, "Halle A"), (2, "Halle A"), (3, "Komplett"), (6, "Halle B")]:
            Tagesfreigabe.objects.create(datum=tag(spalte), stufe=stufen[stufe], geaendert_von=p[5])
        # Liefertermin in Tagen ab heute (negativ = überschritten), Prio
        for bedarf, tage, projekt_, bestellt, lieferant, st, wer, termin, prio in [
            ("Abdeckplatten 20 mm, 4 Stück 2000 × 1000", 9, "Prototyp Förderband", 6, "Handel Nord", "bestellt", p[7], 4, False),
            ("Schrauben M8 × 40, 200 Stück", 4, "Neubau Lagerhalle", None, "", "offen", p[3], None, False),
            ("Ersatzkabel Messgerät", 12, "Kundendienst Süd", None, "", "recherche", p[8], None, True),
            ("Dichtmasse, 10 Kartuschen", 2, "Neubau Lagerhalle", None, "", "offen", p[1], None, False),
            ("Keilriemen Förderband", 15, "Betrieb intern", 14, "Technikservice", "achtung", p[2], -3, True),
            ("Bodenbeschichtung, 40 kg", 30, "Neubau Lagerhalle", 28, "Baustoffe Süd", "erhalten", p[7], -20, False),
        ]:
            Bestellung.objects.create(
                prio=prio, bedarf=bedarf, aufnahmedatum=heute - timedelta(days=tage), projekt=projekt_,
                bestellt_am=heute - timedelta(days=bestellt) if bestellt is not None else None,
                lieferant=lieferant, status=st, erstellt_von=wer, eingetragen_von=wer,
                bestellt_von=p[7] if bestellt is not None else None,  # Person 07 macht den Einkauf
                liefertermin=heute + timedelta(days=termin) if termin is not None else None,
                warnung_fuer_termin=heute + timedelta(days=termin) if termin is not None and termin < 0 else None,
            )
        notizen_anlegen({**p, 90: admin})
