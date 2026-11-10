#!/bin/sh
# Sicherung auf dem Linux-Server: Datenbank (pg_dump, Custom-Format) und Anhänge (tar.gz).
# Läuft als teamplaner-sicherung.service (Timer) bzw. über sudo teamplaner sichern.
# Pfade aus BACKUP_ZIEL/MEDIEN_VERZEICHNIS, alte Sicherungen nach BACKUP_TAGE löschen.
#   sicherung.sh jetzt [kennung]
# Mit Kennung heißen die Dateien datenbank_<kennung>.dump / anhaenge_<kennung>.tar.gz (für Updates).
set -eu
ZIEL=${BACKUP_ZIEL:-/var/backups/teamplaner}
MEDIEN=${MEDIEN_VERZEICHNIS:-/var/lib/teamplaner/medien}

# Zugang zur Datenbank aus der Teamplaner-Konfiguration
: "${PGHOST:=${POSTGRES_HOST:-localhost}}" "${PGPORT:=${POSTGRES_PORT:-5432}}"
: "${PGDATABASE:=${POSTGRES_DB:-teamplaner}}" "${PGUSER:=${POSTGRES_USER:-teamplaner}}"
export PGHOST PGPORT PGDATABASE PGUSER
if [ -z "${PGPASSWORD:-}" ] && [ -n "${POSTGRES_PASSWORD:-}" ]; then
  export PGPASSWORD="$POSTGRES_PASSWORD"
fi

if [ "${1:-}" != "jetzt" ]; then
  echo "Aufruf: sicherung.sh jetzt [kennung]" >&2
  exit 2
fi

stempel=${2:-$(date +%Y-%m-%d_%H%M)}
echo "[backup] $(date '+%F %T') Sicherung $stempel"
pg_dump --format=custom --file="$ZIEL/datenbank_$stempel.dump.tmp"
mv "$ZIEL/datenbank_$stempel.dump.tmp" "$ZIEL/datenbank_$stempel.dump"
tar -czf "$ZIEL/anhaenge_$stempel.tar.gz.tmp" -C "$MEDIEN" .
mv "$ZIEL/anhaenge_$stempel.tar.gz.tmp" "$ZIEL/anhaenge_$stempel.tar.gz"
find "$ZIEL" -maxdepth 1 -type f \( -name 'datenbank_*.dump' -o -name 'anhaenge_*.tar.gz' \) \
  -mtime +"${BACKUP_TAGE:-30}" -print -delete
echo "[backup] fertig"
