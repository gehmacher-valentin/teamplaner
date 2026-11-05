#!/bin/sh
# Start im Produktionscontainer: Migrationen anwenden, dann ASGI-Server.
# Die Frist beim Herunterfahren beendet offene Live-Verbindungen (SSE), damit Updates nicht hängen.
# Mit "auspacken": Betriebsdateien nach /ziel kopieren (Installation, siehe docs/betrieb.md).
set -e
if [ "${1:-}" = "auspacken" ]; then
  exec sh docker/auspacken.sh /ziel
fi
python manage.py migrate --noinput
# Allen Proxys vertrauen ist hier in Ordnung: Port 8000 ist nur im Docker-Netz erreichbar (Caddy davor,
# compose.prod.yaml). Nie veröffentlichen – sonst ließen sich X-Forwarded-* fälschen. Der Linux-Server
# ohne Docker vertraut nur TEAMPLANER_PROXY_IPS (betrieb/linux/web.sh).
exec uvicorn teamplaner.asgi:application \
  --host 0.0.0.0 --port 8000 \
  --workers "${UVICORN_WORKERS:-2}" \
  --proxy-headers --forwarded-allow-ips="*" \
  --timeout-graceful-shutdown 10
