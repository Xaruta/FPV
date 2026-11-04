@echo off
rem FPV-Lagezentrum starten (Windows). Richtet beim ersten Mal die .venv ein.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Richte Python-Umgebung ein ...
  py -3 -m venv .venv 2>nul || python -m venv .venv
  if not exist ".venv\Scripts\python.exe" (
    echo Python 3.11+ nicht gefunden. Bitte INSTALL-WINDOWS.md lesen.
    pause
    exit /b 1
  )
  ".venv\Scripts\python.exe" -m pip install --upgrade pip
  ".venv\Scripts\python.exe" -m pip install -r requirements.txt
)
if not exist data mkdir data
start "" ".venv\Scripts\pythonw.exe" main.py
