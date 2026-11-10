# Entwicklung

Entwickelt und getestet wird auf demselben System wie im Betrieb: Ubuntu 24.04 LTS mit Python 3.12
und PostgreSQL 16 aus den Ubuntu-Paketen, dazu Node.js 22 für den Frontend-Build.

## Einrichtung

Einmalig:

```bash
sudo apt install python3 python3-venv postgresql postgresql-client gettext shellcheck
sudo -u postgres psql -c "CREATE ROLE teamplaner LOGIN CREATEDB PASSWORD 'teamplaner-dev'"
sudo -u postgres psql -c "CREATE DATABASE teamplaner OWNER teamplaner ENCODING 'UTF8' TEMPLATE template0"
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
```

`CREATEDB` braucht pytest für die Testdatenbank. Node.js 22 z. B. aus den Paketen von NodeSource oder
über nvm (Ubuntu 24.04 selbst hat nur Node.js 18).

## Start

In jeder neuen Shell Python-Umgebung und Entwicklungseinstellungen laden:

```bash
. .venv/bin/activate && set -a && . werkzeuge/entwicklung.env && set +a
```

Dann:

```bash
cd frontend && npm ci && npm run build && cd ..
python manage.py migrate
python manage.py demodaten
uvicorn teamplaner.asgi:application --reload --port 8000
```

Danach unter http://localhost:8000 anmelden. Die Demokonten stehen in der [README](../README.md#schnellstart). `demodaten --neu` leert die Datenbank vorher. Der Befehl läuft nur mit
`DJANGO_DEBUG=1` (Entwicklung) oder `TEAMPLANER_DEMO=1` (Test- und Demo-Umgebung), nie im Produktivbetrieb.

E-Mails verschickt der Versanddienst, in einer zweiten Shell: `python manage.py mails_versenden --dauerhaft`
(lädt Codeänderungen nicht selbst nach, dann neu starten). Ohne `EMAIL_HOST` geht nichts hinaus; zum
Ansehen der Mails einen lokalen SMTP-Fänger wie Mailpit starten und die Zeilen in
`werkzeuge/entwicklung.env` aktivieren.

Python-Änderungen lädt der Server automatisch neu. Für das Frontend `npm run watch` im
Ordner `frontend` laufen lassen.

## Tests

```bash
pytest                                         # Backend
ruff check .                                   # Code-Stil
shellcheck --severity=warning werkzeuge/*.sh betrieb/linux/teamplaner betrieb/linux/*.sh pruefung/linux/*.sh
cd frontend && npm test && npm run typecheck   # Frontend
```

GitHub Actions führt alles bei jedem Push aus (`.github/workflows/tests.yml`), und zwar wie auf dem
Zielserver: Ubuntu 24.04 LTS mit Python 3.12 und PostgreSQL 16.

Für Rechteprüfung und Einteilungslogik sind automatische Tests Pflicht.

| Datei | Inhalt |
| --- | --- |
| `tests/test_rechte.py` | Rechtematrix je Rolle |
| `tests/test_planung_rechte.py` | Teamplaner-Ansichten und Freigaben |
| `tests/test_seiten_rechte.py` | serverseitige Abweisung je Rolle und Seite |
| `tests/test_kalender.py` | Feiertage, zählende Tage, Doppelbelegung |
| `tests/test_planung_api.py` | Einteilen, Verschieben, Konflikte, Feiertagsbestätigung, Protokoll |
| `tests/test_ablaeufe.py` | Einladung, Sperre, Erwähnungen, Konfliktschutz, Platzhalter, Suche |
| `tests/test_uebersetzung.py` | englische Übersetzung vollständig und kompiliert |
| `tests/test_gantt.py` | Gantt-Freigaben, Termine, Abhängigkeiten, Ringschluss, Abgleich |
| `tests/test_mail.py` | E-Mail-Einstellungen, Versand, Einladung, Passwort vergessen |
| `tests/test_feiern.py`, `tests/test_foto.py` | Feieranimation, Profilfoto |
| `tests/test_tagesfreigabe.py` | Zeile „Tagesfreigabe“: Rechte, Protokoll, Stufen, Name, Ein- und Ausschalten |
| `tests/test_notizen.py`, `tests/test_bestellungen.py` | Notizen (Sichtbarkeit, Ordnerrechte, Markdown) und Bestellungen (Prio, Liefertermin und Warnung, „bestellt“ ausfüllen, Lieferanten-Vorschläge) |
| `tests/test_heic.py` | HEIC-Fotos werden zu JPEG (Anhänge, Notiz-Anhänge, Profilfoto), Testbild in `tests/daten/` |
| `tests/test_projektliste.py` | Projektpriorität, Navigation, Mitgliederauswahl, Protokoll „erledigt“, Posteingang im Kopf, Gesamtansicht |
| `tests/test_version.py` | Versionsanzeige auf der Seite „Über“ |
| `tests/test_direkt_bearbeiten.py` | Aufgabendetail direkt bearbeiten, Konflikte, Toasts, Gantt-Einstellung am Konto |
| `tests/test_einstellungen.py` | Einstellungsbereich: Schalter, Listen-Editor, Kalender mit Zeiträumen, Personen, Freigaben, Ansichten |
| `frontend/src/teamplaner/*.test.ts` | Rasterlogik und Übersetzung im Browser |
| `frontend/src/editor/*.test.ts`, `frontend/src/lib/*.test.ts` | Markdown beim Einfügen, Editor-Rundlauf, Spaltenbreiten, Personenauswahl, Vorschläge, Restzeit der Admin-Sitzung |

Dazu prüft `shellcheck` die Betriebs- und Bauskripte.

## Aufbau

| Ordner | Inhalt |
| --- | --- |
| `kern/` | Person, Konto, Rolle, Bereich, Gewerk, Protokoll; `rechte.py` = zentrale Rechteprüfung |
| `projekte/` | Projekte, Tags, Abschnitte, Status, Aufgaben (Unteraufgaben = Aufgaben mit `eltern`) |
| `planung/` | Einteilung, Abwesenheit, freie Tage, Ansichten; `kalender.py` (Feiertage, Regeln), `dienste.py` (Schreiben mit Prüfungen), `api.py`, `live.py` (SSE) |
| `zusammenarbeit/` | Kommentare, Erwähnungen, Anhänge, Benachrichtigungen; `mail.py` (E-Mail-Kategorien und Versand) |
| `gantt/` | Gantt-Ansichten mit Freigaben; `daten.py` (Abgleich, Verletzungen), `dienste.py` (Termine, Abhängigkeiten, neue Projekte in Gesamtansichten) |
| `notizen/` | Persönliche Notizen und freigegebene Gruppenordner; `rechte.py`, `markdown.py` (Markdown → bereinigtes HTML) |
| `bestellungen/` | Bestellungsverfolgung (eine Liste für alle); `warnungen.py` (überschrittene Liefertermine) |
| `templates/` | Django-Templates (HTMX) |
| `frontend/` | Vite-Projekt: `src/main.ts` (alle Seiten), `src/teamplaner/` und `src/gantt/` (React), `src/editor/` (Tiptap) |
| `locale/en/` | englische Übersetzung |
| `betrieb/linux/` | Linux-Server: Verwaltungsbefehl `teamplaner`, `installieren.sh`, Sicherung, systemd-Dienste, nginx-/Apache-Vorlagen, Konfigurationsvorlage |
| `pruefung/linux/` | Probeserver (Ubuntu 24.04) und Ablauf für die lokale Prüfung der Linux-Installation |
| `werkzeuge/` | Entwicklung: Installationsarchiv bauen (`paket-bauen.sh`), Abhängigkeiten sperren, Übersetzungswerkzeug, Entwicklungseinstellungen |

Grundregeln:

- Rechte nie in Templates oder im Frontend allein prüfen – immer über `kern.rechte`
  bzw. `planung.rechte` in View/API.
- Einteilungen und Abwesenheiten nur über `planung.dienste` ändern (Prüfungen,
  Versionskonflikt, Protokoll, Live-Meldung).
- Aufgaben über `projekte.dienste.aufgabe_speichern` ändern (Versionskonflikt, Verlauf).

## Übersetzungen

Quelltexte sind deutsch. Neue Texte:

1. Django: in `gettext(...)`/`{% translate %}` einschließen, dann
   ```bash
   python manage.py makemessages -l en --ignore=frontend --ignore=static --ignore=staticfiles --ignore=tests --ignore=media --ignore=.venv
   ```
   englischen Text in `locale/en/LC_MESSAGES/django.po` eintragen (Texteditor oder Poedit),
   danach `python manage.py compilemessages --ignore=.venv`.
   `python werkzeuge/po_werkzeug.py pruefen locale/en/LC_MESSAGES/django.po` listet fehlende Übersetzungen.
2. Frontend: Schlüssel in `frontend/src/teamplaner/texte.ts` bzw. `frontend/src/lib/texte.ts`
   in beiden Wörterbüchern ergänzen.

## Neue Version veröffentlichen

Versionsnummern nach dem Schema `X.Y.Z`: Z für Fehlerbehebungen, Y für neue Funktionen,
X für große Umbrüche.

1. Tests lokal grün (siehe oben).
2. Installation lokal prüfen (Docker nur für die Probeserver; etwa 10 Minuten, beim ersten Mal
   länger, weil die Probeserver gebaut werden):
   ```bash
   bash pruefung/linux/pruefen.sh
   ```
   Baut das Installationsarchiv und spielt auf zwei nachgestellten Servern mit systemd wie
   dem Zielsystem (Ubuntu 24.04 LTS, Python 3.12, PostgreSQL 16) genau die Schritte aus
   [installation-linux.md](installation-linux.md) durch, als root mit umask 0077 wie auf
   gehärteten Servern: Datenbank, Installation, Webserver
   mit Zertifikat, Anmeldung und Live-Verbindung über HTTPS, Wartungsseite, Sicherung, Update
   mit Migration, Rücksprung ohne Datenverlust, defektes Update mit automatischem Rücksprung,
   Wiederherstellung, Python-Wechsel nach einem Upgrade der Distribution (`neu-aufbauen`),
   Neustart des Servers. `ubuntu-nginx` läuft mit nginx und den Standardpfaden, `ubuntu-apache`
   mit Apache und eigenen Pfaden für Konfiguration, Programm, Daten und Sicherungen. Am Ende muss
   je Server „ALLES OK“ stehen.
   Mit `BEHALTEN=1` bleiben die Probeserver stehen (`docker exec -it tp-linux-ubuntu-nginx bash`).
3. Veröffentlichen:
   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```

Der Workflow `.github/workflows/release.yml` führt alle Tests aus, baut auf Ubuntu 24.04 das
**Installationsarchiv** `teamplaner-1.2.0.tar.gz` mit Prüfsumme und hängt beides an den
Release-Eintrag auf GitHub (siehe [installation-linux.md](installation-linux.md#updates)).

Das Archiv lässt sich auch lokal bauen (Ergebnis in `dist/`):

```bash
werkzeuge/paket-bauen.sh 1.2.0
```

Datenbank-Migrationen sollten sich rückwärts ausführen lassen (bei `RunPython` eine
Rückwärtsfunktion angeben), damit `sudo teamplaner zurueck` ohne Datenverlust funktioniert.

## Abhängigkeiten aktualisieren

- Python: Bereiche in `requirements.in`/`requirements-dev.in`, gepinnte Versionen erzeugen mit
  `sh werkzeuge/abhaengigkeiten-sperren.sh` (mit Python 3.12)
- Frontend: `cd frontend && npm outdated && npm update`, danach `npm audit --omit=dev`.

## Lasttest

```bash
python manage.py lasttest
```

Legt vorübergehend 50 zusätzliche Personen mit Einteilungen und Abwesenheiten an, misst
Laden des Teamplaner-Rasters (4 Wochen, alle Personen) und Speichern einer Verschiebung und
rollt danach alles zurück. Ziele: Laden unter 2 s, Speichern unter 0,5 s.

## Bildschirmfotos

Die Bilder in `docs/bilder/` (README) entstehen aus der laufenden Entwicklungsumgebung mit
Demodaten, per Skript im installierten Chrome (`BROWSER=msedge` für Edge). Das Skript richtet die
Zwei-Faktor-Anmeldung der Bereichsleitung selbst ein und braucht deshalb frische Demodaten:

```bash
python manage.py demodaten --neu
cd frontend && npm run bildschirmfotos
```

Welche Seiten mit welchem Konto aufgenommen werden, steht in `frontend/werkzeuge/bildschirmfotos.mjs`.
Nach größeren Änderungen an der Oberfläche neu aufnehmen.
