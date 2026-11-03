#!/usr/bin/env bash
# Richtet nur den systemd-Dienst ein - fuer den Fall, dass die uebrige
# Einrichtung schon steht. Der volle Weg ist installieren.sh.
#
#   sudo ./install/dienst_einrichten.sh [BENUTZER] [PORT] [REPO] [ZWEIG]
#
# Funktioniert flach (/opt/xrechnung/install/) und aus einer Freigabe
# (/opt/xrechnung/programm/aktuell/install/). Die Unit selbst baut
# unit_erzeugen.sh — dort steht auch, warum.
set -eu
HIER="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
PROGRAMM="$(dirname "$HIER")"
# Aus einer Freigabe gestartet, lag BASIS vorher IN der Freigabe: .venv fehlte
# dort, und das Skript brach mit "Programmumgebung fehlt" ab, obwohl sie da war.
if [[ "$PROGRAMM" == */programm/freigaben/* ]]; then
    BASIS="$(cd -P "$PROGRAMM/../../.." && pwd -P)"
else
    BASIS="$PROGRAMM"
fi
BENUTZER="${1:-xrechnung}"
PORT="${2:-8022}"
REPO_ARG=()
[[ -n "${3:-}" ]] && REPO_ARG+=(--repo "$3")
[[ -n "${4:-}" ]] && REPO_ARG+=(--zweig "$4")

[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo starten."; exit 1; }
[[ -x "$BASIS/.venv/bin/python" ]] || { echo "Programmumgebung fehlt - zuerst installieren.sh ausfuehren."; exit 1; }

id "$BENUTZER" >/dev/null 2>&1 || useradd --system --home-dir "$BASIS" --shell /sbin/nologin "$BENUTZER"
mkdir -p "$BASIS/config" "$BASIS/data" "$BASIS/logs"
chown -R "$BENUTZER":"$BENUTZER" "$BASIS/config" "$BASIS/data" "$BASIS/logs"
chmod 700 "$BASIS/config"
# Die venv gehoert dem Dienst: Bei einer Aktualisierung mit neuen
# Abhaengigkeiten muss pip dort schreiben duerfen (siehe xrechnung.service,
# ReadWritePaths). Wie in installieren.sh.
chown -R "$BENUTZER":"$BENUTZER" "$BASIS/.venv"

# Erst vollstaendig erzeugen, dann an Ort und Stelle legen: Scheitert das
# Erzeugen, bleibt die bisherige Unit unberuehrt.
NEU="$(mktemp)"
trap 'rm -f "$NEU"' EXIT
"$HIER/unit_erzeugen.sh" --basis "$BASIS" --benutzer "$BENUTZER" --port "$PORT" \
    "${REPO_ARG[@]+"${REPO_ARG[@]}"}" > "$NEU"
install -m 0644 -o root -g root "$NEU" /etc/systemd/system/xrechnung.service
systemctl daemon-reload
systemctl enable --now xrechnung

if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
    firewall-cmd --permanent --add-port="$PORT"/tcp >/dev/null
    firewall-cmd --reload >/dev/null
fi

systemctl status xrechnung --no-pager -n 5 || true
echo
if [[ ! -L "$BASIS/programm/aktuell" ]]; then
    echo "Hinweis: Die Installation liegt noch flach. Aktualisieren ueber die Oberflaeche"
    echo "geht erst nach: sudo $BASIS/install/umstellen_freigaben.sh"
fi
echo "Oberflaeche: http://$(hostname):$PORT/"
