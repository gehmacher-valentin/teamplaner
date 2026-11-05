#!/bin/sh
# Wöchentliches Backup (sonntags): Datenbank (pg_dump, Custom-Format) und Anhänge (tar.gz).
# Läuft im Container "backup" (Image postgres:17) bzw. auf dem Linux-Server als
# teamplaner-sicherung.service. Alte Sicherungen nach BACKUP_TAGE löschen.
#   Sofort einmal sichern:  ./teamplaner sichern  (Linux-Server: sudo teamplaner sichern)
#   (oder docker compose -f compose.prod.yaml exec backup sh /skripte/backup.sh jetzt [kennung])
# Mit Kennung heißen die Dateien datenbank_<kennung>.dump / anhaenge_<kennung>.tar.gz (für Updates).
set -eu
ZIEL=${BACKUP_ZIEL:-/backups}
MEDIEN=${MEDIEN_VERZEICHNIS:-/medien}

# Zugang zur Datenbank: im Container über PG*-Variablen, auf dem Linux-Server aus der Teamplaner-Konfiguration
: "${PGHOST:=${POSTGRES_HOST:-localhost}}" "${PGPORT:=${POSTGRES_PORT:-5432}}"
: "${PGDATABASE:=${POSTGRES_DB:-teamplaner}}" "${PGUSER:=${POSTGRES_USER:-teamplaner}}"
export PGHOST PGPORT PGDATABASE PGUSER
if [ -z "${PGPASSWORD:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ]; then
  export PGPASSWORD="$POSTGRES_PASSWORD"
fi

sichern() {
  stempel=${1:-$(date +%Y-%m-%d_%H%M)}
  echo "[backup] $(date '+%F %T') Sicherung $stempel"
  pg_dump --format=custom --file="$ZIEL/datenbank_$stempel.dump.tmp"
  mv "$ZIEL/datenbank_$stempel.dump.tmp" "$ZIEL/datenbank_$stempel.dump"
  tar -czf "$ZIEL/anhaenge_$stempel.tar.gz.tmp" -C "$MEDIEN" .
  mv "$ZIEL/anhaenge_$stempel.tar.gz.tmp" "$ZIEL/anhaenge_$stempel.tar.gz"
  find "$ZIEL" -maxdepth 1 -type f \( -name 'datenbank_*.dump' -o -name 'anhaenge_*.tar.gz' \) \
    -mtime +"${BACKUP_TAGE:-30}" -print -delete
  echo "[backup] fertig"
}

if [ "${1:-}" = "jetzt" ]; then
  sichern "${2:-}"
  exit 0
fi

while true; do
  jetzt=$(date +%s)
  # Sonntag zur BACKUP_UHRZEIT (heute, falls Sonntag und noch nicht vorbei, sonst nächster Sonntag)
  ziel=$(date -d "sunday ${BACKUP_UHRZEIT:-02:30}" +%s)
  if [ "$ziel" -le "$jetzt" ]; then
    ziel=$(date -d "next sunday ${BACKUP_UHRZEIT:-02:30}" +%s)
  fi
  echo "[backup] nächste Sicherung $(date -d "@$ziel" '+%F %T')"
  sleep $((ziel - jetzt))
  sichern || echo "[backup] FEHLER bei der Sicherung" >&2
done
