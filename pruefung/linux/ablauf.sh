#!/usr/bin/env bash
# Läuft als root im Probeserver (pruefen.sh): die Schritte aus docs/installation-linux.md,
# danach Proben für Webserver, Live-Verbindung, Update, Rücksprung, defektes Update, Wiederherstellung,
# Wechsel der Python-Version durch ein Upgrade der Distribution (neu-aufbauen).
# Beide auf Ubuntu 24.04: ubuntu-nginx mit den Standardpfaden, ubuntu-apache mit eigenen Pfaden für
# Konfiguration, Programm, Daten, Sicherungen.
#   ablauf.sh ubuntu-nginx|ubuntu-apache [nach-neustart]
set -euo pipefail
ART=$1
PHASE=${2:-voll}
DOMAIN=teamplaner.test
P=/root/pakete
DBPASS=probe-db-passwort-2026
DEMO=Teamplaner-Demo-2026
# Gehärteter Server (CIS): root arbeitet mit umask 0077, das Archiv wird wie von einem Benutzer mit
# dieser umask entpackt (Dateien 600, Verzeichnisse 700)
umask 0077
# Python vor dem Upgrade der Distribution (Schritt 12) und danach. Ubuntu 24.04 hat nur 3.12 im
# Paketarchiv: für die alte Version steht eine Kopie des Interpreters unter /usr/local/bin.
ALT_PYTHON=/usr/local/bin/python3.12 NEU_PYTHON=/usr/bin/python3.12
if [[ $ART == ubuntu-apache ]]; then
  KONF=/srv/tp/konfig/teamplaner.env PROG=/srv/tp/programm DAT=/srv/tp/daten SICH=/srv/tp/sicherungen
else
  KONF=/etc/teamplaner/teamplaner.env PROG=/opt/teamplaner DAT=/var/lib/teamplaner SICH=/var/backups/teamplaner
fi

schritt() { printf '\n######## %s: %s\n' "$ART" "$*"; }
pruefe() { if eval "$2" >/dev/null 2>&1; then echo "  OK      $1"; else echo "  FEHLER  $1"; exit 1; fi; }
https() { curl -sk --resolve "$DOMAIN:443:127.0.0.1" "$@"; }
code() { https -o /dev/null -w '%{http_code}' "https://$DOMAIN$1"; }
sql() { runuser -u postgres -- psql -X -At -d teamplaner -c "$1"; }
version() { basename "$(readlink "$PROG/aktuell")"; }
pfad_in_konfig() { sed -i "s|^$1=.*|$1=$2|" "$KONF"; }
spalte_probe() { sql "select count(*) from information_schema.columns where table_name='kern_bereich' and column_name='probe'"; }
probebereich() { sql "select count(*) from kern_bereich where name='Probebereich'"; }
aufgaben() { sql "select count(*) from projekte_aufgabe"; }
python_von() { readlink -f "$PROG/versionen/$1/venv/bin/python"; }
lesbar() {  # alles unter der aktuellen Version für den Dienstbenutzer lesbar, Verzeichnisse betretbar
  local f
  f="$(cd / && runuser -u teamplaner -- find "$PROG/aktuell/" ! -readable -print -quit)" && [[ -z $f ]]
}

if [[ $PHASE == nach-neustart ]]; then
  schritt "nach dem Neustart"
  pruefe "Dienste und Timer laufen wieder" 'systemctl is-active teamplaner-web teamplaner-mailer teamplaner-sicherung.timer'
  for _ in $(seq 1 30); do [[ $(code /gesund/) == 200 ]] && break; sleep 2; done
  pruefe "über HTTPS erreichbar" '[[ $(code /gesund/) == 200 ]]'
  exit 0
fi

schritt "1 Datenbank (wie INSTALLATION.md)"
runuser -u postgres -- psql -q -c "CREATE ROLE teamplaner LOGIN PASSWORD '$DBPASS'"
runuser -u postgres -- psql -q -c "CREATE DATABASE teamplaner OWNER teamplaner ENCODING 'UTF8' TEMPLATE template0"
pruefe "PostgreSQL $(runuser -u postgres -- psql -XAt -c 'show server_version' | cut -d' ' -f1) bereit" 'sql "select 1"'

schritt "2 Teamplaner installieren (umask 0077, Python $ALT_PYTHON)"
install -m 0755 /usr/bin/python3.12 "$ALT_PYTHON"
export TEAMPLANER_PYTHON=$ALT_PYTHON
cd /root && tar -xzf "$P/teamplaner-0.1.0.tar.gz" --no-same-permissions && cd teamplaner-0.1.0
pruefe "Archiv nur für root lesbar entpackt" '[[ $(stat -c %a requirements.txt) == 600 ]]'
if [[ $ART == ubuntu-apache ]]; then
  # Wie ein vorab eingehängtes Laufwerk: leer bis auf lost+found, gehört root
  mkdir -p "$DAT/lost+found"
  TEAMPLANER_KONFIG=$KONF ./installieren.sh
else
  ./installieren.sh
fi
pruefe "Konfiguration angelegt (root:teamplaner 640)" '[[ $(stat -c "%U:%G %a" "$KONF") == "root:teamplaner 640" ]]'
pruefe "Geheimschlüssel erzeugt" '! grep -q "^DJANGO_SECRET_KEY=wird-bei" "$KONF"'
pruefe "ohne Datenbankpasswort keine Installation" '! ./installieren.sh'
sed -i -e "s|^DJANGO_ALLOWED_HOSTS=.*|DJANGO_ALLOWED_HOSTS=$DOMAIN|" \
  -e "s|^DJANGO_CSRF_TRUSTED_ORIGINS=.*|DJANGO_CSRF_TRUSTED_ORIGINS=https://$DOMAIN|" \
  -e "s|^TEAMPLANER_ADRESSE=.*|TEAMPLANER_ADRESSE=https://$DOMAIN|" \
  -e "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$DBPASS|" "$KONF"
if [[ $ART == ubuntu-apache ]]; then
  pfad_in_konfig TEAMPLANER_PROGRAMM "$PROG"
  pfad_in_konfig TEAMPLANER_DATEN /srv
  pruefe "Systemverzeichnis als Datenpfad abgewiesen" '! ./installieren.sh'
  pfad_in_konfig TEAMPLANER_DATEN "$PROG/daten"
  pruefe "Daten im Programmverzeichnis abgewiesen" '! ./installieren.sh'
  pfad_in_konfig TEAMPLANER_DATEN "$DAT"
  pfad_in_konfig TEAMPLANER_SICHERUNGEN "$SICH"
  # /srv/tp ist mit umask 0077 entstanden (mkdir oben): für den Dienstbenutzer nicht betretbar
  pruefe "nicht betretbares Verzeichnis darüber gemeldet" '{ ./installieren.sh 2>&1 || true; } | grep -q "chmod o+x"'
  chmod 0755 /srv/tp
fi
# ubuntu-apache: zweiter Aufruf ohne TEAMPLANER_KONFIG, der Ort kommt aus dem ersten
./installieren.sh
pruefe "Version 0.1.0 aktiv" '[[ $(version) == 0.1.0 ]]'
if [[ $ART == ubuntu-apache ]]; then
  pruefe "nichts unter den Standardpfaden" '[[ ! -e /opt/teamplaner && ! -e /etc/teamplaner && ! -e /var/lib/teamplaner && ! -e /var/backups/teamplaner ]]'
  pruefe "eingehängtes Datenverzeichnis übernommen (teamplaner 750)" '[[ $(stat -c "%U:%G %a" "$DAT") == "teamplaner:teamplaner 750" ]]'
  pruefe "Verwaltungsbefehl kennt den Ort der Konfiguration" 'grep -qx "KONFIG=$KONF" /usr/local/sbin/teamplaner'
  pruefe "Dienste mit den eigenen Pfaden" '[[ $(systemctl show -p WorkingDirectory --value teamplaner-web) == "$PROG/aktuell" ]] && grep -qx "ReadWritePaths=$SICH" /etc/systemd/system/teamplaner-sicherung.service'
fi
pruefe "Dienste und Timer laufen" 'systemctl is-active teamplaner-web teamplaner-mailer teamplaner-sicherung.timer'
pruefe "Dienste laufen als teamplaner" '[[ $(ps -o user= -p "$(systemctl show -p MainPID --value teamplaner-web)") == teamplaner ]]'
pruefe "Programm für den Dienstbenutzer vollständig lesbar" 'lesbar'
pruefe "Code für den Dienstbenutzer schreibgeschützt" '! runuser -u teamplaner -- touch $PROG/aktuell/x'
pruefe "Python-Umgebung mit $ALT_PYTHON" '[[ $(python_von 0.1.0) == $(readlink -f "$ALT_PYTHON") ]]'
pruefe "erneutes installieren.sh verweist auf update" '{ ./installieren.sh 2>&1 || true; } | grep -q "bereits installiert"'
pruefe "teamplaner ohne sudo wird abgewiesen" '{ runuser -u nobody -- /usr/local/sbin/teamplaner status 2>&1 || true; } | grep -q "sudo"'

schritt "3 Webserver mit Zertifikat"
mkdir -p /etc/ssl/teamplaner
openssl req -x509 -newkey rsa:2048 -nodes -days 30 -subj "/CN=$DOMAIN" \
  -keyout /etc/ssl/teamplaner/schluessel.pem -out /etc/ssl/teamplaner/zertifikat.pem 2>/dev/null
if [[ $ART == ubuntu-nginx ]]; then
  sed -e "s/teamplaner.example.org/$DOMAIN/g" -e "s|/opt/teamplaner/wartung|$PROG/wartung|g" "$PROG"/aktuell/betrieb/linux/nginx/teamplaner.conf \
    > /etc/nginx/sites-available/teamplaner.conf
  # Docker-Host ohne IPv6 (Kernel mit ipv6.disable=1): wie installation-linux.md die listen [::]-Zeilen entfernen
  if [[ ! -e /proc/net/if_inet6 ]]; then
    sed -i '/^[[:space:]]*listen \[::\]/d' /etc/nginx/sites-available/teamplaner.conf
    echo "  Hinweis ohne IPv6: listen [::] entfernt"
  fi
  ln -sf /etc/nginx/sites-available/teamplaner.conf /etc/nginx/sites-enabled/
  nginx -t 2>&1 | tail -n 1
  systemctl reload nginx
else
  sed -e "s/teamplaner.example.org/$DOMAIN/g" -e "s|/opt/teamplaner/wartung|$PROG/wartung|g" "$PROG"/aktuell/betrieb/linux/apache/teamplaner.conf \
    > /etc/apache2/sites-available/teamplaner.conf
  a2enmod -q ssl proxy proxy_http headers http2 >/dev/null
  a2ensite -q teamplaner >/dev/null
  apachectl configtest
  systemctl reload apache2
fi
pruefe "HTTPS /gesund/ 200" '[[ $(code /gesund/) == 200 ]]'
pruefe "Anmeldeseite" 'https "https://$DOMAIN/anmelden/" | grep -q "Teamplaner"'
CSS="$(https "https://$DOMAIN/anmelden/" | grep -o '/static/dist/main\.[^"]*\.css' | head -n 1)"
pruefe "Statische Dateien (gehasht) $CSS" '[[ -n $CSS && $(code "$CSS") == 200 ]]'
pruefe "HTTP/2" '[[ $(https --http2 -o /dev/null -w "%{http_version}" "https://$DOMAIN/gesund/") == 2 ]]'
pruefe "http → https" '[[ $(curl -s -o /dev/null -w "%{http_code}" -H "Host: $DOMAIN" http://127.0.0.1/) == 301 ]]'
pruefe "HSTS gesetzt" 'https -I "https://$DOMAIN/anmelden/" | grep -qi "strict-transport-security"'
# Let's Encrypt per Webroot: „#acme “ in der Vorlage entfernen (installation-linux.md, Zertifikat)
mkdir -p /var/www/letsencrypt/.well-known/acme-challenge
echo acme-probe > /var/www/letsencrypt/.well-known/acme-challenge/probe
chmod -R a+rX /var/www/letsencrypt
if [[ $ART == ubuntu-nginx ]]; then
  sed -i 's/^\([[:space:]]*\)#acme /\1/' /etc/nginx/sites-available/teamplaner.conf
  nginx -t 2>&1 | tail -n 1
  systemctl reload nginx
else
  sed -i 's/^\([[:space:]]*\)#acme /\1/' /etc/apache2/sites-available/teamplaner.conf
  apachectl configtest
  systemctl reload apache2
fi
acme() { curl -sLk --resolve "$DOMAIN:80:127.0.0.1" --resolve "$DOMAIN:443:127.0.0.1" "http://$DOMAIN/.well-known/acme-challenge/probe"; }
# reload kehrt zurück, bevor die neuen Worker übernehmen
for _ in $(seq 1 10); do [[ $(acme) == acme-probe ]] && break; sleep 1; done
pruefe "Let's Encrypt: Prüfdatei über die Weiterleitung von Port 80 erreichbar" '[[ $(acme) == acme-probe ]]'
pruefe "übrige Anfragen weiter an die Anwendung" '[[ $(code /gesund/) == 200 ]]'

schritt "4 Konto, Demodaten, Anmeldung, Live-Verbindung"
# demodaten nur mit TEAMPLANER_DEMO=1; verwalten liest die Konfiguration, danach wieder wie im Betrieb
echo TEAMPLANER_DEMO=1 >> "$KONF"
teamplaner verwalten demodaten | tail -n 1
sed -i '/^TEAMPLANER_DEMO=/d' "$KONF"
teamplaner konto-anlegen --email probe-admin@example.test --name "Person 91" --bereich Produktion \
  --rolle admin --adresse "https://$DOMAIN" | tail -n 1
runuser -u teamplaner -- sh -c "mkdir -p $DAT/medien/probe && echo hallo > $DAT/medien/probe/datei.txt"
AUFGABEN=$(aufgaben)
pruefe "Demodaten ($AUFGABEN Aufgaben)" '[[ $AUFGABEN -gt 0 ]]'
rm -f /tmp/jar
https -c /tmp/jar -b /tmp/jar -o /dev/null "https://$DOMAIN/anmelden/"
TOKEN="$(awk '$6 == "csrftoken" { print $7 }' /tmp/jar)"
https -c /tmp/jar -b /tmp/jar -o /dev/null -e "https://$DOMAIN/anmelden/" \
  --data-urlencode "username=planer@example.test" --data-urlencode "password=$DEMO" \
  --data-urlencode "csrfmiddlewaretoken=$TOKEN" "https://$DOMAIN/anmelden/"
pruefe "Anmeldung über HTTPS (Sitzungscookie Secure)" 'grep -q sessionid /tmp/jar && [[ $(https -b /tmp/jar -o /dev/null -w "%{http_code}" "https://$DOMAIN/meine-aufgaben/") == 200 ]]'
timeout 6 curl -sk -N --resolve "$DOMAIN:443:127.0.0.1" -b /tmp/jar -D /tmp/sse-kopf -o /tmp/sse "https://$DOMAIN/api/planung/stream" || true
pruefe "Live-Verbindung kommt ungepuffert durch" 'grep -qi "text/event-stream" /tmp/sse-kopf && grep -q "verbunden" /tmp/sse'

schritt "5 Wartungsseite"
teamplaner stop
pruefe "503 mit Hinweis, solange die Anwendung steht" '[[ $(code /projekte/) == 503 ]] && https "https://$DOMAIN/projekte/" | grep -q "wird gerade aktualisiert"'
teamplaner start
pruefe "sofort wieder erreichbar" '[[ $(code /gesund/) == 200 ]]'

schritt "6 Sicherung, Status, Prüfung"
teamplaner sichern | tail -n 1
pruefe "Sicherung angelegt, nur für teamplaner lesbar" '[[ $(stat -c "%U %a" "$(ls -t $SICH/datenbank_*.dump | head -n 1)") == "teamplaner 600" ]]'
teamplaner status
teamplaner pruefen

schritt "7 Update auf 0.2.0"
mkdir -p /root/kaputt && cp "$P"/teamplaner-0.2.0.tar.gz* /root/kaputt/ && truncate -s -1000 /root/kaputt/teamplaner-0.2.0.tar.gz
pruefe "beschädigtes Archiv abgewiesen" '! teamplaner update /root/kaputt/teamplaner-0.2.0.tar.gz --ja'
teamplaner update "$P/teamplaner-0.2.0.tar.gz" --ja | tee /tmp/update.txt
pruefe "Prüfsumme kontrolliert" 'grep -q "Prüfsumme in Ordnung" /tmp/update.txt'
pruefe "Version 0.2.0 aktiv" '[[ $(version) == 0.2.0 ]]'
pruefe "neue Version für den Dienstbenutzer vollständig lesbar (umask 0077)" 'lesbar'
pruefe "Migration angewendet" '[[ $(spalte_probe) == 1 ]]'
pruefe "Daten erhalten" '[[ $(aufgaben) == "$AUFGABEN" ]]'
pruefe "Sicherung vor dem Update" 'ls $SICH/datenbank_*_vor-update-0.2.0.dump $SICH/anhaenge_*_vor-update-0.2.0.tar.gz'
pruefe "Verwaltungsbefehl aktualisiert" '[[ $(grep -v "^KONFIG=" /usr/local/sbin/teamplaner | sha256sum) == $(grep -v "^KONFIG=" "$PROG/versionen/0.2.0/betrieb/linux/teamplaner" | sha256sum) ]] && grep -qx "KONFIG=$KONF" /usr/local/sbin/teamplaner'
pruefe "erreichbar" '[[ $(code /gesund/) == 200 ]]'

schritt "8 Eintrag nach dem Update, dann Rücksprung"
sql "insert into kern_bereich (name, sortierung, probe) values ('Probebereich', 99, 'neu')"
teamplaner zurueck --ja
pruefe "Version 0.1.0 aktiv" '[[ $(version) == 0.1.0 ]]'
pruefe "Migration zurückgenommen" '[[ $(spalte_probe) == 0 ]]'
pruefe "Eintrag von nach dem Update erhalten" '[[ $(probebereich) == 1 ]]'
pruefe "übrige Daten erhalten" '[[ $(aufgaben) == "$AUFGABEN" ]]'
pruefe "erreichbar" '[[ $(code /gesund/) == 200 ]]'

schritt "9 Defektes Update (0.3.0) – automatischer Rücksprung"
set +e
teamplaner update "$P/teamplaner-0.3.0.tar.gz" --ja > /tmp/defekt.txt 2>&1
export RC=$?
set -e
cat /tmp/defekt.txt
pruefe "Update meldet Fehler" '[[ $RC != 0 ]] && grep -q "Update auf 0.3.0 fehlgeschlagen" /tmp/defekt.txt'
pruefe "Version 0.1.0 aktiv" '[[ $(version) == 0.1.0 ]]'
pruefe "Datenbank ohne Reste der defekten Version" '[[ $(spalte_probe) == 0 ]]'
pruefe "Daten wie vor dem Update" '[[ $(probebereich) == 1 && $(aufgaben) == "$AUFGABEN" ]]'
pruefe "Protokoll nennt die Ursache" 'grep -q "Absichtlich defekte Migration" $DAT/stand/update-0.3.0-*.log'
pruefe "Protokollschutz nach Wiederherstellung aktiv" '! sql "delete from kern_protokolleintrag"'
pruefe "erreichbar" '[[ $(code /gesund/) == 200 ]]'

schritt "10 Wiederherstellung einer älteren Sicherung inkl. Anhänge"
rm -rf "$DAT/medien/probe"
teamplaner wiederherstellen --ja "$SICH"/datenbank_*_vor-update-0.2.0.dump \
  "$SICH"/anhaenge_*_vor-update-0.2.0.tar.gz
pruefe "Anhang wieder da" '[[ $(cat $DAT/medien/probe/datei.txt) == hallo ]]'
pruefe "Datenstand von vor dem ersten Update" '[[ $(probebereich) == 0 && $(aufgaben) == "$AUFGABEN" ]]'
pruefe "erreichbar" '[[ $(code /gesund/) == 200 ]]'

schritt "11 Sonderfälle"
pruefe "gleiche Version: nichts zu tun" 'teamplaner update "$P/teamplaner-0.1.0.tar.gz" --ja | grep -q "bereits installiert"'
pruefe "kein Rücksprung ohne Update" '! teamplaner zurueck --ja'
pruefe "Prüfung ohne Fehler" 'teamplaner pruefen'

schritt "12 Upgrade der Distribution: Python $ALT_PYTHON → $NEU_PYTHON, neu-aufbauen"
teamplaner update "$P/teamplaner-0.2.0.tar.gz" --ja >/dev/null
pruefe "0.2.0 und vorherige 0.1.0 mit $ALT_PYTHON" '[[ $(version) == 0.2.0 && $(python_von 0.2.0) == $(readlink -f "$ALT_PYTHON") && $(python_von 0.1.0) == $(readlink -f "$ALT_PYTHON") ]]'
mv "$PROG/versionen/0.2.0/wheelhaus" /root/wheelhaus
pruefe "ohne passende Pakete bleibt die bisherige Umgebung, Teamplaner läuft weiter" \
  '! teamplaner neu-aufbauen --ja && [[ $(code /gesund/) == 200 && $(python_von 0.2.0) == $(readlink -f "$ALT_PYTHON") ]]'
mv /root/wheelhaus "$PROG/versionen/0.2.0/wheelhaus"
# Das Upgrade entfernt die alte Python-Version
rm "$ALT_PYTHON"
unset TEAMPLANER_PYTHON
pruefe "danach startet Teamplaner nicht mehr" '! teamplaner neustart'
pruefe "status verweist auf neu-aufbauen" 'teamplaner status | grep "nicht lauffähig.*neu-aufbauen"'
pruefe "pruefen meldet die Umgebung" '{ teamplaner pruefen || true; } | grep "FEHLER.*neu-aufbauen"'
pruefe "update derselben Version verweist auf neu-aufbauen" 'teamplaner update "$P/teamplaner-0.2.0.tar.gz" --ja | grep "neu-aufbauen"'
pruefe "zurueck verweigert, solange die Umgebung nicht lauffähig ist" '! teamplaner zurueck --ja && [[ $(version) == 0.2.0 ]]'
teamplaner neu-aufbauen --ja
pruefe "0.2.0 läuft mit $NEU_PYTHON" '[[ $(version) == 0.2.0 && $(python_von 0.2.0) == $(readlink -f "$NEU_PYTHON") && $(code /gesund/) == 200 ]]'
pruefe "vorherige 0.1.0 ebenfalls neu gebaut" '[[ $(python_von 0.1.0) == $(readlink -f "$NEU_PYTHON") ]]'
pruefe "keine alten Umgebungen übrig" '[[ ! -e $PROG/versionen/0.2.0/venv.alt && ! -e $PROG/versionen/0.1.0/venv.alt ]]'
pruefe "für den Dienstbenutzer vollständig lesbar" 'lesbar'
pruefe "Daten erhalten" '[[ $(aufgaben) == "$AUFGABEN" ]]'
teamplaner zurueck --ja
pruefe "Rücksprung auf 0.1.0 mit neu gebauter Umgebung" '[[ $(version) == 0.1.0 && $(spalte_probe) == 0 && $(code /gesund/) == 200 ]]'
pruefe "Prüfung ohne Fehler" 'teamplaner pruefen'

printf '\n%s: ALLES OK\n' "$ART"
