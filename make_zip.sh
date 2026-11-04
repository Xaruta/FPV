#!/bin/bash
# Baut dist/FPV-Lagezentrum.zip zum Weitergeben (Windows/Linux/Mac): ohne .venv, data/, logs/, spots/, Mac-Apps, Caches.
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"; NAME="$(basename "$DIR")"
mkdir -p dist
rm -f dist/FPV-Lagezentrum.zip
cd ..
zip -rq "$DIR/dist/FPV-Lagezentrum.zip" "$NAME" \
  -x "$NAME/.venv/*" "$NAME/.git/*" "$NAME/data/*" "$NAME/logs/*" "$NAME/spots/*" "$NAME/dist/*" "$NAME/*.app/*" \
     "*/__pycache__/*" "*.pyc" "*/.DS_Store" "*.api_key" "*/.api_key" "*/.env" "*.env"
echo "Fertig: $DIR/dist/FPV-Lagezentrum.zip"
