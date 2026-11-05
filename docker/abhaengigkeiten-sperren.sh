#!/bin/sh
# Löst requirements*.in in einer frischen Umgebung auf und schreibt gepinnte Versionen.
set -e
python -m venv /tmp/lock && . /tmp/lock/bin/activate
pip install -q -r requirements.in
pip freeze --exclude-editable > requirements.txt
pip install -q -r requirements-dev.in
pip freeze --exclude-editable | grep -v -x -F -f requirements.txt > requirements-dev.txt || true
sed -i '1i -r requirements.txt' requirements-dev.txt
echo "requirements.txt und requirements-dev.txt aktualisiert."
