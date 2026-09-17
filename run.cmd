@echo off
REM OPERA XRechnung - Start im Vordergrund (Entwicklung/Test)
setlocal
cd /d "%~dp0"
set "PROGRAMM=%CD%"
set "BASIS=%CD%"

rem Liegt dieses Skript in einer Freigabe (programm\freigaben\<stand>\), ist
rem die Installation drei Ebenen hoeher. Ohne diese Zeilen schreibt ein
rem Handstart Konfiguration und Rechnungen in die Freigabe, wo das Aufraeumen
rem sie spaeter entfernt. Unter Windows laeuft die Aktualisierung zwar an Ort
rem und Stelle — aber ein Verzeichnis, das von einem Linux-Server kopiert
rem wurde, kann trotzdem so aussehen.
echo %CD% | find "\programm\freigaben\" >nul
if not errorlevel 1 (
    for %%I in ("%CD%\..\..\..") do set "BASIS=%%~fI"
    call set "XRECHNUNG_BASIS=%%BASIS%%"
    call set "XRECHNUNG_CONFIG_DIR=%%BASIS%%\config"
    call set "XRECHNUNG_DATEN_DIR=%%BASIS%%\data"
    call set "XRECHNUNG_LOG_DIR=%%BASIS%%\logs"
    call echo Freigabenbetrieb erkannt. Bestand: %%BASIS%%
)

if not exist "%BASIS%\.venv\Scripts\python.exe" (
    echo Erstelle virtuelle Umgebung...
    py -3 -m venv "%BASIS%\.venv" || python -m venv "%BASIS%\.venv" || goto :fehler
    "%BASIS%\.venv\Scripts\python.exe" -m pip install --upgrade pip
    "%BASIS%\.venv\Scripts\python.exe" -m pip install -r requirements.txt || goto :fehler
)

if not exist "%BASIS%\config\app.json" (
    if not exist "%BASIS%\config" mkdir "%BASIS%\config"
    copy "%PROGRAMM%\config\app.example.json" "%BASIS%\config\app.json" >nul
    echo Konfiguration aus der Vorlage angelegt: %BASIS%\config\app.json
)

echo.
echo Oberflaeche:  http://%COMPUTERNAME%:8022/
echo Beenden mit Strg+C
echo.
"%BASIS%\.venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8022
goto :ende

:fehler
echo.
echo Start fehlgeschlagen. Ist Python 3.11 oder neuer installiert?
pause
:ende
endlocal
