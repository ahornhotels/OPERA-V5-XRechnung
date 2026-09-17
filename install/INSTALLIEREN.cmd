@echo off
REM Startet die Installation mit Administratorrechten.
REM Doppelklick genuegt - Windows fragt einmal nach der Erlaubnis.
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administratorrechte werden angefordert...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installieren.ps1"
pause
