#!/usr/bin/env bash
# Installationsarchiv für den Linux-Server bauen (docs/installation-linux.md).
# Läuft auf Ubuntu 24.04 x86_64 wie das Zielsystem (GitHub Actions oder Entwicklungsrechner):
# Frontend bauen, Python-Pakete als Wheels für Python 3.12 beilegen (Installation ohne Internet),
# statische Dateien sammeln, Archiv mit Prüfsumme schreiben.
#   werkzeuge/paket-bauen.sh VERSION [QUELLE] [ZIEL]
#   werkzeuge/paket-bauen.sh 1.2.0     ergibt dist/teamplaner-1.2.0.tar.gz und .sha256
# QUELLE: Quellcode (Standard: dieses Repository, nur Dateien, die Git nicht ignoriert);
# ZIEL: Ausgabeverzeichnis (Standard: dist/ im Repository).
# Braucht python3.12 mit venv (Paket python3-venv), Node.js 22 mit npm, tar, sha256sum.
set -euo pipefail
umask 0022
REPO="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=${1:-}
[[ $VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+ ]] || { echo "Aufruf: werkzeuge/paket-bauen.sh X.Y.Z [QUELLE] [ZIEL]" >&2; exit 2; }
QUELLE="$(cd "${2:-$REPO}" && pwd)"
mkdir -p "${3:-$REPO/dist}" && ZIEL="$(cd "${3:-$REPO/dist}" && pwd)"
PYTHON=${TEAMPLANER_BAU_PYTHON:-python3.12}

fehler() { echo "FEHLER: $*" >&2; exit 1; }
[[ $(uname -m) == x86_64 ]] || fehler "Nur auf x86_64 bauen: die beigelegten Wheels müssen zum Server passen."
[[ $("$PYTHON" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) == 3.12 ]] \
  || fehler "$PYTHON ist nicht Python 3.12 (wie Ubuntu 24.04)."
command -v npm >/dev/null || fehler "npm fehlt (Node.js 22)."

ARBEIT="$(mktemp -d)"
trap 'rm -rf "$ARBEIT"' EXIT
BAU="$ARBEIT/teamplaner-$VERSION"
mkdir "$BAU"

echo "Quellcode aus $QUELLE"
if [[ $(git -C "$QUELLE" rev-parse --show-toplevel 2>/dev/null) == "$QUELLE" ]]; then
  # Alle Dateien, die Git kennt oder nicht ignoriert (auch noch nicht eingecheckte)
  (cd "$QUELLE" && git ls-files -z -co --exclude-standard \
    | while IFS= read -r -d '' f; do if [[ -e $f ]]; then printf '%s\0' "$f"; fi; done \
    | tar --null -T - -cf -) | tar -xf - -C "$BAU"
else
  tar -C "$QUELLE" -cf - --exclude=.git --exclude=node_modules --exclude=__pycache__ --exclude=./static/dist \
    --exclude=./staticfiles --exclude=./media --exclude=./dist --exclude=./VERSION --exclude=./pruefung/linux/arbeit \
    --exclude=.env --exclude=.pytest_cache --exclude=.ruff_cache . | tar -xf - -C "$BAU"
fi

echo "Frontend bauen"
(cd "$BAU/frontend" && npm_config_update_notifier=false npm ci --no-audit --no-fund --loglevel=error \
  && npm run --silent build >/dev/null)

echo "Python-Pakete für $("$PYTHON" --version)"
"$PYTHON" -m venv "$ARBEIT/venv"
"$ARBEIT/venv/bin/pip" wheel -q --disable-pip-version-check --wheel-dir "$BAU/wheelhaus" -r "$BAU/requirements.txt"
# Wie auf dem Server: nur aus den beigelegten Paketen, ohne Internet
"$ARBEIT/venv/bin/pip" install -q --disable-pip-version-check --no-index --find-links "$BAU/wheelhaus" \
  -r "$BAU/requirements.txt"

echo "Statische Dateien sammeln"
cd "$BAU"
echo "$VERSION" > VERSION
DJANGO_SECRET_KEY=nur-fuer-collectstatic TEAMPLANER_STATIC_MANIFEST=1 \
  "$ARBEIT/venv/bin/python" manage.py collectstatic --noinput -v 0

# Nur was auf dem Server gebraucht wird; Rechte vereinheitlichen
cp betrieb/linux/installieren.sh installieren.sh
cp docs/installation-linux.md INSTALLATION.md
rm -rf frontend tests pruefung werkzeuge .github requirements-dev.* .editorconfig .gitattributes .gitignore
find . -type d -name __pycache__ -prune -exec rm -rf {} +
find . -type d -exec chmod 0755 {} + && find . -type f -exec chmod 0644 {} +
chmod 0755 installieren.sh manage.py betrieb/linux/teamplaner betrieb/linux/*.sh

archiv="teamplaner-$VERSION.tar.gz"
tar --sort=name --owner=0 --group=0 --numeric-owner -C "$ARBEIT" -czf "$ZIEL/$archiv" "teamplaner-$VERSION"
(cd "$ZIEL" && sha256sum "$archiv" > "$archiv.sha256")
echo "Fertig: $ZIEL/$archiv"
