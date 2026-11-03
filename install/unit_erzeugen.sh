#!/usr/bin/env bash
# Schreibt die fertige systemd-Unit nach STDOUT — alle Platzhalter ersetzt,
# passend zum Aufbau der Installation, die sie vorfindet.
#
#   install/unit_erzeugen.sh [--basis DIR] [--benutzer NAME] [--port N]
#                            [--repo OWNER/NAME] [--zweig NAME] [--unit-alt DATEI]
#
# Warum ein eigenes Skript: Vorher ersetzte dienst_einrichten.sh nur @BASIS@,
# @BENUTZER@ und @PORT@. @REPO@ und @ZWEIG@ blieben woertlich stehen — der
# Dienst hielt "@REPO@" fuer ein festgenageltes Repository, und die Oberflaeche
# liess sich nicht mehr umstellen. Ausserdem setzte die Vorlage Freigaben
# voraus (WorkingDirectory=.../programm/aktuell): Auf einer flachen Installation
# startete der Dienst gar nicht. Hier steht beides EINMAL, pruefbar ohne root
# (tools/smoketest_betrieb.py ruft es in einem Sandkasten auf).
#
# Nichts hier aendert das System. Schreiben, daemon-reload und Start bleiben
# beim Aufrufer.
set -eu

HIER="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROGRAMM="$(dirname "$HIER")"
# Liegt dieses Skript in einer Freigabe, ist die Installation drei Ebenen
# hoeher. Physischer Pfad (pwd -P), damit auch der Weg ueber programm/aktuell
# als Freigabe erkannt wird — siehe run.sh.
if [[ "$PROGRAMM" == */programm/freigaben/* ]]; then
    BASIS="$(cd -P "$PROGRAMM/../../.." && pwd -P)"
else
    BASIS="$PROGRAMM"
fi
BENUTZER=xrechnung
PORT=8022
REPO=""
ZWEIG=""
REPO_GESETZT=0
ZWEIG_GESETZT=0
UNIT_ALT=/etc/systemd/system/xrechnung.service

while [[ $# -gt 0 ]]; do
    case "$1" in
        --basis)    BASIS="$2"; shift 2 ;;
        --benutzer) BENUTZER="$2"; shift 2 ;;
        --port)     PORT="$2"; shift 2 ;;
        --repo)     REPO="$2"; REPO_GESETZT=1; shift 2 ;;
        --zweig)    ZWEIG="$2"; ZWEIG_GESETZT=1; shift 2 ;;
        --unit-alt) UNIT_ALT="$2"; shift 2 ;;
        *) echo "Unbekannt: $1" >&2; exit 2 ;;
    esac
done

VORLAGE="$HIER/xrechnung.service"
[[ -f "$VORLAGE" ]] || { echo "Vorlage fehlt: $VORLAGE" >&2; exit 1; }

# Ein Wert aus einer JSON-Datei: update.<schluessel>. Leer, wenn es sie nicht
# gibt. '|| true' steht AUSSERHALB der Substitution — ein Heredoc darin
# vertraegt sich nicht damit, siehe umstellen_freigaben.sh.
json_wert() {   # $1 Datei, $2 Schluessel
    [[ -f "$1" ]] || return 0
    local py="$BASIS/.venv/bin/python"
    [[ -x "$py" ]] || py=python3
    "$py" - "$1" "$2" <<'PY' 2>/dev/null || true
import json, sys
print((json.load(open(sys.argv[1], encoding="utf-8")).get("update") or {}).get(sys.argv[2], "") or "")
PY
}

# Woher aktualisiert wird, in dieser Reihenfolge:
#   1. ausdruecklich angegeben
#   2. die bestehende Unit — ein erneutes Einrichten darf einen festgenagelten
#      Zeiger nicht still gegen das tauschen, was der Dienst selbst in
#      app.json geschrieben hat. Genau davor soll die Unit ja schuetzen.
#   3. config/app.json, dann die Vorlage (wie installieren.sh)
aus_unit() {   # $1 Variablenname
    [[ -f "$UNIT_ALT" ]] || return 0
    grep -E "^Environment=$1=" "$UNIT_ALT" | head -1 | cut -d= -f3- || true
}
if [[ $REPO_GESETZT -eq 0 ]]; then
    REPO="$(aus_unit XRECHNUNG_UPDATE_REPO)"
    [[ -n "$REPO" ]] || REPO="$(json_wert "$BASIS/config/app.json" repo)"
    [[ -n "$REPO" ]] || REPO="$(json_wert "$BASIS/config/app.example.json" repo)"
fi
if [[ $ZWEIG_GESETZT -eq 0 ]]; then
    ZWEIG="$(aus_unit XRECHNUNG_UPDATE_ZWEIG)"
    [[ -n "$ZWEIG" ]] || ZWEIG="$(json_wert "$BASIS/config/app.json" zweig)"
fi
[[ -n "$ZWEIG" ]] || ZWEIG=main

# Werte landen in einem sed-Ausdruck mit '|' als Trenner. Ein '|', '&' oder
# Zeilenumbruch darin haette die Unit verbogen, statt aufzufallen.
for wert in "$BASIS" "$BENUTZER" "$PORT" "$REPO" "$ZWEIG"; do
    if [[ "$wert" == *'|'* || "$wert" == *'&'* || "$wert" == *$'\n'* || "$wert" == *'\'* ]]; then
        echo "Unzulaessiges Zeichen in '$wert'" >&2; exit 1
    fi
done

AUFBAU=()
if [[ -L "$BASIS/programm/aktuell" ]]; then
    : # Freigaben: die Vorlage passt wie sie ist.
else
    # Flach: Das Programm liegt direkt in BASIS. programm/ gibt es nicht —
    # und ein fehlender Pfad in ReadWritePaths laesst systemd den Start mit
    # 226/NAMESPACE verweigern, nicht bloss ignorieren.
    AUFBAU+=(-e "s|^WorkingDirectory=@BASIS@/programm/aktuell\$|WorkingDirectory=@BASIS@|")
    AUFBAU+=(-e "/^ReadWritePaths=/s|@BASIS@/programm *||")
fi

ERGEBNIS="$(sed "${AUFBAU[@]+"${AUFBAU[@]}"}" \
    -e "s|@BASIS@|$BASIS|g" -e "s|@BENUTZER@|$BENUTZER|g" -e "s|@PORT@|$PORT|g" \
    -e "s|@REPO@|$REPO|g" -e "s|@ZWEIG@|$ZWEIG|g" "$VORLAGE")"

# Nur die Zeilen pruefen, die systemd liest — in den Kommentaren stehen die
# Platzhalter absichtlich.
if grep -v '^[[:space:]]*#' <<<"$ERGEBNIS" | grep -qE '@[A-Z]+@'; then
    echo "In der Unit sind Platzhalter uebrig geblieben:" >&2
    grep -v '^[[:space:]]*#' <<<"$ERGEBNIS" | grep -E '@[A-Z]+@' >&2
    exit 1
fi
printf '%s\n' "$ERGEBNIS"
