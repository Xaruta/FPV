@echo off
rem Startet FPV-Lagezentrum Web auf http://127.0.0.1:8767 (nur lokal) und oeffnet den Browser.
cd /d "%~dp0.."
if not exist ".venv\Scripts\python.exe" (
  echo Bitte zuerst start.bat einmal ausfuehren ^(richtet Python ein^).
  pause
  exit /b 1
)
if not exist data mkdir data
start "FPV-Lagezentrum Web" /min ".venv\Scripts\python.exe" web\server.py
timeout /t 2 /nobreak >nul
start "" http://127.0.0.1:8767
echo FPV-Lagezentrum Web laeuft: http://127.0.0.1:8767  (Fenster "FPV-Lagezentrum Web" schliessen = beenden)
