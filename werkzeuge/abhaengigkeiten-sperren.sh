#!/bin/sh
# Löst requirements*.in mit Python 3.12 (wie Ubuntu 24.04) in einer frischen Umgebung auf und schreibt
# gepinnte Versionen. Aufruf im Repository: sh werkzeuge/abhaengigkeiten-sperren.sh
set -e
"${PYTHON:-python3.12}" -m venv /tmp/lock && . /tmp/lock/bin/activate
pip install -q -r requirements.in
pip freeze --exclude-editable > requirements.txt
pip install -q -r requirements-dev.in
pip freeze --exclude-editable | grep -v -x -F -f requirements.txt > requirements-dev.txt || true
sed -i '1i -r requirements.txt' requirements-dev.txt
echo "requirements.txt und requirements-dev.txt aktualisiert."
