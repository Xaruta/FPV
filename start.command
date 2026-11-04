#!/bin/bash
# FPV-Lagezentrum starten (macOS: Doppelklick im Finder). Richtet beim ersten Mal die .venv ein.
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Richte Python-Umgebung ein …"
  UV="$HOME/.local/bin/uv"
  if [ -x "$UV" ]; then
    "$UV" venv --python 3.12 .venv && "$UV" pip install --python .venv/bin/python -r requirements.txt
  else
    python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
  fi
fi
mkdir -p data
nohup ./.venv/bin/python main.py >> data/stdout.log 2>&1 &
disown
osascript -e 'tell application "Terminal" to close (every window whose name contains "start.command")' >/dev/null 2>&1 &
exit 0
