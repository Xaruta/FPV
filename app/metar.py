"""METAR/TAF des nächsten Flugplatzes (Roadmap Phase 4).

Quelle: aviationweather.gov Data API (NOAA/NWS, frei, ohne Schlüssel):
  /api/data/stationinfo?bbox=…  → Wetterstationen (Flugplätze mit METAR/TAF) rund um den Spot
  /api/data/metar?ids=…&hours=3 → Meldungen (JSON, inkl. rawOb)
  /api/data/taf?ids=…           → Vorhersagen (JSON, inkl. rawTAF + fcsts)
Es werden nur echte Meldungen angezeigt. Bei Fehlern: letzter gespeicherter Stand mit Hinweis oder gar nichts.
METAR = Wetter am Flugplatz, NICHT am Spot.
"""
from __future__ import annotations

import json
import re
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

from app import config, geo

API = "https://aviationweather.gov/api/data"
STATIONS_FILE = config.DATA_DIR / "metar_stationen.json"
CACHE_FILE = config.DATA_DIR / "metar_cache.json"
STATIONS_TTL = 30 * 86400      # Stationsliste ändert sich kaum
METAR_TTL = 600                # METAR kommt halbstündlich/stündlich – 10 min Cache reicht
FORCE_MIN = 60                 # „Neu laden“ frühestens nach 60 s
MAX_KM = 150                   # weiter weg ist für den Spot wertlos
MAX_AGE_MIN = 180              # ältere METARs gelten nicht als aktuell
OLD_MIN = 90                   # ab hier „veraltet“-Hinweis
HINWEIS = ("METAR/TAF = Wetter am Flugplatz, nicht an deinem Spot (Entfernung, Gelände, Küste/Binnenland). "
           "Für die Ampel zählt das Spot-Wetter von Open-Meteo. Kein Ersatz für eine offizielle Flugwetterberatung.")
_CTX = ssl.create_default_context()


class MetarError(RuntimeError):
    pass


def _get(path: str, params: dict, timeout: int = 20):
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_CTX) as r:
            body = r.read().decode("utf-8").strip()
            if r.status == 204 or not body:
                return []
            return json.loads(body)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            raise MetarError("aviationweather.gov: zu viele Abfragen (429) – bitte später erneut") from e
        raise MetarError(f"aviationweather.gov antwortet mit HTTP {e.code}") from e
    except urllib.error.URLError as e:
        raise MetarError(f"aviationweather.gov nicht erreichbar ({e.reason})") from e
    except TimeoutError as e:
        raise MetarError("aviationweather.gov: Zeitüberschreitung") from e
    except json.JSONDecodeError as e:
        raise MetarError("aviationweather.gov: Antwort war kein gültiges JSON") from e


def _read(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _write(path, obj):
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)
    except OSError:
        pass


# ---------------------------------------------------------------- Stationen
def stations(lat: float, lon: float) -> list[dict]:
    """Flugplätze mit METAR/TAF um den Spot, sortiert nach Entfernung (Cache 30 Tage)."""
    key = f"{lat:.2f},{lon:.2f}"
    cache = _read(STATIONS_FILE, {})
    hit = cache.get(key)
    if hit and time.time() - hit.get("t", 0) < STATIONS_TTL:
        return hit["stationen"]
    found: list[dict] = []
    for d in (0.7, 1.4):
        raw = _get("stationinfo", {"bbox": f"{lat-d:.3f},{lon-d*1.6:.3f},{lat+d:.3f},{lon+d*1.6:.3f}",
                                   "format": "json"})
        found = []
        for s in raw or []:
            types = s.get("siteType") or []
            if not (set(types) & {"METAR", "TAF"}) or s.get("lat") is None:
                continue
            dist = geo.haversine_km(lat, lon, s["lat"], s["lon"])
            if dist > MAX_KM:
                continue
            found.append({"id": s.get("icaoId") or s.get("id"), "name": (s.get("site") or "").strip(),
                          "lat": s["lat"], "lon": s["lon"], "elev": s.get("elev"), "land": s.get("country"),
                          "typen": types, "dist_km": round(dist, 1),
                          "peilung": geo.dir_text(geo.bearing_deg(lat, lon, s["lat"], s["lon"]))})
        if len(found) >= 3:
            break
    found.sort(key=lambda s: s["dist_km"])
    found = [s for s in found if s["id"]][:12]
    if len(cache) > 40:  # klein halten (älteste raus)
        for k in sorted(cache, key=lambda k: cache[k].get("t", 0))[:len(cache) - 40]:
            cache.pop(k, None)
    cache[key] = {"t": time.time(), "stationen": found}
    _write(STATIONS_FILE, cache)
    return found


# ---------------------------------------------------------------- Klartext
WX = {"TS": "Gewitter", "SH": "Schauer", "FZ": "gefrierend", "BL": "treibend", "DR": "fegend", "MI": "flach",
      "BC": "Schwaden", "PR": "teilweise", "RA": "Regen", "DZ": "Niesel", "SN": "Schnee", "SG": "Schneegriesel",
      "PL": "Eiskörner", "GR": "Hagel", "GS": "Graupel", "IC": "Eisnadeln", "UP": "unbek. Niederschlag",
      "FG": "Nebel", "BR": "Dunst", "HZ": "Trübung", "FU": "Rauch", "SA": "Sand", "DU": "Staub", "VA": "Vulkanasche",
      "SQ": "Böenwalze", "FC": "Trichterwolke", "PO": "Staubwirbel", "SS": "Sandsturm", "DS": "Staubsturm"}
COVER = {"FEW": "wenige (1–2/8)", "SCT": "aufgelockert (3–4/8)", "BKN": "stark bewölkt (5–7/8)",
         "OVC": "bedeckt (8/8)", "VV": "Vertikalsicht"}
CAT = {"VFR": "VFR – gute Sicht/hohe Wolken", "MVFR": "MVFR – eingeschränkt",
       "IFR": "IFR – schlechte Sicht/tiefe Wolken", "LIFR": "LIFR – sehr schlecht"}
_WXTOK = re.compile(r"^(\+|-|VC)?((?:MI|PR|BC|DR|BL|SH|TS|FZ)?)((?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PO|SQ|FC|SS|DS)+)$")


def wx_text(s: str | None) -> str:
    """'-SHRA BR' → 'leichte Schauer Regen, Dunst'."""
    out = []
    for tok in (s or "").split():
        m = _WXTOK.match(tok)
        if not m:
            continue
        pre, desc, ph = m.groups()
        phs = [WX.get(ph[i:i + 2], ph[i:i + 2]) for i in range(0, len(ph), 2)]
        if desc == "SH" and phs:
            core = [phs[0] + "schauer"] + phs[1:]          # Regenschauer, Schneeschauer …
        elif desc == "TS":
            core = ["Gewitter"] + (["mit " + " und ".join(phs)] if phs else [])
        else:
            core = ([WX.get(desc, desc)] if desc else []) + phs
        words = []
        if pre in ("+", "-"):
            strong = pre == "+"
            words.append(("starkes" if strong else "leichtes") if desc == "TS" else ("starker" if strong else "leichter"))
        words += core
        if pre == "VC":
            words.append("in der Nähe")
        out.append(" ".join(words))
    return ", ".join(out)


def _wx_from_raw(raw: str) -> str:
    toks = [t for t in (raw or "").split()[2:] if _WXTOK.match(t) and t not in ("RE",)]
    return " ".join(toks)


def vis_text(raw: str | None, visib) -> tuple[str, int | None]:
    """Sicht aus dem Rohtext (Meter), sonst aus 'visib' (US-Meilen)."""
    toks = (raw or "").split()
    if "CAVOK" in toks:
        return "CAVOK (≥ 10 km, keine tiefen Wolken)", 10000
    for i, t in enumerate(toks):
        if t.endswith("KT") and i + 1 < len(toks):
            nxt = [x for x in toks[i + 1:i + 3] if not re.match(r"^\d{3}V\d{3}$", x)]
            if nxt and re.match(r"^\d{4}(NDV)?$", nxt[0]):
                m = int(nxt[0][:4])
                return ("≥ 10 km" if m >= 9999 else f"{m} m" if m < 5000 else f"{m/1000:.1f} km".replace(".", ",")), m
            break
    if visib in (None, ""):
        return "–", None
    if str(visib).endswith("+"):
        return "≥ 10 km", 10000
    try:
        m = round(float(visib) * 1609.34 / 100) * 100
        return (f"{m} m" if m < 5000 else f"{m/1000:.1f} km".replace(".", ",")), m
    except ValueError:
        return str(visib), None


def wind_text(wdir, wspd, wgst=None) -> str:
    if wspd is None:
        return "–"
    if wspd == 0:
        return "Windstille"
    d = "variabel" if str(wdir).upper() == "VRB" else (f"aus {int(wdir):03d}° ({geo.dir_text(int(wdir))})"
                                                       if wdir not in (None, "") else "Richtung ?")
    t = f"{d}, {wspd} kt ≈ {wspd*0.5144:.0f} m/s"
    if wgst:
        t += f", Böen {wgst} kt ≈ {wgst*0.5144:.0f} m/s"
    return t


def clouds_text(clouds, cover=None) -> str:
    if cover in ("CAVOK",):
        return "keine Wolken unter 5000 ft"
    if not clouds:
        return {"NSC": "keine signifikanten Wolken", "NCD": "keine Wolken erkannt", "CLR": "keine Wolken (auto)",
                "SKC": "wolkenlos"}.get(cover or "", "keine Angabe")
    parts = []
    for c in clouds:
        b = c.get("base")
        parts.append(f"{COVER.get(c.get('cover'), c.get('cover'))} in {b} ft ≈ {round(b*0.3048/10)*10} m"
                     if b is not None else COVER.get(c.get("cover"), c.get("cover") or "?"))
    return "; ".join(parts)


def _hm(epoch) -> str:
    return datetime.fromtimestamp(epoch).strftime("%H:%M") if epoch else "?"


def _dhm(epoch) -> str:
    return datetime.fromtimestamp(epoch).strftime("%d.%m. %H:%M") if epoch else "?"


def decode_metar(m: dict, st: dict | None) -> dict:
    raw = m.get("rawOb") or ""
    obs = m.get("obsTime")
    age = int((time.time() - obs) / 60) if obs else None
    vis, vis_m = vis_text(raw, m.get("visib"))
    wxs = m.get("wxString") or _wx_from_raw(raw)
    wspd, wgst = m.get("wspd"), m.get("wgst")
    return {
        "id": m.get("icaoId"), "name": (st or {}).get("name") or m.get("name"), "roh": raw,
        "zeit": _hm(obs), "zeit_epoch": obs, "alter_min": age,
        "veraltet": age is not None and age > OLD_MIN,
        "wind": wind_text(m.get("wdir"), wspd, wgst), "wind_dir": m.get("wdir"),
        "wind_kt": wspd, "wind_ms": round(wspd * 0.5144, 1) if wspd is not None else None,
        "boeen_kt": wgst, "boeen_ms": round(wgst * 0.5144, 1) if wgst else None,
        "sicht": vis, "sicht_m": vis_m, "wetter": wx_text(wxs) or "kein signifikantes Wetter gemeldet",
        "wetter_code": wxs or "", "wolken": clouds_text(m.get("clouds"), m.get("cover")),
        "temp": m.get("temp"), "taupunkt": m.get("dewp"),
        "qnh": round(m["altim"]) if m.get("altim") is not None else None,
        "kategorie": m.get("fltCat"), "kategorie_text": CAT.get(m.get("fltCat") or "", ""),
        "auto": " AUTO " in f" {raw} ",
    }


def decode_taf(t: dict) -> dict:
    per = []
    for f in t.get("fcsts") or []:
        ch, prob = f.get("fcstChange"), f.get("probability")
        head = {"BECMG": "Übergang", "TEMPO": "zeitweise", "FM": "ab", "PROB": "möglich"}.get(ch or "", "Grundwerte")
        if prob:
            head = f"{prob} % {head}" if ch else f"{prob} % möglich"
        bits = []
        if f.get("wspd") is not None:
            bits.append("Wind " + wind_text(f.get("wdir"), f.get("wspd"), f.get("wgst")))
        if f.get("visib") not in (None, ""):
            bits.append("Sicht " + vis_text(None, f.get("visib"))[0])
        if f.get("wxString"):
            bits.append(wx_text(f["wxString"]) or f["wxString"])
        if f.get("clouds"):
            bits.append(clouds_text(f["clouds"]))
        elif f.get("vertVis"):
            bits.append(f"Vertikalsicht {f['vertVis']} ft")
        tf, tt = f.get("timeFrom"), f.get("timeTo")
        same = tf and tt and datetime.fromtimestamp(tf).date() == datetime.fromtimestamp(tt).date()
        per.append({"von": _dhm(tf), "bis": _hm(tt) if same else _dhm(tt), "art": head,
                    "text": "; ".join(bits) or "keine Änderung angegeben"})
    return {"id": t.get("icaoId"), "name": t.get("name"), "roh": t.get("rawTAF") or "",
            "ausgabe": _dhm(t.get("issueTime") and datetime.fromisoformat(
                t["issueTime"].replace("Z", "+00:00")).timestamp()),
            "gueltig": f"{_dhm(t.get('validTimeFrom'))} – {_dhm(t.get('validTimeTo'))}", "perioden": per}


# ---------------------------------------------------------------- Abruf
def _ages(out: dict) -> dict:
    """Alter der Meldungen beim Ausliefern neu berechnen (Cache-Treffer)."""
    now = time.time()
    m = out.get("metar")
    if m and m.get("zeit_epoch"):
        m["alter_min"] = int((now - m["zeit_epoch"]) / 60)
        m["veraltet"] = m["alter_min"] > OLD_MIN
    for w in out.get("weitere") or []:
        if w.get("zeit_epoch"):
            w["alter_min"] = int((now - w["zeit_epoch"]) / 60)
    return out


def fetch(lat: float, lon: float, force: bool = False) -> dict:
    """Nächster Flugplatz mit aktuellem METAR (+TAF). Nie erfundene Werte."""
    key = f"{lat:.3f},{lon:.3f}"
    c = _read(CACHE_FILE, {})
    if c.get("key") == key and time.time() - c.get("t", 0) < (FORCE_MIN if force else METAR_TTL):
        c["aus_cache"] = True
        return _ages(c)
    try:
        sts = stations(lat, lon)
        if not sts:
            raise MetarError(f"Kein Flugplatz mit METAR/TAF im Umkreis von {MAX_KM} km gefunden")
        ids = ",".join(s["id"] for s in sts[:8])
        metars = _get("metar", {"ids": ids, "format": "json", "hours": 3})
        tafs = _get("taf", {"ids": ids, "format": "json"})
    except MetarError as e:
        if c.get("key") == key:
            c.update({"fehler": f"{e} – zeige letzten gespeicherten Stand ({c.get('abruf')})", "aus_cache": True})
            return _ages(c)
        return {"key": key, "t": 0, "abruf": None, "fehler": str(e), "station": None, "metar": None, "taf": None,
                "weitere": [], "hinweis": HINWEIS}
    byid = {s["id"]: s for s in sts}
    latest: dict[str, dict] = {}
    for m in metars or []:
        i = m.get("icaoId")
        if i and (i not in latest or (m.get("obsTime") or 0) > (latest[i].get("obsTime") or 0)):
            latest[i] = m
    now = time.time()
    haupt = None
    for s in sts:
        m = latest.get(s["id"])
        if m and m.get("obsTime") and now - m["obsTime"] <= MAX_AGE_MIN * 60:
            haupt = s
            break
    metar = decode_metar(latest[haupt["id"]], haupt) if haupt else None
    taf_by = {t.get("icaoId"): t for t in (tafs or []) if t.get("icaoId")}
    taf_st = None
    if haupt and haupt["id"] in taf_by:
        taf_st = haupt
    else:
        taf_st = next((s for s in sts if s["id"] in taf_by), None)
    taf = decode_taf(taf_by[taf_st["id"]]) if taf_st else None
    if taf:
        taf.update({"dist_km": taf_st["dist_km"], "peilung": taf_st["peilung"]})
    weitere = []
    for s in sts[:8]:
        if haupt and s["id"] == haupt["id"]:
            continue
        m = latest.get(s["id"])
        d = decode_metar(m, s) if m else None
        weitere.append({"id": s["id"], "name": s["name"], "dist_km": s["dist_km"], "peilung": s["peilung"],
                        "lat": s["lat"], "lon": s["lon"],
                        "zeit": d["zeit"] if d else None, "zeit_epoch": d["zeit_epoch"] if d else None, "alter_min": d["alter_min"] if d else None,
                        "wind": d["wind"] if d else None, "qnh": d["qnh"] if d else None,
                        "hat_metar": bool(d), "hat_taf": s["id"] in taf_by})
    out = {"key": key, "t": now, "abruf": time.strftime("%H:%M:%S"), "aus_cache": False,
           "fehler": None if haupt else "Kein aktuelles METAR (≤ 3 h) bei den nächsten Flugplätzen – "
                                       "viele kleine/militärische Plätze melden nachts oder am Wochenende nicht.",
           "station": haupt, "metar": metar, "taf": taf, "weitere": weitere[:5], "hinweis": HINWEIS,
           "quelle": "aviationweather.gov (NOAA/NWS)"}
    _write(CACHE_FILE, out)
    return out
