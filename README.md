# 🛸 FPV-Lagezentrum

Dunkles Cockpit für FPV-Piloten: **Wetter-Ampel, kleines Flugradar, Spots, Preflight-Checkliste, dipul-Hinweis**.
Als Desktop-Programm (CustomTkinter) und als handytaugliche Web-Oberfläche. Läuft auf **macOS, Linux und Windows**.

> ⚠️ **Kein Rechtsrat.** Ob und wo geflogen werden darf, zeigt verbindlich nur die offizielle **dipul-Karte der DFS**
> (https://maptool-dipul.dfs.de/) bzw. die Vorgaben von LBA/EASA. Die Ampel bewertet nur das Wetter.

## Funktionen
| Karte | Quelle | Inhalt |
|---|---|---|
| 📍 Standort / Spots | Open-Meteo Geocoding | Ort suchen, mehrere Spots speichern („Haus“, „Field“), im Web auch Gerätestandort |
| 🚦 Flug-Ampel | eigene Regeln | Grün/Gelb/Rot aus Wind, Böen, Regen, Gewitter, Sicht, Kälte, Dunkelheit – Grenzwerte einstellbar |
| 🌤 Wetter | Open-Meteo Forecast | Große Zahlen, Windkompass, Böen, Regen, Sicht, Wolken, 8-Stunden-Vorschau, Sonnenauf-/-untergang |
| ✈ Flugradar | OpenSky Network (anonym) | Luftfahrzeuge in ±0,5° (≈ 55 km) sortiert nach Distanz, Höhe, Tempo, Kurs; „TIEF & NAH“-Markierung; Auto-Refresh 60 s |
| ✅ Preflight | lokal | Editierbare Checkliste mit Fortschritt & Motivation, „↺ Zurücksetzen“, **🖨 Drucken** (A4-HTML, im Web `/druck/checkliste`, leer: `?leer=1`) |
| 🗂 Spot-Datenbank | lokal + Open-Meteo | Profil je Spot: GPS/Höhe, dipul/OSM/OpenAIP, Gelände, Hindernisse, Routen, Gefahren (→ Checkliste), Funk, Bewertung, Medienordner, Export/Import |
| 🏆 Wo fliege ich heute? | Open-Meteo | Alle Spots mit echter Ampel, sortiert nach Ampel + Nähe, Entfernung, Wetter, Bewertung oder zuletzt geflogen |
| 📒 Flugtag & Logbuch | lokal + Open-Meteo | Flugtag starten/beenden, echter Wetter-Snapshot, Wind-/Böenverlauf, Notizen mit Tags, Suche, Ordner öffnen |
| ✈ Flüge & Wartung | lokal | Pro Pack: Dauer, Akku, Drohne, ok/Crash – am laufenden oder nachträglich an jedem Flugtag; Reparaturen mit Teil/Kosten |
| 📊 Flugstatistik | lokal (aus dem Logbuch) | Flugtage/Monat, Flugstunden, Top-Spots, Akkus, Wetter der Flugtage, Crashes/Reparaturen, Ø-Flugzeit-Verlauf; CSV + Druckseite |
| 🗺 Karte (`/karte`) | OSM + OpenSky | Dunkle Leaflet-Karte: alle Spots (Ampel), Flugzeuge nach Kurs/Höhe, Spuren, 1/5/10-km-Ringe, Routenlinien |
| 🗺 dipul / EASA | Link | Deep-Link in die dipul-Karte genau am Spot (`/geozones/@lon,lat,1000r`), dazu OpenAIP |
| 🛫 Flugplatz-Wetter | aviationweather.gov (NOAA) | METAR + TAF des nächsten Flugplatzes: Wind, Sicht, Wetter, Wolken, QNH, Alter, Klartext + Rohtext |
| 📄 NOTAM | – | **folgt** (keine freie, schlüssellose API gefunden – es werden keine NOTAMs erfunden) |

Keine API-Schlüssel nötig. OpenSky anonym: ca. 400 Abrufe/Tag – Desktop und Web teilen sich einen Cache
(`data/opensky_cache.json`), das Restkontingent wird angezeigt.

## Installation & Start
Voraussetzung: **Python 3.11+**. Einzige Abhängigkeit: `customtkinter` (siehe `requirements.txt`).

```bash
git clone <REPO-URL> FPV-Lagezentrum && cd FPV-Lagezentrum
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python main.py          # Desktop-Programm
.venv/bin/python web/server.py    # Web-Oberfläche → http://127.0.0.1:8767
```

- **macOS:** `start.command` doppelklicken (richtet beim ersten Mal die `.venv` ein). Optional Starter-Apps bauen:
  `./make_app.sh` → `FPV-Lagezentrum.app`, `FPV-Lagezentrum Web starten.app`, `FPV-Lagezentrum Web stoppen.app`
  im Projektordner.
- **Linux:** wie oben im Terminal, Web auch per `web/start-web.sh` / `web/stop-web.sh`.
- **Windows:** siehe `INSTALL-WINDOWS.md` (`start.bat`, `web\start-web.bat`).

Port: **8767** (nur 127.0.0.1, kein Passwort).

Handy im Tailnet (optional, NIE Funnel) – nur bei Bedarf von Hand:
```bash
tailscale serve --bg --https=8767 http://127.0.0.1:8767   # wieder aus: tailscale serve --https=8767 off
FPV_TS_HOST=<rechnername>.<tailnet>.ts.net  # vor dem Web-Start setzen, sonst lehnt der Server fremde Host-Header ab
```

## Erster Start
Die App startet **ohne Standort** („Bitte Standort setzen“). Ort suchen (z. B. „Hannover“) → Treffer wählen →
Spot-Namen eintragen → **Spot speichern**. Einstellungen liegen in `data/settings.json`.
Optional als Vorlage: `settings.example.json` nach `data/settings.json` kopieren (Beispiel-Spot Hannover).

## Weitergeben (Windows)
**Projektordner + `INSTALL-WINDOWS.md`** weitergeben. Am einfachsten `./make_zip.sh` → `dist/FPV-Lagezentrum.zip`
(ohne `.venv`, ohne `data/`, ohne Mac-Apps, also ohne persönliche Spots). Drüben: entpacken, `start.bat`.

## Flugtag & Logbuch (v1.1)
1. Spot wählen → **▶ Flugtag starten**: legt `logs/JJJJ-MM-TT_Spot/` an mit `flugtag.json`, `flugtag.md`,
   `verlauf.jsonl`, `notizen.jsonl` und leerem `medien/` – plus echtem Wetter-Snapshot (Open-Meteo) inkl. Ampel,
   Sonnenstand und Checklisten-Stand. Ist das Wetter nicht abrufbar, steht dort ehrlich „kein Snapshot“.
2. Solange Desktop **oder** Web läuft, kommt alle 15 min ein Messpunkt dazu (Wind, Böen, Temp, Sicht, Sonne, Ampel)
   – Diagramm mit Böen-Grenzlinien in der Logbuch-Karte. Intervall: `verlauf_minuten` in `data/settings.json`.
3. **➕ Notiz** mit Zeitstempel und Tag (böig, thermisch, nass, Störungen, voll, perfekt, Crash).
4. Videos/Fotos selbst nach `medien/` legen (📂 Ordner öffnen) – sie werden per Dateizeit dem Wetter zugeordnet.
5. **■ Flugtag beenden** → End-Snapshot + `zusammenfassung.md` (min/Ø/max nur aus gespeicherten Messwerten).
6. Suche über Datum, Spot, Region, Notizen (`logs/index.json`, „↻ Index“ baut ihn neu auf).

Anderer Ablageort: `"logs_dir"` in `data/settings.json` (z. B. `D:\\FPV\\logs` oder `~/FPV-Logs`). Es wird nie etwas gelöscht.
## Spot-Datenbank (v1.2)
- Jeder Spot hat ein Profil unter `spots/<id>/profil.json` und einen Ordner `spots/<id>/medien/` für Übersichtsfotos.
  Vorhandene Spots werden beim Start automatisch übernommen. „🗑 Löschen“ entfernt nur den Listeneintrag – das Profil bleibt.
- **🗂 Spot-Profil** (Spot-Karte): Gelände, Hindernisse, Flugrouten, Gefahrenstellen (hoch/mittel/niedrig; mit
  „Checkliste“ erscheinen sie als Zusatzpunkte in Checkliste, Druck und Flugtag), Funk, Bewertung, private Notizen.
- **🏆 Wo fliege ich heute?** holt mit einem Abruf das aktuelle Wetter aller Spots. Entfernung ab aktivem Spot bzw. im Web
  ab Gerätestandort. Klappt der Abruf nicht, steht das dort – erfundene Werte gibt es nicht.
- **Teilen:** Profil exportieren → `spot-<id>.json` (ohne Medien, private Notizen nur auf Wunsch) → beim Freund „⬇ Import“.
- Anderer Ablageort: `"spots_dir"` in `data/settings.json`. `spots/` gehört nicht in die Weitergabe-Kopie.

## Flüge & Statistik (v1.3)
- **✈ Flüge & Wartung** (Logbuch-Karte, solange ein Flugtag läuft) oder **✈** hinter jedem Tag in der Logbuch-Liste
  (nachträglich). Ein Eintrag pro Akku-Pack: Start, Dauer (`3:45` oder `4` = Minuten), Zeitquelle, Akku-ID, Drohne,
  ok/Crash, Notiz. Alle Felder sind optional – leere Felder erscheinen in der Statistik als „keine Angabe“.
- Wartung/Reparatur: Teil (Props, Arm, Motor …), Anzahl, Drohne, Kosten (optional), Notiz.
- Gespeichert in `logs/<Flugtag>/fluege.jsonl` und `wartung.jsonl`. Es wird nur angehängt; „↩“ hängt eine Storno-Zeile an.
- **Akku-Register** (im Statistik-Fenster/-Karte): ID wie auf dem Pack, Zellen, mAh, Kaufdatum, „ausgemustert“ → `data/akkus.json`.
- **📊 Statistik** rechnet bei jedem Klick alles neu aus den Logbuch-Dateien (Filter von/bis/Spot/Drohne).
  **⬇ CSV** = eine Zeile pro Flug (öffnet direkt in Excel/LibreOffice), **🖨 Druck** = A4-Seite (Web: `/druck/statistik`).

## Karte (v1.4)
- Web: **http://127.0.0.1:8767/karte** (oder „🗺 Karte“ oben auf der Web-Seite). Desktop: **🗺 Karte öffnen** in der
  Spot-Karte – startet den Web-Server bei Bedarf und öffnet die Karte im Browser.
- Spots als Kreise (Farbe = Ampel, grau = noch nicht abgerufen; aktiver Spot groß mit weißem Ring). **🚦 Ampeln holen**
  macht einen echten Open-Meteo-Abruf für alle Spots. Klick auf einen Spot → Kurzinfo, Routen, Gefahren, Links, „aktiv setzen“.
- Flugzeuge (OpenSky): Pfeil gedreht nach Kurs, Farbe nach Höhe (rot < 600 m, orange < 1500 m, gelb < 3000 m, blau höher,
  grau Boden/unbekannt). Maus drauf → Callsign, Höhe, Distanz. Live alle 60 s (Haken „Live“), Spuren der letzten ~15 min.
  Bei OpenSky-Fehlern erscheint ein roter Hinweis – es werden nie Flugzeuge erfunden.
- **Routen als Linie:** im Spot-Profil unter „Routen“ Koordinatenpaare (Dezimalgrad, mind. 3 Nachkommastellen) eintragen,
  z. B. `Runde Nord: 52.3759, 9.7320; 52.3771, 9.7335; 52.3783, 9.7351`. Ab 2 Punkten (≤ 30 km vom Spot) wird eine Linie
  gezeichnet, sonst bleibt die Route Text im Popup.
- Kacheln © OpenStreetMap-Mitwirkende, live aus dem Internet (kein Offline-Modus). Leaflet liegt lokal in `web/vendor/leaflet/`.
  Wie die Web-Seite nur lokal bzw. im Tailnet (`tailscale serve`), kein Funnel. Geozonen: nur dipul ist maßgeblich.

## Flugplatz-Wetter METAR/TAF (v1.5)
- Karte **🛫 Flugplatz-Wetter** in Desktop (rechte Spalte) und Web: nächster Flugplatz mit aktuellem METAR (≤ 3 h) zum
  aktiven Spot, Entfernung/Richtung, Wind (kt + m/s), Sicht, Wetter, Wolken, Temperatur/Taupunkt, **QNH**, Alter der
  Meldung, VFR/IFR-Kategorie, Rohtext; darunter der **TAF** in Perioden und weitere Plätze mit QNH. 🔄 = neu laden (≥ 60 s).
- Auf `/karte`: Flugplatz-Marker 🛫 (blau = Platz des angezeigten METAR) mit Popup.
- Quelle: aviationweather.gov Data API (NOAA/NWS), frei ohne Schlüssel; Stationsliste 30 Tage, Meldungen 10 min gecacht.
- **Wichtig:** METAR/TAF ist das Wetter am Flugplatz, nicht an deinem Spot. Die Ampel nutzt weiter das Spot-Wetter (Open-Meteo).
  Kein Ersatz für eine offizielle Flugwetterberatung. Fehler werden angezeigt, es werden nie Meldungen erfunden.

## Licht & Dämmerung, Ops-Streifen, dipul-Geozonen (v1.7)
- **Licht**: Wetter-Karte zeigt „☀ noch 1 h 20 min Licht bis Sonnenuntergang 16:55 · dunkel ab 17:33“, in der
  Dämmerung „🌇 noch X bis dunkel“, nachts „🌙 Nacht – Dämmerung ab …“, bei tiefer Sonne „⚠ Gegenlicht aus SW“.
  Ampel wird gelb ab 30 min vor Sonnenuntergang, in der Dämmerung und nachts. Flugtag-Status und `flugtag.md`
  enthalten die Lichtlage. Rein lokal berechnet – kein Abruf, ±1–2 min.
- **Ops-Streifen** unter dem Titel: `📍 Spot │ 🟢 Ampel │ ☀ Licht` (Desktop + Web, aktualisiert jede Minute).
- **dipul-Geozonen am Spot** (Karte „🗺 dipul / EASA“): fragt den **offiziellen dipul-WFS** ab und listet, welche
  geografischen Gebiete (§ 21h LuftVO) am Spot bzw. im Umkreis ~250 m liegen, mit Höhen. „🔄 Geozonen prüfen“ holt neu
  (sonst Cache 30 min). Auf `/karte` gibt es die Ebene „dipul-Geozonen“ (offizieller WMS, ab Zoom 9, standardmäßig aus;
  `/karte?dipul=1`). Quelle: dipul, CC-BY-ND 4.0. **Nur Hinweis – verbindlich ist die dipul-Karte. Kein Rechtsrat.**

## Version
**1.8-public** – öffentliche, bereinigte Fassung (Stand v1.7 ohne Phase 5 „Vernetzung“). Persönliche Daten
(`data/`, `logs/`, `spots/`) gehören nicht ins Repository und stehen in `.gitignore`.

Weitere Pläne: `ROADMAP.md`.

## Dateien
`main.py` · `app/` (config, settings, net, geo, weather, opensky, notam, sun, logbook, export, spots, stats, batteries, mapdata, webmap, metar, dipul, gui/) · `web/server.py`, `web/karte.py`, `web/vendor/leaflet/` ·
`ROADMAP.md` · `ARCHITEKTUR.md` · `INSTALL-WINDOWS.md`

Daten: Open-Meteo (CC BY 4.0) · The OpenSky Network (nicht-kommerzielle Nutzung) · METAR/TAF: aviationweather.gov (NOAA/NWS) · Karten © OpenStreetMap-Mitwirkende (ODbL) · Leaflet (BSD-2) · Geozonen: dipul, CC-BY-ND 4.0 (offizieller WFS/WMS, unverändert angezeigt).
