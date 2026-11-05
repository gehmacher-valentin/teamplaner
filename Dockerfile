# syntax=docker/dockerfile:1

# --- Frontend bauen (Teamplaner, Styles, HTMX) ---
# Immer auf der Plattform des Build-Rechners: das Ergebnis (JS/CSS) ist für alle Plattformen gleich,
# so läuft der Node-Build beim arm64-Paket nicht emuliert.
FROM --platform=$BUILDPLATFORM node:22-alpine AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- Gemeinsame Python-Basis ---
FROM python:3.13-slim AS basis
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
RUN useradd --create-home --uid 1000 app
COPY requirements.txt ./
RUN pip install -r requirements.txt

# --- Entwicklung: Quellcode wird per Volume eingebunden ---
FROM basis AS dev
# gettext für makemessages/compilemessages (die .mo-Dateien liegen im Repository)
RUN apt-get update \
    && apt-get install -y --no-install-recommends gettext \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
# Kurze Frist beim Herunterfahren: offene Live-Verbindungen (SSE) blockieren sonst den Neustart
CMD ["uvicorn", "teamplaner.asgi:application", "--host", "0.0.0.0", "--port", "8000", "--reload", "--timeout-graceful-shutdown", "2"]

# --- Installationsarchiv für Linux-Server ohne Docker (docs/installation-linux.md) ---
#   docker build --target linux-paket --build-arg TEAMPLANER_VERSION=1.2.0 --output type=local,dest=dist .
# Python-Pakete als Wheels für die Python-Versionen gängiger Server (Debian 12: 3.11,
# Ubuntu 24.04 und RHEL 9: 3.12), damit die Installation ohne Internetzugang auskommt.
FROM --platform=linux/amd64 python:3.11-slim AS raeder-311
RUN --mount=type=bind,source=requirements.txt,target=/requirements.txt \
    pip wheel --no-cache-dir --disable-pip-version-check -q --wheel-dir /raeder -r /requirements.txt
FROM --platform=linux/amd64 python:3.12-slim AS raeder-312
RUN --mount=type=bind,source=requirements.txt,target=/requirements.txt \
    pip wheel --no-cache-dir --disable-pip-version-check -q --wheel-dir /raeder -r /requirements.txt
FROM --platform=linux/amd64 python:3.13-slim AS raeder-313
RUN --mount=type=bind,source=requirements.txt,target=/requirements.txt \
    pip wheel --no-cache-dir --disable-pip-version-check -q --wheel-dir /raeder -r /requirements.txt

FROM basis AS linux-bau
ARG TEAMPLANER_VERSION
WORKDIR /bau/teamplaner-${TEAMPLANER_VERSION}
COPY . .
COPY --from=frontend /build/static/dist ./static/dist
COPY --from=raeder-311 /raeder ./wheelhaus/
COPY --from=raeder-312 /raeder ./wheelhaus/
COPY --from=raeder-313 /raeder ./wheelhaus/
# Nur was auf dem Server gebraucht wird; Rechte vereinheitlichen (Windows-Checkouts)
RUN test -n "$TEAMPLANER_VERSION" || { echo "TEAMPLANER_VERSION fehlt (--build-arg)"; exit 1; } \
    && echo "$TEAMPLANER_VERSION" > VERSION \
    && DJANGO_SECRET_KEY=nur-fuer-collectstatic TEAMPLANER_STATIC_MANIFEST=1 python manage.py collectstatic --noinput -v 0 \
    && cp betrieb/linux/installieren.sh installieren.sh \
    && cp docs/installation-linux.md INSTALLATION.md \
    && find docker -type f ! -name backup.sh -delete \
    && rm -rf frontend tests pruefung Dockerfile compose*.yaml .env.example requirements-dev.* \
              .dockerignore .editorconfig .gitattributes .gitignore \
    && find . -type d -name __pycache__ -prune -exec rm -rf {} + \
    && find . -type d -exec chmod 0755 {} + && find . -type f -exec chmod 0644 {} + \
    && chmod 0755 installieren.sh manage.py docker/backup.sh betrieb/linux/teamplaner betrieb/linux/*.sh \
    && mkdir /aus && cd /bau \
    && tar --owner=0 --group=0 --numeric-owner -czf "/aus/teamplaner-$TEAMPLANER_VERSION.tar.gz" "teamplaner-$TEAMPLANER_VERSION" \
    && cd /aus && sha256sum "teamplaner-$TEAMPLANER_VERSION.tar.gz" > "teamplaner-$TEAMPLANER_VERSION.tar.gz.sha256"

FROM scratch AS linux-paket
COPY --from=linux-bau /aus/ /

# --- Produktion (Container) ---
FROM basis AS prod
# Versionsnummer aus dem Git-Tag (Release-Workflow); leer = aus dem Quellcode gebaut
ARG TEAMPLANER_VERSION=""
LABEL org.opencontainers.image.title="Teamplaner" \
      org.opencontainers.image.version="${TEAMPLANER_VERSION}"
COPY --chown=app:app . .
COPY --from=frontend --chown=app:app /build/static/dist ./static/dist
RUN if [ -n "$TEAMPLANER_VERSION" ]; then echo "$TEAMPLANER_VERSION" > VERSION; fi \
    && DJANGO_SECRET_KEY=nur-fuer-collectstatic python manage.py collectstatic --noinput \
    && mkdir -p /app/media && chown app:app /app/media
USER app
EXPOSE 8000
ENTRYPOINT ["sh", "docker/start.sh"]
