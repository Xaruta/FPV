#!/bin/bash
# Startet FPV-Lagezentrum Web auf http://127.0.0.1:8767 (nur lokal) und öffnet den Browser.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PORT=8767; LOG="$DIR/data/web.log"; PID="$DIR/data/web.pid"
mkdir -p "$DIR/data"
PY="$DIR/.venv/bin/python"; [ -x "$PY" ] || PY="$(command -v python3)"
up() { curl -s -m 2 -o /dev/null "http://127.0.0.1:$PORT/health"; }
if ! up; then
  nohup "$PY" "$DIR/web/server.py" >>"$LOG" 2>&1 </dev/null &
  echo $! >"$PID"; disown
  for i in $(seq 1 30); do up && break; sleep 0.5; done
fi
up || { echo "FPV-Lagezentrum Web startet nicht – siehe $LOG"; exit 1; }
if [ "$1" != "--no-open" ]; then
  if command -v open >/dev/null; then open "http://127.0.0.1:$PORT"; elif command -v xdg-open >/dev/null; then xdg-open "http://127.0.0.1:$PORT"; fi
fi
echo "FPV-Lagezentrum Web läuft: http://127.0.0.1:$PORT"
