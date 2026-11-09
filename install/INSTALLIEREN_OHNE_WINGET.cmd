@echo off
REM Wie INSTALLIEREN.cmd, aber ohne winget: Python kommt direkt als
REM Installer von python.org, dessen Signatur vor dem Start geprueft wird.
REM Fuer aeltere Windows ohne winget (Server 2012 R2/2016/2019, Windows 8.1,
REM Windows 10 LTSC) und fuer Rechner, auf denen winget gesperrt ist oder
REM haengt. INSTALLIEREN.cmd nimmt diesen Weg ohnehin, wenn winget fehlt.
cd /d "%~dp0"

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administratorrechte werden angefordert...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0installieren.ps1" -OhneWinget
pause
