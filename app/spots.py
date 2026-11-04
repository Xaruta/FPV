"""Spot-Datenbank (Roadmap Phase 7).

Jeder Spot hat ein Profil:  <spots_dir>/<spot-id>/profil.json  +  medien/
`settings.json → spots` bleibt die schlanke Liste (id, name, lat, lon, region), damit Wetter/Radar/Logbuch
unverändert funktionieren. Fehlt ein Profil, wird es aus diesem Eintrag angelegt (Migration, nichts geht verloren).
Die App löscht nie ein Profil oder einen Medienordner – „Spot löschen“ entfernt nur den Listeneintrag.
"""
from __future__ import annotations

import copy
import json
import logging
import os
import re
import tempfile
import threading
import time
import unicodedata
from pathlib import Path

from app import config, geo, settings
from app.net import get_json

log = logging.getLogger("spots")
_LOCK = threading.Lock()
SCHEMA = 1

GELAENDE_TAGS = ["Wiese", "Feld", "Wald", "Industrie", "Bando", "Hügel", "Wasser", "Strand", "Park", "Sandgrube"]
HINDERNIS_ARTEN = ["Bäume", "Stromleitung", "Mast", "Gebäude", "Zaun", "Windrad", "Sonstiges"]
GEFAHR_ARTEN = ["Straße", "Bahn", "Hochspannung", "Spazierweg", "Tiere/Weide", "Wasser", "Wohnhäuser", "Sonstiges"]
STUFEN = ["niedrig", "mittel", "hoch"]
FUNK_SYSTEME = ["", "Analog", "DJI O3/O4", "HDZero", "Walksnail", "gemischt"]
BEWERTUNG_KAT = ["gesamt", "freestyle", "cinematic", "race", "ruhe", "erreichbarkeit"]

EMPTY = {
    "schema": SCHEMA, "id": "", "name": "", "lat": None, "lon": None, "region": "", "hoehe": None,
    "startplatz": {"lat": None, "lon": None, "text": ""},
    "gelaende": {"tags": [], "untergrund": "", "groesse": "", "windschutz": "", "thermik": "",
                 "zugang": "", "besucher": "", "text": ""},
    "hindernisse": [],      # [{"art", "text", "hoehe_m"}]
    "routen": [],           # ["Gap zwischen den Eichen", …]
    "gefahren": [],         # [{"art", "text", "stufe", "checkliste": bool}]
    "funk": {"system": "", "vtx_kanal": "", "stoerquellen": "", "reichweite": "", "link": "", "mobilfunk": "",
             "text": ""},
    "bewertung": {k: 0 for k in BEWERTUNG_KAT},   # 0 = nicht bewertet, sonst 1–5
    "notizen": "",          # privat – beim Export standardmäßig weggelassen
    "erstellt": None, "geaendert": None,
}


# ------------------------------------------------------------------ Pfade & Helfer
def spots_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or settings.load()
    raw = (cfg.get("spots_dir") or "").strip()
    p = Path(os.path.expandvars(os.path.expanduser(raw))) if raw else config.PROJECT_DIR / "spots"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def slug(name: str) -> str:
    s = (name or "").strip().lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        s = s.replace(a, b)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:40]
    return s or "spot"


def _spot_dir(sid: str, base: Path | None = None) -> Path:
    base = base or spots_dir()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,50}", sid or ""):
        raise ValueError("Ungültige Spot-ID.")
    return base / sid


def _write_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _num(v, lo=None, hi=None):
    if v in (None, ""):
        return None
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        raise ValueError(f"Keine Zahl: {v}") from None
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        raise ValueError(f"Wert außerhalb des Bereichs: {v}")
    return x


def _txt(v, n=500) -> str:
    return str(v or "").strip()[:n]


def normalize(p: dict) -> dict:
    """Profil auf das Schema bringen (fehlende Felder ergänzen, Typen prüfen). Wirft ValueError bei Unsinn."""
    out = copy.deepcopy(EMPTY)
    p = p if isinstance(p, dict) else {}
    out["id"] = _txt(p.get("id"), 51)
    out["name"] = _txt(p.get("name"), 60)
    out["lat"] = _num(p.get("lat"), -90, 90)
    out["lon"] = _num(p.get("lon"), -180, 180)
    if out["lat"] is None or out["lon"] is None:
        raise ValueError("Spot braucht gültige Koordinaten.")
    out["region"] = _txt(p.get("region"), 200)
    out["hoehe"] = _num(p.get("hoehe"), -500, 9000)
    sp = p.get("startplatz") or {}
    out["startplatz"] = {"lat": _num(sp.get("lat"), -90, 90), "lon": _num(sp.get("lon"), -180, 180),
                         "text": _txt(sp.get("text"), 300)}
    g = p.get("gelaende") or {}
    out["gelaende"] = {k: _txt(g.get(k), 1000) for k in EMPTY["gelaende"] if k != "tags"}
    out["gelaende"]["tags"] = [_txt(t, 30) for t in (g.get("tags") or []) if _txt(t, 30)][:20]
    out["hindernisse"] = [{"art": _txt(h.get("art"), 40), "text": _txt(h.get("text"), 300),
                           "hoehe_m": _num(h.get("hoehe_m"), 0, 1000)}
                          for h in (p.get("hindernisse") or []) if isinstance(h, dict)
                          and (_txt(h.get("text")) or _txt(h.get("art")))][:50]
    out["routen"] = [_txt(r, 300) for r in (p.get("routen") or []) if _txt(r)][:50]
    out["gefahren"] = []
    for h in p.get("gefahren") or []:
        if not isinstance(h, dict) or not (_txt(h.get("text")) or _txt(h.get("art"))):
            continue
        st = h.get("stufe") if h.get("stufe") in STUFEN else "mittel"
        out["gefahren"].append({"art": _txt(h.get("art"), 40), "text": _txt(h.get("text"), 300), "stufe": st,
                                "checkliste": bool(h.get("checkliste", True))})
    out["gefahren"] = out["gefahren"][:50]
    f = p.get("funk") or {}
    out["funk"] = {k: _txt(f.get(k), 1000) for k in EMPTY["funk"]}
    b = p.get("bewertung") or {}
    out["bewertung"] = {}
    for k in BEWERTUNG_KAT:
        try:
            out["bewertung"][k] = max(0, min(5, int(float(b.get(k) or 0))))
        except (TypeError, ValueError):
            out["bewertung"][k] = 0
    out["notizen"] = _txt(p.get("notizen"), 5000)
    out["erstellt"] = p.get("erstellt") or _now()
    out["geaendert"] = p.get("geaendert")
    return out


# ------------------------------------------------------------------ Laden / Speichern / Migration
def load(sid: str, cfg: dict | None = None) -> dict | None:
    f = _spot_dir(sid, spots_dir(cfg)) / "profil.json"
    try:
        return normalize(json.loads(f.read_text(encoding="utf-8")))
    except FileNotFoundError:
        return None
    except Exception as e:  # noqa: BLE001 – kaputte Datei nie überschreiben
        log.warning("Profil %s nicht lesbar: %s", sid, e)
        raise ValueError(f"Profil {sid} ist beschädigt – bitte {f} prüfen.") from e


def _unique_id(name: str, base: Path, taken: set[str]) -> str:
    stem = slug(name)
    sid, i = stem, 2
    while sid in taken or (base / sid).exists():
        sid, i = f"{stem}-{i}", i + 1
    return sid


def migrate(cfg: dict | None = None) -> dict:
    """Spots aus settings.json mit ID versehen und fehlende Profile anlegen. Idempotent, verliert nichts."""
    own = cfg is None
    cfg = cfg or settings.load()
    base = spots_dir(cfg)
    changed = False
    with _LOCK:
        taken = {s["id"] for s in cfg["spots"] if s.get("id")}
        for s in cfg["spots"]:
            if not s.get("id"):
                # vorhandenes Profil gleichen Namens wiederverwenden (z. B. nach Löschen & Neuanlegen)
                same = next((f.parent.name for f in base.glob("*/profil.json") if _name_of(f) == s["name"]
                             and f.parent.name not in taken), None) if base.exists() else None
                s["id"] = same or _unique_id(s["name"], base, taken)
                taken.add(s["id"])
                changed = True
            d = base / s["id"]
            if not (d / "profil.json").exists():
                prof = normalize({**s, "erstellt": _now()})
                _write_json(d / "profil.json", prof)
                log.info("Spot-Profil angelegt: %s", s["id"])
            else:  # Koordinaten/Region, die über die einfache Spot-Maske geändert wurden, ins Profil übernehmen
                try:
                    prof = load(s["id"], cfg)
                except ValueError:
                    prof = None
                if prof and (abs(prof["lat"] - s["lat"]) > 1e-6 or abs(prof["lon"] - s["lon"]) > 1e-6
                             or (s.get("region") and s["region"] != prof["region"]) or prof["name"] != s["name"]):
                    prof.update(lat=s["lat"], lon=s["lon"], name=s["name"], region=s.get("region") or prof["region"],
                                geaendert=_now())
                    _write_json(d / "profil.json", prof)
            (d / "medien").mkdir(parents=True, exist_ok=True)
    if changed and own:
        settings.save(cfg)
    return cfg


def _name_of(f: Path) -> str | None:
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("name")
    except Exception:  # noqa: BLE001
        return None


def save(profile: dict, cfg: dict | None = None) -> dict:
    """Profil speichern und den schlanken Eintrag in settings.json nachziehen (Name/Koordinaten/Region)."""
    own = cfg is None
    cfg = cfg or settings.load()
    p = normalize(profile)
    if not p["name"]:
        raise ValueError("Spot braucht einen Namen.")
    base = spots_dir(cfg)
    with _LOCK:
        others = [s for s in cfg["spots"] if s.get("id") != p["id"]]
        if any(s.get("name") == p["name"] for s in others):
            raise ValueError(f"Es gibt schon einen Spot „{p['name']}“.")
        if not p["id"]:
            p["id"] = _unique_id(p["name"], base, {s.get("id") for s in cfg["spots"]})
        p["geaendert"] = _now()
        d = _spot_dir(p["id"], base)
        _write_json(d / "profil.json", p)
        (d / "medien").mkdir(parents=True, exist_ok=True)
        old = next((s for s in cfg["spots"] if s.get("id") == p["id"]), None)
        entry = {"id": p["id"], "name": p["name"], "lat": round(p["lat"], 6), "lon": round(p["lon"], 6)}
        if p["region"]:
            entry["region"] = p["region"]
        if old is not None:
            if cfg.get("active") == old.get("name"):
                cfg["active"] = p["name"]
            cfg["spots"] = [entry if s is old else s for s in cfg["spots"]]
        else:
            cfg["spots"].append(entry)
    if own:
        settings.save(cfg)
    return p


def profiles(cfg: dict | None = None) -> list[dict]:
    cfg = migrate(cfg) if cfg else migrate()
    out = []
    for s in cfg["spots"]:
        try:
            p = load(s["id"], cfg)
        except ValueError:
            p = None
        out.append(p or normalize(s))
    return out


def by_name(name: str, cfg: dict | None = None) -> dict | None:
    cfg = cfg or settings.load()
    s = next((x for x in cfg["spots"] if x.get("name") == name), None)
    if not s:
        return None
    if not s.get("id"):
        migrate()
        cfg = settings.load()
        s = next((x for x in cfg["spots"] if x.get("name") == name), None)
    return load(s["id"], cfg) if s and s.get("id") else None


def active_profile(cfg: dict | None = None) -> dict | None:
    cfg = cfg or settings.load()
    sp = settings.active_spot(cfg)
    return by_name(sp["name"], cfg) if sp else None


# ------------------------------------------------------------------ Links, Medien, Checkliste, Statistik
def links(p: dict) -> dict:
    lat, lon = p["lat"], p["lon"]
    return {
        "dipul": geo.dipul_url(lat, lon),
        "osm": f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=16/{lat:.5f}/{lon:.5f}",
        "openaip": config.OPENAIP_MAP,   # OpenAIP hat keine dokumentierten Koordinaten-Parameter → Karte öffnen
        "gps": f"{lat:.6f}, {lon:.6f}",
    }


def media_dir(sid: str, cfg: dict | None = None) -> Path:
    d = _spot_dir(sid, spots_dir(cfg)) / "medien"
    d.mkdir(parents=True, exist_ok=True)
    return d


def media(sid: str, cfg: dict | None = None) -> list[str]:
    from app import logbook
    d = media_dir(sid, cfg)
    return sorted(f.name for f in d.iterdir() if f.is_file() and f.suffix.lower() in logbook.MEDIA_EXT)


STUFE_ICON = {"hoch": "🔴", "mittel": "🟡", "niedrig": "🟢"}


def checklist_extras(p: dict | None, min_stufe: str = "niedrig") -> list[str]:
    """Gefahrenstellen des Spots als zusätzliche Checklisten-Hinweise (hoch zuerst)."""
    if not p:
        return []
    lvl = STUFEN.index(min_stufe)
    items = [g for g in p.get("gefahren") or [] if g.get("checkliste") and STUFEN.index(g["stufe"]) >= lvl]
    items.sort(key=lambda g: -STUFEN.index(g["stufe"]))
    return [f"{STUFE_ICON[g['stufe']]} {g['art'] or 'Gefahr'}{': ' + g['text'] if g['text'] else ''} – beachtet?"
            for g in items]


def day_stats(p: dict, cfg: dict | None = None) -> dict:
    """Flugtage an diesem Spot aus dem Logbuch-Index (Phase 6) – per Spot-ID, ältere Tage per Name."""
    from app import logbook
    try:
        rows = logbook.search("", cfg, limit=100000)
    except Exception:  # noqa: BLE001
        rows = []
    mine = [r for r in rows if r.get("spot_id") == p["id"] or (not r.get("spot_id") and r.get("spot") == p["name"])]
    return {"flugtage": len(mine), "zuletzt": max((r.get("datum") or "" for r in mine), default=None) or None,
            "ordner": [r["ordner"] for r in mine[:20]]}


# ------------------------------------------------------------------ Export / Import
def export(sid: str, privat: bool = False, cfg: dict | None = None) -> dict:
    p = load(sid, cfg)
    if not p:
        raise ValueError("Spot-Profil nicht gefunden.")
    out = copy.deepcopy(p)
    if not privat:
        out["notizen"] = ""
    out.pop("id", None)
    return {"format": "fpv-lagezentrum-spot", "version": SCHEMA, "exportiert": _now(),
            "hinweis": "Spot-Profil ohne Medien. Geozonen immer selbst in der dipul-Karte prüfen.", "spot": out}


def import_profile(data: dict, cfg: dict | None = None) -> dict:
    if not isinstance(data, dict):
        raise ValueError("Keine gültige Spot-Datei.")
    prof = data.get("spot") if isinstance(data.get("spot"), dict) else data
    if not isinstance(prof, dict):
        raise ValueError("Keine gültige Spot-Datei.")
    own = cfg is None
    cfg = cfg or settings.load()
    p = normalize({**prof, "id": ""})
    names = {s["name"] for s in cfg["spots"]}
    base, i = p["name"] or "Import", 2
    p["name"] = base
    while p["name"] in names:
        p["name"], i = f"{base} ({i})", i + 1
    p["erstellt"] = _now()
    p = save(p, cfg)
    if own:
        settings.save(cfg)
    return p


# ------------------------------------------------------------------ „Wo fliege ich heute?“
_multi_cache: dict = {}
MULTI_TTL = 900   # 15 min


def fetch_many(coords: list[tuple[float, float]], force: bool = False) -> list[dict | None]:
    """Ein Open-Meteo-Abruf für mehrere Koordinaten (nur aktuelle Werte). Ergebnis je Spot oder None."""
    from app import weather
    if not coords:
        return []
    key = tuple((round(a, 4), round(b, 4)) for a, b in coords)
    hit = _multi_cache.get(key)
    if hit and not force and time.time() - hit[0] < MULTI_TTL:
        return hit[1]
    data, _ = get_json(config.FORECAST_URL, {
        "latitude": ",".join(f"{a:.5f}" for a, _ in coords), "longitude": ",".join(f"{b:.5f}" for _, b in coords),
        "current": weather.CURRENT, "wind_speed_unit": "ms", "timezone": "Europe/Berlin",
    })
    rows = data if isinstance(data, list) else [data]
    out = []
    for r in rows:
        c = (r or {}).get("current") or {}
        if not c:
            out.append(None)
            continue
        out.append({"messzeit": (c.get("time") or "")[11:16], "temp": c.get("temperature_2m"),
                    "tag": bool(c.get("is_day")), "regen": c.get("precipitation"), "code": c.get("weather_code"),
                    "wetter": weather.WMO.get(c.get("weather_code"), "–"), "sicht": c.get("visibility"),
                    "wind": c.get("wind_speed_10m"), "boeen": c.get("wind_gusts_10m"),
                    "richtung": c.get("wind_direction_10m"), "richtung_txt": geo.dir_text(c.get("wind_direction_10m")),
                    "hoehe": (r or {}).get("elevation")})
    while len(out) < len(coords):
        out.append(None)
    _multi_cache[key] = (time.time(), out, time.strftime("%H:%M:%S"))
    return out


AMPEL_RANG = {"gruen": 0, "gelb": 1, "rot": 2, None: 3}


def today(sort: str = "kombi", lat: float | None = None, lon: float | None = None, force: bool = False,
          cfg: dict | None = None) -> dict:
    """Spots mit Entfernung und echter Ampel. sort: kombi | distanz | wetter | bewertung | zuletzt."""
    from app import weather
    cfg = migrate(cfg) if cfg else migrate()
    profs = profiles(cfg)
    origin_txt = "Gerätestandort"
    if lat is None or lon is None:
        sp = settings.active_spot(cfg)
        lat, lon = (sp["lat"], sp["lon"]) if sp else (None, None)
        origin_txt = f"aktiver Spot „{sp['name']}“" if sp else "–"
    err = None
    try:
        ws = fetch_many([(p["lat"], p["lon"]) for p in profs], force=force)
    except Exception as e:  # noqa: BLE001 – ehrlich melden, Liste trotzdem zeigen
        err = f"Wetter nicht abrufbar: {e}"
        ws = [None] * len(profs)
    rows = []
    for p, w in zip(profs, ws):
        amp = weather.assess(w, cfg["thresholds"]) if w else None
        st = day_stats(p, cfg)
        if w and w.get("hoehe") is not None and p.get("hoehe") is None:
            try:  # Höhe (Open-Meteo-Elevation) einmalig ins Profil übernehmen – nur die Profildatei, nie settings
                f = _spot_dir(p["id"], spots_dir(cfg)) / "profil.json"
                if f.exists():
                    p["hoehe"] = w["hoehe"]
                    with _LOCK:
                        _write_json(f, p)
            except Exception:  # noqa: BLE001
                pass
        rows.append({
            "id": p["id"], "name": p["name"], "region": p["region"], "lat": p["lat"], "lon": p["lon"],
            "distanz_km": round(geo.haversine_km(lat, lon, p["lat"], p["lon"]), 1) if lat is not None else None,
            "wetter": w, "ampel": amp["stufe"] if amp else None, "ampel_titel": amp["titel"] if amp else "unbekannt",
            "gruende": amp["gruende"] if amp else ([err] if err else ["keine Daten"]),
            "bewertung": p["bewertung"]["gesamt"], "gefahren_hoch": sum(1 for g in p["gefahren"] if g["stufe"] == "hoch"),
            "flugtage": st["flugtage"], "zuletzt": st["zuletzt"], "links": links(p),
        })
    big = 1e9
    keys = {
        "distanz": lambda r: (r["distanz_km"] if r["distanz_km"] is not None else big,),
        "wetter": lambda r: (AMPEL_RANG[r["ampel"]], (r["wetter"] or {}).get("boeen") or big),
        "bewertung": lambda r: (-r["bewertung"], r["distanz_km"] or big),
        "zuletzt": lambda r: (r["zuletzt"] is None, "" if r["zuletzt"] is None else
                              "".join(chr(255 - ord(ch)) for ch in r["zuletzt"])),
        "kombi": lambda r: (AMPEL_RANG[r["ampel"]], r["distanz_km"] if r["distanz_km"] is not None else big),
    }
    rows.sort(key=keys.get(sort, keys["kombi"]))
    hit = next((v for k, v in _multi_cache.items() if v[1] is ws), None)
    return {"spots": rows, "sort": sort if sort in keys else "kombi", "ursprung": origin_txt, "fehler": err,
            "abruf": hit[2] if hit else None, "quelle": "Open-Meteo (aktuelle Werte, Cache 15 min)",
            "hinweis": "Nur Wetter-Orientierung – Geozonen & Regeln immer in der dipul-Karte prüfen. Kein Rechtsrat."}


def cached_weather(profs: list[dict]) -> tuple[list[dict | None], str | None]:
    """Nur schon vorhandene Werte aus dem 15-min-Cache von fetch_many – löst KEINEN Abruf aus."""
    key = tuple((round(p["lat"], 4), round(p["lon"], 4)) for p in profs)
    hit = _multi_cache.get(key)
    if hit and time.time() - hit[0] < MULTI_TTL:
        return hit[1], hit[2]
    return [None] * len(profs), None
