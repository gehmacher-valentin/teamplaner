#!/usr/bin/env bash
# Startet die Anwendung für die Browser-Tests (frontend/e2e, docs/entwicklung.md): eigene Datenbank
# mit frischen Demodaten, eigener Ordner für Anhänge, eigener Port. Die Entwicklungsdatenbank bleibt
# unberührt. Wird von Playwright gestartet (frontend/playwright.config.ts), braucht die
# Python-Umgebung im Pfad und das gebaute Frontend (npm run build).
set -euo pipefail
cd "$(dirname "$0")/.."

export DJANGO_DEBUG=1 TEAMPLANER_DEMO=1 TEAMPLANER_STATIC_MANIFEST=0
export DJANGO_SECRET_KEY="${DJANGO_SECRET_KEY:-e2e-nicht-fuer-produktion}"
export DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
export POSTGRES_HOST="${POSTGRES_HOST:-localhost}" POSTGRES_USER="${POSTGRES_USER:-teamplaner}"
export POSTGRES_PASSWORD="${POSTGRES_PASSWORD:-teamplaner-dev}"
export POSTGRES_DB="${E2E_DB:-teamplaner_e2e}"
PORT="${E2E_PORT:-8010}"
export TEAMPLANER_ADRESSE="http://localhost:$PORT"
export TEAMPLANER_MEDIA_ROOT="${E2E_MEDIA:-${TMPDIR:-/tmp}/teamplaner-e2e-media}"
# Ohne Mailversand: Einladungslinks erscheinen in der Oberfläche
unset EMAIL_HOST

[[ -f static/dist/main.js ]] || { echo "Frontend fehlt: cd frontend && npm run build" >&2; exit 1; }
rm -rf "$TEAMPLANER_MEDIA_ROOT"

# Datenbank anlegen, falls sie fehlt (die Rolle braucht CREATEDB wie für pytest)
python - <<'PY'
import os

import psycopg

name = os.environ["POSTGRES_DB"]
with psycopg.connect(host=os.environ["POSTGRES_HOST"], port=os.environ.get("POSTGRES_PORT", "5432"),
                     user=os.environ["POSTGRES_USER"], password=os.environ["POSTGRES_PASSWORD"],
                     dbname="postgres", autocommit=True) as verbindung:
    if not verbindung.execute("SELECT 1 FROM pg_database WHERE datname = %s", [name]).fetchone():
        verbindung.execute(psycopg.sql.SQL("CREATE DATABASE {} ENCODING 'UTF8' TEMPLATE template0")
                           .format(psycopg.sql.Identifier(name)))
PY
python manage.py migrate --no-input -v 0
python manage.py demodaten --neu
exec uvicorn teamplaner.asgi:application --host 127.0.0.1 --port "$PORT" --log-level warning
