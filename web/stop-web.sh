#!/bin/bash
# Stoppt FPV-Lagezentrum Web (Port 8767). Andere Programme auf anderen Ports bleiben unberührt.
DIR="$(cd "$(dirname "$0")/.." && pwd)"
PIDS=$(lsof -nP -t -iTCP:8767 -sTCP:LISTEN 2>/dev/null)
if [ -z "$PIDS" ]; then echo "FPV-Lagezentrum Web war nicht gestartet."; exit 0; fi
for p in $PIDS; do
  CMD=$(ps -o command= -p "$p"); CWD=$(lsof -a -p "$p" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')
  if echo "$CMD" | grep -q "FPV-Lagezentrum/web/server.py" || { [ "$CWD" = "$DIR" ] && echo "$CMD" | grep -q "web/server.py"; }; then
    kill "$p"
  fi
done
sleep 1; rm -f "$DIR/data/web.pid"
echo "FPV-Lagezentrum Web gestoppt."
