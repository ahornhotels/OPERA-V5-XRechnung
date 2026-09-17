# Installiert OPERA XRechnung auf einem Windows-Rechner.
# Liegt im Ordner install\ und wird ueber INSTALLIEREN.cmd aufgerufen,
# das die Administratorrechte anfordert.
#
# Jeder Schritt, der etwas aus dem Internet laedt oder am System aendert, wird
# vorher angesagt und muss bestaetigt werden. Wer ablehnt, ueberspringt nur
# diesen Schritt - am Ende steht, was offen blieb und wie es nachzuholen ist.
#
#   -OhneRueckfrage  alles ohne Nachfrage (fuer unbeaufsichtigte Laeufe)
#   -OhneDienst      keinen Windows-Dienst anlegen
#   -OhnePruefer     KoSIT-Pruefprogramm nicht herunterladen
#   -Port 8022       abweichender Port

param(
    [switch]$OhneRueckfrage,
    [switch]$OhneDienst,
    [switch]$OhnePruefer,
    [int]$Port = 8022
)

$ErrorActionPreference = "Stop"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$Basis = Split-Path -Parent $PSScriptRoot
$Fehler = @()
$Uebersprungen = @()
$Schritt = 0

function Titel($text) {
    $script:Schritt++
    Write-Host ""
    Write-Host "== Schritt $script:Schritt - $text" -ForegroundColor Cyan
}
function Gut($text)  { Write-Host "   [ok]   $text" -ForegroundColor Green }
function Info($text) { Write-Host "          $text" -ForegroundColor Gray }
function Schlecht($text) {
    Write-Host "   [!]    $text" -ForegroundColor Yellow
    $script:Fehler += $text
}
function Uebergangen($text) {
    Write-Host "   [--]   uebersprungen" -ForegroundColor Gray
    $script:Uebersprungen += $text
}
function Vorhanden($befehl) { $null -ne (Get-Command $befehl -ErrorAction SilentlyContinue) }

# Ruft ein externes Programm auf: Nativ <programm> <argumente...>
# Gibt stdout UND stderr als Textzeilen zurueck; der Rueckgabewert des
# Programms steht danach in $script:NativCode.
#
# Warum nicht einfach '& programm 2>&1' oder '2>$null': Unter Windows
# PowerShell 5.1 — der, die INSTALLIEREN.cmd startet — wird jede UMGELEITETE
# stderr-Zeile eines externen Programms zu einem Fehlerdatensatz
# (NativeCommandError). Mit $ErrorActionPreference = "Stop" bricht das Skript
# daran ab, obwohl das Programm nur etwas mitteilen wollte. 'java -version'
# schreibt IMMER nach stderr; 'nssm stop' bei einem Dienst, den es noch nicht
# gibt, ebenso. Der Installer brach so auf jedem Rechner ab, auf dem Java schon
# lag, und bei jeder Ersteinrichtung vor dem Anlegen des Dienstes. PowerShell 7
# verhaelt sich anders — auf einem Entwicklungsrechner faellt es nicht auf.
#
# Innerhalb der Funktion gilt "Continue" nur fuer diesen einen Aufruf.
# Entschieden wird ueber den Rueckgabewert, nicht darueber, ob stderr etwas
# enthielt. Eine einfache Funktion mit $args, kein param()-Block: Sonst hielte
# PowerShell '-version' fuer einen Parameter von Nativ statt von java.
function Nativ {
    $ErrorActionPreference = "Continue"
    $programm = $args[0]
    $argumente = @($args | Select-Object -Skip 1)
    $script:NativCode = -1
    $ausgabe = @(& $programm @argumente 2>&1 | ForEach-Object { "$_" })
    $script:NativCode = $LASTEXITCODE
    return $ausgabe
}

# Den Suchpfad aus der Registry neu lesen. Ein Installer (winget, MSI) traegt
# sich dort ein — in DIESEM Prozess kommt davon nichts an. Beide Teile,
# Maschine UND Benutzer: Vorher las der Java-Schritt nur den Maschinenteil und
# warf damit alles weg, was im Benutzerpfad stand, unter anderem den
# Python-Starter einer Benutzerinstallation.
function PfadNeuLaden {
    $maschine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $benutzer = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = (@($maschine, $benutzer) | Where-Object { $_ }) -join ";"
}

# Sagt an, was passieren soll: Was, woher, wozu.
function Ansage($was, $quelle, $zweck) {
    Write-Host "   ->     $was" -ForegroundColor White
    if ($quelle) { Write-Host "          Quelle: $quelle" -ForegroundColor Gray }
    if ($zweck)  { Write-Host "          Zweck:  $zweck"  -ForegroundColor Gray }
}

# Rueckfrage. Enter bedeutet Ja.
# Laesst sich nicht lesen - etwa weil das Fenster ohne Konsole laeuft -, gilt
# das als Nein. Sonst wuerde ein Lauf ohne Eingabemoeglichkeit stillschweigend
# jeden Download bestaetigen.
function Frage {
    if ($OhneRueckfrage) {
        Write-Host "          (ohne Rueckfrage bestaetigt)" -ForegroundColor Gray
        return $true
    }
    if (-not [Environment]::UserInteractive) {
        Schlecht "Keine Eingabe moeglich. Fuer unbeaufsichtigte Laeufe -OhneRueckfrage angeben."
        return $false
    }
    try   { $antwort = Read-Host "          Fortfahren? [J/n]" }
    catch { Schlecht "Keine Eingabe moeglich. Fuer unbeaufsichtigte Laeufe -OhneRueckfrage angeben."; return $false }
    return ($antwort -eq "" -or $antwort -match '^[jJyY]')
}

function Laden($url, $ziel) {
    Info "lade $([IO.Path]::GetFileName($ziel)) ..."
    $alt = $ProgressPreference
    $ProgressPreference = "SilentlyContinue"
    try   { Invoke-WebRequest -Uri $url -OutFile $ziel -UseBasicParsing -TimeoutSec 300 }
    finally { $ProgressPreference = $alt }
}

function LetztesRelease($repo, $muster) {
    $daten = Invoke-RestMethod -Uri "https://api.github.com/repos/$repo/releases/latest" `
                               -Headers @{ "User-Agent" = "OPERA-XRechnung" } -TimeoutSec 60
    $treffer = $daten.assets | Where-Object { $_.name -like $muster } | Select-Object -First 1
    if (-not $treffer) { throw "Im Release $($daten.tag_name) von $repo gibt es keine Datei $muster" }
    return $treffer
}

Write-Host ""
Write-Host "  OPERA XRechnung - Einrichtung (Windows)" -ForegroundColor White
Write-Host "  Zielordner: $Basis"
Write-Host ""
Write-Host "  Folgendes ist vorgesehen. Jeder Punkt wird einzeln angesagt und muss"
Write-Host "  bestaetigt werden - Ablehnen ueberspringt nur diesen Punkt:"
Write-Host ""
Write-Host "    1. Python 3.12                ueber winget von python.org"
Write-Host "    2. Java 21 (JRE)              ueber winget von adoptium.net"
Write-Host "    3. Python-Bausteine           von pypi.org"
Write-Host "    4. KoSIT-Pruefprogramm        von github.com/itplr-kosit"
Write-Host "    5. Konfigurationsvorlage      oertlich, kein Download"
Write-Host "    6. NSSM und Windows-Dienst    nssm.cc, dann oertlich"
Write-Host "    7. Firewall-Freigabe Port $Port  oertlich, kein Download"
Write-Host ""
if ($OhneRueckfrage) {
    Write-Host "  Alle Rueckfragen sind abgeschaltet (-OhneRueckfrage)."
    Write-Host ""
}

# ---------------------------------------------------------------- 1. Python
Titel "Python"
$Python = $null
foreach ($kandidat in @("py", "python")) {
    if (Vorhanden $kandidat) {
            try {
                $version = (Nativ $kandidat --version) -join " "
                if ($version -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 11) {
                    $Python = $kandidat; Gut "$version gefunden"; break
                } else { Info "$version ist zu alt (gebraucht wird 3.11 oder neuer)" }
            } catch { }
        }
    }
    if (-not $Python) {
        if (Vorhanden "winget") {
            Ansage "Python 3.12 installieren (dauert einige Minuten)" "winget, Quelle python.org" `
                   "die Anwendung ist in Python geschrieben"
            if (Frage) {
                $null = Nativ winget install --id Python.Python.3.12 --silent --accept-package-agreements `
                       --accept-source-agreements --scope machine
                if ($script:NativCode -ne 0) { Info "winget meldet Rueckgabewert $script:NativCode" }
                PfadNeuLaden
                if (Vorhanden "py") { $Python = "py"; Gut "Python installiert" }
            } else {
                Uebergangen "Python - ohne Python laeuft nichts. Nachholen: https://www.python.org/downloads/windows/ (Haken bei 'Add python.exe to PATH')"
            }
        } else {
            Info "winget ist nicht vorhanden - Python muss von Hand installiert werden"
        }
    }
    if (-not $Python) {
        Schlecht "Ohne Python 3.11 oder neuer geht es nicht weiter. Von https://www.python.org/downloads/windows/ installieren - Haken bei 'Add python.exe to PATH' setzen - und erneut starten."
        Write-Host ""; exit 1
    }

    # ------------------------------------------------------------------ 2. Java
    Titel "Java (fuer die Rechnungspruefung)"
    if (Vorhanden "java") {
        Gut ((Nativ java -version) | Select-Object -First 1)
    } elseif (Vorhanden "winget") {
        Ansage "Java 21 (JRE) installieren" "winget, Quelle adoptium.net" `
               "das KoSIT-Pruefprogramm ist ein Java-Programm"
        if (Frage) {
            $null = Nativ winget install --id EclipseAdoptium.Temurin.21.JRE --silent `
                   --accept-package-agreements --accept-source-agreements
            if ($script:NativCode -ne 0) { Info "winget meldet Rueckgabewert $script:NativCode" }
            PfadNeuLaden
            if (Vorhanden "java") { Gut "Java installiert" }
            else { Schlecht "Java wurde installiert, ist aber noch nicht im Suchpfad. Nach einem Neustart erneut pruefen." }
        } else {
            Uebergangen "Java - die Rechnungspruefung bleibt aus. Nachholen: https://adoptium.net/de/temurin/releases/ (JRE 21, Windows x64)"
        }
    } else {
        Schlecht "Java fehlt und winget ist nicht vorhanden. Von https://adoptium.net/de/temurin/releases/ die JRE 21 fuer Windows x64 installieren. Ohne Java laeuft nur die Rechnungspruefung nicht."
    }

    # ------------------------------------------------- 3. Programmumgebung anlegen
    Titel "Programmumgebung"
    $VenvPython = Join-Path $Basis ".venv\Scripts\python.exe"
    Ansage "Python-Bausteine laden (FastAPI, uvicorn, oracledb, lxml ...)" "pypi.org" `
           "Webserver, Oracle-Zugriff und XML-Verarbeitung"
    if (Frage) {
        if (-not (Test-Path $VenvPython)) {
            if ($Python -eq "py") { $null = Nativ $Python -3 -m venv (Join-Path $Basis ".venv") }
            if (-not (Test-Path $VenvPython)) { $null = Nativ $Python -m venv (Join-Path $Basis ".venv") }
        }
        if (-not (Test-Path $VenvPython)) { Schlecht "Die Umgebung liess sich nicht anlegen."; exit 1 }
        $null = Nativ $VenvPython -m pip install --upgrade pip --quiet
        $pipAusgabe = Nativ $VenvPython -m pip install -r (Join-Path $Basis "requirements.txt") --quiet
        if ($script:NativCode -ne 0) {
            Schlecht "Die Bausteine liessen sich nicht laden - Internetzugang pruefen."
            $pipAusgabe | Select-Object -Last 5 | ForEach-Object { Info $_ }
        }
        else { Gut "Bausteine geladen" }
    } else {
        Uebergangen "Python-Bausteine - ohne sie startet die Anwendung nicht. Nachholen: .venv\Scripts\pip install -r requirements.txt"
    }

    # ------------------------------------------------------------- 4. Pruefprogramm
    Titel "KoSIT-Pruefprogramm"
    $ValidOrdner = Join-Path $Basis "validation"
    New-Item -ItemType Directory -Force -Path $ValidOrdner | Out-Null
    $JarZiel = Join-Path $ValidOrdner "validationtool.jar"
    if ($OhnePruefer) {
        Uebergangen "KoSIT-Pruefprogramm (-OhnePruefer)"
    } elseif (Test-Path $JarZiel) {
        Gut "Pruefprogramm liegt bereits vor"
    } else {
        Ansage "KoSIT-Validator und die deutschen Pruefregeln laden (zusammen etwa 60 MB)" `
               "github.com/itplr-kosit (validator + validator-configuration-xrechnung)" `
               "prueft jede erzeugte Rechnung, bevor sie hinausgeht - laeuft nur oertlich"
        if (-not (Frage)) {
            Uebergangen "KoSIT-Pruefprogramm - Anleitung unter Handbuch, Abschnitt 'Der Weg von Hand'"
        } else {
            try {
                $tmp = Join-Path $env:TEMP ("xr-" + [Guid]::NewGuid().ToString("N"))
                New-Item -ItemType Directory -Force -Path $tmp | Out-Null

                # Seit v1.6.x liegt die standalone.jar direkt als Release-Datei
                # bei; frueher steckte sie in einem distribution.zip.
                $asset = $null
                foreach ($muster in @("*standalone.jar", "*distribution.zip", "validator-*.zip")) {
                    try { $asset = LetztesRelease "itplr-kosit/validator" $muster; break } catch { }
                }
                if (-not $asset) { throw "Im aktuellen Release ist weder eine standalone.jar noch ein Zip zu finden" }

                if ($asset.name -like "*.jar") {
                    Laden $asset.browser_download_url $JarZiel
                    Gut "Pruefprogramm eingerichtet ($($asset.name))"
                } else {
                    $zip = Join-Path $tmp "validator.zip"
                    Laden $asset.browser_download_url $zip
                    Expand-Archive -Path $zip -DestinationPath (Join-Path $tmp "validator") -Force
                    $jar = Get-ChildItem -Path (Join-Path $tmp "validator") -Filter "*standalone.jar" -Recurse |
                           Select-Object -First 1
                    if (-not $jar) { throw "Im Paket ist keine standalone.jar enthalten" }
                    Copy-Item $jar.FullName $JarZiel -Force
                    Gut "Pruefprogramm eingerichtet ($($asset.name))"
                }

                $conf = LetztesRelease "itplr-kosit/validator-configuration-xrechnung" "*.zip"
                $czip = Join-Path $tmp "konfiguration.zip"
                Laden $conf.browser_download_url $czip
                $regeln = Join-Path $ValidOrdner "xrechnung-3.0.2"
                New-Item -ItemType Directory -Force -Path $regeln | Out-Null
                Expand-Archive -Path $czip -DestinationPath $regeln -Force
                $szenarien = Get-ChildItem -Path $regeln -Filter "scenarios.xml" -Recurse | Select-Object -First 1
                if ($szenarien) {
                    if ($szenarien.DirectoryName -ne $regeln) {
                        Copy-Item (Join-Path $szenarien.DirectoryName "*") $regeln -Recurse -Force
                    }
                    Gut "Pruefregeln eingerichtet ($($conf.name))"
                } else {
                    Schlecht "Im Regelpaket wurde keine scenarios.xml gefunden - bitte von Hand ablegen."
                }
                Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
            } catch {
                Schlecht "Pruefprogramm konnte nicht geladen werden: $($_.Exception.Message)"
                Info "Nachholbar: Anleitung unter Handbuch -> Installation, 'Der Weg von Hand'."
            }
        }
}

# ------------------------------------------------------------ 5. Konfiguration
Titel "Konfiguration"
$ConfDatei = Join-Path $Basis "config\app.json"
if (Test-Path $ConfDatei) {
    Gut "vorhandene Konfiguration bleibt unveraendert"
} else {
    Copy-Item (Join-Path $Basis "config\app.example.json") $ConfDatei
    Gut "aus der Vorlage angelegt - Werte spaeter in der Oberflaeche eintragen"
}
foreach ($ordner in @("data", "logs", "data\xml", "data\archiv")) {
    New-Item -ItemType Directory -Force -Path (Join-Path $Basis $ordner) | Out-Null
}

# ------------------------------------------------------------ 5b. Ordnerrechte
# C:\XRechnung erbt seine Rechte von C:\. Dort duerfen "Benutzer" lesen und
# Ordner anlegen, auf Client-Windows auch aendern. Damit lagen offen:
#   - config\secret.key, app.json, ERSTES_PASSWORT.txt — der Schluessel und
#     die damit entschluesselbaren Zugangsdaten zu OPERA und zum Mailserver;
#   - .venv, app\, install\nssm.exe — Code, den der Dienst als LocalSystem
#     ausfuehrt. Wer dort schreiben kann, ist beim naechsten Neustart SYSTEM.
# Unter Linux regeln das Dienstkonto und chmod 700; unter Windows tat es
# niemand. Deshalb: Vererbung abschneiden, nur SYSTEM (der Dienst) und die
# Administratoren behalten Zugriff. Der Dienst braucht nichts weiter.
#
# Mit SIDs statt Namen: Auf einem deutschen Windows heisst die Gruppe
# "Administratoren", icacls mit "Administrators" liefe dort ins Leere.
# Die Reihenfolge ist Absicht — erst Eigentuemer, dann alles auf geerbt
# zuruecksetzen, dann die eigenen Eintraege setzen, ZULETZT die Vererbung
# kappen. Andersherum gaebe es einen Moment ohne jeden Zugriff, und ein
# Abbruch dort liesse einen Ordner zurueck, an den nur noch mit Besitzuebernahme
# heranzukommen ist. Jeder Lauf fuehrt zum selben Ergebnis.
Titel "Ordnerrechte"
Ansage "Zugriff auf $Basis auf SYSTEM und Administratoren beschraenken" "" `
       "Schluessel, Zugangsdaten und Programmdateien sind sonst fuer alle Benutzer lesbar bzw. aenderbar"
if (-not (Frage)) {
    Uebergangen "Ordnerrechte - $Basis bleibt fuer normale Benutzer lesbar. Nachholen: installieren.ps1 erneut ausfuehren"
} else {
    $sidSystem = "S-1-5-18"
    $sidAdmins = "S-1-5-32-544"
    # Der Eigentuemer hat IMMER das Recht, die Rechte zu aendern. Hat ein
    # normaler Benutzer den Ordner angelegt, koennte er sich den Zugriff
    # sonst einfach zurueckgeben.
    $adminName = (New-Object System.Security.Principal.SecurityIdentifier($sidAdmins)).Translate(
                 [System.Security.Principal.NTAccount]).Value
    $rechteFehler = @()
    $schritte = @(
        @($Basis, "/setowner", $adminName, "/T", "/C", "/Q"),
        @($Basis, "/reset", "/T", "/C", "/Q"),
        @($Basis, "/grant:r", "*$($sidSystem):(OI)(CI)F", "*$($sidAdmins):(OI)(CI)F", "/C", "/Q"),
        @($Basis, "/inheritance:r", "/C", "/Q")
    )
    foreach ($schritt in $schritte) {
        $icaclsAusgabe = Nativ icacls @schritt
        if ($script:NativCode -ne 0) {
            $rechteFehler += "icacls $($schritt[1]): $(($icaclsAusgabe | Select-Object -Last 2) -join ' ')"
        }
    }
    if ($rechteFehler.Count -eq 0) {
        Gut "Vererbung entfernt; Vollzugriff nur fuer SYSTEM und $adminName (Eigentuemer: $adminName)"
    } else {
        Schlecht "Ordnerrechte nicht vollstaendig gesetzt: $($rechteFehler -join '; ')"
    }
    Info "Jetzt gilt fuer $($Basis):"
    Nativ icacls $Basis | Where-Object { $_ -and $_ -notmatch '^(Successfully|Erfolgreich)' } |
        ForEach-Object { Info "  $($_.Trim())" }
    Info "run.cmd von Hand geht damit nur noch in einer Eingabeaufforderung als Administrator."
}

# ------------------------------------------------------------------ 6. Dienst
Titel "Windows-Dienst"
$Dienst = "OperaXRechnung"
if ($OhneDienst) {
    Uebergangen "Windows-Dienst (-OhneDienst). Start von Hand ueber run.cmd"
} else {
    $nssm = Join-Path $Basis "install\nssm.exe"
    if (-not (Test-Path $nssm) -and (Test-Path (Join-Path $Basis "nssm.exe"))) {
        Move-Item (Join-Path $Basis "nssm.exe") $nssm -Force
    }
    if (-not (Test-Path $nssm)) {
        Ansage "NSSM laden (etwa 350 KB)" "nssm.cc" `
               "damit die Anwendung als Windows-Dienst laeuft und beim Hochfahren mitstartet"
        if (-not (Frage)) {
            Uebergangen "NSSM - ohne das Werkzeug kein Dienst. Start bis dahin ueber run.cmd"
        } else {
            try {
                $tmp = Join-Path $env:TEMP ("nssm-" + [Guid]::NewGuid().ToString("N"))
                New-Item -ItemType Directory -Force -Path $tmp | Out-Null
                Laden "https://nssm.cc/release/nssm-2.24.zip" (Join-Path $tmp "nssm.zip")
                Expand-Archive -Path (Join-Path $tmp "nssm.zip") -DestinationPath $tmp -Force
                $gefunden = Get-ChildItem -Path $tmp -Filter "nssm.exe" -Recurse |
                            Where-Object { $_.DirectoryName -like "*win64*" } | Select-Object -First 1
                if ($gefunden) { Copy-Item $gefunden.FullName $nssm -Force }
                Remove-Item $tmp -Recurse -Force -ErrorAction SilentlyContinue
            } catch {
                Schlecht "nssm.exe konnte nicht geladen werden: $($_.Exception.Message)"
            }
        }
    }
    if (Test-Path $nssm) {
        Ansage "Dienst 'OperaXRechnung' einrichten und starten" "" `
               "die Anwendung laeuft dann im Hintergrund und startet beim Hochfahren mit"
        if (-not (Frage)) {
            Uebergangen "Windows-Dienst - Nachholen: install\dienst_einrichten.cmd als Administrator"
        } else {
            # stop/remove scheitern bei einer Ersteinrichtung erwartungsgemaess —
            # den Dienst gibt es noch nicht. Ihr Rueckgabewert zaehlt nicht.
            $null = Nativ $nssm stop $Dienst
            $null = Nativ $nssm remove $Dienst confirm
            $schritte = @(
                @("install", $Dienst, $VenvPython, "-m uvicorn app.main:app --host 0.0.0.0 --port $Port"),
                @("set", $Dienst, "AppDirectory", $Basis),
                @("set", $Dienst, "DisplayName", "OPERA XRechnung"),
                @("set", $Dienst, "Description", "Erzeugt XRechnungen aus OPERA und versendet sie"),
                @("set", $Dienst, "Start", "SERVICE_AUTO_START"),
                @("set", $Dienst, "AppStdout", (Join-Path $Basis "logs\dienst.log")),
                @("set", $Dienst, "AppStderr", (Join-Path $Basis "logs\dienst.log")),
                @("set", $Dienst, "AppRotateFiles", "1"),
                @("start", $Dienst)
            )
            $gescheitert = @()
            foreach ($schritt in $schritte) {
                $null = Nativ $nssm @schritt
                if ($script:NativCode -ne 0) { $gescheitert += "nssm $($schritt[0]) $($schritt[2]) (Rueckgabewert $script:NativCode)" }
            }
            if ($gescheitert.Count -eq 0) {
                Gut "Dienst '$Dienst' eingerichtet und gestartet"
            } else {
                Schlecht "Dienst '$Dienst' nicht vollstaendig eingerichtet: $($gescheitert -join '; ')"
            }
        }
    } else {
        Info "Ohne nssm.exe kein Dienst. Start bis dahin ueber run.cmd."
    }
}

# ---------------------------------------------------------------- 7. Firewall
Titel "Firewall"
$regel = "OPERA XRechnung $Port"
Ansage "Port $Port/tcp dauerhaft freigeben" "" `
       "sonst ist die Oberflaeche nur auf diesem Rechner erreichbar"
if (Frage) {
    # delete scheitert, wenn es die Regel noch nicht gibt — das ist der Normalfall.
    $null = Nativ netsh advfirewall firewall delete rule "name=$regel"
    $netshAusgabe = Nativ netsh advfirewall firewall add rule "name=$regel" dir=in action=allow protocol=TCP "localport=$Port"
    if ($script:NativCode -eq 0) { Gut "Port $Port im lokalen Netz freigegeben" }
    else { Schlecht "Firewall-Regel nicht angelegt: $($netshAusgabe -join ' ')" }
} else {
    Uebergangen "Firewall-Freigabe - Nachholen: netsh advfirewall firewall add rule name=`"$regel`" dir=in action=allow protocol=TCP localport=$Port"
}

# --------------------------------------------------------------- 8. Erreichbar?
Titel "Erreichbarkeit"
Start-Sleep -Seconds 4
try {
    $antwort = Invoke-WebRequest -Uri "http://127.0.0.1:$Port/health" -UseBasicParsing -TimeoutSec 20
    if ($antwort.StatusCode -eq 200) { Gut "Die Anwendung antwortet" }
} catch {
    if ($OhneDienst) { Info "Kein Dienst eingerichtet - bitte run.cmd starten." }
    else { Schlecht "Die Anwendung antwortet noch nicht. In logs\dienst.log steht der Grund." }
}

# ----------------------------------------------------------------- Abschluss
Write-Host ""
Write-Host "  --------------------------------------------------" -ForegroundColor White
Write-Host "  Einrichtung abgeschlossen." -ForegroundColor Green
if ($Uebersprungen.Count -gt 0) {
    Write-Host ""
    Write-Host "  Uebersprungen:"
    foreach ($f in $Uebersprungen) { Write-Host "    - $f" }
}
if ($Fehler.Count -gt 0) {
    Write-Host ""
    Write-Host "  Offen:" -ForegroundColor Yellow
    foreach ($f in $Fehler) { Write-Host "    - $f" -ForegroundColor Yellow }
}
Write-Host ""
Write-Host "  Oberflaeche:  http://$env:COMPUTERNAME`:$Port/"
Write-Host "                (am Server auch http://localhost:$Port/)"
Write-Host ""

$erst = Join-Path $Basis "config\ERSTES_PASSWORT.txt"
if (Test-Path $erst) {
    Write-Host "  Erste Anmeldung:" -ForegroundColor White
    Get-Content $erst | ForEach-Object { Write-Host "    $_" }
} else {
    Write-Host "  Erste Anmeldung: Benutzer und Startpasswort stehen nach dem ersten"
    Write-Host "  Start in config\ERSTES_PASSWORT.txt."
}
Write-Host ""
Write-Host "  Danach: Passwort aendern (Menue 'Benutzer'), dann unter"
Write-Host "  'Konfiguration' Datenbank, Haus und Mailversand eintragen."
Write-Host "  Das Handbuch steht in der Oberflaeche unter 'Handbuch'."
Write-Host ""
