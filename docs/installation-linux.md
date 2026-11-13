# Installation auf einem Linux-Server

Für Administrator:innen, die Linux-Server betreiben. Teamplaner läuft direkt auf dem Server, ohne
Container, als systemd-Dienste unter einem eigenen Benutzer hinter nginx oder Apache. Die Installation
braucht kein Internet, alle Python-Pakete liegen dem Archiv bei.

| Teil | Aufgabe |
| --- | --- |
| `teamplaner-web.service` | Webanwendung, lauscht lokal auf `127.0.0.1:8000` |
| `teamplaner-mailer.service` | verschickt E-Mails, wendet täglich die Löschfristen an, prüft Liefertermine |
| `teamplaner-sicherung.timer` | sichert Datenbank und Anhänge jeden Sonntag um 02:30 |
| PostgreSQL | Daten |
| nginx oder Apache | HTTPS mit Zertifikat, Weiterleitung an die Anwendung, Wartungsseite bei Updates |
| `teamplaner` | Verwaltungsbefehl (`sudo teamplaner hilfe`) |

## Aufbau

```
Browser ── 443 HTTPS ──▶ Webserver (nginx/Apache, Zertifikat) ── HTTP ──▶ 127.0.0.1:8000 Teamplaner ──▶ PostgreSQL
        ── 80 HTTP ───▶ Webserver: nur 301 auf HTTPS
```

- Von außen erreichbar ist nur der Webserver: 443 für HTTPS, 80 nur für die Weiterleitung auf HTTPS
  (und, falls genutzt, die Let's-Encrypt-Prüfung).
- Die Anwendung lauscht nur auf `127.0.0.1:8000`, ohne TLS. Port 8000 wird nicht freigegeben; er ist von
  außen ohnehin nicht erreichbar.
- Der Webserver ist Pflicht (Reverse Proxy): Er beendet TLS und reicht die Anfragen weiter. Die Anwendung
  braucht und kennt kein Zertifikat.
- Ein vorhandener Webserver lässt sich nutzen: Teamplaner bekommt dort einen eigenen vHost, siehe
  [Webserver](#4-webserver). Installation der Anwendung (Schritte 1 bis 3) und Webserver sind getrennt.

## Vor der Installation

### Zu entscheiden

| Frage | Möglichkeiten | Worauf es ankommt |
| --- | --- | --- |
| Unter welcher Adresse läuft Teamplaner? | eigene Domain oder Subdomain | Die Adresse steht in allen Links in E-Mails. Später ändern heißt: alte Links gelten nicht mehr. Ein Unterpfad wie `https://intranet.example.org/teamplaner/` geht nicht, Teamplaner liegt immer unter `/`. |
| Wer soll es erreichen? | nur intern oder VPN, oder aus dem Internet | Die Anmeldung ist für den Betrieb aus dem Internet ausgelegt (Zwei-Faktor, Sperren). Die Firewall braucht eingehend nur 80 und 443, beide zum Webserver. |
| Woher kommt das Zertifikat? | vorhandenes, Let's Encrypt, interne CA, gekauft | Nur der Webserver braucht es, nicht die Anwendung. Es muss die Adresse abdecken (Name im Zertifikat oder Wildcard). Ein vorhandenes, automatisch erneuertes Zertifikat geht; die Erneuerung bleibt beim Webserver, Teamplaner merkt davon nichts. HTTPS ist Pflicht, ohne funktionieren Anmeldung und Cookies nicht. |
| Welcher Webserver? | vorhandener nginx oder Apache, neu installierter, zentraler Proxy | Vorlagen liegen für nginx und Apache bei. Für einen eigenen Proxy siehe [Anforderungen an den Webserver](#anforderungen-an-den-webserver). |
| Wo läuft die Datenbank? | auf demselben Server (empfohlen) oder zentral | Zentral: Verbindung ist nicht verschlüsselt und PgBouncer im Transaktionsmodus geht nicht, weil die Live-Aktualisierung `LISTEN/NOTIFY` nutzt. |
| Gibt es E-Mail? | SMTP-Server oder keiner | Dringend empfohlen. Ohne E-Mail keine Einladungen, kein „Passwort vergessen“ und keine Benachrichtigungen per Mail; Links gibt dann die Verwaltung von Hand weiter. |
| Wohin gehen die Sicherungen zusätzlich? | Backup-System, Netzlaufwerk | Die eingebaute Sicherung liegt auf demselben Server. Sie schützt vor Fehlbedienung, nicht vor dem Ausfall des Servers. |
| Wie lange bleiben Daten? | Standardwerte oder eigene Fristen | Protokolle und Benachrichtigungen 365 Tage, deaktivierte Konten 90 Tage. Die eigene Datenschutzvorgabe prüfen. |
| Wer wird erste:r Admin? | eine Person, oder ein technisches Konto mit `--systemkonto` | Admins brauchen eine Authenticator-App. Ein Systemkonto erscheint in keiner Personenauswahl. |

Zeitzone (`Europe/Vienna`) und automatische Feiertage (Österreich) sind fest eingestellt. Weitere freie
Tage trägt ein Admin in der Anwendung ein.

### Bereitzuhalten

- [ ] Server, der die [Anforderungen](#anforderungen) erfüllt, mit `sudo`-Zugang
- [ ] DNS-Eintrag der Adresse auf den Server
- [ ] für den Webserver: Zertifikat für die Adresse mit Zwischenzertifikaten und privatem Schlüssel
      (PEM), oder das vorhandene, falls es die Adresse abdeckt
- [ ] SMTP: Server, Port, Benutzer, Passwort und Absenderadresse
- [ ] E-Mail-Adresse und Name für das erste Admin-Konto
- [ ] Installationsarchiv `teamplaner-X.Y.Z.tar.gz` und `.sha256` von der
      [Release-Seite](https://github.com/gehmacher-valentin/teamplaner/releases)

### Anforderungen

| | |
| --- | --- |
| System | Ubuntu 24.04 LTS x86_64 |
| Python | 3.12 aus Ubuntu (Pakete `python3`, `python3-venv`); das Archiv enthält die Python-Pakete genau dafür |
| PostgreSQL | 16 aus Ubuntu (Pakete `postgresql`, `postgresql-client`) |
| Webserver | nginx oder Apache, mit HTTP/2; ein vorhandener geht |
| Ressourcen | 2 CPU-Kerne, 4 GB RAM, 20 GB Speicher plus Platz für Anhänge und Sicherungen |
| Netzwerk | eingehend 80 und 443 zum Webserver, ausgehend nur der SMTP-Server; 8000 bleibt lokal |

Die Installation wird automatisch auf Ubuntu 24.04 LTS (Python 3.12, PostgreSQL 16) geprüft: mit nginx
und den Standardpfaden sowie mit Apache und eigenen Pfaden.

## Installation

### 1. Pakete

Für die Anwendung:

```bash
sudo apt install python3 python3-venv postgresql postgresql-client
```

Nur wenn noch kein Webserver läuft: `sudo apt install nginx` (oder `apache2`).

### 2. Datenbank

```bash
sudo -u postgres psql -c "CREATE ROLE teamplaner LOGIN PASSWORD 'langes-zufallspasswort'"
sudo -u postgres psql -c "CREATE DATABASE teamplaner OWNER teamplaner ENCODING 'UTF8' TEMPLATE template0"
```

Superuser-Rechte sind nicht nötig, die Rolle muss nur Eigentümerin der Datenbank sein.

### 3. Teamplaner

```bash
sha256sum -c teamplaner-1.0.0.tar.gz.sha256
tar -xzf teamplaner-1.0.0.tar.gz
cd teamplaner-1.0.0
sudo ./installieren.sh                      # legt /etc/teamplaner/teamplaner.env an
sudo nano /etc/teamplaner/teamplaner.env    # Werte eintragen, bei Bedarf andere Pfade
sudo ./installieren.sh                      # installiert, richtet die Datenbank ein, startet
```

Andere Installationspfade: siehe [Andere Pfade](#andere-pfade).

Pflichtwerte in `/etc/teamplaner/teamplaner.env`:

| Einstellung | Inhalt |
| --- | --- |
| `DJANGO_ALLOWED_HOSTS` | Domain, z. B. `teamplaner.example.org` |
| `DJANGO_CSRF_TRUSTED_ORIGINS`, `TEAMPLANER_ADRESSE` | Adresse mit `https://` |
| `POSTGRES_PASSWORD` | Passwort aus Schritt 2 |
| `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `DEFAULT_FROM_EMAIL` | SMTP; leer = kein Versand |

`DJANGO_SECRET_KEY` erzeugt die Installation selbst. Die übrigen Werte sind in der Datei beschrieben und
haben Standardwerte:

| Einstellung | Standard | Bedeutung |
| --- | --- | --- |
| `TEAMPLANER_SITZUNG_TAGE` | 30 | angemeldet bleiben bis so viele Tage nach der Anmeldung |
| `TEAMPLANER_ADMIN_INAKTIV_MINUTEN` | 60 | Admins nach so vielen Minuten ohne Aktivität abmelden |
| `TEAMPLANER_FEHLVERSUCHE` / `TEAMPLANER_FEHLVERSUCHE_JE_IP` | 5 / 20 | Sperre je Konto bzw. IP-Adresse für `TEAMPLANER_SPERRE_MINUTEN` (15) |
| `TEAMPLANER_LINK_GUELTIG_TAGE` / `TEAMPLANER_RESET_GUELTIG_STUNDEN` | 7 / 2 | Gültigkeit von Einladungs- und Reset-Links |
| `TEAMPLANER_AUFBEWAHRUNG_TAGE` / `TEAMPLANER_DEAKTIVIERT_TAGE` | 365 / 90 | Löschfristen für Protokolle und deaktivierte Konten |
| `TEAMPLANER_ANHANG_MAX_MB` | 25 | größter Anhang; die Grenze im Webserver (30 MB) mitziehen |
| `BACKUP_TAGE` | 30 | Aufbewahrung der Sicherungen |

Eine bestimmte Python-Version erzwingen: `sudo TEAMPLANER_PYTHON=python3.12 ./installieren.sh`

Die Installation legt an:

| Pfad (Standard) | Inhalt | Ändern |
| --- | --- | --- |
| Benutzer und Gruppe `teamplaner` | Systembenutzer ohne Anmeldung | |
| `/opt/teamplaner/versionen/<version>` | Programm mit eigener Python-Umgebung, schreibgeschützt | `TEAMPLANER_PROGRAMM` |
| `/opt/teamplaner/aktuell` | Verweis auf die laufende Version | `TEAMPLANER_PROGRAMM` |
| `/opt/teamplaner/wartung` | Wartungsseite für den Webserver | `TEAMPLANER_PROGRAMM` |
| `/etc/teamplaner/teamplaner.env` | Konfiguration, Rechte 0640 | `TEAMPLANER_KONFIG` |
| `/var/lib/teamplaner/medien` | Anhänge und Profilfotos | `TEAMPLANER_DATEN` |
| `/var/lib/teamplaner/stand` | Update-Protokolle | `TEAMPLANER_DATEN` |
| `/var/backups/teamplaner` | Sicherungen | `TEAMPLANER_SICHERUNGEN` |
| `/etc/systemd/system/teamplaner-*` | Dienste und Timer | fest |
| `/usr/local/sbin/teamplaner` | Verwaltungsbefehl | fest |

#### Andere Pfade

Programm-, Daten- und Sicherungsverzeichnis stehen in der Konfiguration im Abschnitt „Pfade“. Sie werden
zwischen dem ersten und dem zweiten Aufruf von `installieren.sh` eingetragen und gelten ab dann fest:
Die Installation schreibt sie in die systemd-Dienste und richtet Eigentümer und Rechte ein.

```
TEAMPLANER_PROGRAMM=/srv/teamplaner/programm
TEAMPLANER_DATEN=/srv/teamplaner/daten
TEAMPLANER_SICHERUNGEN=/srv/teamplaner/sicherungen
```

Den Ort der Konfiguration selbst legt der erste Aufruf fest. Der zweite Aufruf übernimmt ihn ohne
erneute Angabe und trägt ihn fest in den Verwaltungsbefehl ein:

```bash
sudo TEAMPLANER_KONFIG=/srv/teamplaner/konfig/teamplaner.env ./installieren.sh
```

Regeln, die `installieren.sh` vor dem Installieren prüft:

- absolute Pfade aus Buchstaben, Ziffern und `. _ -`
- je ein eigenes Verzeichnis, nicht ineinander; die Konfiguration nicht in einem der drei
- kein Systemverzeichnis wie `/srv` oder `/var/lib`, nichts unter `/home`, `/root`, `/run` oder `/tmp`
  (für die gehärteten Dienste nicht sichtbar)
- das Verzeichnis besteht noch nicht oder ist leer; ein vorab eingehängtes Laufwerk mit `lost+found`
  geht
- die Verzeichnisse darüber darf jeder betreten (`o+x`), sonst kommen Dienstbenutzer und Webserver nicht
  hin; das betrifft vor allem selbst angelegte Verzeichnisse auf Servern mit `umask 077`

Bei anderem Programmverzeichnis in der Webserver-Konfiguration auch den Pfad der Wartungsseite anpassen.
Nach der Installation die Pfade nicht mehr ändern: `sudo teamplaner pruefen` meldet es, wenn sie nicht
mehr zu den Diensten passen.

### 4. Webserver

Teamplaner bekommt im Webserver einen eigenen vHost für seine Adresse. Die Vorlage ist genau dieser
vHost: Port 80 leitet auf HTTPS weiter, Port 443 reicht an die Anwendung weiter. Bei einem vorhandenen
Webserver kommt nur diese eine Datei dazu; übrige vHosts, Zertifikatserneuerung und Firewall bleiben,
wie sie sind.

In der Vorlage anpassen:

- Domain: nginx 2×, Apache 3×
- Zertifikat und Schlüssel: die Pfade des vorhandenen Zertifikats, bei certbot z. B.
  `/etc/letsencrypt/live/<domain>/fullchain.pem` und `privkey.pem`. Ein neues Zertifikat z. B. als
  `/etc/ssl/teamplaner/zertifikat.pem` und `/etc/ssl/teamplaner/schluessel.pem` ablegen, dann bleibt die
  Vorlage, wie sie ist.
- bei anderem `TEAMPLANER_PROGRAMM` den Pfad der Wartungsseite

**nginx**:

```bash
sudo cp /opt/teamplaner/aktuell/betrieb/linux/nginx/teamplaner.conf /etc/nginx/sites-available/
sudo nano /etc/nginx/sites-available/teamplaner.conf
sudo ln -s /etc/nginx/sites-available/teamplaner.conf /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

**Apache** (statt nginx, Paket `apache2`):

```bash
sudo cp /opt/teamplaner/aktuell/betrieb/linux/apache/teamplaner.conf /etc/apache2/sites-available/
sudo nano /etc/apache2/sites-available/teamplaner.conf
sudo a2enmod ssl proxy proxy_http headers http2 && sudo a2ensite teamplaner
sudo apachectl configtest && sudo systemctl reload apache2
```

#### Zertifikat und Erneuerung

Das Zertifikat liest nur der Webserver. Wird es erneuert, reicht wie bei den übrigen vHosts ein Reload
des Webservers; an Teamplaner wird nichts weitergegeben und nichts neu gestartet. certbot lädt den
Webserver mit dem nginx- bzw. Apache-Plugin selbst neu, sonst mit
`--deploy-hook "systemctl reload nginx"` (bzw. `apache2`).

Prüft certbot per Webroot (HTTP-01), muss `/.well-known/acme-challenge/` aus dem Webroot kommen statt aus
der Anwendung. Let's Encrypt folgt der Weiterleitung von Port 80 auf HTTPS; deshalb steht die Ausnahme
in beiden Vorlagen vorbereitet im HTTPS-vHost: dort `#acme ` vor den Zeilen entfernen, Webroot
`/var/www/letsencrypt`. Mit dem nginx- oder Apache-Plugin von certbot und mit DNS-01 ist nichts zu tun.

#### Anforderungen an den Webserver

Das gilt für eine eigene Konfiguration oder einen zentralen Proxy:

- eigener vHost für die Adresse, Weiterleitung von `/` (kein Unterpfad)
- Weiterleitung an `http://127.0.0.1:8000` mit `X-Forwarded-Proto: https` und dem `Host` des Aufrufs
- Adresse der Besucher in `X-Forwarded-For`, sonst sperrt die IP-Sperre im Zweifel alle
- `/api/planung/stream` (Server-Sent Events) nicht puffern und bis 1 Stunde offen halten
- HTTP/2 zum Browser: jede offene Seite hält eine Live-Verbindung, mit HTTP/1.1 gehen nur sechs je Browser
- Anfragen bis 30 MB zulassen
- bei 502 und 503 die Wartungsseite `/opt/teamplaner/wartung/wartung.html` zeigen (liegt unter
  `TEAMPLANER_PROGRAMM`)

Proxy auf einem anderen Rechner: in der Konfiguration `TEAMPLANER_HOST=0.0.0.0` und
`TEAMPLANER_PROXY_IPS=<IP des Proxys>` setzen und Port 8000 nur für den Proxy freigeben. Die Strecke vom
Proxy zur Anwendung ist dann unverschlüsseltes HTTP im internen Netz. Die Wartungsseite auf den Proxy
kopieren, wenn er sie zeigen soll.

### 5. Erstes Konto und Prüfung

```bash
sudo teamplaner konto-anlegen --email admin@example.org --name "Vorname Nachname" \
  --bereich Allgemein --rolle admin
sudo teamplaner pruefen
```

`konto-anlegen` gibt einen Link aus, 7 Tage gültig, unter dem das Passwort gesetzt wird. Ist der
E-Mail-Versand eingerichtet, geht die Einladung zusätzlich per E-Mail an die Person (`--keine-mail`
unterdrückt das); ohne Versand sagt der Befehl ausdrücklich, dass keine E-Mail hinausgeht. Bei der ersten
Anmeldung richtet das Konto die Zwei-Faktor-Anmeldung ein; die Ersatzcodes sicher aufbewahren.
`pruefen` kontrolliert Konfiguration, Datenbank, Dienste, Sicherung und Rechte.

Danach in der Anwendung unter **Einstellungen**:

1. **Allgemein:** Organisationsname, Tagesfreigabe nach Bedarf
2. **Listen:** Bereiche, Gewerke und Status an die eigene Organisation anpassen
3. **Kalender:** zusätzliche freie Tage
4. **Personen:** weitere Personen einladen. Die Einladung testet zugleich den E-Mail-Versand.

## Betrieb

| Befehl | Wirkung |
| --- | --- |
| `sudo teamplaner status` | Version, Dienste, Erreichbarkeit, letzte und nächste Sicherung |
| `sudo teamplaner pruefen` | Installation und Konfiguration prüfen |
| `sudo teamplaner logs [web\|mailer\|sicherung]` | Protokoll ansehen |
| `sudo teamplaner neustart` | nach Änderungen an der Konfiguration |
| `sudo teamplaner sichern` | sofort sichern |
| `sudo teamplaner wiederherstellen DUMP [ANHAENGE]` | Sicherung einspielen (fragt nach) |
| `sudo teamplaner neu-aufbauen` | Python-Umgebung nach einem Upgrade der Distribution neu bauen |
| `sudo teamplaner verwalten BEFEHL` | Django-Verwaltungsbefehl als Dienstbenutzer |
| `sudo teamplaner verwalten mail_protokoll [--tage N] [--status offen\|gesendet\|fehler]` | was wann an wen verschickt wurde, was offen ist, was fehlschlug |

**E-Mail-Versand.** Der Dienst `teamplaner-mailer` verschickt alle paar Sekunden, was offen ist, und
versucht es bei Fehlern bis zu fünfmal. Nachvollziehen lässt sich der Versand auf drei Wegen:

- In der Anwendung unter **Einstellungen → E-Mail-Versand** (nur Admin): offene, aufgegebene und
  verschickte E-Mails, mit Warnung, wenn offene E-Mails länger als 15 Minuten liegen. Aufgegebene
  Benachrichtigungen lassen sich dort erneut einreihen.
- `sudo teamplaner verwalten mail_protokoll`: dieselben Angaben als Tabelle.
- `sudo teamplaner logs mailer`: je E-Mail eine Zeile mit Art, Empfänger und Eintrag, bei Fehlern mit
  Versuch und Grund.

Betreff und Text stehen nirgends im Protokoll (der Betreff enthält Aufgabentitel, der Text
Passwort-Links). Die Empfängeradressen im Journal sind personenbezogene Daten, und das Journal hat
eine eigene Aufbewahrung (`journald.conf`), unabhängig von `TEAMPLANER_AUFBEWAHRUNG_TAGE`. Mit
`TEAMPLANER_PROTOKOLL_EMPFAENGER=0` in der Konfiguration stehen sie dort gekürzt. In der Anwendung
sieht sie nur der Admin, der die Konten ohnehin verwaltet.

`sudo teamplaner verwalten mails_versenden` ist ein einzelner Versandlauf, kein Protokoll: Läuft der
Dienst, ist meist nichts mehr offen.

**Sicherung.** Sonntags um 02:30 nach `/var/backups/teamplaner` (`datenbank_*.dump`, `anhaenge_*.tar.gz`),
vor jedem Update zusätzlich. Bitte dieses Verzeichnis und `/etc/teamplaner` (bzw. die eigenen Pfade) in die
eigene Sicherung aufnehmen. Zeitpunkt ändern: `sudo systemctl edit teamplaner-sicherung.timer`.

**Überwachung.** `https://<domain>/gesund/` liefert `{"status": "ok"}`, solange Anwendung und Datenbank
erreichbar sind.

**Neustart des Servers.** Dienste und Timer starten selbst.

**Upgrade der Distribution.** Die Python-Umgebung gehört zur Python-Version, mit der sie gebaut wurde.
Wechselt ein Upgrade diese Version, startet Teamplaner nicht mehr und `sudo teamplaner status` zeigt die
Umgebung als „nicht lauffähig“. `sudo teamplaner neu-aufbauen` baut sie ohne Internet neu, auch für die
vorherige Version. Daten bleiben unberührt, und startet die neue Umgebung nicht, gilt wieder die alte.
Das Archiv enthält die Python-Pakete nur für Python 3.12 (Ubuntu 24.04). Vor einem Upgrade auf ein
Ubuntu mit anderer Python-Version muss das Bauskript (`werkzeuge/paket-bauen.sh`) diese Version mit
abdecken, sonst bleibt nach dem Upgrade nur die alte, nicht mehr lauffähige Umgebung.

## Updates

Updates gibt es nur auf Befehl. Archiv und `.sha256` in dasselbe Verzeichnis legen, dann:

```bash
sudo teamplaner update teamplaner-1.1.0.tar.gz
```

1. Prüfsumme kontrollieren und neue Version vorbereiten, Teamplaner läuft weiter.
2. Rückfrage, dann Dienste anhalten. Besucher sehen die Wartungsseite.
3. Datenbank und Anhänge sichern (`…_vor-update-<version>`).
4. Umschalten, Migrationen, Start, Gesundheitsprüfung.
5. **Startet die neue Version nicht, geht es automatisch zurück**, mit der alten Version und der
   Datenbank aus Schritt 3. Das Protokoll liegt unter `/var/lib/teamplaner/stand/` (Datenverzeichnis).

Nicht erreichbar ist Teamplaner meist unter einer Minute. Zurück auf die vorherige Version, Einträge seit
dem Update bleiben erhalten:

```bash
sudo teamplaner zurueck
```

Die letzten drei Versionen bleiben unter `versionen` im Programmverzeichnis. Betriebssystem, PostgreSQL und
Webserver werden unabhängig davon aktualisiert, Python-Bibliotheken kommen mit den Teamplaner-Versionen.

## Fehlersuche

| Symptom | Ursache und Abhilfe |
| --- | --- |
| `nginx -t` meldet `Address family not supported by protocol` | Server ohne IPv6: in der Vorlage die Zeilen `listen [::]…` entfernen |
| 502 oder Wartungsseite bleibt stehen | Anwendung läuft nicht: `sudo teamplaner status`, `sudo teamplaner logs web` |
| 400 Bad Request | Domain fehlt in `DJANGO_ALLOWED_HOSTS` |
| 403 beim Anmelden | Adresse mit `https://` fehlt in `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Anmeldung springt zurück oder Weiterleitungsschleife | Proxy setzt `X-Forwarded-Proto: https` nicht, oder seine IP fehlt in `TEAMPLANER_PROXY_IPS` |
| Änderungen anderer erscheinen erst nach dem Neuladen | Proxy puffert `/api/planung/stream` |
| Datenbankfehler „ident authentication failed“ | Eintrag in `pg_hba.conf` fehlt, siehe [Datenbank](#2-datenbank) |
| Mails kommen nicht an | Einstellungen → E-Mail-Versand oder `sudo teamplaner verwalten mail_protokoll`: offen (Dienst läuft nicht? `sudo teamplaner status`), aufgegeben (Grund in `sudo teamplaner logs mailer`) oder verschickt (Spam-Ordner, Mailserver des Empfängers). Schalter „E-Mail-Versand“ unter Einstellungen → Allgemein prüfen |
| Konto gesperrt | `sudo teamplaner verwalten axes_reset_username <email>` (kleingeschrieben) |
| IP-Adresse gesperrt | `sudo teamplaner verwalten axes_reset_ip <ip>` |
| Admin hat das Telefon verloren | `sudo teamplaner verwalten zwei_faktor_zuruecksetzen <email>` |

## Deinstallation

```bash
sudo systemctl disable --now teamplaner-web teamplaner-mailer teamplaner-sicherung.timer
sudo rm /etc/systemd/system/teamplaner-* /usr/local/sbin/teamplaner && sudo systemctl daemon-reload
sudo rm -rf /opt/teamplaner
```

Erhalten bleiben Datenbank, `/var/lib/teamplaner`, `/var/backups/teamplaner` und `/etc/teamplaner`. Bei
[anderen Pfaden](#andere-pfade) gelten die eigenen.

## Sicherheit

- Die Dienste laufen als unprivilegierter Benutzer mit systemd-Härtung (`ProtectSystem=strict`,
  `NoNewPrivileges`, eigenes `/tmp`). Schreiben dürfen sie nur im Daten- und im Sicherungsverzeichnis.
- Installation und Updates setzen die Rechte im Programmverzeichnis selbst, auch bei strenger umask von
  root (027, 077).
- Die Anwendung lauscht nur lokal und verbindet sich nach außen nur mit dem SMTP-Server.
- Passwörter mit Argon2, Sperre je Konto und je IP-Adresse, Cookies nur über HTTPS, Content-Security-Policy.
  Zwei-Faktor-Anmeldung ist Pflicht für Admin und Bereichsleitung.
- Das Änderungsprotokoll ist in der Datenbank per Trigger gegen Ändern geschützt und erst nach einem Jahr
  löschbar. Die Löschfristen wendet `teamplaner-mailer` täglich an, sofort mit
  `sudo teamplaner verwalten aufraeumen`.
- Andere Admin-Konten lassen sich nur über die Kommandozeile ändern.
