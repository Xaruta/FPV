"""Wetter von Open-Meteo + Ampel-Bewertung für FPV-Flüge."""
from __future__ import annotations

import time

from app import config, geo
from app.net import get_json

WMO = {
    0: "klar", 1: "überwiegend klar", 2: "teilweise bewölkt", 3: "bedeckt", 45: "Nebel", 48: "Reifnebel",
    51: "leichter Niesel", 53: "Niesel", 55: "starker Niesel", 56: "gefrierender Niesel", 57: "gefrierender Niesel",
    61: "leichter Regen", 63: "Regen", 65: "starker Regen", 66: "gefrierender Regen", 67: "gefrierender Regen",
    71: "leichter Schnee", 73: "Schnee", 75: "starker Schnee", 77: "Schneegriesel",
    80: "Regenschauer", 81: "Regenschauer", 82: "heftige Schauer", 85: "Schneeschauer", 86: "Schneeschauer",
    95: "Gewitter", 96: "Gewitter mit Hagel", 99: "Gewitter mit Hagel",
}

CURRENT = ("temperature_2m,apparent_temperature,relative_humidity_2m,is_day,precipitation,weather_code,"
           "cloud_cover,visibility,wind_speed_10m,wind_direction_10m,wind_gusts_10m")
HOURLY = "temperature_2m,precipitation_probability,precipitation,wind_speed_10m,wind_gusts_10m,wind_direction_10m"

_cache: dict = {}


def fetch(lat: float, lon: float, force: bool = False) -> dict:
    key = (round(lat, 4), round(lon, 4))
    hit = _cache.get(key)
    if hit and not force and time.time() - hit["_t"] < config.WEATHER_MIN_INTERVAL:
        return hit
    data, _ = get_json(config.FORECAST_URL, {
        "latitude": lat, "longitude": lon, "current": CURRENT, "hourly": HOURLY,
        "daily": "sunrise,sunset", "forecast_days": 2, "forecast_hours": 8,
        "wind_speed_unit": "ms", "timezone": "Europe/Berlin",
    })
    c = data.get("current") or {}
    if not c:
        raise RuntimeError("Open-Meteo lieferte keine aktuellen Werte.")
    h = data.get("hourly") or {}
    hours = []
    for i, t in enumerate(h.get("time") or []):
        hours.append({"zeit": t[11:16], "temp": _at(h, "temperature_2m", i), "wind": _at(h, "wind_speed_10m", i),
                      "boeen": _at(h, "wind_gusts_10m", i), "richtung": _at(h, "wind_direction_10m", i),
                      "regen_pct": _at(h, "precipitation_probability", i), "regen": _at(h, "precipitation", i)})
    d = data.get("daily") or {}
    sunrise = (d.get("sunrise") or [None])[0]
    sunset = (d.get("sunset") or [None])[0]
    w = {
        "_t": time.time(),
        "abruf": time.strftime("%H:%M:%S"),
        "messzeit": (c.get("time") or "")[11:16],
        "temp": c.get("temperature_2m"), "gefuehlt": c.get("apparent_temperature"),
        "feuchte": c.get("relative_humidity_2m"), "tag": bool(c.get("is_day")),
        "regen": c.get("precipitation"), "code": c.get("weather_code"),
        "wetter": WMO.get(c.get("weather_code"), "–"),
        "wolken": c.get("cloud_cover"), "sicht": c.get("visibility"),
        "wind": c.get("wind_speed_10m"), "boeen": c.get("wind_gusts_10m"), "richtung": c.get("wind_direction_10m"),
        "richtung_txt": geo.dir_text(c.get("wind_direction_10m")),
        "pfeil": geo.wind_arrow(c.get("wind_direction_10m")),
        "sonnenaufgang": sunrise[11:16] if sunrise else None,
        "sonnenuntergang": sunset[11:16] if sunset else None,
        "stunden": hours,
        "hoehe": data.get("elevation"),
        "lat": lat, "lon": lon,
    }
    _cache[key] = w
    return w


def _at(h, k, i):
    v = h.get(k) or []
    return v[i] if i < len(v) else None


def assess(w: dict, th: dict) -> dict:
    """Ampel: 'gruen' | 'gelb' | 'rot' mit deutschen Gründen. Nur eine Orientierung!"""
    red, yellow = [], []
    wind, gust = w.get("wind") or 0, w.get("boeen") or 0
    if gust >= th["gust_max"]:
        red.append(f"Böen {gust:.1f} m/s ≥ {th['gust_max']:.0f}")
    elif gust >= th["gust_warn"]:
        yellow.append(f"Böen {gust:.1f} m/s ≥ {th['gust_warn']:.0f}")
    if wind >= th["wind_max"]:
        red.append(f"Wind {wind:.1f} m/s ≥ {th['wind_max']:.0f}")
    elif wind >= th["wind_warn"]:
        yellow.append(f"Wind {wind:.1f} m/s ≥ {th['wind_warn']:.0f}")
    rain = w.get("regen") or 0
    if rain >= th["precip_max"]:
        red.append(f"Niederschlag {rain:.1f} mm")
    elif rain > 0:
        yellow.append(f"leichter Niederschlag {rain:.1f} mm")
    code = w.get("code") or 0
    if code >= 95:
        red.append("Gewitter")
    elif code in (56, 57, 66, 67):
        red.append("gefrierender Niederschlag")
    elif code in (45, 48):
        yellow.append("Nebel")
    vis = w.get("sicht")
    if vis is not None:
        if vis < th["vis_min"]:
            red.append(f"Sicht nur {vis / 1000:.1f} km")
        elif vis < 3 * th["vis_min"]:
            yellow.append(f"Sicht {vis / 1000:.1f} km")
    t = w.get("temp")
    if t is not None and t < th["temp_min"]:
        yellow.append(f"kalt ({t:.0f} °C) – Akkus vorwärmen")
    lt = None
    if w.get("lat") is not None and w.get("lon") is not None:
        from app import sun
        lt = sun.light(w["lat"], w["lon"])     # lokal berechnet, immer „jetzt“ (auch bei Wetter aus dem Cache)
        if lt.get("warnung"):
            yellow.append(lt["warnung"])
    elif not w.get("tag", True):
        yellow.append("Dunkelheit – Nachtflug: Beleuchtung & Regeln beachten")
    if red:
        lvl, title = "rot", "Nicht fliegen"
    elif yellow:
        lvl, title = "gelb", "Mit Vorsicht"
    else:
        lvl, title = "gruen", "Gute Bedingungen"
    return {"stufe": lvl, "titel": title, "gruende": red + yellow or ["Wind, Böen, Regen und Sicht im grünen Bereich"],
            "hinweis": "Nur Wetter-Orientierung – Geozonen & Regeln immer in der dipul-Karte prüfen.", "licht": lt}
