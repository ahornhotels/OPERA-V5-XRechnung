#!/usr/bin/env bash
# Richtet OPERA XRechnung auf Rocky Linux 9 oder 10 ein.
#
#   sudo ./install/installieren.sh
#
# Jeder Schritt, der etwas aus dem Internet laedt oder am System aendert, wird
# vorher angesagt und muss bestaetigt werden. Wer ablehnt, ueberspringt nur
# diesen Schritt - am Ende steht, was offen blieb und wie es nachzuholen ist.
#
# Schalter:
#   --ohne-rueckfrage, -j   alles ohne Nachfrage (fuer unbeaufsichtigte Laeufe)
#   --ohne-dienst           keinen systemd-Dienst anlegen
#   --ohne-pruefer          KoSIT-Pruefprogramm nicht herunterladen
#   --port 8022             abweichender Port
#   --benutzer NAME         Dienstkonto (Vorgabe: xrechnung)

set -u
BASIS="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT=8022
DIENSTBENUTZER=xrechnung
OHNE_DIENST=0
OHNE_PRUEFER=0
OHNE_RUECKFRAGE=0
SCHRITT=0
FEHLER=()
UEBERSPRUNGEN=()

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ohne-rueckfrage|-j) OHNE_RUECKFRAGE=1; shift ;;
        --ohne-dienst)        OHNE_DIENST=1; shift ;;
        --ohne-pruefer)       OHNE_PRUEFER=1; shift ;;
        --port)               PORT="$2"; shift 2 ;;
        --benutzer)           DIENSTBENUTZER="$2"; shift 2 ;;
        *) echo "Unbekannter Schalter: $1"; exit 1 ;;
    esac
done

rot=$'\e[33m'; gruen=$'\e[32m'; blau=$'\e[36m'; grau=$'\e[90m'; weiss=$'\e[97m'; normal=$'\e[0m'
titel()    { SCHRITT=$((SCHRITT+1)); printf '\n%s== Schritt %d - %s%s\n' "$blau" "$SCHRITT" "$1" "$normal"; }
gut()      { printf '   %s[ok]%s   %s\n' "$gruen" "$normal" "$1"; }
info()     { printf '          %s%s%s\n' "$grau" "$1" "$normal"; }
schlecht() { printf '   %s[!]%s    %s\n' "$rot" "$normal" "$1"; FEHLER+=("$1"); }
uebergangen() { printf '   %s[--]%s   uebersprungen\n' "$grau" "$normal"; UEBERSPRUNGEN+=("$1"); }

# Sagt an, was passieren soll: Was, woher, wozu.
ansage() {   # $1 Was, $2 Quelle, $3 Wozu
    printf '   %s->%s     %s\n' "$weiss" "$normal" "$1"
    [[ -n "${2:-}" ]] && printf '          Quelle: %s\n' "$2"
    [[ -n "${3:-}" ]] && printf '          Zweck:  %s\n' "$3"
}

# Rueckfrage. Ja ist die Vorgabe - Enter genuegt.
frage() {
    if [[ $OHNE_RUECKFRAGE -eq 1 ]]; then
        printf '          %s(ohne Rueckfrage bestaetigt)%s\n' "$grau" "$normal"
        return 0
    fi
    # Der Prompt wird GETRENNT ausgegeben, nicht ueber 'read -p'. Grund: Bash
    # schreibt den Prompt von 'read -p' auf STDERR — die Umleitung 2>/dev/null,
    # die den Fehlschlag ohne Terminal abfangen soll, verschluckt ihn dann mit.
    # Der Installer stuende stumm da und wartete auf eine Eingabe, die er nie
    # angekuendigt hat.
    local antwort=""
    local text="          Fortfahren? [J/n] "
    printf '%s' "$text" >/dev/tty 2>/dev/null || printf '%s' "$text"

    # Das Ergebnis des Lesens wird ausgewertet, nicht nur die Antwort: schlaegt
    # es fehl (kein Terminal, Eingabe geschlossen), gilt das als Nein. Sonst
    # bestaetigte ein Lauf ohne Terminal stillschweigend jeden Download.
    if { read -r antwort </dev/tty; } 2>/dev/null; then
        :
    elif [[ -t 0 ]] && read -r antwort; then
        :
    else
        printf '\n'
        schlecht "Keine Eingabe moeglich (kein Terminal). Fuer unbeaufsichtigte Laeufe --ohne-rueckfrage angeben."
        return 1
    fi
    [[ -z "$antwort" || "$antwort" =~ ^[jJyY] ]]
}

if [[ $EUID -ne 0 ]]; then
    echo "Bitte mit sudo starten:  sudo $0"
    exit 1
fi

# Der Dienst laeuft unter einem eigenen Konto und mit ProtectHome=true. Unter
# /root oder /home kommt er deshalb nicht an seine eigenen Dateien — /root hat
# auf Rocky die Rechte dr-xr-x---, und ProtectHome blendet beide Baeume ohnehin
# aus. Der Fehler erschiene spaeter als "203/EXEC: Unable to locate executable",
# also als fehlende Datei, obwohl sie da ist. Deshalb hier abfangen.
case "$BASIS" in
    /root|/root/*|/home/*)
        echo
        echo "  Das Programm liegt unter $BASIS."
        echo
        echo "  Dort kann der Dienst nicht laufen: Er startet unter einem eigenen"
        echo "  Konto, und die systemd-Unit blendet /root und /home aus"
        echo "  (ProtectHome=true). Der Start scheiterte spaeter mit"
        echo "  '203/EXEC - Unable to locate executable', obwohl die Datei da ist."
        echo
        echo "  Bitte nach /opt/xrechnung verschieben und erneut starten:"
        echo "      mv \"$BASIS\" /opt/xrechnung && cd /opt/xrechnung"
        echo "      sudo ./install/installieren.sh"
        echo
        echo "  Nur einrichten ohne Dienst geht auch hier: --ohne-dienst"
        echo
        [[ $OHNE_DIENST -eq 1 ]] || exit 1
        ;;
esac

cat <<VORWORT

  OPERA XRechnung - Einrichtung (Rocky Linux 9/10)
  Zielordner: $BASIS

  Folgendes ist vorgesehen. Jeder Punkt wird einzeln angesagt und muss
  bestaetigt werden - Ablehnen ueberspringt nur diesen Punkt:

    1. Python 3.12                aus den Rocky-Paketquellen (dnf), falls noetig
    2. Java (JRE 11/17/21)        aus den Rocky-Paketquellen (dnf), falls noetig
    3. Python-Bausteine           von pypi.org
    4. KoSIT-Pruefprogramm        von github.com/itplr-kosit
    5. Konfigurationsvorlage      oertlich, kein Download
    6. systemd-Dienst             oertlich, kein Download
    7. Firewall-Freigabe Port $PORT  oertlich, kein Download

VORWORT
if [[ $OHNE_RUECKFRAGE -eq 1 ]]; then
    echo "  Alle Rueckfragen sind abgeschaltet (--ohne-rueckfrage)."
    echo
fi

# ---------------------------------------------------------------- 1. Python
titel "Python"
PY=""
for kandidat in python3.12 python3.11 python3; do
    if command -v "$kandidat" >/dev/null 2>&1; then
        v=$("$kandidat" -c 'import sys; print(sys.version_info[0]*100+sys.version_info[1])' 2>/dev/null || echo 0)
        if [[ "$v" -ge 311 ]]; then PY="$kandidat"; gut "$($kandidat --version) ist bereits vorhanden"; break; fi
        info "$($kandidat --version) ist zu alt (gebraucht wird 3.11 oder neuer)"
    fi
done
if [[ -z "$PY" ]]; then
    ansage "Python 3.12 installieren" "Rocky-Paketquellen (dnf)" "die Anwendung ist in Python geschrieben"
    if frage; then
        dnf install -y python3.12 python3.12-pip
        command -v python3.12 >/dev/null 2>&1 && PY=python3.12 && gut "Python 3.12 installiert"
    else
        uebergangen "Python - ohne Python laeuft nichts. Nachholen: sudo dnf install python3.12 python3.12-pip"
    fi
fi
if [[ -z "$PY" ]]; then
    schlecht "Ohne Python 3.11 oder neuer geht es nicht weiter."
    exit 1
fi

# ------------------------------------------------------------------ 2. Java
titel "Java (fuer die Rechnungspruefung)"
if command -v java >/dev/null 2>&1 && java -version >/dev/null 2>&1; then
    gut "$(java -version 2>&1 | head -1)"
else
    ansage "Java (JRE ohne Oberflaeche) installieren" "Rocky-Paketquellen (dnf)" \
           "das KoSIT-Pruefprogramm ist ein Java-Programm; 11, 17 und 21 gehen alle"
    if frage; then
        # Paketnamen unterscheiden sich zwischen Rocky 9 und 10 - der Reihe nach
        # probieren, das erste vorhandene genuegt.
        # Rocky 10 fuehrt nur noch 21 und 25, Rocky 9 auch 17 und 11.
        # Reihenfolge: LTS 21 zuerst, dann 25 als Rueckfall auf Rocky 10,
        # danach die aelteren fuer Rocky 9.
        for paket in java-21-openjdk-headless java-25-openjdk-headless \
                     java-17-openjdk-headless java-11-openjdk-headless; do
            info "versuche $paket"
            if dnf install -y "$paket" >/dev/null 2>&1 && java -version >/dev/null 2>&1; then
                break
            fi
        done
        if java -version >/dev/null 2>&1; then gut "$(java -version 2>&1 | head -1)"
        else schlecht "Java liess sich nicht einrichten. Ohne Java laeuft nur die Rechnungspruefung nicht, alles andere schon. Von Hand: dnf search openjdk"; fi
    else
        uebergangen "Java - die Rechnungspruefung bleibt aus. Nachholen: sudo dnf install java-21-openjdk-headless (oder 17)"
    fi
fi

# ------------------------------------------------- 3. Programmumgebung anlegen
titel "Programmumgebung"
VENVPY="$BASIS/.venv/bin/python"
ansage "Python-Bausteine laden ($(grep -c . "$BASIS/requirements.txt") Pakete: FastAPI, uvicorn, oracledb, lxml ...)" \
       "pypi.org" "Webserver, Oracle-Zugriff und XML-Verarbeitung"
if frage; then
    # venv bringt sein eigenes pip mit (ensurepip) — ein systemweites
    # python3-pip wird NICHT gebraucht. Auf einer Minimalinstallation fehlt es
    # oft, das ist in Ordnung.
    [[ -x "$VENVPY" ]] || "$PY" -m venv "$BASIS/.venv"
    if [[ ! -x "$VENVPY" ]]; then
        schlecht "Die Umgebung liess sich nicht anlegen. Fehlt das venv-Modul? Pruefen mit: $PY -m venv --help"
        exit 1
    fi
    if ! "$VENVPY" -m pip --version >/dev/null 2>&1; then
        info "pip fehlt in der Umgebung, wird nachgeholt (ensurepip)"
        "$VENVPY" -m ensurepip --upgrade >/dev/null 2>&1
    fi
    if ! "$VENVPY" -m pip --version >/dev/null 2>&1; then
        schlecht "In der Umgebung gibt es kein pip. Nachholen: $PY -m ensurepip oder sudo dnf install python3-pip"
        exit 1
    fi
    "$VENVPY" -m pip install --upgrade pip --quiet
    if "$VENVPY" -m pip install -r "$BASIS/requirements.txt" --quiet; then
        gut "Bausteine geladen"
    else
        schlecht "Die Bausteine liessen sich nicht laden - Internetzugang oder Proxy pruefen."
    fi
else
    uebergangen "Python-Bausteine - ohne sie startet die Anwendung nicht. Nachholen: .venv/bin/pip install -r requirements.txt"
fi

# ------------------------------------------------------------- 4. Pruefprogramm
titel "KoSIT-Pruefprogramm"
VALID="$BASIS/validation"
mkdir -p "$VALID"
if [[ $OHNE_PRUEFER -eq 1 ]]; then
    uebergangen "KoSIT-Pruefprogramm (--ohne-pruefer)"
elif [[ -f "$VALID/validationtool.jar" ]]; then
    gut "Pruefprogramm liegt bereits vor"
elif ! command -v curl >/dev/null 2>&1; then
    schlecht "curl fehlt ('sudo dnf install curl'), Pruefprogramm nicht geladen."
else
    ansage "KoSIT-Validator und die deutschen Pruefregeln laden (zusammen etwa 60 MB)" \
           "github.com/itplr-kosit (validator + validator-configuration-xrechnung)" \
           "prueft jede erzeugte Rechnung, bevor sie hinausgeht - laeuft nur oertlich"
    if frage; then
        tmp=$(mktemp -d)
        hole_asset() {   # $1 = Repository, $2 = Namensmuster
            curl -sS -H 'User-Agent: OPERA-XRechnung' \
                 "https://api.github.com/repos/$1/releases/latest" |
            "$PY" -c "
import json,sys,fnmatch
try: d=json.load(sys.stdin)
except Exception: sys.exit(0)
for a in d.get('assets',[]):
    if fnmatch.fnmatch(a['name'], '$2'):
        print(a['browser_download_url']); break
"
        }
        # Seit v1.6.x liegt die standalone.jar direkt als Release-Datei bei;
        # frueher steckte sie in einem distribution.zip. Erst das Einfache
        # versuchen, dann die Zip-Varianten.
        url=$(hole_asset "itplr-kosit/validator" "*standalone.jar")
        if [[ -n "$url" ]]; then
            info "lade $(basename "$url")"
            if curl -sSL "$url" -o "$VALID/validationtool.jar"; then
                gut "Pruefprogramm eingerichtet ($(basename "$url"))"
            else schlecht "Pruefprogramm konnte nicht geladen werden."; fi
        else
            for muster in "*distribution.zip" "validator-*.zip" "*.zip"; do
                url=$(hole_asset "itplr-kosit/validator" "$muster")
                [[ -n "$url" ]] && break
            done
            if [[ -n "$url" ]]; then
                info "lade $(basename "$url")"
                if curl -sSL "$url" -o "$tmp/validator.zip"; then
                    "$PY" -c "import zipfile; zipfile.ZipFile('$tmp/validator.zip').extractall('$tmp/v')"
                    jar=$(find "$tmp/v" -name '*standalone.jar' | head -1)
                    if [[ -n "$jar" ]]; then cp "$jar" "$VALID/validationtool.jar"; gut "Pruefprogramm eingerichtet"
                    else schlecht "Im Paket ist keine standalone.jar enthalten."; fi
                else schlecht "Pruefprogramm konnte nicht geladen werden."; fi
            else schlecht "Auf GitHub war weder eine standalone.jar noch ein Zip zu finden."; fi
        fi

        url=$(hole_asset "itplr-kosit/validator-configuration-xrechnung" "*.zip")
        if [[ -n "$url" ]]; then
            info "lade $(basename "$url")"
            if curl -sSL "$url" -o "$tmp/regeln.zip"; then
                mkdir -p "$VALID/xrechnung-3.0.2"
                "$PY" -c "import zipfile; zipfile.ZipFile('$tmp/regeln.zip').extractall('$VALID/xrechnung-3.0.2')"
                sz=$(find "$VALID/xrechnung-3.0.2" -name scenarios.xml | head -1)
                if [[ -n "$sz" ]]; then
                    [[ "$(dirname "$sz")" != "$VALID/xrechnung-3.0.2" ]] && cp -r "$(dirname "$sz")"/* "$VALID/xrechnung-3.0.2/"
                    gut "Pruefregeln eingerichtet"
                else schlecht "Im Regelpaket wurde keine scenarios.xml gefunden."; fi
            else schlecht "Pruefregeln konnten nicht geladen werden."; fi
        else schlecht "Auf GitHub war kein Regelpaket zu finden."; fi
        rm -rf "$tmp"
    else
        uebergangen "KoSIT-Pruefprogramm - Anleitung unter Handbuch, Abschnitt 'Der Weg von Hand'"
    fi
fi

# ------------------------------------------------------------ 5. Konfiguration
titel "Konfiguration"
mkdir -p "$BASIS/config" "$BASIS/data/xml" "$BASIS/data/archiv" "$BASIS/logs"
if [[ -f "$BASIS/config/app.json" ]]; then
    gut "vorhandene Konfiguration bleibt unveraendert"
else
    cp "$BASIS/config/app.example.json" "$BASIS/config/app.json"
    gut "aus der Vorlage angelegt - Werte spaeter in der Oberflaeche eintragen"
fi

# ------------------------------------------------------------------ 6. Dienst
titel "systemd-Dienst"
if [[ $OHNE_DIENST -eq 1 ]]; then
    uebergangen "systemd-Dienst (--ohne-dienst). Start von Hand ueber ./run.sh"
else
    ansage "Dienstkonto '$DIENSTBENUTZER' anlegen und Dienst 'xrechnung' einrichten" "" \
           "die Anwendung laeuft dann im Hintergrund und startet beim Hochfahren mit"
    if frage; then
        if ! id "$DIENSTBENUTZER" >/dev/null 2>&1; then
            useradd --system --home-dir "$BASIS" --shell /sbin/nologin "$DIENSTBENUTZER"
            info "Dienstkonto '$DIENSTBENUTZER' angelegt"
        fi
        chown -R "$DIENSTBENUTZER":"$DIENSTBENUTZER" "$BASIS/config" "$BASIS/data" "$BASIS/logs"
        chmod 700 "$BASIS/config"
        # Die venv gehoert dem Dienst: Bei einer Aktualisierung mit neuen
        # Abhaengigkeiten muss pip dort schreiben duerfen, ohne root.
        [[ -d "$BASIS/.venv" ]] && chown -R "$DIENSTBENUTZER":"$DIENSTBENUTZER" "$BASIS/.venv"
        # Repository und Zweig gehen in die Unit, nicht nur in config/app.json.
        # Die Unit gehoert root; app.json gehoert dem Dienst. Wer den Dienst
        # uebernimmt, soll ihn nicht auf ein fremdes Repository richten koennen.
        # '|| true' gehoert NICHT in die Substitution mit Heredoc — siehe
        # umstellen_freigaben.sh. Hier liefe es, aber die sichere Form ist
        # dieselbe Zeilenzahl.
        REPO_VORGABE="$(python3 - "$BASIS/config/app.example.json" <<'PYQ' 2>/dev/null
import json, sys
print((json.load(open(sys.argv[1])).get("update") or {}).get("repo", ""))
PYQ
        )" || REPO_VORGABE=""
        # Die Unit kommt aus unit_erzeugen.sh: Es kennt beide Aufbauten —
        # flach und mit Freigaben — und ersetzt ALLE Platzhalter. Vorher
        # schrieb diese Stelle die Vorlage mit WorkingDirectory=programm/aktuell
        # auch dann, wenn das Programm noch flach lag; der Dienst startete
        # dann nicht, und die Meldung sagte nur "Der Dienst startet nicht".
        "$BASIS/install/unit_erzeugen.sh" --basis "$BASIS" --benutzer "$DIENSTBENUTZER" \
            --port "$PORT" --repo "${REPO_VORGABE}" --zweig main \
            > /etc/systemd/system/xrechnung.service
        systemctl daemon-reload
        systemctl enable --now xrechnung >/dev/null 2>&1
        sleep 3
        if systemctl is-active --quiet xrechnung; then
            gut "Dienst 'xrechnung' laeuft und startet beim Hochfahren mit"
        else
            schlecht "Der Dienst startet nicht. Ursache: journalctl -u xrechnung -n 50"
        fi
    else
        uebergangen "systemd-Dienst - Start von Hand ueber ./run.sh, Nachholen: sudo ./install/dienst_einrichten.sh"
    fi
fi

# Die Unit-Vorlage erwartet das Programm unter programm/aktuell. Bei einer
# frischen Installation aus dem Archiv liegt es noch flach — dann steht die
# Umstellung als eigener Schritt an, damit sie sichtbar bleibt und einzeln
# zurueckgenommen werden kann.
if [[ $OHNE_DIENST -ne 1 ]] && [[ ! -L "$BASIS/programm/aktuell" ]]; then
    titel "Freigabeverzeichnisse"
    ansage "Programm nach programm/freigaben/ umstellen" "" \
           "erst damit kann sich die Anwendung selbst aktualisieren und zurueckgehen"
    if frage; then
        "$BASIS/install/umstellen_freigaben.sh" --basis "$BASIS" \
            --benutzer "$DIENSTBENUTZER" --port "$PORT" --ja \
            && gut "Umstellung abgeschlossen" \
            || schlecht "Umstellung fehlgeschlagen - siehe Meldungen oben"
    else
        uebergangen "Freigabeverzeichnisse - Nachholen: sudo ./install/umstellen_freigaben.sh"
    fi
fi

# ---------------------------------------------------------------- 7. Firewall
titel "Firewall"
if command -v firewall-cmd >/dev/null 2>&1 && systemctl is-active --quiet firewalld; then
    ansage "Port $PORT/tcp dauerhaft freigeben" "" \
           "sonst ist die Oberflaeche nur auf diesem Rechner erreichbar"
    if frage; then
        firewall-cmd --permanent --add-port="$PORT"/tcp >/dev/null 2>&1
        firewall-cmd --reload >/dev/null 2>&1
        gut "Port $PORT im lokalen Netz freigegeben"
    else
        uebergangen "Firewall-Freigabe - Nachholen: sudo firewall-cmd --permanent --add-port=$PORT/tcp && sudo firewall-cmd --reload"
    fi
else
    info "firewalld laeuft nicht - keine Regel noetig"
fi

# --------------------------------------------------------------- 8. Erreichbar?
titel "Erreichbarkeit"
if [[ $OHNE_DIENST -eq 1 ]] || ! systemctl is-active --quiet xrechnung 2>/dev/null; then
    info "Kein laufender Dienst - bitte ./run.sh starten."
elif curl -sS --max-time 20 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    gut "Die Anwendung antwortet"
else
    schlecht "Die Anwendung antwortet noch nicht. Ursache: journalctl -u xrechnung -n 50"
fi

# ----------------------------------------------------------------- Abschluss
echo
echo "  --------------------------------------------------"
if [[ ${#FEHLER[@]} -eq 0 && ${#UEBERSPRUNGEN[@]} -eq 0 ]]; then
    printf '  %sEinrichtung abgeschlossen.%s\n' "$gruen" "$normal"
else
    printf '  %sEinrichtung abgeschlossen.%s\n' "$gruen" "$normal"
    if [[ ${#UEBERSPRUNGEN[@]} -gt 0 ]]; then
        echo
        echo "  Uebersprungen:"
        for f in "${UEBERSPRUNGEN[@]}"; do echo "    - $f"; done
    fi
    if [[ ${#FEHLER[@]} -gt 0 ]]; then
        echo
        printf '  %sOffen:%s\n' "$rot" "$normal"
        for f in "${FEHLER[@]}"; do echo "    - $f"; done
    fi
fi
echo
echo "  Oberflaeche:  http://$(hostname):$PORT/"
echo "                (am Server auch http://localhost:$PORT/)"
echo
if [[ -f "$BASIS/config/ERSTES_PASSWORT.txt" ]]; then
    echo "  Erste Anmeldung:"
    sed 's/^/    /' "$BASIS/config/ERSTES_PASSWORT.txt"
else
    echo "  Erste Anmeldung: Benutzer und Startpasswort stehen nach dem ersten"
    echo "  Start in config/ERSTES_PASSWORT.txt."
fi
echo
echo "  Danach: Passwort aendern (Menue 'Benutzer'), dann unter"
echo "  'Konfiguration' Datenbank, Haus und Mailversand eintragen."
echo "  Das Handbuch steht in der Oberflaeche unter 'Handbuch'."
echo
