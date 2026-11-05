# Betrieb mit Docker

Installation, Updates, Sicherung und Wiederherstellung auf einem Server mit Docker, für eine VM, einen
gemieteten Server oder einen Kleinrechner mit arm64. Ohne Docker: [installation-linux.md](installation-linux.md).

## Aufbau

`compose.prod.yaml` startet fünf Container:

| Container | Aufgabe |
| --- | --- |
| `caddy` | HTTPS (Let's Encrypt oder internes Zertifikat), Reverse Proxy, Sicherheits-Header, Wartungsseite |
| `app` | Django-Anwendung (Uvicorn/ASGI), wendet beim Start Datenbank-Migrationen an |
| `mailer` | verschickt E-Mail-Benachrichtigungen sofort (prüft alle 5 Sekunden), wendet täglich die Löschfristen an und prüft die Liefertermine der Bestellungen |
| `db` | PostgreSQL 17 |
| `backup` | wöchentliche Sicherung von Datenbank und Anhängen (sonntags) |

Daten liegen in Docker-Volumes: `pgdata` (Datenbank), `medien` (Anhänge), `caddy_data`
(Zertifikate). Sicherungen landen im Verzeichnis `BACKUP_VERZEICHNIS` (Standard `./backups`).
Bedient wird alles über das Skript `./teamplaner` im Installationsverzeichnis
(`./teamplaner hilfe` zeigt alle Befehle).

## Versionen und Pakete

Jede Version hat eine Nummer `X.Y.Z` und liegt als Paket für amd64 und arm64 unter
`ghcr.io/gehmacher-valentin/teamplaner-app`. Der Server lädt nur diese Pakete, Quellcode und Bauen sind dort
nicht nötig.

## Installation

Voraussetzungen: Linux mit Docker Engine und Docker Compose, Zugang zu `ghcr.io`
und Docker Hub (bei `TLS_ART=auto` auch Let's Encrypt).

1. **Docker installieren:** nach der [Anleitung von Docker](https://docs.docker.com/engine/install/).
2. **Betriebsdateien holen:**
   ```bash
   sudo mkdir -p /srv/teamplaner && sudo chown "$USER": /srv/teamplaner && cd /srv/teamplaner
   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/ziel" ghcr.io/gehmacher-valentin/teamplaner-app:latest auspacken
   ```
   Das legt `teamplaner` (Verwaltungsskript), `compose.prod.yaml`, `.env.example` und
   `docker/` (Caddy, Sicherung) an.
3. **Konfigurieren:**
   ```bash
   cp .env.example .env && chmod 600 .env
   nano .env
   ```
4. **Starten:** `./teamplaner start`

Werte in `.env`:

- `TEAMPLANER_DOMAIN`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS`: die Adresse
  des Systems (z. B. `teamplaner.example.org` bzw. `https://teamplaner.example.org`).
- `TLS_ART=auto`: Zertifikat von Let's Encrypt – Domain muss aus dem Internet erreichbar
  sein (Port 80 und 443). `TLS_ART=intern`: Caddy erzeugt ein eigenes Zertifikat (internes
  Netz, VPN). Browser zeigen dann eine Warnung, bis das Stammzertifikat aus dem Volume
  `caddy_data` (`/data/caddy/pki/authorities/local/root.crt`) auf den Geräten verteilt ist.
  Ein eigenes Zertifikat lässt sich in `docker/caddy/Caddyfile` mit
  `tls /pfad/zertifikat.pem /pfad/schluessel.pem` eintragen.
- `DJANGO_SECRET_KEY`: langer Zufallswert, z. B. `openssl rand -base64 48`.
- `POSTGRES_PASSWORD`: langes Zufallspasswort.
- `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL`:
  SMTP-Server für Einladungen, „Passwort vergessen“ und Benachrichtigungen. Leer = kein Versand; Einladungs- und Reset-Links lassen sich dann nur kopieren. Ein- und
  ausschalten lässt sich der Versand zusätzlich in der App unter Einstellungen → Allgemein.
  `TEAMPLANER_ADRESSE` ist die Adresse, auf die Links in E-Mails zeigen.
- `TEAMPLANER_VERSION` setzt `./teamplaner update` selbst.

### Erstes Admin-Konto

```bash
./teamplaner konto-anlegen --email admin@example.org --name "Vorname Nachname" \
  --bereich Allgemein --rolle admin --adresse https://teamplaner.example.org
```

Der Befehl gibt einen Link aus, mit dem das Passwort gesetzt wird. Bei der ersten Anmeldung
richtet das Admin-Konto die Zwei-Faktor-Anmeldung ein (Authenticator-App am Telefon; Pflicht für
Admin und Bereichsleitung). Alle weiteren Konten legen Admin oder Bereichsleitung unter
**Einstellungen → Personen** an; die Einladung geht per E-Mail hinaus (sofern SMTP eingetragen ist) und
lässt sich zusätzlich als Link kopieren.

### Aus dem Quellcode

Ohne Zugang zu `ghcr.io` lässt sich die Anwendung auch auf dem Server bauen:
`git clone`, `.env` wie oben, dann
`docker compose -f compose.prod.yaml -f compose.build.yaml --env-file .env up -d --build`.
Updates dort mit `git pull` und demselben Befehl; `./teamplaner update` und
`./teamplaner zurueck` gelten nur für Installationen aus Paketen.

### Hinter einem vorhandenen Reverse Proxy

`TLS_ART=intern` setzen und in `TEAMPLANER_DOMAIN`, `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS` und `TEAMPLANER_ADRESSE` den öffentlichen Namen eintragen. Der Proxy leitet
per **HTTPS** an Port 443 weiter (bei HTTP entsteht eine Weiterleitungsschleife) und prüft das interne
Zertifikat nicht. Die Live-Aktualisierung braucht nichts Zusätzliches: Die Anwendung sendet alle 20 s ein
Lebenszeichen.

## Test- und Produktivumgebung

Zwei getrennte Verzeichnisse mit eigener `.env` und eigenem `./teamplaner`, z. B.
`/srv/teamplaner-test` und `/srv/teamplaner`. Unterschiedliche Werte für
`COMPOSE_PROJECT_NAME`, `TEAMPLANER_DOMAIN` und – wenn beide auf demselben Server laufen –
`HTTP_PORT`/`HTTPS_PORT`. Updates zuerst in der Testumgebung einspielen und prüfen, dann
dieselbe Version in der Produktivumgebung: `./teamplaner update 1.2.0`.

## Update

Updates werden nie automatisch eingespielt, sondern nur auf Befehl:

```bash
cd /srv/teamplaner
./teamplaner status      # installierte und neueste Version, Zustand, letzte Sicherung
./teamplaner update      # neueste Version – oder gezielt: ./teamplaner update 1.2.0
```

Ablauf:

1. Das neue Paket wird geladen, während das System weiterläuft; dann folgt eine Rückfrage.
2. Die Anwendung hält an. Besucher sehen eine Wartungsseite, die sich selbst neu lädt.
3. Sicherung von Datenbank und Anhängen (`backups/…_vor-update-<version>`).
4. Die Betriebsdateien der neuen Version werden übernommen; die `.env` bleibt unverändert.
   Neue Einstellungen aus `.env.example` werden am Ende genannt.
5. Die neue Version startet, wendet Datenbank-Migrationen an und muss innerhalb von fünf
   Minuten gesund antworten.
6. **Startet sie nicht, geht es automatisch zurück:** alte Version, Datenbank aus der
   Sicherung von Schritt 3. Das Fehlerprotokoll der neuen Version liegt unter `stand/`.

Nicht erreichbar ist das System nur während Sicherung und Neustart – meist unter einer
Minute. Offene Teamplaner-Seiten verbinden sich danach
selbst neu und laden verpasste Änderungen nach.

### Rücksprung auf die Vorversion

```bash
./teamplaner zurueck
```

Nimmt die Datenbank-Migrationen der neueren Version zurück und startet die vorherige
Version. Einträge seit dem Update bleiben erhalten, soweit die alte Version sie darstellen
kann. Lässt sich eine Migration nicht zurücknehmen, bietet der Befehl an, die Sicherung vom
Update einzuspielen – dann gehen Einträge seit dem Update verloren (eigene Rückfrage, auch
mit `--ja`). Zurück geht es jeweils einen Schritt; für ältere Stände eine Sicherung aus jener
Zeit einspielen und `TEAMPLANER_VERSION` in der `.env` passend setzen.

## Backup

Der Container `backup` sichert jeden Sonntag um `BACKUP_UHRZEIT` (Standard 02:30):

- `datenbank_JJJJ-MM-TT_HHMM.dump` – PostgreSQL im Custom-Format
- `anhaenge_JJJJ-MM-TT_HHMM.tar.gz` – alle Anhänge

Sicherungen älter als `BACKUP_TAGE` (Standard 30, also die letzten vier bis fünf) werden gelöscht. Das Backup-Verzeichnis
sollte zusätzlich auf ein anderes System kopiert werden (z. B. nächtlicher `rsync`), denn eine Sicherung auf demselben Server schützt nicht vor dem Ausfall des Servers.

Sofort sichern: `./teamplaner sichern` · Protokoll: `./teamplaner logs backup`

## Wiederherstellung

```bash
./teamplaner wiederherstellen backups/datenbank_2026-10-21_0230.dump backups/anhaenge_2026-10-21_0230.tar.gz
```

Der Befehl fragt nach, hält die Anwendung an (Besucher sehen die Wartungsseite), ersetzt die
Datenbank vollständig – auch Tabellen späterer Versionen verschwinden – und die Anhänge und
startet wieder. Ohne Anhänge-Datei wird nur die Datenbank zurückgesetzt.

## E-Mail

Jede Person wählt unter **Einstellungen → Benachrichtigungen** je Ereignis, wofür sie eine E-Mail bekommt;
Standard ist alles aus. Der Container `mailer` verschickt offene Benachrichtigungen sofort,
fehlgeschlagene bis zu fünfmal erneut. Protokoll: `./teamplaner logs mailer`.
Test nach dem Einrichten: eine Person einladen, die Mail muss ankommen.

## Überwachung

- `https://<domain>/gesund/` liefert `{"status": "ok"}`, solange Anwendung und Datenbank
  erreichbar sind – geeignet für ein externes Monitoring.
- Zustand, Version, letzte Sicherung: `./teamplaner status`
- Fehlerlog: `./teamplaner logs app`
- Speicherplatz: `docker system df` und `du -sh backups`

## Sicherheit

- Nur HTTPS; Caddy setzt HSTS, `nosniff`, `Referrer-Policy`. Cookies sind `Secure` und `HttpOnly`.
- Passwörter mit Argon2; Sperre eines Kontos nach `TEAMPLANER_FEHLVERSUCHE` Fehlversuchen für
  `TEAMPLANER_SPERRE_MINUTEN` Minuten (Groß-/Kleinschreibung der E-Mail egal), zusätzlich Sperre
  einer IP-Adresse nach `TEAMPLANER_FEHLVERSUCHE_JE_IP` Fehlversuchen über alle Konten.
- Zwei-Faktor-Anmeldung (Code aus einer Authenticator-App) Pflicht für Admin und Bereichsleitung,
  freiwillig für alle anderen. Telefon verloren: Ersatzcodes, oder Admin/Bereichsleitung setzen sie
  unter **Einstellungen → Personen** zurück; für Admin-Konten
  `… manage.py zwei_faktor_zuruecksetzen <email>`.
- Angemeldet bleiben bis `TEAMPLANER_SITZUNG_TAGE` (30) Tage nach der Anmeldung; Admins werden nach
  `TEAMPLANER_ADMIN_INAKTIV_MINUTEN` (60) Minuten ohne eigene Aktivität abgemeldet.
- Konten ändern, deaktivieren oder Passwort-Links auslösen nur für Konten mit niedrigerer Rolle;
  andere Admin-Konten nur über die Kommandozeile (`… manage.py shell`). Links zum Zurücksetzen
  eines bestehenden Passworts gehen nur per E-Mail an die Person selbst und gelten
  `TEAMPLANER_RESET_GUELTIG_STUNDEN` (2) Stunden. Bei Änderungen an Passwort, E-Mail-Adresse oder
  Zwei-Faktor-Anmeldung bekommt die Person einen Sicherheitshinweis per E-Mail.
- Gesperrtes Konto vorzeitig freigeben (E-Mail kleingeschrieben):
  `docker compose -f compose.prod.yaml --env-file .env exec app python manage.py axes_reset_username <email>`,
  gesperrte IP-Adresse: `… manage.py axes_reset_ip <ip>`
- Das Änderungsprotokoll ist in der Datenbank gegen Ändern geschützt und lässt sich erst nach einem Jahr
  löschen. Löschfristen (`TEAMPLANER_AUFBEWAHRUNG_TAGE`, 365; `TEAMPLANER_DEAKTIVIERT_TAGE`, 90) wendet der
  Dienst `mailer` täglich an, sofort: `… manage.py aufraeumen`. Deaktivierte Konten verlieren nach der
  Frist E-Mail, Passwort, Foto und persönliche Notizen; Name, Kommentare und Anhänge bleiben.
- Große oder alte Anhänge findet und löscht der Admin unter **Einstellungen → Speicherplatz**.
- Die `.env` enthält Passwörter: nur für den Betreiber lesbar (`chmod 600 .env`).
- Sicherheitsupdates von Python, Django und den übrigen Bibliotheken kommen mit neuen
  Versionen. Das Betriebssystem des Servers selbst aktuell halten (z. B. `unattended-upgrades`).
