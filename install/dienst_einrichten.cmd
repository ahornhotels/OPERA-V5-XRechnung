@echo off
REM Richtet nur den Windows-Dienst ein - fuer den Fall, dass die uebrige
REM Einrichtung schon steht. Der volle Weg ist INSTALLIEREN.cmd.
setlocal
cd /d "%~dp0.."
set DIENST=OperaXRechnung
set PORT=8022
REM Name und Port dieser Installation, vom Installer gemerkt
if exist "config\instanz.cmd" call "config\instanz.cmd"
set "ANZEIGE=OPERA XRechnung"
if defined INSTANZ set "ANZEIGE=OPERA XRechnung %INSTANZ%"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Bitte mit Rechtsklick als Administrator ausfuehren.
    pause & exit /b 1
)
if not exist "install\nssm.exe" (
    echo nssm.exe fehlt. Von https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip laden, entpacken und
    echo aus dem Ordner win64 die Datei nssm.exe nach install\ kopieren.
    echo Liefert nssm.cc Fehler 503, dieselbe Datei hier laden:
    echo https://web.archive.org/web/2024id_/https://nssm.cc/ci/nssm-2.24-101-g897c7ad.zip
    pause & exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Die Programmumgebung fehlt. Bitte zuerst INSTALLIEREN.cmd ausfuehren.
    pause & exit /b 1
)

REM Gehoert der Dienst einer ANDEREN Installation auf diesem Rechner, wird er
REM nicht angefasst. Erkannt am Programmpfad des Dienstes: Es muss die
REM nssm.exe dieses Ordners sein.
sc query %DIENST% >nul 2>&1
if not errorlevel 1 (
    sc qc %DIENST% | find /i "%CD%\install\nssm.exe" >nul
    if errorlevel 1 (
        echo Den Dienst %DIENST% gibt es schon, er gehoert aber zu einer anderen
        echo Installation auf diesem Rechner. Hier wurde nichts geaendert.
        echo Fuer eine weitere Installation: install\installieren.ps1 -Instanz NORD -Port 8023
        pause & exit /b 1
    )
)

install\nssm.exe stop %DIENST% 2>nul
install\nssm.exe remove %DIENST% confirm 2>nul
install\nssm.exe install %DIENST% "%CD%\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port %PORT%"
install\nssm.exe set %DIENST% AppDirectory "%CD%"
install\nssm.exe set %DIENST% DisplayName "%ANZEIGE%"
install\nssm.exe set %DIENST% Description "Erzeugt XRechnungen aus OPERA und versendet sie"
install\nssm.exe set %DIENST% Start SERVICE_AUTO_START
install\nssm.exe set %DIENST% AppStdout "%CD%\logs\dienst.log"
install\nssm.exe set %DIENST% AppStderr "%CD%\logs\dienst.log"
install\nssm.exe set %DIENST% AppRotateFiles 1
netsh advfirewall firewall add rule name="OPERA XRechnung %PORT%" dir=in action=allow protocol=TCP localport=%PORT%
install\nssm.exe start %DIENST%

echo.
echo Dienst eingerichtet. Oberflaeche: http://%COMPUTERNAME%:%PORT%/
pause
endlocal
