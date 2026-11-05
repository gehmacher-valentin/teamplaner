#!/bin/sh
# Wiederherstellung aus einem Backup. Überschreibt Datenbank und Anhänge!
# Aufruf auf dem Server im Installationsverzeichnis (siehe docs/betrieb.md):
#   ./teamplaner wiederherstellen backups/datenbank_2026-10-21_0230.dump backups/anhaenge_2026-10-21_0230.tar.gz
# Optionen: --ja (ohne Rückfrage), --ohne-start (Anwendung danach nicht starten; für ./teamplaner)
set -eu
JA=0
STARTEN=1
while [ $# -gt 0 ]; do
  case "$1" in
    --ja) JA=1 ;;
    --ohne-start) STARTEN=0 ;;
    *) break ;;
  esac
  shift
done
DUMP="${1:-}"
ANHAENGE="${2:-}"
COMPOSE="docker compose -f compose.prod.yaml --env-file .env"

[ -f "$DUMP" ] || { echo "Datei nicht gefunden: ${DUMP:-(keine angegeben)}" >&2; exit 1; }
[ -z "$ANHAENGE" ] || [ -f "$ANHAENGE" ] || { echo "Datei nicht gefunden: $ANHAENGE" >&2; exit 1; }
if [ "$JA" = 0 ]; then
  if [ -n "$ANHAENGE" ]; then was="Datenbank und Anhänge werden"; else was="Die Datenbank wird"; fi
  echo "Achtung: $was durch die Sicherung ersetzt. Fortfahren? (ja/nein)"
  read -r antwort
  [ "$antwort" = "ja" ] || { echo "Abgebrochen."; exit 1; }
fi

# Caddy läuft weiter und zeigt solange die Wartungsseite
$COMPOSE stop app mailer
$COMPOSE up -d --wait db
# Schema vollständig leeren: Tabellen einer neueren Version (spätere Migrationen) dürfen nicht übrig bleiben
$COMPOSE exec -T db sh -c 'psql -q -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"'
$COMPOSE exec -T db sh -c 'pg_restore --no-owner --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB"' < "$DUMP"
if [ -n "$ANHAENGE" ]; then
  ordner=$(cd "$(dirname "$ANHAENGE")" && pwd)
  $COMPOSE run --rm -T --no-deps --entrypoint sh -v "$ordner:/sicherung:ro" app \
    -c "find /app/media -mindepth 1 -delete && tar -xzf /sicherung/$(basename "$ANHAENGE") -C /app/media"
fi
if [ "$STARTEN" = 1 ]; then
  $COMPOSE up -d app mailer
fi
echo "Wiederherstellung abgeschlossen."
