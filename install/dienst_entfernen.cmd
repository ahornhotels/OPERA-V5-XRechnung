@echo off
REM Entfernt den Windows-Dienst. Programm, Konfiguration und Daten bleiben.
setlocal
cd /d "%~dp0.."
set DIENST=OperaXRechnung

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Bitte mit Rechtsklick als Administrator ausfuehren.
    pause & exit /b 1
)
if exist "install\nssm.exe" (
    install\nssm.exe stop %DIENST%
    install\nssm.exe remove %DIENST% confirm
) else (
    sc stop %DIENST%
    sc delete %DIENST%
)
netsh advfirewall firewall delete rule name="OPERA XRechnung 8022"
echo.
echo Dienst entfernt. Konfiguration unter config\ und Daten unter data\ sind unberuehrt.
pause
endlocal
