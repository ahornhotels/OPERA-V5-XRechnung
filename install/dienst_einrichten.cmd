@echo off
REM Richtet nur den Windows-Dienst ein - fuer den Fall, dass die uebrige
REM Einrichtung schon steht. Der volle Weg ist INSTALLIEREN.cmd.
setlocal
cd /d "%~dp0.."
set DIENST=OperaXRechnung

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Bitte mit Rechtsklick als Administrator ausfuehren.
    pause & exit /b 1
)
if not exist "install\nssm.exe" (
    echo nssm.exe fehlt. Von https://nssm.cc/download laden, entpacken und
    echo aus dem Ordner win64 die Datei nssm.exe nach install\ kopieren.
    pause & exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
    echo Die Programmumgebung fehlt. Bitte zuerst INSTALLIEREN.cmd ausfuehren.
    pause & exit /b 1
)

install\nssm.exe stop %DIENST% 2>nul
install\nssm.exe remove %DIENST% confirm 2>nul
install\nssm.exe install %DIENST% "%CD%\.venv\Scripts\python.exe" "-m uvicorn app.main:app --host 0.0.0.0 --port 8022"
install\nssm.exe set %DIENST% AppDirectory "%CD%"
install\nssm.exe set %DIENST% DisplayName "OPERA XRechnung"
install\nssm.exe set %DIENST% Description "Erzeugt XRechnungen aus OPERA und versendet sie"
install\nssm.exe set %DIENST% Start SERVICE_AUTO_START
install\nssm.exe set %DIENST% AppStdout "%CD%\logs\dienst.log"
install\nssm.exe set %DIENST% AppStderr "%CD%\logs\dienst.log"
install\nssm.exe set %DIENST% AppRotateFiles 1
netsh advfirewall firewall add rule name="OPERA XRechnung 8022" dir=in action=allow protocol=TCP localport=8022
install\nssm.exe start %DIENST%

echo.
echo Dienst eingerichtet. Oberflaeche: http://%COMPUTERNAME%:8022/
pause
endlocal
