#!/bin/sh
# Kopiert die Betriebsdateien aus dem Image in ein Verzeichnis auf dem Server (Installation und
# ./teamplaner update). Die .env bleibt unberührt; .env.example trägt die Version dieses Images.
#   docker run --rm --user "$(id -u):$(id -g)" -v "$PWD:/ziel" ghcr.io/gehmacher-valentin/teamplaner-app:<version> auspacken
set -eu
ZIEL="${1:-/ziel}"
[ -d "$ZIEL" ] && [ -w "$ZIEL" ] || {
  echo "Zielverzeichnis $ZIEL fehlt oder ist nicht beschreibbar (docker run ... -v \"\$PWD:/ziel\")" >&2
  exit 1
}
VERSION=$(cat VERSION 2>/dev/null || echo latest)

mkdir -p "$ZIEL/docker/caddy"
cp compose.prod.yaml "$ZIEL/compose.prod.yaml"
cp docker/backup.sh docker/wiederherstellen.sh "$ZIEL/docker/"
cp docker/caddy/Caddyfile "$ZIEL/docker/caddy/Caddyfile"
sed "s/^TEAMPLANER_VERSION=.*/TEAMPLANER_VERSION=$VERSION/" .env.example > "$ZIEL/.env.example"
# Skript über eine neue Datei ersetzen: ein gerade laufendes ./teamplaner liest ungestört weiter
cp docker/teamplaner.sh "$ZIEL/teamplaner.neu"
chmod +x "$ZIEL/teamplaner.neu"
mv -f "$ZIEL/teamplaner.neu" "$ZIEL/teamplaner"

echo "Teamplaner $VERSION: Betriebsdateien in $ZIEL abgelegt."
