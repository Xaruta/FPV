"""Daten für die Karten-Ansicht (Roadmap Phase 2): Spot-Marker, Routen-Polylinien, Flugzeug-Spuren.

Keine eigenen Abrufe außer den bestehenden (OpenSky über opensky.fetch, Wetter nur aus dem Cache).
Track-Historie liegt nur im Speicher des Web-Servers (geht beim Neustart verloren – gewollt, kein Datenbestand).
"""
from __future__ import annotations

import re
import threading
import time

from app import geo, settings, spots

# „52.3759, 9.7320“ oder „52.3759 9.7320“ – Dezimalgrad mit Punkt, mindestens 3 Nachkommastellen
_PAIR = re.compile(r"(-?\d{1,2}\.\d{3,})\s*[,;/ ]\s*(-?\d{1,3}\.\d{3,})")
ROUTE_MAX_KM = 30          # Punkte weiter weg vom Spot gelten als Tippfehler → keine Linie
TRACK_LEN = 20             # Positionen je Flugzeug
TRACK_MAX_AGE = 15 * 60    # s
_TRACKS: dict[str, list] = {}
_TLOCK = threading.Lock()
_last_abruf = None


def route_points(text: str, lat: float, lon: float) -> list[list[float]] | None:
    """Koordinaten-Paare aus einem Routen-Text. Nur wenn ≥ 2 gültige Paare in der Nähe des Spots → Polylinie."""
    pts = []
    for a, b in _PAIR.findall(text or ""):
        la, lo = float(a), float(b)
        if -90 <= la <= 90 and -180 <= lo <= 180 and geo.haversine_km(lat, lon, la, lo) <= ROUTE_MAX_KM:
            pts.append([la, lo])
    return pts if len(pts) >= 2 else None


def spot_layer(cfg: dict | None = None) -> dict:
    from app import weather
    cfg = cfg or settings.load()
    profs = spots.profiles(cfg)
    ws, abruf = spots.cached_weather(profs)
    act = settings.active_spot(cfg)
    out = []
    for p, w in zip(profs, ws):
        amp = weather.assess(w, cfg["thresholds"]) if w else None
        st = spots.day_stats(p, cfg)
        routes = []
        for r in p.get("routen") or []:
            routes.append({"text": r, "punkte": route_points(r, p["lat"], p["lon"])})
        sp = p.get("startplatz") or {}
        out.append({
            "id": p["id"], "name": p["name"], "lat": p["lat"], "lon": p["lon"], "region": p.get("region") or "",
            "hoehe": p.get("hoehe"), "aktiv": bool(act and act["name"] == p["name"]),
            "startplatz": [sp["lat"], sp["lon"]] if sp.get("lat") is not None and sp.get("lon") is not None else None,
            "startplatz_text": sp.get("text") or "",
            "gelaende": (p.get("gelaende") or {}).get("tags") or [],
            "gefahren": [{"art": g["art"], "stufe": g["stufe"], "text": g["text"]} for g in p.get("gefahren") or []],
            "hindernisse": len(p.get("hindernisse") or []), "bewertung": (p.get("bewertung") or {}).get("gesamt"),
            "routen": routes, "flugtage": st["flugtage"], "zuletzt": st["zuletzt"], "links": spots.links(p),
            "ampel": amp["stufe"] if amp else None, "ampel_titel": amp["titel"] if amp else None,
            "gruende": amp["gruende"][:3] if amp else [],
            "wind": w.get("wind") if w else None, "boeen": w.get("boeen") if w else None,
            "messzeit": w.get("messzeit") if w else None,
        })
    return {"spots": out, "aktiv": act, "wetter_abruf": abruf,
            "wetter_hinweis": None if abruf else "Ampel noch nicht abgerufen – „🚦 Ampeln holen“ (ein Open-Meteo-Abruf)."}


def update_tracks(radar: dict) -> dict[str, list]:
    """Neue Positionen aus einem OpenSky-Ergebnis anhängen (nur bei neuem Abruf), alte Spuren verwerfen."""
    global _last_abruf
    now = time.time()
    with _TLOCK:
        stamp = (radar.get("key"), radar.get("t"))
        if radar.get("t") and stamp != _last_abruf:
            _last_abruf = stamp
            for p in radar.get("flugzeuge") or []:
                tr = _TRACKS.setdefault(p["icao24"], [])
                pos = [p["lat"], p["lon"], now]
                if not tr or tr[-1][:2] != pos[:2]:
                    tr.append(pos)
                    del tr[:-TRACK_LEN]
        for k in [k for k, tr in _TRACKS.items() if now - tr[-1][2] > TRACK_MAX_AGE]:
            del _TRACKS[k]
        return {k: [x[:2] for x in tr] for k, tr in _TRACKS.items()}
