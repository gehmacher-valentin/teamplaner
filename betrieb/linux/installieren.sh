#!/bin/sh
# Erstinstallation des Teamplaners auf einem Linux-Server (INSTALLATION.md).
# Aufruf im entpackten Archiv:  sudo ./installieren.sh
# Beim ersten Aufruf entsteht /etc/teamplaner/teamplaner.env; nach dem Ausfüllen noch einmal aufrufen.
set -eu
cd "$(dirname "$0")"
exec bash betrieb/linux/teamplaner einrichten "$(pwd)"
