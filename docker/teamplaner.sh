#!/usr/bin/env bash
# Verwaltung einer Teamplaner-Installation auf dem Server (siehe docs/betrieb.md).
# Liegt nach der Installation als ./teamplaner im Installationsverzeichnis.
set -euo pipefail

HILFE="Aufruf: ./teamplaner <befehl> [-j|--ja]

  status                  installierte und neueste Version, Zustand der Dienste, letzte Sicherung
  update [VERSION]        neueste (oder angegebene) Version einspielen: Sicherung, laden, starten;
                          startet sie nicht, geht es automatisch auf den alten Stand zurück
  zurueck                 zurück auf die Version vor dem letzten Update
  start | stop            alle Dienste starten bzw. anhalten
  logs [DIENST]           Protokoll ansehen (app, mailer, caddy, db, backup)
  sichern                 sofort eine Sicherung anlegen
  wiederherstellen DUMP [ANHAENGE]
                          Sicherung einspielen (überschreibt die Daten)
  konto-anlegen OPTIONEN  Konto anlegen, z. B. das erste Admin-Konto (siehe docs/betrieb.md)

  -j, --ja                Rückfragen bestätigen (außer solchen, bei denen Daten verloren gehen)"

VERZ="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Im Quellcode liegt dieses Skript unter docker/
[[ -f "$VERZ/compose.prod.yaml" ]] || VERZ="$(dirname "$VERZ")"
cd "$VERZ"
STAND="$VERZ/stand"
WARTEN="${TEAMPLANER_WARTEN:-300}"
JA=0
CADDY_NEU=0

meldung() { printf '\n==> %s\n' "$*"; }
fehler() { printf '\nFehler: %s\n' "$*" >&2; exit 1; }
compose() { docker compose -f compose.prod.yaml --env-file .env "$@"; }

bestaetigen() {
  [[ $JA == 1 ]] && return 0
  local antwort=""
  read -r -p "$1 [j/N] " antwort || true
  [[ $antwort =~ ^[jJyY] ]]
}

# Wert aus .env (letzte Zeile gewinnt, umgebende Anführungszeichen entfernt), sonst $2
env_wert() {
  local wert
  wert="$(sed -n "s/^$1=//p" .env | tail -n 1)"
  wert="${wert%\"}"
  wert="${wert#\"}"
  printf '%s' "${wert:-${2:-}}"
}

env_setzen() {
  if grep -q "^$1=" .env; then
    sed -i "s|^$1=.*|$1=$2|" .env
  else
    printf '%s=%s\n' "$1" "$2" >> .env
  fi
}

voraussetzungen() {
  command -v docker >/dev/null || fehler "Docker ist nicht installiert (siehe docs/betrieb.md)."
  docker info >/dev/null 2>&1 \
    || fehler "Kein Zugriff auf Docker. Benutzer zur Gruppe docker hinzufügen (sudo usermod -aG docker \$USER, neu anmelden) oder mit sudo aufrufen."
  docker compose version >/dev/null 2>&1 || fehler "Docker Compose fehlt."
  [[ -f .env ]] || fehler "Keine .env in $VERZ – zuerst: cp .env.example .env und die Werte eintragen."
}

sperren() {  # nie zwei Updates/Rücksprünge gleichzeitig
  mkdir -p "$STAND"
  command -v flock >/dev/null || return 0
  exec 9>"$STAND/.sperre"
  flock -n 9 || fehler "Ein anderer ./teamplaner-Befehl läuft gerade."
}

image() { env_wert TEAMPLANER_IMAGE ghcr.io/gehmacher-valentin/teamplaner-app; }

image_version() {  # Version aus dem Label eines lokal vorhandenen Images
  docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.version" }}' "$1" 2>/dev/null || true
}

installierte_version() {
  local v
  v="$(env_wert TEAMPLANER_VERSION latest)"
  [[ $v != latest ]] || v="$(image_version "$(image):latest")"
  printf '%s' "${v:-unbekannt}"
}

neueste_version() {  # lädt das Paket "latest" und liest dessen Version
  docker pull -q "$(image):latest" >/dev/null 2>&1 || return 1
  image_version "$(image):latest"
}

ist_version() { [[ $1 =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; }

hoeher() {  # ist Version $1 neuer als $2?
  [[ $1 != "$2" && "$(printf '%s\n%s\n' "$1" "$2" | sort -V | tail -n 1)" == "$1" ]]
}

sicherungsordner() { env_wert BACKUP_VERZEICHNIS ./backups; }

migrationen() {  # angewendete Datenbank-Migrationen, je Zeile "app name", sortiert
  compose exec -T db sh -c \
    'psql -At -F " " -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT app, name FROM django_migrations"' \
    | LC_ALL=C sort
}

dateien_sichern() {  # aktuelle Betriebsdateien nach $1 kopieren
  rm -rf "$1"
  mkdir -p "$1/docker/caddy"
  cp compose.prod.yaml teamplaner "$1/"
  [[ ! -f .env.example ]] || cp .env.example "$1/"
  cp docker/backup.sh docker/wiederherstellen.sh "$1/docker/"
  cp docker/caddy/Caddyfile "$1/docker/caddy/"
}

dateien_uebernehmen() {  # Betriebsdateien aus $1 übernehmen (das laufende Skript erst ganz am Ende)
  cmp -s "$1/docker/caddy/Caddyfile" docker/caddy/Caddyfile || CADDY_NEU=1
  mkdir -p docker/caddy
  cp "$1/compose.prod.yaml" compose.prod.yaml
  cp "$1/docker/backup.sh" "$1/docker/wiederherstellen.sh" docker/
  # cp überschreibt die Datei an Ort und Stelle: der laufende Caddy sieht sie ohne Neustart
  cp "$1/docker/caddy/Caddyfile" docker/caddy/Caddyfile
  [[ ! -f "$1/.env.example" ]] || cp "$1/.env.example" .env.example
}

skript_uebernehmen() {
  cp "$1/teamplaner" teamplaner.neu
  chmod +x teamplaner.neu
  mv -f teamplaner.neu teamplaner
}

starten() {  # alle Dienste starten und warten, bis die Anwendung gesund antwortet
  compose up -d --wait --wait-timeout "$WARTEN" || return 1
  # Sicherungsdienst mit dem aktuellen Skript neu starten, Caddy die neue Konfiguration laden lassen
  compose up -d --no-deps --force-recreate backup >/dev/null 2>&1 || return 1
  if [[ $CADDY_NEU == 1 ]]; then
    compose exec -T caddy caddy reload --config /etc/caddy/Caddyfile --adapter caddyfile >/dev/null 2>&1 \
      || compose restart caddy >/dev/null 2>&1 || return 1
    CADDY_NEU=0
  fi
}

neue_einstellungen() {  # Schlüssel aus .env.example, die in .env noch fehlen
  local schluessel='s/^\([A-Z_][A-Z0-9_]*\)=.*/\1/p' fehlend
  fehlend="$(LC_ALL=C comm -23 <(sed -n "$schluessel" .env.example | LC_ALL=C sort -u) \
                               <(sed -n "$schluessel" .env | LC_ALL=C sort -u) | tr '\n' ' ')"
  [[ -z ${fehlend// /} ]] \
    || echo "Neue Einstellungen in .env.example (bis sie in .env stehen, gelten Standardwerte): $fehlend"
}

migrationen_zuruecknehmen() {  # Migrationen seit dem Update mit der neuen Version rückwärts ausführen
  local apps app ziel
  apps="$(LC_ALL=C comm -13 "$STAND/migrationen.txt" <(migrationen) | cut -d' ' -f1 | sort -u)"
  if [[ -z $apps ]]; then
    echo "Keine Datenbank-Änderungen zurückzunehmen."
    return 0
  fi
  for app in $apps; do
    ziel="$(awk -v a="$app" '$1 == a { n = $2 } END { print (n == "" ? "zero" : n) }' "$STAND/migrationen.txt")"
    echo "  $app → $ziel"
    compose run --rm --no-deps -T --entrypoint python app manage.py migrate "$app" "$ziel" --noinput || return 1
  done
}

# ---------------------------------------------------------------------------------------------

cmd_status() {
  voraussetzungen
  local laufend neu letzte
  laufend="$(installierte_version)"
  echo "Installation:          $VERZ"
  echo "Installierte Version:  $laufend"
  if neu="$(neueste_version)" && [[ -n $neu ]]; then
    if hoeher "$neu" "$laufend"; then
      echo "Neueste Version:       $neu  → einspielen mit ./teamplaner update"
    else
      echo "Neueste Version:       $neu (installiert ist aktuell)"
    fi
  else
    echo "Neueste Version:       nicht abrufbar (Internetverbindung? docker login $(image | cut -d/ -f1)?)"
  fi
  letzte="$(find "$(sicherungsordner)" -maxdepth 1 -name 'datenbank_*.dump' 2>/dev/null | sort | tail -n 1)"
  echo "Letzte Sicherung:      ${letzte:-keine}"
  if [[ -f $STAND/vorherige-version ]]; then
    echo "Rücksprung möglich auf $(cat "$STAND/vorherige-version") (./teamplaner zurueck)"
  fi
  echo
  compose ps
}

cmd_update() {
  voraussetzungen
  [[ ! -d .git ]] || fehler "Installation aus dem Quellcode – Update dort mit git pull und
  docker compose -f compose.prod.yaml -f compose.build.yaml --env-file .env up -d --build"
  sperren
  local alt ziel kennung dump fehlerlog
  alt="$(installierte_version)"
  if [[ -n ${1:-} ]]; then
    ziel="${1#v}"
  else
    meldung "Suche die neueste Version"
    ziel="$(neueste_version)" || fehler "Keine Verbindung zur Paketquelle $(image) (Internetverbindung? docker login?)."
  fi
  ist_version "$ziel" || fehler "Ungültige Version '$ziel' (erwartet z. B. 1.2.0)."
  if [[ $ziel == "$alt" ]]; then
    echo "Version $alt ist bereits installiert."
    return 0
  fi
  if ist_version "$alt" && ! hoeher "$ziel" "$alt"; then
    fehler "$ziel ist älter als die installierte Version $alt. Zurück nach einem Update: ./teamplaner zurueck"
  fi

  meldung "Lade Version $ziel"
  docker pull "$(image):$ziel" || fehler "Version $ziel nicht gefunden oder kein Zugriff auf $(image) (docker login?)."
  bestaetigen "Update von $alt auf $ziel einspielen? Das System ist dabei kurz nicht erreichbar." || fehler "Abgebrochen."

  kennung="$(date +%Y-%m-%d_%H%M%S)_vor-update-$ziel"
  dump="$(sicherungsordner)/datenbank_$kennung.dump"
  fehlerlog="$STAND/update-$ziel-$(date +%Y-%m-%d_%H%M%S).log"

  meldung "Anwendung anhalten (Besucher sehen solange eine Wartungsseite)"
  compose stop app mailer

  meldung "Sicherung von Datenbank und Anhängen"
  if ! compose exec -T backup sh /skripte/backup.sh jetzt "$kennung" || [[ ! -f $dump ]]; then
    compose start app mailer
    fehler "Sicherung fehlgeschlagen – Update abgebrochen, Version $alt läuft weiter."
  fi

  # Stand für den Rücksprung festhalten, Betriebsdateien der neuen Version auspacken
  if ! { dateien_sichern "$STAND/vorher" \
         && migrationen > "$STAND/migrationen.txt" \
         && rm -rf "$STAND/neu" && mkdir -p "$STAND/neu" \
         && docker run --rm --user "$(id -u):$(id -g)" -v "$STAND/neu:/ziel" "$(image):$ziel" auspacken >/dev/null; }; then
    compose start app mailer
    fehler "Vorbereitung fehlgeschlagen – Update abgebrochen, Version $alt läuft weiter."
  fi
  printf '%s\n' "$alt" > "$STAND/vorherige-version"
  printf '%s\n' "$dump" > "$STAND/sicherung"

  meldung "Version $ziel starten (Datenbank-Migrationen laufen dabei automatisch)"
  dateien_uebernehmen "$STAND/neu"
  env_setzen TEAMPLANER_VERSION "$ziel"
  if starten; then
    skript_uebernehmen "$STAND/neu"
    meldung "Update auf $ziel abgeschlossen."
    neue_einstellungen
    echo "Zurück auf $alt, falls nötig: ./teamplaner zurueck"
    return 0
  fi

  compose logs --no-color --tail 300 app mailer > "$fehlerlog" 2>&1 || true
  meldung "Version $ziel startet nicht – automatischer Rücksprung auf $alt"
  compose stop app mailer || true
  dateien_uebernehmen "$STAND/vorher"
  env_setzen TEAMPLANER_VERSION "$alt"
  sh docker/wiederherstellen.sh --ja --ohne-start "$dump"
  starten || fehler "Auch Version $alt startet nicht. Protokoll: ./teamplaner logs app"
  rm -f "$STAND/vorherige-version"
  fehler "Update auf $ziel fehlgeschlagen. Version $alt läuft wieder, mit dem Datenstand von vor dem Update.
Fehlerprotokoll der neuen Version: $fehlerlog"
}

cmd_zurueck() {
  voraussetzungen
  sperren
  [[ -f $STAND/vorherige-version && -d $STAND/vorher ]] || fehler "Kein Update gefunden, von dem es zurückgehen könnte."
  local alt jetzt dump
  alt="$(cat "$STAND/vorherige-version")"
  jetzt="$(installierte_version)"
  dump="$(cat "$STAND/sicherung")"
  echo "Zurück von Version $jetzt auf $alt. Datenbank-Änderungen der Version $jetzt werden zurückgenommen;"
  echo "alle Einträge seit dem Update bleiben erhalten, soweit die alte Version sie darstellen kann."
  bestaetigen "Fortfahren?" || fehler "Abgebrochen."

  meldung "Anwendung anhalten"
  compose stop app mailer
  meldung "Datenbank-Migrationen zurücknehmen"
  if ! migrationen_zuruecknehmen; then
    echo
    echo "Die Datenbank-Änderungen lassen sich nicht automatisch zurücknehmen."
    echo "Ausweg: die Sicherung vom Update einspielen ($dump)."
    echo "ACHTUNG: Alles, was seit dem Update eingetragen wurde, geht dabei verloren."
    if [[ ! -f $dump ]] || ! JA=0 bestaetigen "Sicherung einspielen?"; then
      compose start app mailer
      fehler "Abgebrochen – Version $jetzt läuft weiter."
    fi
    sh docker/wiederherstellen.sh --ja --ohne-start "$dump"
  fi

  meldung "Version $alt starten"
  dateien_uebernehmen "$STAND/vorher"
  env_setzen TEAMPLANER_VERSION "$alt"
  starten || fehler "Version $alt startet nicht. Protokoll: ./teamplaner logs app"
  skript_uebernehmen "$STAND/vorher"
  rm -f "$STAND/vorherige-version"
  meldung "Version $alt läuft wieder."
}

cmd_start() {
  voraussetzungen
  meldung "Starte Teamplaner $(installierte_version)"
  starten || fehler "Die Anwendung startet nicht. Protokoll: ./teamplaner logs app"
  local port
  port="$(env_wert HTTPS_PORT 443)"
  if [[ $port == 443 ]]; then port=""; else port=":$port"; fi
  meldung "Läuft: https://$(env_wert TEAMPLANER_DOMAIN localhost)$port"
}

main() {
  local argumente=() a befehl
  for a in "$@"; do
    case "$a" in
      -j | --ja) JA=1 ;;
      -h | --hilfe | --help) befehl=hilfe ;;
      *) argumente+=("$a") ;;
    esac
  done
  set -- "${argumente[@]+"${argumente[@]}"}"
  befehl="${befehl:-${1:-hilfe}}"
  [[ $# -eq 0 ]] || shift
  case "$befehl" in
    status) cmd_status ;;
    update) cmd_update "${1:-}" ;;
    zurueck | zurück) cmd_zurueck ;;
    start) cmd_start ;;
    stop) voraussetzungen && compose stop ;;
    logs) voraussetzungen && compose logs -f --tail 200 "$@" ;;
    sichern) voraussetzungen && compose exec -T backup sh /skripte/backup.sh jetzt ;;
    wiederherstellen)
      voraussetzungen
      sperren
      if [[ $JA == 1 ]]; then sh docker/wiederherstellen.sh --ja "$@"; else sh docker/wiederherstellen.sh "$@"; fi ;;
    konto-anlegen) voraussetzungen && compose exec -T app python manage.py konto_anlegen "$@" ;;
    hilfe) echo "$HILFE" ;;
    *) echo "$HILFE" >&2; exit 1 ;;
  esac
}

main "$@"
