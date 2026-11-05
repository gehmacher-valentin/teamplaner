#!/usr/bin/env bash
# Probe der Linux-Installation ohne Docker (docs/installation-linux.md):
# baut drei Archive (aktueller Stand als 0.1.0, 0.2.0 mit zusätzlicher Migration, 0.3.0 absichtlich
# defekt), startet Probeserver mit systemd – Debian 12 mit nginx, Rocky Linux 9 mit Apache – und
# spielt darauf als root mit umask 0077 Installation, Webserver, Update, Rücksprung, defektes Update,
# Wiederherstellung, Python-Wechsel nach einem Upgrade der Distribution (neu-aufbauen) und einen
# Neustart des Servers durch (ablauf.sh). Braucht nur Docker auf dem Entwicklungsrechner.
#   pruefung/linux/pruefen.sh              beide Probeserver
#   pruefung/linux/pruefen.sh debian       nur einer
#   BEHALTEN=1 pruefung/linux/pruefen.sh   Probeserver danach nicht löschen (docker exec -it tp-linux-debian bash)
set -euo pipefail
cd "$(dirname "$0")/../.."
export MSYS_NO_PATHCONV=1   # Git Bash unter Windows: Pfade für docker nicht umschreiben
ARBEIT=pruefung/linux/arbeit
SERVER=("$@")
[[ ${#SERVER[@]} -gt 0 ]] || SERVER=(debian rocky)

schritt() { printf '\n======== %s\n' "$*"; }

schritt "Archive bauen"
rm -rf "$ARBEIT" && mkdir -p "$ARBEIT/pakete" "$ARBEIT/v2"
docker build -q --target linux-paket --build-arg TEAMPLANER_VERSION=0.1.0 --output "type=local,dest=$ARBEIT/pakete" . >/dev/null
# 0.2.0: aktueller Stand plus eine Migration; 0.3.0: zusätzlich eine Migration, die fehlschlägt
git ls-files -co --exclude-standard -z | xargs -0 tar -cf - | tar -xf - -C "$ARBEIT/v2"
migrationen=(kern/migrations/0*.py)  # Glob ist sortiert; ohne find -printf, läuft auch auf macOS (bash 3.2)
letzte="$(basename "${migrationen[${#migrationen[@]}-1]}")"
cat > "$ARBEIT/v2/kern/migrations/0900_probe_update.py" <<EOF
# Nur für die Probe (pruefung/linux/pruefen.sh)
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("kern", "${letzte%.py}")]
    operations = [migrations.AddField("bereich", "probe", models.CharField(max_length=10, null=True, blank=True))]
EOF
docker build -q --target linux-paket --build-arg TEAMPLANER_VERSION=0.2.0 --output "type=local,dest=$ARBEIT/pakete" "$ARBEIT/v2" >/dev/null
cat > "$ARBEIT/v2/kern/migrations/0901_probe_defekt.py" <<'EOF'
# Nur für die Probe: schlägt absichtlich fehl
from django.db import migrations


def fehler(apps, schema_editor):
    raise RuntimeError("Absichtlich defekte Migration (Probe)")


class Migration(migrations.Migration):
    dependencies = [("kern", "0900_probe_update")]
    operations = [migrations.RunPython(fehler, migrations.RunPython.noop)]
EOF
docker build -q --target linux-paket --build-arg TEAMPLANER_VERSION=0.3.0 --output "type=local,dest=$ARBEIT/pakete" "$ARBEIT/v2" >/dev/null
ls -l "$ARBEIT/pakete"

starten() {  # Probeserver mit systemd starten und warten, bis er hochgefahren ist
  local name=$1 stand
  for _ in $(seq 1 60); do
    stand="$(docker exec "$name" systemctl is-system-running 2>/dev/null || true)"
    [[ $stand == running || $stand == degraded ]] && return 0
    sleep 2
  done
  echo "Probeserver $name fährt nicht hoch ($stand)"
  return 1
}

ergebnis=0
for art in "${SERVER[@]}"; do
  name="tp-linux-$art"
  schritt "Probeserver $art"
  # amd64 wie die Archive (sie enthalten amd64-Pakete); auf Apple-Rechnern emuliert
  docker build -q --platform linux/amd64 -t "$name" -f "pruefung/linux/$art.Dockerfile" pruefung/linux >/dev/null
  docker rm -f "$name" >/dev/null 2>&1 || true
  docker run -d --platform linux/amd64 --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
    --tmpfs /run --tmpfs /run/lock --name "$name" "$name" >/dev/null
  starten "$name"
  docker cp "$ARBEIT/pakete" "$name:/root/pakete"
  docker cp pruefung/linux/ablauf.sh "$name:/root/ablauf.sh"
  if docker exec "$name" bash /root/ablauf.sh "$art" \
     && { schritt "$art: Neustart des Servers"; docker restart -t 20 "$name" >/dev/null && starten "$name"; } \
     && docker exec "$name" bash /root/ablauf.sh "$art" nach-neustart; then
    echo "==> $art: ALLES OK"
  else
    echo "==> $art: FEHLGESCHLAGEN"
    ergebnis=1
  fi
  [[ ${BEHALTEN:-0} == 1 ]] || docker rm -f "$name" >/dev/null
done
exit $ergebnis
