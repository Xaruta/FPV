#!/bin/bash
# Baut die Starter-Apps (AppleScript, eigenes Symbol) im Projektordner (optional zusätzlich nach $FPV_APP_COPY_DIR):
#   FPV-Lagezentrum.app                – Desktop-Programm
#   FPV-Lagezentrum Web starten.app    – Web-Oberfläche starten + Browser öffnen (http://127.0.0.1:8767)
#   FPV-Lagezentrum Web stoppen.app    – Web-Oberfläche beenden
# Erneut ausführbar (ersetzt nur diese drei Apps).
set -e
cd "$(dirname "$0")"
DIR="$(pwd)"
TMP="$(mktemp -d)"

ICONSET="$TMP/icon.iconset"; mkdir -p "$ICONSET"
for s in 16 32 128 256 512; do
  sips -z $s $s app/icon.png --out "$ICONSET/icon_${s}x${s}.png" >/dev/null
  d=$((s*2)); sips -z $d $d app/icon.png --out "$ICONSET/icon_${s}x${s}@2x.png" >/dev/null
done
iconutil -c icns "$ICONSET" -o "$TMP/applet.icns"

build() {  # build <Name> <AppleScript-Datei>
  local NAME="$1" SRC="$2" APP="$DIR/$1.app"
  rm -rf "$APP"
  osacompile -o "$APP" "$SRC"
  cp "$TMP/applet.icns" "$APP/Contents/Resources/applet.icns"
  rm -f "$APP/Contents/Resources/Assets.car"
  /usr/libexec/PlistBuddy -c "Delete :CFBundleIconName" "$APP/Contents/Info.plist" 2>/dev/null || true
  /usr/libexec/PlistBuddy -c "Set :CFBundleName $NAME" "$APP/Contents/Info.plist" 2>/dev/null || true
  touch "$APP"
  codesign --force --deep -s - "$APP" 2>/dev/null || true
  if [ -n "$FPV_APP_COPY_DIR" ] && [ -d "$FPV_APP_COPY_DIR" ]; then
    rm -rf "$FPV_APP_COPY_DIR/$NAME.app"
    cp -R "$APP" "$FPV_APP_COPY_DIR/$NAME.app"
    echo "Kopiert nach: $FPV_APP_COPY_DIR/$NAME.app"
  fi
}

cat > "$TMP/desk.applescript" <<OSA
do shell script "cd " & quoted form of "$DIR" & " && if [ -x .venv/bin/python ]; then mkdir -p data; nohup ./.venv/bin/python main.py >> data/stdout.log 2>&1 & else open start.command; fi"
OSA
build "FPV-Lagezentrum" "$TMP/desk.applescript"

cat > "$TMP/webstart.applescript" <<OSA
try
	do shell script "/bin/bash " & quoted form of "$DIR/web/start-web.sh"
on error e
	display dialog "FPV-Lagezentrum Web konnte nicht gestartet werden:" & return & e & return & return & "Details: $DIR/data/web.log" buttons {"OK"} default button "OK" with title "FPV-Lagezentrum Web" with icon stop
end try
OSA
build "FPV-Lagezentrum Web starten" "$TMP/webstart.applescript"

cat > "$TMP/webstop.applescript" <<OSA
set s to do shell script "/bin/bash " & quoted form of "$DIR/web/stop-web.sh"
display notification s with title "FPV-Lagezentrum Web"
OSA
build "FPV-Lagezentrum Web stoppen" "$TMP/webstop.applescript"

rm -rf "$TMP"
echo "Fertig."
