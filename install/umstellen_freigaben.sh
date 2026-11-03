#!/usr/bin/env bash
# Stellt eine bestehende, flache Installation auf Freigabeverzeichnisse um.
#
#   vorher                          nachher
#   /opt/xrechnung/app/             /opt/xrechnung/programm/freigaben/<ts>-<sha>/app/
#   /opt/xrechnung/sql/             /opt/xrechnung/programm/aktuell -> freigaben/<ts>-<sha>
#   /opt/xrechnung/config/          /opt/xrechnung/config/     (bleibt)
#   /opt/xrechnung/data/            /opt/xrechnung/data/       (bleibt)
#   /opt/xrechnung/validation/      /opt/xrechnung/validation/ (bleibt)
#
# Warum VERSCHOBEN und nicht kopiert wird: Dann gibt es zu jedem Zeitpunkt
# genau einen Ort, an dem die Dateien liegen, und keinen Zweifel, welcher der
# gueltige ist. Scheitert etwas, schiebt der Rueckweg sie zurueck.
#
# Warum es diese Umstellung gibt, steht in docs/12_AKTUALISIERUNG.md.
set -euo pipefail

BASIS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DIENSTBENUTZER=xrechnung
PORT=8022
PORT_GESETZT=0
BENUTZER_GESETZT=0
REPO=""
ZWEIG=main
JA=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --basis)    BASIS="$2"; shift 2 ;;
        --benutzer) DIENSTBENUTZER="$2"; BENUTZER_GESETZT=1; shift 2 ;;
        --port)     PORT="$2"; PORT_GESETZT=1; shift 2 ;;
        --repo)     REPO="$2"; shift 2 ;;
        --zweig)    ZWEIG="$2"; shift 2 ;;
        --ja)       JA=1; shift ;;
        *) echo "Unbekannt: $1"; exit 2 ;;
    esac
done

rot=$'\e[31m'; gruen=$'\e[32m'; grau=$'\e[90m'; normal=$'\e[0m'
gut()      { printf '   %s[ok]%s   %s\n' "$gruen" "$normal" "$1"; }
info()     { printf '          %s%s%s\n' "$grau" "$1" "$normal"; }
schlecht() { printf '   %s[!]%s    %s\n' "$rot" "$normal" "$1"; }

[[ $EUID -eq 0 ]] || { schlecht "Bitte als root ausfuehren (sudo)."; exit 1; }

# Port und Dienstkonto aus der BESTEHENDEN Unit uebernehmen, sofern nicht
# ausdruecklich angegeben. Sonst schriebe die Umstellung die Vorgabewerte in
# die neue Unit — und der Dienst liefe danach auf einem anderen Port oder unter
# einem anderen Konto als vorher. Das faellt erst auf, wenn niemand mehr
# hinkommt.
UNIT_ALT=/etc/systemd/system/xrechnung.service
if [[ -f "$UNIT_ALT" ]]; then
    [[ $PORT_GESETZT -eq 0 ]] && {
        AUS_UNIT="$(grep -oE -- '--port [0-9]+' "$UNIT_ALT" | head -1 | awk '{print $2}')"
        [[ -n "${AUS_UNIT:-}" ]] && PORT="$AUS_UNIT"
    } || true
    [[ $BENUTZER_GESETZT -eq 0 ]] && {
        AUS_UNIT="$(grep -oE '^User=.*' "$UNIT_ALT" | head -1 | cut -d= -f2)"
        [[ -n "${AUS_UNIT:-}" ]] && DIENSTBENUTZER="$AUS_UNIT"
    } || true
    info "Aus der bestehenden Unit uebernommen: Benutzer $DIENSTBENUTZER, Port $PORT"
fi
id "$DIENSTBENUTZER" >/dev/null 2>&1 || {
    schlecht "Das Dienstkonto '$DIENSTBENUTZER' gibt es nicht."; exit 1; }

PROGRAMM_BEREICHE=(app sql tools docs install beispiele requirements.txt run.sh run.cmd
                   VERSION README.md HANDBUCH.md INSTALLATION.md PROTOTYP.md)

if [[ -L "$BASIS/programm/aktuell" ]]; then
    gut "Diese Installation laeuft bereits mit Freigaben — nichts zu tun."
    exit 0
fi

# --- Vorpruefungen --------------------------------------------------------
if [[ -z "$REPO" ]]; then
    # Dieselbe ausgeschriebene Form wie oben beim SHA. Diese Fassung liefe zwar
    # auch mit '|| true' in der Substitution, aber zwei Schreibweisen fuer
    # dasselbe laden dazu ein, die falsche zu kopieren.
    REPO="$(python3 - "$BASIS/config/app.json" <<'PY' 2>/dev/null
import json, sys
print((json.load(open(sys.argv[1])).get("update") or {}).get("repo", ""))
PY
    )" || REPO=""
fi
[[ -n "$REPO" ]] || { schlecht "Kein Repository bekannt. Mit --repo angeben."; exit 1; }

# Der Test steht BEWUSST ausserhalb der Kommandosubstitution. Ein Heredoc in
# einer Substitution vertraegt sich nicht mit einem '[[ ]] &&' davor: Bash
# schiebt beim erneuten Parsen das '|| true' hinter den Heredoc-Koerper, uebrig
# bleibt das Fragment '|| true)"' — ein Syntaxfehler, der erst beim AUSFUEHREN
# auftritt. 'bash -n' findet ihn nicht, weil der Inhalt einer Substitution erst
# beim Lauf geparst wird. Er hat das Skript beim ersten Versuch auf dem Server
# abbrechen lassen, bevor irgendetwas geschehen war.
SHA=migration
if [[ -f "$BASIS/data/update_stand.json" ]]; then
    ERMITTELT="$(python3 - "$BASIS/data/update_stand.json" <<'PY' 2>/dev/null
import json, sys
print(json.load(open(sys.argv[1])).get("sha", "")[:8])
PY
    )" || ERMITTELT=""
    [[ -n "$ERMITTELT" ]] && SHA="$ERMITTELT" || true
fi

# SELinux: Symlinks und ein verschobenes Arbeitsverzeichnis sind dort eine
# eigene Frage. Wir setzen nichts voraus, wir sehen nach und sagen es.
if command -v getenforce >/dev/null 2>&1; then
    MODUS="$(getenforce 2>/dev/null || echo unbekannt)"
    if [[ "$MODUS" == "Enforcing" ]]; then
        schlecht "SELinux steht auf Enforcing. Nach der Umstellung liegt das Programm"
        info "unter $BASIS/programm/freigaben/... — die Dateikennzeichnung muss dorthin"
        info "mitgenommen werden: restorecon -R $BASIS  (oder semanage fcontext)."
        info "Bitte pruefen und die Umstellung nur fortsetzen, wenn das geklaert ist."
        [[ $JA -eq 1 ]] || { read -r -p "   Trotzdem fortfahren? [j/N] " a </dev/tty || a=n
                             [[ "$a" == [jJ]* ]] || exit 1; }
    else
        gut "SELinux: $MODUS — unproblematisch"
    fi
fi

echo
echo "Umstellung auf Freigabeverzeichnisse"
echo "  Basis:      $BASIS"
echo "  Dienst:     $DIENSTBENUTZER, Port $PORT"
echo "  Quelle:     $REPO ($ZWEIG) — wird in der systemd-Unit festgenagelt"
echo "  Freigabe:   programm/freigaben/$(date +%Y%m%d-%H%M%S)-$SHA"
echo
if [[ $JA -ne 1 ]]; then
    read -r -p "Fortfahren? [j/N] " antwort </dev/tty || antwort=n
    [[ "$antwort" == [jJ]* ]] || { echo "Abgebrochen."; exit 1; }
fi

ZEITSTEMPEL="$(date +%Y%m%d-%H%M%S)"
FREIGABE="$BASIS/programm/freigaben/$ZEITSTEMPEL-$SHA"
UNIT=/etc/systemd/system/xrechnung.service
UNIT_SICHERUNG="$BASIS/data/xrechnung.service.vor-$ZEITSTEMPEL"

# --- 1. Dienst anhalten ---------------------------------------------------
LIEF=0
if systemctl is-active --quiet xrechnung 2>/dev/null; then
    LIEF=1
    systemctl stop xrechnung
    gut "Dienst angehalten"
fi

zurueck() {
    schlecht "Umstellung fehlgeschlagen — es wird zurueckgeschoben."
    for name in "${PROGRAMM_BEREICHE[@]}"; do
        [[ -e "$FREIGABE/$name" ]] && mv "$FREIGABE/$name" "$BASIS/$name" || true
        # Die Programmdateien gehoerten vorher root. Sie beim Dienstkonto zu
        # lassen hiesse, die flache Installation in genau dem Zustand
        # zurueckzugeben, vor dem die Notbremse warnt.
        [[ -e "$BASIS/$name" ]] && chown -R root:root "$BASIS/$name" || true
    done
    rm -f "$BASIS/programm/aktuell"
    [[ -f "$UNIT_SICHERUNG" ]] && cp "$UNIT_SICHERUNG" "$UNIT" || true
    systemctl daemon-reload
    [[ $LIEF -eq 1 ]] && systemctl start xrechnung
    schlecht "Alter Zustand wiederhergestellt. Nichts ist verloren."
    exit 1
}
trap zurueck ERR

# --- 2. Verschieben und umhaengen ----------------------------------------
mkdir -p "$FREIGABE"
VERSCHOBEN=0
for name in "${PROGRAMM_BEREICHE[@]}"; do
    if [[ -e "$BASIS/$name" ]]; then
        mv "$BASIS/$name" "$FREIGABE/$name"
        VERSCHOBEN=$((VERSCHOBEN+1))
    fi
done
# Die Freigabe traegt ihren Stand bei sich. Ohne diesen Vermerk kaeme nach
# einem Zuruecksetzen auf sie nur die verkuerzte Kennung aus dem
# Verzeichnisnamen — die reicht zwar, ist aber ungenauer als noetig, weil der
# volle Wert in data/update_stand.json steht.
if [[ -f "$BASIS/data/update_stand.json" ]]; then
    python3 - "$BASIS/data/update_stand.json" "$FREIGABE/.freigabe.json" <<'PY' || true
import json, sys
alt = json.load(open(sys.argv[1]))
json.dump({"sha": alt.get("sha", ""), "datum": alt.get("datum", ""),
           "eingespielt": alt.get("eingespielt", "")},
          open(sys.argv[2], "w"), indent=2)
PY
fi
ln -sfn "freigaben/$ZEITSTEMPEL-$SHA" "$BASIS/programm/aktuell"
gut "$VERSCHOBEN Bereiche verschoben, 'aktuell' zeigt darauf"

# --- 3. Eigentuemer -------------------------------------------------------
chown -R "$DIENSTBENUTZER":"$DIENSTBENUTZER" "$BASIS/programm"
# '|| true' ist hier kein Schmuck: Unter 'set -e' mit ERR-trap ist der
# Rueckgabewert eines nicht zutreffenden [[ ]] gleich 1 — fehlt die venv,
# zuende der trap mitten in einer fehlerfreien Umstellung.
[[ -d "$BASIS/.venv" ]] && chown -R "$DIENSTBENUTZER":"$DIENSTBENUTZER" "$BASIS/.venv" || true
for ordner in config data logs; do
    [[ -d "$BASIS/$ordner" ]] && chown -R "$DIENSTBENUTZER":"$DIENSTBENUTZER" "$BASIS/$ordner" || true
done
gut "Eigentuemer gesetzt: programm, .venv, config, data, logs -> $DIENSTBENUTZER"
info "$BASIS selbst bleibt bei root, ebenso die systemd-Unit."
info "install/ liegt IM Programm und gehoert deshalb dem Dienst — es wird bei"
info "jeder Aktualisierung mitersetzt, das ist so gewollt."

# --- 4. Unit neu schreiben ------------------------------------------------
[[ -f "$UNIT" ]] && cp "$UNIT" "$UNIT_SICHERUNG" || true
sed -e "s|@BASIS@|$BASIS|g" -e "s|@BENUTZER@|$DIENSTBENUTZER|g" \
    -e "s|@PORT@|$PORT|g" -e "s|@REPO@|$REPO|g" -e "s|@ZWEIG@|$ZWEIG|g" \
    "$FREIGABE/install/xrechnung.service" > "$UNIT"
systemctl daemon-reload
systemctl start xrechnung
gut "Unit neu geschrieben, Dienst gestartet"

# --- 5. Pruefen, BEVOR es als erledigt gilt -------------------------------
# "Dienst laeuft" ist kein Erfolg: Er laeuft auch mit kaputtem
# Validierungspfad. Geprueft wird deshalb, was der Anwender braucht.
trap - ERR
sleep 4
FEHLGESCHLAGEN=0

# Ohne curl nicht aufgeben: Sonst meldete ausgerechnet die Pruefung, die ueber
# Erfolg entscheidet, einen Fehlschlag, weil ein Werkzeug fehlt.
erreichbar() {
    if command -v curl >/dev/null 2>&1; then
        curl -fsS --max-time 10 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1
    else
        "$BASIS/.venv/bin/python" - "$PORT" <<'PYH' >/dev/null 2>&1
import sys, urllib.request
urllib.request.urlopen(f"http://127.0.0.1:{sys.argv[1]}/health", timeout=10).read()
PYH
    fi
}
if erreichbar; then
    gut "Die Anwendung antwortet auf Port $PORT"
else
    schlecht "Die Anwendung antwortet NICHT auf Port $PORT"
    info "journalctl -u xrechnung -n 50"
    FEHLGESCHLAGEN=1
fi

# Der Suchpfad kommt aus XRECHNUNG_BASIS, nicht aus dem Arbeitsverzeichnis:
# Nach dem Verschieben liegt dort kein app/ mehr, und ein ModuleNotFoundError
# landete in der Variablen statt auf dem Bildschirm. Die Pruefung haette dann
# nach GELUNGENER Umstellung einen Fehlschlag gemeldet — und wer der Ausgabe
# folgt, zerlegt eine Installation, die in Ordnung war.
PRUEFUNG="$(sudo -u "$DIENSTBENUTZER" \
    XRECHNUNG_BASIS="$BASIS" XRECHNUNG_CONFIG_DIR="$BASIS/config" \
    XRECHNUNG_DATEN_DIR="$BASIS/data" XRECHNUNG_LOG_DIR="$BASIS/logs" \
    "$BASIS/.venv/bin/python" - <<'PY' 2>&1 || true
import os, sys
sys.path.insert(0, os.environ["XRECHNUNG_BASIS"] + "/programm/aktuell")
from app import config, pfade, validate, xml_build
cfg = config.laden()
z = validate.zustand(cfg)
proben = sorted((pfade.PROGRAMM / "beispiele").glob("*.xml"))
print("BASIS", pfade.BASIS)
print("VALIDATOR", "bereit" if z["bereit"] else "FEHLT: " + "; ".join(z["fehlt"]))
if z["bereit"] and proben:
    fehler, _ = validate.pruefen_ausfuehrlich(cfg, proben[0].read_bytes())
    print("BELEG", proben[0].name, "OK" if not fehler else "FEHLER: " + "; ".join(fehler))
elif not proben:
    print("BELEG keine Probe im Programmverzeichnis")
PY
)"
echo "$PRUEFUNG" | while IFS= read -r zeile; do info "$zeile"; done
if echo "$PRUEFUNG" | grep -q "ModuleNotFoundError\|Traceback"; then
    schlecht "Die Pruefung selbst ist gescheitert — das sagt nichts ueber die Umstellung."
    info "Bitte die Meldung oben lesen, bevor irgendetwas zurueckgeschoben wird."
    FEHLGESCHLAGEN=1
elif echo "$PRUEFUNG" | grep -q "VALIDATOR bereit"; then
    gut "Der Validator wird gefunden — der Pfad zeigt in den Bestand, nicht in die Freigabe"
else
    schlecht "Der Validator wird NICHT gefunden. Genau das faellt sonst erst bei der"
    info "naechsten Rechnung auf. Bitte validierung.kosit_jar pruefen."
    FEHLGESCHLAGEN=1
fi
if echo "$PRUEFUNG" | grep -q "BELEG.*OK"; then
    gut "Ein Beleg laeuft durch die Validierung"
fi

ABLAGE="$(sudo -u "$DIENSTBENUTZER" \
    XRECHNUNG_BASIS="$BASIS" XRECHNUNG_CONFIG_DIR="$BASIS/config" \
    XRECHNUNG_DATEN_DIR="$BASIS/data" XRECHNUNG_LOG_DIR="$BASIS/logs" \
    "$BASIS/.venv/bin/python" -c '
import os, sys
sys.path.insert(0, os.environ["XRECHNUNG_BASIS"] + "/programm/aktuell")
from app import ablauf, config
print(ablauf._ordner(config.laden(), "archiv_ordner"))' 2>&1 || true)"
if [[ "$ABLAGE" == "$BASIS/data"* ]]; then
    gut "Die Rechnungsablage zeigt in den Bestand: $ABLAGE"
else
    schlecht "Die Rechnungsablage zeigt NICHT in den Bestand: $ABLAGE"
    info "So wuerden archivierte Rechnungen beim Aufraeumen alter Freigaben geloescht."
    FEHLGESCHLAGEN=1
fi

echo
if [[ $FEHLGESCHLAGEN -eq 1 ]]; then
    schlecht "Die Umstellung ist NICHT in Ordnung. Rueckweg:"
    info "  systemctl stop xrechnung"
    info "  mv $FREIGABE/* $BASIS/ && rm $BASIS/programm/aktuell"
    info "  cp $UNIT_SICHERUNG $UNIT && systemctl daemon-reload && systemctl start xrechnung"
    exit 1
fi
gut "Umstellung abgeschlossen. Alter Stand liegt als Freigabe $ZEITSTEMPEL-$SHA."
info "Die naechste Aktualisierung legt eine zweite Freigabe daneben und haengt um."
info "Zurueckgehen geht dann in der Oberflaeche unter Konfiguration."
