#!/usr/bin/env bash
# OPERA XRechnung - Start im Vordergrund (Entwicklung/Test).
# Fuer den Dauerbetrieb: install/installieren.sh richtet einen systemd-Dienst ein.
set -u
# pwd -P, nicht pwd: Gestartet ueber programm/aktuell/run.sh liefert das
# logische pwd ".../programm/aktuell" — der Symlink, nicht die Freigabe. Die
# Erkennung unten sucht aber "/programm/freigaben/" und fand es nicht. Dann
# galt die Freigabe als Installation: eine neue .venv, eine neue app.json und
# die Rechnungen IN der Freigabe, die das Aufraeumen spaeter loescht. Und
# programm/aktuell ist genau der Weg, den man von Hand nimmt.
PROGRAMM="$(cd -P "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$PROGRAMM"

# Liegt dieses Skript in einer Freigabe (programm/freigaben/<stand>/), dann ist
# die Installation drei Ebenen hoeher — und Konfiguration, Arbeitsliste und die
# erzeugten Rechnungen gehoeren DORTHIN.
#
# Ohne diese Zeilen greift der Rueckfall in app/pfade.py, BASIS wird gleich
# PROGRAMM, und wer zum Fehlersuchen von Hand startet, schreibt seine
# Rechnungen in die Freigabe — wo das Aufraeumen sie spaeter entfernt. Es
# traefe ausgerechnet den, der gerade sucht und dem Ergebnis vertraut.
if [[ "$PROGRAMM" == */programm/freigaben/* ]]; then
    BASIS="$(cd -P "$PROGRAMM/../../.." && pwd -P)"
    export XRECHNUNG_BASIS="$BASIS"
    export XRECHNUNG_CONFIG_DIR="$BASIS/config"
    export XRECHNUNG_DATEN_DIR="$BASIS/data"
    export XRECHNUNG_LOG_DIR="$BASIS/logs"
    echo "Freigabenbetrieb erkannt. Bestand: $BASIS"
else
    BASIS="$PROGRAMM"
fi

VENV="$BASIS/.venv"
if [[ ! -x "$VENV/bin/python" ]]; then
    echo "Erstelle virtuelle Umgebung..."
    for kandidat in python3.12 python3.11 python3; do
        command -v "$kandidat" >/dev/null 2>&1 && { "$kandidat" -m venv "$VENV" && break; }
    done
    if [[ ! -x "$VENV/bin/python" ]]; then
        echo "Python 3.11 oder neuer wird gebraucht und wurde nicht gefunden."
        exit 1
    fi
    # venv bringt sein pip selbst mit; ein systemweites pip ist nicht noetig.
    "$VENV/bin/python" -m pip --version >/dev/null 2>&1 || "$VENV/bin/python" -m ensurepip --upgrade
    "$VENV/bin/python" -m pip install --upgrade pip
    "$VENV/bin/python" -m pip install -r requirements.txt || exit 1
fi

if [[ ! -f "$BASIS/config/app.json" ]]; then
    mkdir -p "$BASIS/config"
    cp "$PROGRAMM/config/app.example.json" "$BASIS/config/app.json"
    echo "Konfiguration aus der Vorlage angelegt: $BASIS/config/app.json"
fi

echo
echo "Oberflaeche:  http://$(hostname):8022/"
echo "Beenden mit Strg+C"
echo
exec "$VENV/bin/python" -m uvicorn app.main:app --host 0.0.0.0 --port 8022
