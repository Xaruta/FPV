"""Geocoding (Open-Meteo), Distanz/Kurs und Links zu offiziellen Karten."""
from __future__ import annotations

import math

from app import config
from app.net import get_json

DIRS = ["N", "NNO", "NO", "ONO", "O", "OSO", "SO", "SSO", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"]
ARROWS = ["↑", "↗", "→", "↘", "↓", "↙", "←", "↖"]


def geocode(name: str, count: int = 5) -> list[dict]:
    name = (name or "").strip()
    if len(name) < 2:
        raise ValueError("Bitte mindestens 2 Zeichen eingeben.")
    data, _ = get_json(config.GEOCODE_URL, {"name": name, "count": count, "language": "de", "format": "json"})
    out = []
    for r in data.get("results") or []:
        label = ", ".join(x for x in (r.get("name"), r.get("admin1"), r.get("country")) if x)
        out.append({"name": r.get("name"), "label": label, "lat": r["latitude"], "lon": r["longitude"],
                    "elevation": r.get("elevation")})
    return out


def haversine_km(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 6371.0088 * 2 * math.asin(math.sqrt(a))


def bearing_deg(lat1, lon1, lat2, lon2) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def dir_text(deg) -> str:
    if deg is None:
        return "–"
    return DIRS[int((float(deg) % 360) / 22.5 + 0.5) % 16]


def wind_arrow(from_deg) -> str:
    """Pfeil in die Richtung, in die der Wind weht (Wind kommt AUS from_deg)."""
    if from_deg is None:
        return "·"
    to = (float(from_deg) + 180) % 360
    return ARROWS[int(to / 45 + 0.5) % 8]


def dipul_url(lat: float, lon: float, radius_m: int = 1000) -> str:
    return config.DIPUL_MAP.format(lat=lat, lon=lon, r=int(radius_m))
