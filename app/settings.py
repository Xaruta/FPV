"""Einstellungen in data/settings.json: Spots, aktiver Spot, Grenzwerte, Checkliste."""
from __future__ import annotations

import copy
import json
import os
import tempfile
import threading

from app import config

DEFAULT_THRESHOLDS = {
    "wind_warn": 6.0,    # m/s Mittelwind – gelb
    "wind_max": 9.0,     # m/s Mittelwind – rot
    "gust_warn": 8.0,    # m/s Böen – gelb
    "gust_max": 11.0,    # m/s Böen – rot
    "precip_max": 0.5,   # mm/h – ab hier rot (darunter >0 = gelb)
    "vis_min": 1500.0,   # m – darunter rot (unter 3x = gelb)
    "temp_min": 3.0,     # °C – darunter gelb (LiPo kalt!)
}

DEFAULT_CHECKLIST = [
    "Akkus geladen & warm (LiPo > 15 °C), Spannung geprüft",
    "Props fest, unbeschädigt, richtige Drehrichtung",
    "VTX-Kanal/Leistung gesetzt, Brille auf gleichem Kanal",
    "Antennen dran (VTX + RX) – nie ohne Antenne einschalten!",
    "GPS-Fix / Home-Point gesetzt",
    "Failsafe getestet (Funke aus → Drohne reagiert richtig)",
    "Arm-Switch & Modi geprüft, Throttle unten",
    "dipul-Karte gecheckt: keine Geozone / Genehmigung vorhanden",
    "Spotter / Umfeld frei – keine Menschen, Tiere, Straßen",
    "Versicherung & e-ID (Kennzeichnung) an der Drohne",
]

DEFAULTS = {
    "spots": [],            # [{"name": "Haus", "lat": 52.1, "lon": 9.9}]
    "active": None,         # Name des aktiven Spots
    "thresholds": DEFAULT_THRESHOLDS,
    "radar_box_deg": 0.5,   # ± Grad um den Spot
    "radar_auto": True,
    "radar_interval": 60,   # Sekunden
    "checklist": [{"text": t, "done": False} for t in DEFAULT_CHECKLIST],
    "logs_dir": "",         # leer = <Projekt>/logs ; sonst absoluter Pfad oder ~/…
    "verlauf_minuten": 15,
    "spots_dir": "",        # leer = <Projekt>/spots (Spot-Profile + Spot-Medien)
}

_LOCK = threading.Lock()


def load() -> dict:
    data = copy.deepcopy(DEFAULTS)
    try:
        with open(config.SETTINGS_FILE, encoding="utf-8") as f:
            stored = json.load(f)
        if isinstance(stored, dict):
            data.update({k: v for k, v in stored.items() if k in DEFAULTS})
            th = copy.deepcopy(DEFAULT_THRESHOLDS)
            th.update(stored.get("thresholds") or {})
            data["thresholds"] = th
    except FileNotFoundError:
        pass
    except Exception:  # noqa: BLE001 – kaputte Datei nicht löschen, nur Standardwerte nehmen
        pass
    return data


def save(data: dict) -> None:
    with _LOCK:
        config.DATA_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=config.DATA_DIR, prefix=".settings_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, config.SETTINGS_FILE)


def active_spot(data: dict) -> dict | None:
    for s in data.get("spots") or []:
        if s.get("name") == data.get("active"):
            return s
    spots = data.get("spots") or []
    return spots[0] if spots else None


def upsert_spot(data: dict, name: str, lat: float, lon: float, region: str | None = None) -> dict:
    name = (name or "").strip() or f"Spot {len(data['spots']) + 1}"
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError("Koordinaten außerhalb des gültigen Bereichs.")
    old = next((s for s in data["spots"] if s.get("name") == name), {})
    spot = {"name": name, "lat": round(lat, 6), "lon": round(lon, 6)}
    if old.get("id"):
        spot["id"] = old["id"]   # Profil (spots/<id>/) bleibt verknüpft
    reg = (region or "").strip() or (old.get("region") if old and abs(old.get("lat", 0) - lat) < 0.01
                                      and abs(old.get("lon", 0) - lon) < 0.01 else None)
    if reg:
        spot["region"] = reg
    if old:
        data["spots"] = [spot if s is old else s for s in data["spots"]]
    else:
        data["spots"].append(spot)
    data["active"] = name
    return spot


def remove_spot(data: dict, name: str) -> None:
    """Entfernt nur den Listeneintrag – das Profil unter spots/<id>/ bleibt erhalten."""
    data["spots"] = [s for s in data["spots"] if s.get("name") != name]
    if data.get("active") == name:
        data["active"] = data["spots"][0]["name"] if data["spots"] else None
