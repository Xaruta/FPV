# FPV-Lagezentrum unter Windows installieren

1. **Python 3.11 oder neuer** installieren: https://www.python.org/downloads/windows/
   Beim Installer unbedingt **„Add python.exe to PATH“** anhaken. (Der Python-Launcher `py` wird mitinstalliert.)
2. Den Ordner **FPV-Lagezentrum** (bzw. das ZIP entpacken) z. B. nach `C:\Users\<Name>\FPV-Lagezentrum` legen.
   Pfad am besten ohne Sonderzeichen.
3. **`start.bat`** doppelklicken.
   Beim ersten Mal wird automatisch eine Python-Umgebung (`.venv`) angelegt und `customtkinter` installiert
   (Internet nötig, ca. 1 Minute). Danach öffnet sich das Fenster.
4. Optional Web-Oberfläche: **`web\start-web.bat`** → Browser öffnet http://127.0.0.1:8767.
   Beenden: das minimierte Fenster „FPV-Lagezentrum Web“ schließen oder `web\stop-web.bat`.

Von Hand (Eingabeaufforderung im Ordner):
```bat
py -3 -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
.venv\Scripts\python main.py
.venv\Scripts\python web\server.py
```

**Probleme?**
- „Python nicht gefunden“ → Schritt 1 wiederholen, PATH-Haken setzen, PC neu anmelden.
- Windows-Firewall fragt nach: nicht nötig – der Web-Server lauscht nur lokal (127.0.0.1).
- Fehler stehen in `data\fpv-lagezentrum.log`.
- Einstellungen & Spots: `data\settings.json` (kann man sichern/kopieren).

Keine Konten, keine API-Schlüssel. Hinweis: Die Ampel bewertet nur das Wetter – Geozonen immer in der
offiziellen dipul-Karte prüfen (https://maptool-dipul.dfs.de/).
