@echo off
REM Entfernt den Windows-Dienst. Programm, Konfiguration und Daten bleiben.
setlocal
cd /d "%~dp0.."
set DIENST=OperaXRechnung
set PORT=8022
if exist "config\instanz.cmd" call "config\instanz.cmd"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Bitte mit Rechtsklick als Administrator ausfuehren.
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
if exist "install\nssm.exe" (
    install\nssm.exe stop %DIENST%
    install\nssm.exe remove %DIENST% confirm
) else (
    sc stop %DIENST%
    sc delete %DIENST%
)
netsh advfirewall firewall delete rule name="OPERA XRechnung %PORT%"
echo.
echo Dienst entfernt. Konfiguration unter config\ und Daten unter data\ sind unberuehrt.
pause
endlocal
