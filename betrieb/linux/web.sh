#!/bin/sh
# Startet den ASGI-Server (aus teamplaner-web.service, Arbeitsverzeichnis: aktuelle Version im
# Programmverzeichnis). Werte aus der Konfiguration (teamplaner.env); nur der Webserver davor ist von
# außen erreichbar.
# Die Frist beim Herunterfahren beendet offene Live-Verbindungen (SSE), damit Neustarts nicht hängen.
exec venv/bin/uvicorn teamplaner.asgi:application \
  --host "${TEAMPLANER_HOST:-127.0.0.1}" --port "${TEAMPLANER_PORT:-8000}" \
  --workers "${UVICORN_WORKERS:-2}" \
  --proxy-headers --forwarded-allow-ips "${TEAMPLANER_PROXY_IPS:-127.0.0.1}" \
  --timeout-graceful-shutdown 10 --no-server-header
