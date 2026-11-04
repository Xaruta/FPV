# Roadmap – FPV-Lagezentrum

Leitlinie: echte Daten oder gar keine. Keine rechtlichen Zusicherungen – dipul/DFS, LBA und EASA sind maßgeblich.
Alles bleibt plattformneutral (macOS, Linux, Windows); Weitergabe = **Projektordner + INSTALL-WINDOWS.md**.

## Phase 1 – jetzt (v1.0, 01.11.2026) ✅
- [x] Spots speichern (mehrere), Ortssuche (Open-Meteo Geocoding), Browser-Gerätestandort im Web
- [x] Wetter: große Zahlen, Windkompass/-pfeil, Böen, Regen, Sicht, Wolken, 8-h-Vorschau, Sonnenauf-/untergang
- [x] Flug-Ampel grün/gelb/rot mit einstellbaren Grenzwerten
- [x] Flugradar OpenSky (anonym, geteilter Cache, Restkontingent, Auto-Refresh, „TIEF & NAH“)
- [x] Preflight-Checkliste (editierbar, Fortschritt, Motivation)
- [x] dipul-Deep-Link am Spot + OpenAIP-Link, Hinweis-Karte
- [x] NOTAM-Stub („folgt“)
- [x] Desktop (CustomTkinter) + Web (127.0.0.1:8767), Mac-Starter-Apps, Windows-`.bat` + Anleitung

## Phase 2 – Karte — ✅ Grundstufe gebaut (v1.4, 01.11.2026)
- [x] Echte Karte im Web unter **`/karte`**: Leaflet 1.9.4 **lokal mitgeliefert** (`web/vendor/leaflet/`, kein CDN),
      OSM-Kacheln dunkel per CSS-Filter (Standard) oder hell umschaltbar – CARTO dark verlangt inzwischen einen API-Key
- [x] Karte zentriert auf den aktiven Spot; Marker für alle Spots (Farbe = Ampel **nur aus dem Cache**, sonst grau,
      „🚦 Ampeln holen“ = ein echter Open-Meteo-Abruf), Popup mit Ampel/Gründen, Routen, Gefahren, dipul/OSM/OpenAIP,
      „Als aktiven Spot setzen“; Start-/Landeplatz als eigener Punkt
- [x] Flugzeug-Icons gedreht nach Kurs, Farbe nach Höhe; Tooltip: Callsign, Höhe, Distanz, Tempo, Kurs, Steigen, Alter
- [x] Radius-Ringe 1/5/10 km + Rechteck des Radar-Ausschnitts; Live-Refresh 60 s (pausiert bei verstecktem Tab)
- [x] Track-Historie: letzte 20 Positionen je ICAO24 (max. 15 min), **nur im Speicher** des Web-Servers
- [x] Flugrouten aus dem Spot-Profil als Linien, wenn der Routentext ≥ 2 Koordinatenpaare (≤ 30 km vom Spot) enthält;
      sonst nur Text im Popup
- [x] OpenSky-Fehler → roter Hinweis auf der Karte (keine Flugzeuge bzw. letzter gespeicherter Stand), nie erfundene Ziele
- [x] Desktop: Button **„🗺 Karte öffnen“** (startet den lokalen Web-Server bei Bedarf, öffnet `127.0.0.1:8767/karte`);
      Web-Hauptseite: Button „🗺 Karte“

**Noch offen:** Offline-Kacheln (Kachel-Cache/MBTiles fürs Field), Tracks in SQLite (überleben Neustart),
eingebettete Desktop-Karte (WebView/`tkintermapview`), Routen auf der Karte zeichnen (`routen.geojson`),
Hindernis-Positionen als Koordinaten/Marker.

## Phase 3 – UAS-Geozonen — ✅ Hinweis-Stufe gebaut (v1.7, 01.11.2026)
Geprüft 01.11.2026: Die dipul (BMDV/DFS) bietet **offizielle, öffentliche OGC-Dienste ohne Schlüssel** an –
WFS (Vektordaten, GeoJSON-Ausgabe) und WMS (Raster) unter `https://uas-betrieb.de/geoservices/dipul/ows`,
Doku: https://dipul.de/homepage/de/informationen/geografische-gebiete/wfs-wms/ . Lizenz **CC BY-ND 4.0**,
Quellenangabe „dipul, CC-BY-ND 4.0“, Hinweis auf mögliches Rate-Limit. Damit ist eine legale freie Quelle vorhanden –
**kein Scraping, kein Reverse-Engineering des Map-Tools**. (Die ED-318-Downloads für Hersteller mit Konto bleiben ungenutzt.)
- [x] `app/dipul.py`: WFS-GetFeature mit `INTERSECTS` am Spot-Punkt + Quadrat ±250 m, alle angebotenen Layer
      (Liste per GetCapabilities, 24 h gemerkt), Cache 30 min, Fehler ehrlich (letzter Stand mit Hinweis oder „✗“)
- [x] Anzeige in der dipul-Karte (Desktop + Web): „Am Spot laut dipul-Daten: Kontrollzone …, Naturschutzgebiet …“
      inkl. Höhenangaben (ab Boden / ab X m über Grund / bis X ft MSL), „Im Umkreis ~250 m: …“, Quelle + Lizenz-Link
- [x] `/karte`: Ebene „dipul-Geozonen (offiziell, ab Zoom 9)“ = WMS unverändert eingeblendet, standardmäßig aus
      (`/karte?dipul=1` schaltet sie direkt ein), Attribution in der Karte
- [x] Bewusst **keine** Ampel-Änderung und keine „darf/darf nicht“-Aussage: Gebiete bedeuten je nach Art Verbot,
      Zustimmung, Abstand oder nur Info – das bewertet der Pilot in der dipul-Karte. Immer Hinweis „dipul maßgeblich“.
- [ ] Später optional: Zonen als Notiz in den Flugtag-Schnappschuss; Modellflugplätze (derzeit nur im WMS, nicht im WFS)

## Phase 4 – Luftfahrt-Infos — ✅ METAR/TAF gebaut (v1.5, 01.11.2026)
- [x] Nächster Flugplatz zum aktiven Spot: aviationweather.gov `stationinfo` (Bounding-Box um den Spot, nur Stationen mit
      METAR/TAF, ≤ 150 km), lokal gecacht 30 Tage in `data/metar_stationen.json` – kein eigener Flugplatz-Datensatz nötig
- [x] METAR + TAF von der aviationweather.gov Data API (NOAA/NWS, frei, ohne Schlüssel): nächster Platz mit Meldung
      ≤ 3 h; TAF vom selben Platz, sonst vom nächsten Platz mit TAF; Cache 10 min (`data/metar_cache.json`)
- [x] Klartext auf Deutsch: Wind (kt + m/s, Böen), Sicht, Wetter (Regenschauer, Nebel …), Wolken (Achtel, ft + m),
      Temperatur/Taupunkt, **QNH**, VFR/MVFR/IFR, **Alter der Meldung** (ab 90 min „veraltet“), Rohtext; TAF-Perioden
- [x] Karte in Desktop + Web (🛫 Flugplatz-Wetter) mit Hinweis „Flugplatz-Wetter ≠ Spot-Wetter“; weitere Plätze mit QNH
- [x] Flugplatz-Marker auf `/karte` (Ebene „Flugplätze (METAR)“, Popup mit METAR)
- [x] Fehler ehrlich: letzter gespeicherter Stand mit Hinweis oder gar keine Daten – nie erfundene Meldungen
- [ ] NOTAM-Feed: **weiter Platzhalter** – erneut geprüft: keine freie Quelle ohne Schlüssel (FAA-API 401 ohne Client-ID,
      aviationweather.gov ohne NOTAM-Endpunkt). Option später: FAA-API mit eigenem Key (nie fest im Code) – deckt
      Deutschland aber nur über ICAO-Austausch ab; maßgeblich bleiben dipul/DFS-AIS
- [x] Bürgerliche Dämmerung, „noch X min Licht“ (v1.7): `sun.light()` – Sonnenuntergang, Ende der bürgerlichen
      Dämmerung (−6°), Countdown, Phase Tag/tief/Dämmerung/Nacht, Gegenlicht-Hinweis bei Sonne < 6° (mit Richtung);
      in Wetter-Karte, Ampel (🌆 dunkel ab), Flugtag (Status, Snapshot, flugtag.md), `/api/licht`
- [x] Ampel gelb bei ≤ 30 min bis Sonnenuntergang, in der Dämmerung und nachts (Gegenlicht nur Hinweis, keine Ampel)
- [x] Ops-Streifen oben (Desktop + Web): 📍 Spot │ Ampel │ Licht

## Phase 5 – Vernetzung — nicht Teil dieser öffentlichen Fassung
Funk-/Crew-Vernetzung ist bewusst ausgeklammert und soll als eigenständiges Projekt entstehen.
- Idee: „Kann ich heute fliegen?“ → Zusammenfassung per lokalem Sprachmodell (nur aus echten Daten)

## Phase 6 – Logbuch & Flugtage — ✅ Grundstufe gebaut (v1.1, 01.11.2026)
**Umgesetzt:** Flugtag starten/beenden (Desktop + Web), Ordner `JJJJ-MM-TT_Spot` unter `logs_dir` (Standard `logs/`)
mit flugtag.json/.md, medien/, verlauf.jsonl, notizen.jsonl; echter Start-/End-Snapshot (sonst „kein Snapshot“);
Wind-/Böenverlauf alle 15 min solange App oder Web läuft; Sonnenstand lokal; Notizen mit Tags; Medien-Zuordnung per
Dateizeit; zusammenfassung.md; index.json + Suche; Checkliste druckbar (`/druck/checkliste`, Desktop 🖨); Ordner öffnen.
**Noch offen:** Reverse-Geocoding der Region (bisher aus Geocoding-Treffer), Medien „Importieren“, Bearbeiten/
Nachtragen alter Tage, Ampel-Wechsel-Markierung im Diagramm, KI-Zusammenfassung, Filter Monat/Region.

**6.1 Flugtag speichern (Auto-Snapshot)**
- Button „📒 Flugtag speichern“ (Desktop + Web) legt einen Eintrag an und füllt automatisch aus:
  Datum/Uhrzeit, Spot-Name, Koordinaten, **Region** (Reverse-Geocoding des Spots: Ort, Landkreis, Bundesland –
  Quelle noch zu wählen, z. B. Nominatim mit eigenem User-Agent/Rate-Limit oder Open-Meteo-Geocoding-Name des Spots),
  **Wetter-Snapshot** (Ampel-Stufe + Gründe, Wind, Böen, Richtung, Temperatur, Sicht, Wolken, Regen – Werte aus dem
  letzten echten Open-Meteo-Abruf, mit Messzeit), Stand der Preflight-Checkliste (x/y erledigt).
- Von Hand ergänzbar: Notiz, Anzahl Akkus/Flüge, Drohne/Setup, Crash-Zähler 😅, Bewertung (1–5 ⭐).
- Nie erfundene Werte: fehlt ein Abruf, steht „kein Wetter-Snapshot“ im Eintrag.

**6.2 Fester Logs-Ordner, ein Unterordner pro Flugtag**
- Basisordner konfigurierbar in `settings.json` (`logs_dir`), Standard: `logs/` im Projekt; Alternative z. B.
  `~/Documents/FPV-Logs` (Windows: `%USERPROFILE%\Documents\FPV-Logs`) – immer per pathlib, plattformneutral.
- Pro Flugtag ein Ordner `JJJJ-MM-TT_Spotname` (Spotname dateinamensicher: Umlaute ok, `/\:*?"<>|` → `-`);
  mehrere Sessions am selben Tag/Spot → `…_2`, `…_3`.
- Inhalt je Ordner:
  ```
  logs/
    2026-11-08_Field/
      flugtag.json      maschinenlesbar (Snapshot + Notizen, Schema-Version)
      flugtag.md        menschenlesbar (gleicher Inhalt, druckbar)
      medien/           ← hier legt man Videos/Fotos/DVR/Blackbox selbst ab (App liest nur, verschiebt nichts)
    index.json          Such-Index (siehe 6.3), jederzeit neu aufbaubar
  ```
- Button „📂 Ordner öffnen“ (macOS `open`, Windows `os.startfile`, Linux `xdg-open`).
- Die App löscht oder verschiebt nie Dateien im Logs-Ordner.

**6.3 Lokaler, durchsuchbarer Index (Desktop + Web)**
- `index.json` (später optional SQLite-FTS) mit einer Zeile pro Flugtag: Datum, Spot, Region, Ampel, Wind/Böen,
  Anzahl Medien-Dateien (gezählt, nicht kopiert), Notiz-Auszug.
- „Index neu aufbauen“ scannt alle `*/flugtag.json` – so bleiben auch von Hand angelegte/kopierte Ordner auffindbar.
- Ansicht „📒 Logbuch“: Filter nach Zeitraum, Spot, Region, Ampel-Stufe; Volltextsuche in Notizen;
  Gruppierung nach Tagen bzw. Orten; Klick öffnet Eintrag + Medienordner.
- Web: `GET /api/log?q=&spot=&von=&bis=`, `POST /api/log` – Medien werden im Web nur aufgelistet, nicht ausgeliefert
  (bleibt lokal, 127.0.0.1).
- Statistik (Details siehe Phase 8): Flugtage pro Monat, Lieblingsspots, Streak-Motivation („3 Wochenenden in Folge geflogen!“).

**6.4 Checkliste drucken/exportieren**
- „🖨 Checkliste drucken“: sauberes HTML mit Print-CSS (hell, A4, große Kästchen ☐, Spot/Datum/Ampel im Kopf,
  Platz für Notizen) – Web: eigene Seite `/druck/checkliste`, Desktop: HTML in `logs/…` erzeugen und im Browser öffnen.
- PDF: über den Druckdialog des Browsers („Als PDF sichern“) – keine zusätzliche Abhängigkeit; optional später
  direkte PDF-Erzeugung (z. B. `reportlab`) nur wenn wirklich gebraucht.
- Optional Variante „leere Vorlage“ ohne Haken für die Fototasche.

**6.5 Flugtag-Management (Live-Begleitung des Tages)**
- **Automatischer Flugtag:** „▶ Flugtag starten“ (oder automatisch beim ersten App-Start eines Tages am aktiven Spot,
  abschaltbar) legt `JJJJ-MM-TT_Spot/` an – Datum + Spot-Name ohne Tippen. „■ Flugtag beenden“ schließt ihn ab.
- **Wetter-Snapshot beim Start:** erster echter Open-Meteo-Abruf + Ampel wird als `start`-Snapshot gespeichert
  (Messzeit dabei; ohne erfolgreichen Abruf: „kein Snapshot“, nichts erfunden).
- **Wind- & Böenverlauf:** solange der Flugtag läuft, alle 15 min (Takt von Open-Meteo-„current“) ein Messpunkt
  in `verlauf.jsonl` (Zeit, Wind, Böen, Richtung, Temp, Sicht, Ampel). Anzeige als kleines Liniendiagramm
  (Desktop: Canvas, Web: SVG) mit Grenzwert-Linien gelb/rot; Lücken bleiben als Lücken sichtbar.
- **Temperatur, Sicht & Sonnenstand:** pro Messpunkt mitgeschrieben; Sonnenstand (Höhe/Azimut) lokal berechnet
  (NOAA-Formel, keine API) + Sonnenauf-/-untergang und bürgerliche Dämmerung; Hinweis „Gegenlicht aus SW“ / „noch 40 min Licht“.
- **Eigene Notizen zu Flugbedingungen:** Schnellnotizen mit Zeitstempel („Böen hinter der Baumreihe“, „Video-Störungen
  Kanal R3“), optional Schnell-Tags (böig, thermisch, nass, Störungen, voll). Landen in `notizen.jsonl`.
- **Videos & Fotos zuordnen:** Dateien in `medien/` werden beim Öffnen/Beenden gescannt; Zuordnung zu Messpunkt/Notiz
  per Dateizeit (mtime bzw. Kamera-Metadaten, falls vorhanden). Optional „Medien importieren …“ = **Kopieren**
  von SD-Karte/DVR in `medien/` (Original bleibt, nie Verschieben/Löschen). Anzeige: Liste mit Uhrzeit und Wetter dieser Minute.
- **Automatische Tageszusammenfassung:** beim Beenden (oder um Mitternacht nachträglich) erzeugt die App aus den
  echten Daten `zusammenfassung.md`: Zeitraum, Spot/Region, min/max/Ø Wind & Böen, Ampel-Anteile (z. B. 70 % grün),
  Temperaturspanne, Sicht, Sonnenzeiten, Anzahl Notizen & Medien, Highlights aus Notizen. Zuerst regelbasiert
  (Vorlage), optional später Text-Feinschliff über ein lokales Sprachmodell (nur aus den gespeicherten Werten).

## Phase 7 – Spot-Datenbank (Ausbau der Spots aus Phase 1) — ✅ gebaut (v1.2, 01.11.2026)
**Umgesetzt (Desktop + Web):** Spot-Profile `spots/<id>/profil.json` + `medien/`, automatische Migration der
bestehenden Spots (nichts geht verloren, „Löschen“ entfernt nur den Listeneintrag); GPS + Höhe (Open-Meteo-Elevation,
wird beim ersten „Wo heute?“ übernommen), Start-/Landeplatz, Links dipul/OSM/OpenAIP, GPS kopieren; Gelände (Tags +
Felder), Hindernisse (Liste mit Art/Höhe), Flugrouten (Liste), Gefahrenstellen mit Schweregrad → Zusatzpunkte in
Checkliste, Druck-Checkliste und Flugtag; Funk/Empfang; Bewertung gesamt + 5 Kategorien; Flugtage/zuletzt geflogen
aus dem Logbuch; „🏆 Wo fliege ich heute?“ (ein Open-Meteo-Abruf für alle Spots, Cache 15 min, sortierbar nach Ampel +
Nähe / Entfernung / Wetter / Bewertung / zuletzt; Web optional ab Gerätestandort; Fehler werden angezeigt, Ampel dann
„unbekannt“); Export/Import einzelner Profile als JSON (private Notizen optional).
**Noch offen:** Marker + Routenlinien gibt es seit v1.4 auf `/karte` (aus Koordinaten im Routentext); Routen zeichnen (`routen.geojson`), Positionen der Hindernisse als Koordinaten,
automatische Verknüpfung der Flugtag-Medien in der Spot-Ansicht (bisher nur Anzahl Flugtage), Reverse-Geocoding der Region.

Jeder Spot bekommt ein eigenes **Profil** statt nur Name + Koordinaten. Bestehende Spots aus `settings.json`
werden beim ersten Start automatisch übernommen (Migration, nichts geht verloren).
- **GPS + Kartenlinks:** Koordinaten, Höhe (Open-Meteo-Elevation), Start-/Landeplatz als eigener Punkt;
  Links zu dipul (Geozonen am Spot), OpenStreetMap und OpenAIP; in Phase 2 Marker auf der eigenen Karte.
- **Fotos/Videos:** Ordner `spots/<Spot>/medien/` (Übersichtsfotos, Parkplatz, Zufahrt) + automatische Verknüpfung
  mit den Medien aller Flugtage an diesem Spot (Phase 6).
- **Geländecharakteristik:** Wiese/Feld/Wald/Industrie/Bando/Hügel/Wasser, Untergrund, Größe, Windschutz/Leeseite,
  typische Thermik, Zugang/Parken, Besucherverkehr (Freitext + Auswahl-Tags).
- **Hindernisse & mögliche Flugrouten:** Liste (Bäume, Leitungen, Masten, Gebäude) mit optionaler Position/Höhe;
  Routen-Ideen als Text, ab Phase 2 als Linien auf der Karte (GeoJSON pro Spot).
- **Bekannte Gefahrenstellen:** z. B. Straße, Bahn, Hochspannung, Spaziergänger-Weg, Tiere/Weide, Wasser –
  mit Schweregrad; werden vor jedem Flug in der Checkliste als Zusatzpunkte eingeblendet.
- **Empfangsqualität / Funkbesonderheiten:** VTX-Kanal-Erfahrungen (analog/DJI/HDZero/Walksnail), Störquellen,
  Reichweite/Abschattung je Richtung, ELRS/Crossfire-Notizen, Mobilfunk am Spot.
- **Persönliche Bewertungen:** Sterne 1–5 gesamt + Kategorien (Freestyle, Cinematic, Race, Ruhe, Erreichbarkeit),
  „zuletzt geflogen“, Anzahl Flugtage (aus Phase 6).
- **Sortierung & Auswahl:** nach **Entfernung** (Gerätestandort im Web bzw. „Heimat“-Spot), nach **aktuellen
  Wetterbedingungen** (Ampel je Spot, ein Open-Meteo-Abruf mit mehreren Koordinaten, Cache 15 min), nach Bewertung,
  zuletzt geflogen. Ansicht „🏆 Wo fliege ich heute?“ = grüne Spots in der Nähe zuerst (Wetter-Hinweis, kein Rechtsrat).
- **Teilen:** Export/Import einzelner Spot-Profile als `.json` (zum Weitergeben an andere Pilot:innen) – ohne Medien,
  private Notizen optional ausblendbar.

## Phase 8 – Flugstatistik (baut auf Phase 6 + 7 auf) — ✅ gebaut (v1.3, 01.11.2026)
**Umgesetzt (Desktop + Web):** pro Flugtag `fluege.jsonl` (Start, Dauer mm:ss/Minuten, Zeitquelle, Akku-ID, Drohne,
ok/Crash, Notiz) und `wartung.jsonl` (Teil, Anzahl, Drohne, Kosten optional, Notiz) – eintragen am laufenden Flugtag
(„✈ Flüge & Wartung“) oder nachträglich an jedem Logbuch-Tag (✈). Nur anhängen; „↩“ storniert per Storno-Zeile,
nichts wird gelöscht. Akku-Register `data/akkus.json` (ID, Zellen, mAh, Kaufdatum, ausgemustert).
„📊 Statistik“ rechnet bei jedem Aufruf alles neu aus den Logbuch-Dateien: Flugtage/Monat, Flugzeit gesamt/Monat,
Ø pro Flug, Wochen-Serie, häufigste Spots (Flugtage, Flugzeit, zuletzt), Drohnen (Flüge, Crashes, Flüge seit Crash,
Reparaturen), Akkus (Zyklen = Flüge, Flugzeit, Ø, zuletzt, „müder Akku“-Hinweis ab 8 Flügen), Wetter-Ampel der
Flugtage + Wind-Histogramm (Tagesstart-Snapshot) + Ø/max aus dem Verlauf, Crashes/Reparaturen/Teile-Verbrauch/Kosten,
Entwicklung der Flugzeit (gleitender Ø über 5 Flüge) + Ø je Monat, Rekorde. Filter von/bis/Spot/Drohne.
Nicht Erfasstes wird gezählt und als „keine Angabe“ gezeigt. Export: CSV (eine Zeile pro Flug, `;` + UTF-8-BOM für
deutsches Excel) und druckbare A4-Seite (`/druck/statistik`).
**Noch offen:** Jahresvergleich als eigenes Diagramm, Flugzeit pro Spot/Drohne als Diagramm (bisher Tabelle),
Lager-/Ladespannungs-Erinnerung, Fotos zu Reparaturen, Blackbox/OSD-Import (Flugzeit automatisch statt Eintippen),
Bearbeiten eines Eintrags (bisher: stornieren + neu eintragen).

Grundlage: pro Flugtag eine Liste **einzelner Flüge/Packs** in `fluege.jsonl` (Start/Ende oder Dauer, Akku-ID,
Drohne/Setup, optional Blackbox/OSD-Flugzeit, Ergebnis ok/Crash) + `wartung.jsonl` für Reparaturen.
Alle Kennzahlen nur aus erfassten Daten; was nicht erfasst ist, wird als „keine Angabe“ gezeigt, nicht geschätzt.
- **Flugtage pro Monat:** Balken je Monat (+ Jahresvergleich), Streaks („4 Wochenenden in Folge“).
- **Flugstunden insgesamt:** Summe der Flugdauern (gesamt, pro Jahr/Monat, pro Drohne, pro Spot); Anzahl Flüge.
- **Häufigste Spots:** Rangliste nach Flugtagen und Flugzeit, „zuletzt geflogen“, Verknüpfung zum Spot-Profil (Phase 7).
- **Verwendete Akkus:** Akku-Register (ID/Name, Zellen, mAh, Kaufdatum) → Zyklen, Flugzeit je Pack, Ø-Flugzeit,
  Ausreißer/„müder Akku“-Hinweis, letzter Einsatz; optional Lager-/Ladespannung-Erinnerung.
- **Wetterbedingungen der Flugtage:** Verteilung Ampel grün/gelb/rot, Ø/Max Wind & Böen, Temperatur-Spanne,
  „bei welchem Wind fliege ich am meisten“ (Histogramm aus den Snapshots/Verläufen von 6.1/6.5).
- **Reparaturen & Abstürze:** Crash-Zähler pro Flugtag/Drohne/Spot, Reparatur-Log (Teil, Kosten optional, Datum,
  Notiz/Foto), „Flüge seit letztem Crash“, Ersatzteil-Verbrauch (Props, Arme, Kameras …).
- **Entwicklung der Flugzeiten:** Verlauf Ø-Flugzeit pro Pack/Flug über die Zeit (gleitender Mittelwert),
  getrennt nach Drohne/Akku-Typ; persönliche Rekorde (längster Flug, meiste Packs an einem Tag).
- **Darstellung:** Desktop-Tab „📊 Statistik“ (Canvas-Diagramme, ohne Zusatzpakete), Web-Seite `/statistik` (SVG);
  Export als CSV und druckbare HTML-Seite (Print-CSS wie 6.4).

## Verteilung / Windows
- Jetzt: zip-fähiger Ordner (`make_zip.sh`), `start.bat`, `INSTALL-WINDOWS.md`
- Später: **PyInstaller**-`.exe` (`pyinstaller --noconsole --onedir main.py`, `--collect-data customtkinter`)
  – muss auf einem Windows-Rechner/CI (z. B. GitHub Actions `windows-latest`) gebaut werden
- Optional: Einstellungen nach `%LOCALAPPDATA%\FPV-Lagezentrum` statt Projektordner (Umgebungsvariable)

## Bekannte Grenzen v1.7
- Licht/Dämmerung: lokal berechnet (NOAA-Näherung, ±1–2 min), Zeiten in der Zeitzone des Rechners, ohne Gelände-
  oder Wolkenhorizont. „Gegenlicht“ ist nur ein Hinweis auf tief stehende Sonne, keine Blendungsmessung.
- dipul-Hinweis: Punkt + Quadrat ±250 m, nicht der echte Flugradius; Daten können vom Map-Tool abweichen (Stand,
  temporäre Gebiete, Modellflugplätze fehlen im WFS). „Nichts gefunden“ heißt **nicht** „Fliegen erlaubt“ – Regeln der
  offenen Kategorie, Abstände und Genehmigungen gelten trotzdem. Bei Ausfall/Rate-Limit: ehrlicher Fehler.

## Allgemeine Grenzen
- Desktop und Web schreiben dieselbe `settings.json`; laufen beide gleichzeitig, gewinnt die letzte Änderung
  (Desktop lädt fremde Änderungen erst beim Neustart).
- OpenSky zeigt nur ADS-B/MLAT-Ziele; Rettungshubschrauber in Bodennähe können fehlen.
- Verlaufspunkte entstehen nur, solange Desktop oder Web läuft (kein eigener Hintergrunddienst).
- Laufen Desktop und Web gleichzeitig, sieht der Desktop einen im Web gestarteten Flugtag spätestens nach 60 s.
- Spot-Profile: Desktop und Web schreiben dieselbe Profildatei – zuletzt gespeichert gewinnt.
- Flüge/Wartung: Einträge sind unveränderlich (Storno + neu). Die Statistik zählt nur, was eingetragen wurde.
- Akku-Zyklen = Anzahl eingetragener Flüge mit dieser Akku-ID (keine Messung von Ladezyklen).
- Karte: Kacheln kommen live von tile.openstreetmap.org (Internet nötig, kein Offline-Modus); Flugspuren gehen beim
  Neustart des Web-Servers verloren und entstehen nur, solange die Karte (oder ein anderer Radar-Abruf) läuft.
- Karte: Spot-Ampeln erscheinen erst nach „🚦 Ampeln holen“ bzw. „Wo fliege ich heute?“ (Cache 15 min, pro Prozess).
- METAR/TAF: Flugplatz-Wetter, oft 10–50 km vom Spot entfernt; kleine und militärische Plätze melden nachts/am
  Wochenende nicht – dann wird der nächste Platz mit aktueller Meldung genommen oder ehrlich „kein aktuelles METAR“ gezeigt.
  Zeiten in Ortszeit des Rechners; der Rohtext bleibt in UTC (…Z).
