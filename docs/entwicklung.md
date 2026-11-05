# Entwicklung

## Voraussetzungen

- Docker
- Node.js 20.19+ oder 22 für den Frontend-Build

Python und PostgreSQL laufen im Container, lokal ist nichts weiter nötig.

## Start

```bash
cd frontend && npm ci && npm run build && cd ..
docker compose up -d
docker compose exec app python manage.py migrate
docker compose exec app python manage.py demodaten
```

Danach unter http://localhost:8000 anmelden. Die Demokonten stehen in der [README](../README.md#schnellstart). `demodaten --neu` leert die Datenbank vorher. Der Befehl läuft nur mit
`DJANGO_DEBUG=1` (Entwicklung) oder `TEAMPLANER_DEMO=1` (Test- und Demo-Umgebung), nie im Produktivbetrieb.

E-Mails landen in Mailpit: http://localhost:8025 (nichts geht nach außen). Der Versanddienst
`mailer` lädt Codeänderungen nicht selbst nach: `docker compose restart mailer`.

Python-Änderungen lädt der Server automatisch neu. Für das Frontend `npm run watch` im
Ordner `frontend` laufen lassen.

## Tests

```bash
docker compose exec app pytest                 # Backend
docker compose exec app ruff check .           # Code-Stil
cd frontend && npm test && npm run typecheck   # Frontend
```

GitHub Actions führt alles bei jedem Push aus (`.github/workflows/tests.yml`).

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
| `tests/test_version.py` | Versionsanzeige, Suche nach neueren Versionen in der Registry |
| `tests/test_direkt_bearbeiten.py` | Aufgabendetail direkt bearbeiten, Konflikte, Toasts, Gantt-Einstellung am Konto |
| `tests/test_einstellungen.py` | Einstellungsbereich: Schalter, Listen-Editor, Kalender mit Zeiträumen, Personen, Freigaben, Ansichten |
| `frontend/src/teamplaner/*.test.ts` | Rasterlogik und Übersetzung im Browser |
| `frontend/src/editor/*.test.ts`, `frontend/src/lib/*.test.ts` | Markdown beim Einfügen, Editor-Rundlauf, Spaltenbreiten, Personenauswahl, Vorschläge, Restzeit der Admin-Sitzung |

Dazu prüft `shellcheck` die Betriebsskripte in `docker/`.

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
| `betrieb/linux/` | Linux-Server ohne Docker: Verwaltungsbefehl `teamplaner`, `installieren.sh`, systemd-Dienste, nginx-/Apache-Vorlagen, Konfigurationsvorlage |
| `pruefung/linux/` | Probeserver (Debian, Rocky) und Ablauf für die lokale Prüfung der Linux-Installation |
| `docker/` | Container-Betrieb (`teamplaner.sh` = `./teamplaner`, Start, Auspacken, Wiederherstellung), Caddy-Konfiguration; `backup.sh` dient beiden Betriebsarten |

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
   docker compose exec app python manage.py makemessages -l en --ignore=frontend --ignore=static --ignore=staticfiles --ignore=tests --ignore=media
   ```
   englischen Text in `locale/en/LC_MESSAGES/django.po` eintragen (Texteditor oder Poedit),
   danach `docker compose exec app python manage.py compilemessages --ignore="*site-packages*"`.
   `docker/po_werkzeug.py pruefen locale/en/LC_MESSAGES/django.po` listet fehlende Übersetzungen.
2. Frontend: Schlüssel in `frontend/src/teamplaner/texte.ts` bzw. `frontend/src/lib/texte.ts`
   in beiden Wörterbüchern ergänzen.

## Neue Version veröffentlichen

Versionsnummern nach dem Schema `X.Y.Z`: Z für Fehlerbehebungen, Y für neue Funktionen,
X für große Umbrüche.

1. Tests lokal grün (siehe oben).
2. Installation lokal prüfen (nur Docker nötig; etwa 3 Minuten, beim ersten Mal
   länger, weil die Probeserver gebaut werden):
   ```bash
   bash pruefung/linux/pruefen.sh
   ```
   Baut das Installationsarchiv und spielt auf zwei nachgestellten Servern mit systemd –
   Debian 12 mit nginx und Rocky Linux 9 (wie RHEL) mit Apache – genau die Schritte aus
   [installation-linux.md](installation-linux.md) durch – als root mit umask 0077 wie auf
   gehärteten Servern: Datenbank, Installation, Webserver
   mit Zertifikat, Anmeldung und Live-Verbindung über HTTPS, Wartungsseite, Sicherung, Update
   mit Migration, Rücksprung ohne Datenverlust, defektes Update mit automatischem Rücksprung,
   Wiederherstellung, Python-Wechsel nach einem Upgrade der Distribution (`neu-aufbauen`),
   Neustart des Servers. Am Ende muss je Server „ALLES OK“ stehen.
   Mit `BEHALTEN=1` bleiben die Probeserver stehen (`docker exec -it tp-linux-debian bash`).
3. Veröffentlichen:
   ```bash
   git tag v1.2.0
   git push origin v1.2.0
   ```

Der Workflow `.github/workflows/release.yml` führt alle Tests aus und baut
- das **Installationsarchiv** `teamplaner-1.2.0.tar.gz` mit Prüfsumme für Linux-Server ohne
  Docker, beides am Release-Eintrag auf GitHub (siehe [installation-linux.md](installation-linux.md#updates));
- die **Container-Pakete** für amd64 und arm64 unter `ghcr.io/gehmacher-valentin/teamplaner-app`
  (Tags `1.2.0`, `1.2`, `latest`) für Docker-Installationen (siehe [betrieb.md](betrieb.md#update)).

Das Archiv lässt sich auch lokal bauen:
`docker build --target linux-paket --build-arg TEAMPLANER_VERSION=1.2.0 --output type=local,dest=dist .`

Lokal ausprobieren, ohne zu veröffentlichen:
`docker compose -f compose.prod.yaml -f compose.build.yaml --env-file .env up -d --build`
(eigene `.env` mit anderen Ports und `COMPOSE_PROJECT_NAME`).

Datenbank-Migrationen sollten sich rückwärts ausführen lassen (bei `RunPython` eine
Rückwärtsfunktion angeben), damit `./teamplaner zurueck` ohne Datenverlust funktioniert.

## Abhängigkeiten aktualisieren

- Python: Bereiche in `requirements.in`/`requirements-dev.in`, gepinnte Versionen erzeugen mit
  `docker run --rm -v "$(pwd)":/app -w /app python:3.13-slim sh docker/abhaengigkeiten-sperren.sh`
- Frontend: `cd frontend && npm outdated && npm update`, danach `npm audit --omit=dev`.

## Lasttest

```bash
docker compose exec app python manage.py lasttest
```

Legt vorübergehend 50 zusätzliche Personen mit Einteilungen und Abwesenheiten an, misst
Laden des Teamplaner-Rasters (4 Wochen, alle Personen) und Speichern einer Verschiebung und
rollt danach alles zurück. Ziele: Laden unter 2 s, Speichern unter 0,5 s.

## Bildschirmfotos

Die Bilder in `docs/bilder/` (README) entstehen aus der laufenden Entwicklungsumgebung mit
Demodaten, per Skript im installierten Chrome (`BROWSER=msedge` für Edge). Das Skript richtet die
Zwei-Faktor-Anmeldung der Bereichsleitung selbst ein und braucht deshalb frische Demodaten:

```bash
docker compose exec app python manage.py demodaten --neu
cd frontend && npm run bildschirmfotos
```

Welche Seiten mit welchem Konto aufgenommen werden, steht in `frontend/werkzeuge/bildschirmfotos.mjs`.
Nach größeren Änderungen an der Oberfläche neu aufnehmen.
