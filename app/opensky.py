"""Kleines Flugradar über die OpenSky Network REST-API (anonym, mit Tageslimit).

Ergebnisse werden in data/opensky_cache.json zwischengespeichert, damit Desktop und Web sich
das anonyme Kontingent (ca. 400 Credits/Tag) teilen und nicht doppelt abfragen.
"""
from __future__ import annotations

import json
import os
import time

from app import config, geo
from app.net import NetError, get_json


def _read_cache():
    try:
        with open(config.RADAR_CACHE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:  # noqa: BLE001
        return None


def _write_cache(obj):
    try:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = config.RADAR_CACHE.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, config.RADAR_CACHE)
    except OSError:
        pass


def fetch(lat: float, lon: float, box: float = 0.5, force: bool = False) -> dict:
    box = min(max(float(box), 0.1), 2.0)
    key = f"{lat:.4f},{lon:.4f},{box:.2f}"
    c = _read_cache()
    age_ok = config.RADAR_MIN_INTERVAL if force else 50
    if c and c.get("key") == key and time.time() - c.get("t", 0) < age_ok:
        c["aus_cache"] = True
        return c
    params = {"lamin": round(lat - box, 4), "lamax": round(lat + box, 4),
              "lomin": round(lon - box, 4), "lomax": round(lon + box, 4)}
    try:
        data, headers = get_json(config.OPENSKY_URL, params, timeout=20)
    except NetError as e:
        if e.status == 429:
            msg = "OpenSky-Tageskontingent (anonym) erschöpft – später erneut versuchen."
        elif e.status in (502, 503, 504):
            msg = "OpenSky ist gerade überlastet – gleich nochmal versuchen."
        else:
            msg = f"OpenSky nicht erreichbar: {e}"
        if c and c.get("key") == key:
            c.update({"fehler": msg, "aus_cache": True})
            return c
        return {"key": key, "t": 0, "flugzeuge": [], "fehler": msg, "rest": None, "abruf": None}
    planes = []
    for s in data.get("states") or []:
        try:
            plat, plon = s[6], s[5]
            if plat is None or plon is None:
                continue
            alt = s[13] if s[13] is not None else s[7]
            dist = geo.haversine_km(lat, lon, plat, plon)
            planes.append({
                "icao24": s[0], "rufzeichen": (s[1] or "").strip() or s[0].upper(), "land": s[2],
                "lat": plat, "lon": plon, "boden": bool(s[8]),
                "hoehe_m": round(alt) if alt is not None else None,
                "speed_kmh": round(s[9] * 3.6) if s[9] is not None else None,
                "kurs": round(s[10]) if s[10] is not None else None,
                "steig": round(s[11], 1) if s[11] is not None else None,
                "squawk": s[14],
                "dist_km": round(dist, 1),
                "peilung": geo.dir_text(geo.bearing_deg(lat, lon, plat, plon)),
                "alter_s": int(data.get("time", time.time()) - (s[4] or 0)),
            })
        except (IndexError, TypeError):
            continue
    planes.sort(key=lambda p: p["dist_km"])
    rest = headers.get("X-Rate-Limit-Remaining") or headers.get("x-rate-limit-remaining")
    out = {"key": key, "t": time.time(), "abruf": time.strftime("%H:%M:%S"), "flugzeuge": planes,
           "fehler": None, "rest": int(rest) if rest and str(rest).isdigit() else None,
           "box": box, "aus_cache": False}
    _write_cache(out)
    return out


def alt_class(p: dict) -> str:
    """Grobe Einordnung für FPV: tief fliegende Luftfahrzeuge in der Nähe sind relevant."""
    h = p.get("hoehe_m")
    if p.get("boden"):
        return "am Boden"
    if h is None:
        return "?"
    if h < 600 and p.get("dist_km", 99) < 10:
        return "TIEF & NAH"
    if h < 1000:
        return "tief"
    return ""
