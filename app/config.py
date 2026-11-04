"""Pfade & Grundwerte des FPV-Lagezentrums (Desktop + Web teilen sich diese Datei)."""
from __future__ import annotations

from pathlib import Path

APP_NAME = "FPV-Lagezentrum"
APP_VERSION = "1.8-public"

PROJECT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_DIR / "data"
LOG_FILE = DATA_DIR / "fpv-lagezentrum.log"
LOCK_FILE = DATA_DIR / "fpv-lagezentrum.lock"
SETTINGS_FILE = DATA_DIR / "settings.json"
RADAR_CACHE = DATA_DIR / "opensky_cache.json"
README = PROJECT_DIR / "README.md"

# Datenquellen (alle frei, ohne Schlüssel)
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPENSKY_URL = "https://opensky-network.org/api/states/all"
DIPUL_HOME = "https://www.dipul.de/homepage/de/"
DIPUL_MAP = "https://maptool-dipul.dfs.de/geozones/@{lon:.6f},{lat:.6f},{r}r?language=de&zoom=12.0"
OPENAIP_MAP = "https://www.openaip.net/map"
HTTP_TIMEOUT = 15
USER_AGENT = f"{APP_NAME}/{APP_VERSION} (+https://github.com/)"

# OpenSky anonym: ca. 400 Credits/Tag; kleine Box (<25 Quadratgrad) = 1 Credit pro Abruf.
RADAR_MIN_INTERVAL = 25      # Sekunden – Desktop & Web teilen sich den Cache
WEATHER_MIN_INTERVAL = 300   # Sekunden – Open-Meteo aktualisiert ohnehin nur 15-minütig

# Web
WEB_HOST = "127.0.0.1"
WEB_PORT = 8767
WEB_URL = f"http://{WEB_HOST}:{WEB_PORT}"
import os as _os
# Optional: Tailnet-Hostname, falls die Web-Oberfläche später per „tailscale serve“ geteilt wird (nie Funnel).
TS_HOST = _os.environ.get("FPV_TS_HOST", "")
