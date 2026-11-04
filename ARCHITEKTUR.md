# Architektur – FPV-Lagezentrum

```
main.py                 Desktop-Start (Logging, Einzelinstanz-Lock: fcntl / msvcrt)
app/config.py           Pfade (pathlib, relativ zum Projekt), URLs, Ports, Intervalle
app/settings.py         data/settings.json: Spots, aktiver Spot, Grenzwerte, Checkliste (atomar geschrieben)
app/net.py              HTTP-JSON-Helfer (urllib, nur Standardbibliothek) → NetError mit deutscher Meldung
app/geo.py              Geocoding, Haversine-Distanz, Peilung, Windpfeil, dipul-Deep-Link
app/weather.py          Open-Meteo abrufen (5-min-Cache) + assess() → Ampel grün/gelb/rot + Gründe
app/opensky.py          OpenSky /states/all mit Bounding-Box, Dateicache (geteilt Desktop/Web), Fehler/429
app/notam.py            Stub („folgt“) – bewusst ohne Daten
app/sun.py              Sonnenstand (Höhe/Azimut/Phase) lokal berechnet (NOAA-Formel, ohne API)
app/logbook.py          Flugtage: starten/beenden, Snapshot, Verlauf (tick), Notizen, Medien-Zuordnung,
                        Zusammenfassung, index.json + Suche, Ordner öffnen (os.startfile / open / xdg-open)
app/spots.py            Spot-Datenbank: Profile (normalize/save/load), Migration aus settings.json, Links,
                        Gefahren → Checklisten-Zusatzpunkte, Flugtage je Spot, Export/Import, fetch_many + today()
app/gui/spots_view.py   Desktop: ProfileEditor (Tabs) und TodayWindow („Wo fliege ich heute?“)
app/export.py           Checkliste als druckbares HTML (helles A4-Print-CSS, „Als PDF sichern“ über Browser)
app/gui/theme.py        Farben (dunkles GitHub-Dark-Theme)
app/gui/main_window.py  CustomTkinter-Fenster; Netz in Threads, Ergebnisse über Queue in den UI-Thread
web/server.py           ThreadingHTTPServer auf 127.0.0.1:8767, eine HTML-Seite + JSON-API, Host-Header-Prüfung
```

**JSON-API (Web):** `GET /health`, `/api/state`, `/api/weather[?force=1]`, `/api/radar[?force=1]`, `/api/geocode?q=` ·
`POST /api/spot` (inkl. `region`), `/api/spot/delete`, `/api/active`, `/api/checklist`, `/api/thresholds`, `/api/auto`.
Logbuch: `GET /api/flugtag` (aktiver Tag + Verlauf/Notizen/Medien), `GET /api/log?q=`, `GET /log/<ordner>` (MD-Ansicht),
`GET /druck/checkliste[?leer=1]` · `POST /api/flugtag/start`, `/api/flugtag/ende`, `/api/flugtag/notiz {text,tags}`,
`/api/log/reindex`, `/api/oeffnen {ordner}` (Ordnername wird gegen Pfad-Ausbruch geprüft).
Spots: `GET /api/spots/heute?sort=kombi|distanz|wetter|bewertung|zuletzt[&lat=&lon=][&force=1]`,
`GET /api/spotprofil[?id=]`, `GET /api/spotprofil/export?id=[&privat=1]` (Download) ·
`POST /api/spotprofil {profil}`, `/api/spotprofil/import {data}`, `/api/spotprofil/medien {id}` (Ordner öffnen).
Verlauf-Takt: Desktop (`after`, 60 s) und Web (Hintergrund-Thread, 60 s) rufen `logbook.tick()`; geschrieben wird
nur, wenn der letzte Punkt älter als `verlauf_minuten` (Standard 15) ist und Open-Meteo eine neue Messzeit liefert –
laufen beide, entstehen keine Doppelpunkte.

**Abhängigkeiten:** nur `customtkinter` (Desktop). Web-Server = reine Standardbibliothek.

**Plattformen:** Kernlogik ohne macOS-Pfade/Tools. Mac-spezifisch sind nur `start.command`, `make_app.sh`,
`web/*.sh` und die `.app`-Starter; Windows nutzt `start.bat`, `web\start-web.bat`, `web\stop-web.bat`.

**Datenschutz:** Nur Koordinaten des aktiven Spots gehen an Open-Meteo/OpenSky. Keine Konten, keine Schlüssel.

## Logbuch (Roadmap Phase 6) – gebaut v1.1 (Stand-Skizze; Abweichungen siehe unten)
```
app/logbook.py          Flugtag anlegen (Snapshot aus weather.fetch/assess + Spot + Checkliste),
                        Ordnername JJJJ-MM-TT_Spot, flugtag.json/.md schreiben, Index aufbauen/suchen
app/region.py           Reverse-Geocoding Spot → Region (Quelle wählbar, mit Cache & Rate-Limit)
app/flightday.py        Flugtag starten/beenden, Messpunkt-Takt (Thread/after), Notizen, Medien-Zuordnung per Zeit
app/sun.py              Sonnenstand/-zeiten lokal berechnet (NOAA-Formel, ohne API)
app/summary.py          Tageszusammenfassung aus verlauf/notizen/medien (regelbasiert, optional lokales Sprachmodell)
app/export.py           Checkliste/Flugtag als druckbares HTML (Print-CSS); PDF über Browser-Druck
app/gui/logbook_view.py Desktop-Ansicht Logbuch (Filter, Suche, „Ordner öffnen“)
web/server.py           + GET /api/log, POST /api/log, GET /druck/checkliste
logs/                   Standard-Basisordner (konfigurierbar: settings.json → logs_dir)
  JJJJ-MM-TT_Spot/        flugtag.json  (Kopf: Spot, Region, Start-/End-Snapshot, Status offen/beendet)
                          verlauf.jsonl (alle 15 min: Wind, Böen, Richtung, Temp, Sicht, Sonnenstand, Ampel)
                          notizen.jsonl (Zeitstempel, Text, Tags)
                          zusammenfassung.md · flugtag.md
                          medien/ (Videos/Fotos – selbst abgelegt oder per „Importieren“ kopiert)
  index.json              Such-Index, jederzeit aus den flugtag.json neu aufbaubar
```
Umgesetzt in v1.1: `logbook.py` (enthält Flugtag-Logik + Zusammenfassung), `sun.py`, `export.py`, Logbuch-Karte
direkt im Hauptfenster/Web statt eigener View. Noch offen: `region.py` (Reverse-Geocoding – Region kommt bisher aus
dem Geocoding-Treffer beim Spot-Speichern), Medien-„Importieren“, End-Snapshot-Vergleich im Web, KI-Zusammenfassung.
`logs/aktiv.json` merkt sich den laufenden Tag (Desktop und Web sehen denselben).

Regeln: Logs-Ordner wird nur beschrieben (neue Einträge) und gelesen, nie gelöscht/verschoben; Medien werden
nicht kopiert oder hochgeladen; alle Pfade per pathlib (macOS/Windows/Linux); `logs/` und `data/` gehören nicht
in die Weitergabe-Kopie bzw. ins Repository (`make_zip.sh`/`.gitignore` schließt sie aus).

## Spot-Datenbank (Roadmap Phase 7) – gebaut v1.2
```
app/spots.py            Spot-Profile laden/speichern, Migration aus settings.json, Sortierung (Distanz/Wetter/Bewertung),
                        Export/Import einzelner Profile
app/weather.py          + fetch_many(): ein Open-Meteo-Abruf für mehrere Spots (Ampel je Spot, Cache 15 min)
app/gui/spots_view.py   Spot-Liste + Profil-Editor (Tabs: Allgemein, Gelände, Hindernisse/Gefahren, Funk, Bewertung, Medien)
web/server.py           + GET /api/spots?sort=distanz|wetter|bewertung&lat=&lon=, GET/POST /api/spots/<id>
spots/                  (konfigurierbar wie logs/; nicht in der Weitergabe-Kopie)
  <spot-id>/              profil.json  (GPS, Höhe, Gelände, Hindernisse[], Gefahren[], Funk{}, Bewertung{}, Routen)
                          routen.geojson (ab Phase 2: Routen/Hindernisse als Geometrie)
                          medien/        (Spot-Fotos/-Videos)
```
Umgesetzt wie skizziert; `routen.geojson` folgt mit Phase 2. Spot-IDs sind ASCII-Slugs (ä→ae, Windows-sicher),
`settings.json → spots[]` trägt zusätzlich `id`. Ein Profil wird nie gelöscht; ein gleichnamiger neuer Spot übernimmt es wieder.
Flugtage (Phase 6) verweisen per `spot-id` auf das Profil; Gefahrenstellen eines Spots erweitern die
Preflight-Checkliste automatisch. Sortierung „Wetter“ nutzt nur echte Abrufe; fehlt einer, steht der Spot unter „unbekannt“.

## Flugstatistik (Roadmap Phase 8) – gebaut v1.3
```
app/logbook.py          + add_flight / add_maintenance / storno (nur anhängen), flights(d) / maintenance(d) (Storno herausgefiltert),
                          parse_duration, fmt_dur; Index-Zeilen + fluege, flugzeit_s, crashes, wartung; flugtag.md/zusammenfassung.md
                          listen Flüge + Wartung (werden nach jedem Eintrag neu erzeugt)
app/batteries.py        Akku-Register data/akkus.json (upsert, nie löschen – „ausgemustert“)
app/stats.py            compute(cfg, von, bis, spot, drohne) – alles bei jedem Aufruf neu aus logs/*/…; flights_csv(); print_html()
app/gui/stats_view.py   FlightsWindow (Eintragen) + StatsWindow (Canvas-Balken/-Linie, Tabellen, Akku-Register, CSV, Druck)
web/server.py           + GET /api/fluege[?ordner=], /api/statistik?von=&bis=&spot=&drohne=, /api/statistik.csv, /druck/statistik
                        + POST /api/flug {ordner?, start, dauer, quelle, akku, drohne, ergebnis, notiz}, /api/wartung
                          {ordner?, teil, anzahl, drohne, kosten, notiz}, /api/storno {kind: flug|wartung, id, ordner?}, /api/akku
logs/JJJJ-MM-TT_Spot/   + fluege.jsonl  {id, zeit, start, dauer_s|null, quelle, akku, drohne, ergebnis ok|crash|null, notiz}
                        + wartung.jsonl {id, zeit, datum, teil, anzahl, drohne, kosten|null, notiz}
                          Storno = zusätzliche Zeile {storno: id, zeit}
```
Kein eigener Datenbestand: Statistiken werden immer aus den Dateien berechnet. Fehlende Werte werden gezählt
(„ohne Dauer“, „ohne Ergebnis“, „ohne Akku“) und als „keine Angabe“ angezeigt. Wetter-Anteile kommen aus dem
Tagesstart-Snapshot (Phase 6), Ø/max Wind/Böen aus `verlauf.jsonl`. Ohne `ordner` gilt der aktive Flugtag;
Ordnernamen laufen durch denselben Pfad-Guard wie das Logbuch.

## Karte (Roadmap Phase 2) – gebaut v1.4
```
app/mapdata.py          spot_layer(cfg) – alle Spots + Profilinfos, Ampel NUR aus spots._multi_cache (kein Netz);
                        route_points(text, lat, lon) – Koordinatenpaare aus Routentext (≥ 2, ≤ 30 km) oder None;
                        update_tracks(radar) – Spuren je ICAO24 im Speicher (20 Punkte, 15 min), nur bei neuem Abruf
app/spots.py            + cached_weather(profs) – liest den Multi-Cache (TTL 900 s), sonst [None…]
app/webmap.py           ensure_server() – /health prüfen, sonst web/server.py losgelöst starten (Popen, plattformneutral,
                        Log data/web.log, PID data/web.pid); Desktop-Button öffnet danach /karte per webbrowser
web/karte.py            MAP_PAGE (raw string): Leaflet-Vollbildkarte, eigene Layer Spots/Routen/Ringe/Flugzeuge/Spuren
web/vendor/leaflet/     Leaflet 1.9.4 (leaflet.js/.css, images/, LICENSE) – lokal ausgeliefert, kein CDN
web/server.py           + GET /karte, /vendor/leaflet/<datei> (nur .js/.css/.png, Pfad-Guard),
                          /api/karte/spots, /api/karte/radar[?force=1] (opensky.fetch am aktiven Spot + hinweis + spuren + box)
```
Kacheln: tile.openstreetmap.org (dunkel per CSS-Filter `invert/hue-rotate`). Flugzeuge kommen ausschließlich aus
`opensky.fetch` (gemeinsamer Datei-Cache mit Desktop/Hauptseite); bei `fehler` werden keine Spuren ergänzt.

## METAR/TAF (Roadmap Phase 4) – gebaut v1.5
```
app/metar.py            stations(lat, lon) – aviationweather.gov /api/data/stationinfo?bbox (±0,7°, sonst ±1,4°),
                          nur siteType METAR/TAF, ≤ 150 km, Cache data/metar_stationen.json (30 Tage, max. 40 Orte)
                        fetch(lat, lon, force) – /api/data/metar?ids=<8 nächste>&hours=3 + /api/data/taf?ids=…;
                          nächster Platz mit METAR ≤ 3 h; decode_metar/decode_taf (deutscher Klartext); Cache
                          data/metar_cache.json (10 min, force ≥ 60 s); Fehler → letzter Stand + „fehler“ oder leer
app/notam.py            weiter Platzhalter (FAA-API 401 ohne Key, aviationweather.gov ohne NOTAM-Endpunkt)
app/gui/main_window.py  Karte „🛫 Flugplatz-Wetter“ (rechte Spalte), refresh_metar() in refresh_all()
web/server.py           + GET /api/metar[?force=1] (aktiver Spot) · Web-Karte METAR_HTML/METAR_JS (raw strings)
web/karte.py            + Ebene „Flugplätze (METAR)“ (liest /api/metar, also denselben Cache)
```
HTTP 204/leer = keine Meldung (kein Fehler). Zeiten werden in Ortszeit angezeigt, das Alter beim Ausliefern neu berechnet.

## Licht & dipul-Geozonen (Roadmap Phase 4 Rest + Phase 3) – gebaut v1.7
```
app/sun.py              times(lat, lon, day) → Dämmerungsbeginn/Aufgang/Untergang/Dämmerungsende (−0,833° / −6°, Scan + Bisektion)
                        light(lat, lon, now) → phase (tag|tief|daemmerung_abend|daemmerung_morgen|nacht), min_bis_untergang,
                          min_bis_dunkel, text/kurz, warnung (nur ≤ 30 min, Dämmerung, Nacht), gegenlicht (Hinweis), ≈ 1 ms
app/weather.py          assess(): sun.light statt Tag-Check → Warnung als gelber Grund, Rückgabe "licht"
app/logbook.py          Snapshot "licht" + Zeile „Licht: …“ in flugtag.md
app/dipul.py            check(lat, lon, radius_m=250): WFS 1.1.0 GetFeature (JSON), typeName = alle per GetCapabilities
                          vorhandenen Layer, CQL_FILTER INTERSECTS(geom, SRID=4326;POINT/POLYGON) je Layer → am_spot / umkreis,
                          Cache 30 min (Prozess), Fehler → letzter Stand + Hinweis oder am_spot=None. Keine Bewertung, nur Liste.
GUI                     ops_set(spot|ampel|licht) → Kopfzeile · refresh_light() jede Minute · refresh_dipul() bei Spot-Wechsel
web/server.py           GET /api/licht · GET /api/dipul[?force=1] · /api/flugtag + "licht" · JS opsSet/lichtLoad/dzLoad
web/karte.py            L.tileLayer.wms(uas-betrieb.de/geoservices/dipul/wms), transparent, minZoom 9, Overlay standardmäßig aus
```
