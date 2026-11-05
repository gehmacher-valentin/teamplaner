#!/bin/sh
# Sicherung auf dem Linux-Server (teamplaner-sicherung.service, teamplaner sichern);
# derselbe Ablauf wie im Docker-Betrieb, Pfade aus BACKUP_ZIEL/MEDIEN_VERZEICHNIS.
exec sh "$(dirname "$0")/../../docker/backup.sh" "$@"
