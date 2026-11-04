"""dipul-Geozonen am Spot – über den OFFIZIELLEN WFS der DFS/BMDV (Phase 3, v1.7).

Quelle & Lizenz (geprüft 01.11.2026, https://dipul.de/homepage/de/informationen/geografische-gebiete/wfs-wms/):
  * WFS/WMS unter https://uas-betrieb.de/geoservices/dipul/ows – öffentlich, ohne Schlüssel.
  * Lizenz CC BY-ND 4.0, Quellenangabe „dipul, CC-BY-ND 4.0“. Daten werden unverändert angezeigt (keine Bearbeitung).
  * Rate-Limit möglich → nur Punkt-/Umkreis-Abfrage am aktiven Spot, 30 min Cache, kein Massendownload.
Kein Scraping, kein Reverse-Engineering des Map-Tools. Ergebnis = HINWEIS, keine rechtliche Zusicherung:
verbindlich ist allein die dipul-Karte bzw. die zuständige Behörde.
"""
from __future__ import annotations

import json
import math
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from app import config
from app.net import _CTX

WFS_URL = "https://uas-betrieb.de/geoservices/dipul/ows"
WMS_URL = "https://uas-betrieb.de/geoservices/dipul/wms"
LIZENZ_URL = "https://dipul.de/homepage/de/informationen/geografische-gebiete/wfs-wms/"
QUELLE = "dipul, CC-BY-ND 4.0"
RADIUS_M = 250
CACHE_S = 1800
HINWEIS = ("Nur Hinweis aus den offiziellen dipul-Geodaten (WFS). Verbindlich ist allein die dipul-Karte – "
           "Details, Ausnahmen & Genehmigungen dort bzw. bei der zuständigen Behörde prüfen. Kein Rechtsrat.")

# Reihenfolge = Anzeige-Reihenfolge (Luftraum zuerst). „inaktive_…“ bewusst weggelassen.
LAYERS = [
    ("flugbeschraenkungsgebiete", "Flugbeschränkungsgebiet"), ("kontrollzonen", "Kontrollzone"),
    ("flughaefen", "Flughafen"), ("flugplaetze", "Flugplatz"),
    ("temporaere_betriebseinschraenkungen", "Temporäre Betriebseinschränkung"),
    ("modellflugplaetze", "Modellflugplatz (nur Info)"),  # derzeit nur im WMS, nicht im WFS
   
    ("militaerische_anlagen", "Militärische Anlage"), ("justizvollzugsanstalten", "JVA / Maßregelvollzug"),
    ("labore", "Einrichtung BSL-4"), ("behoerden", "Behörde / Verfassungsorgan"),
    ("diplomatische_vertretungen", "Diplomatische Vertretung"), ("internationale_organisationen", "Internationale Organisation"),
    ("polizei", "Polizei-Liegenschaft"), ("sicherheitsbehoerden", "Sicherheitsbehörde"),
    ("kraftwerke", "Kraftwerk"), ("umspannwerke", "Umspannwerk"), ("stromleitungen", "Stromleitung"),
    ("windkraftanlagen", "Windkraftanlage"), ("industrieanlagen", "Industrieanlage"),
    ("krankenhaeuser", "Krankenhaus"), ("wohngrundstuecke", "Wohngrundstück"), ("freibaeder", "Freibad / Badestrand"),
    ("bundesautobahnen", "Bundesautobahn"), ("bundesstrassen", "Bundesstraße"), ("bahnanlagen", "Bahnanlage"),
    ("binnenwasserstrassen", "Binnenwasserstraße"), ("seewasserstrassen", "Seewasserstraße"),
    ("schifffahrtsanlagen", "Schifffahrtsanlage"),
    ("nationalparks", "Nationalpark"), ("naturschutzgebiete", "Naturschutzgebiet"),
    ("ffh-gebiete", "FFH-Gebiet"), ("vogelschutzgebiete", "Vogelschutzgebiet"),
]
_LABEL = dict(LAYERS)
_ORDER = {k: i for i, (k, _) in enumerate(LAYERS)}
_cache: dict = {}
_lock = threading.Lock()


def _num(v):
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


def _zone(f: dict) -> dict:
    layer = str(f.get("id", "")).split(".")[0]
    p = f.get("properties") or {}
    name = p.get("generated_name_DE") or p.get("name") or "(ohne Namen)"
    unten_agl, unten_ft, oben_ft = _num(p.get("lower_limit_m_agl")), _num(p.get("lower_limit_ft_msl")), _num(p.get("upper_limit_ft_msl"))
    hoehe = []
    if unten_agl is not None:
        hoehe.append("ab Boden" if unten_agl == 0 else f"ab {unten_agl:g} m über Grund")
    elif unten_ft is not None:
        hoehe.append(f"ab {unten_ft:g} ft MSL")
    if oben_ft:
        hoehe.append(f"bis {oben_ft:g} ft MSL")
    return {"layer": layer, "art": _LABEL.get(layer, layer), "name": str(name)[:160],
            "hoehe": ", ".join(hoehe), "rechtsgrundlage": str(p.get("legal_ref") or "")[:80],
            "info_only": layer == "modellflugplaetze"}


_types: dict = {"t": 0.0, "names": None}


def _available() -> list[str]:
    """Welche Layer bietet der WFS gerade an? (GetCapabilities, 24 h gemerkt) – robust gegen Dienständerungen."""
    if _types["names"] is not None and time.time() - _types["t"] < 86400:
        return _types["names"]
    import re
    url = f"{WFS_URL}?service=WFS&version=1.1.0&request=GetCapabilities"
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=25, context=_CTX) as r:
            xml = r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, TimeoutError) as e:
        raise RuntimeError(f"Keine Verbindung zu {urllib.parse.urlparse(WFS_URL).netloc} ({getattr(e, 'reason', e)})") from e
    have = set(re.findall(r"<(?:wfs:)?Name>dipul:([^<]+)</(?:wfs:)?Name>", xml))
    names = [k for k, _ in LAYERS if k in have]
    if not names:
        raise RuntimeError("dipul-WFS meldet keine bekannten Layer (Dienst geändert?)")
    _types.update(t=time.time(), names=names)
    return names


def _query(wkt: str) -> list[dict]:
    names = [f"dipul:{k}" for k in _available()]
    params = {"service": "WFS", "version": "1.1.0", "request": "GetFeature", "typeName": ",".join(names),
              "outputFormat": "application/json", "maxFeatures": "200",
              "CQL_FILTER": ";".join([f"INTERSECTS(geom,SRID=4326;{wkt})"] * len(names))}
    url = f"{WFS_URL}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"User-Agent": config.USER_AGENT, "Accept": "application/json"})
    host = urllib.parse.urlparse(WFS_URL).netloc
    try:
        with urllib.request.urlopen(req, timeout=25, context=_CTX) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"HTTP {e.code} von {host}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Keine Verbindung zu {host} ({e.reason})") from e
    except TimeoutError as e:
        raise RuntimeError(f"Zeitüberschreitung bei {host}") from e
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as e:
        import re
        m = re.search(rb"<ows:ExceptionText>(.*?)</ows:ExceptionText>", raw, re.S)
        why = m.group(1).decode("utf-8", "replace").strip()[:120] if m else "kein JSON"
        raise RuntimeError(f"dipul-WFS: {why} (evtl. Dienst geändert / Rate-Limit)") from e
    return [_zone(f) for f in data.get("features") or []]


def _uniq(zs: list[dict]) -> list[dict]:
    seen, out = set(), []
    for z in sorted(zs, key=lambda z: (_ORDER.get(z["layer"], 99), z["name"])):
        k = (z["layer"], z["name"])
        if k not in seen:
            seen.add(k)
            out.append(z)
    return out


def _kurz(r: dict) -> str:
    if r.get("fehler") and r.get("am_spot") is None:
        return "🗺 dipul ✗"
    a = [z for z in r["am_spot"] if not z["info_only"]]
    if a:
        return f"🗺 dipul: {len(a)} Gebiet(e) am Spot"
    return f"🗺 dipul: {len(r['umkreis'])} im Umkreis" if r["umkreis"] else "🗺 dipul: nichts gefunden"


def check(lat: float, lon: float, radius_m: int = RADIUS_M, force: bool = False) -> dict:
    """Geografische Gebiete (§ 21h LuftVO) am Spot + im Quadrat ±radius_m. Fehler ehrlich, nie erfunden."""
    key = (round(lat, 5), round(lon, 5), int(radius_m))
    now = time.time()
    with _lock:
        hit = _cache.get(key)
    if hit and not force and now - hit["_t"] < CACHE_S:
        return {**{k: v for k, v in hit.items() if k != "_t"}, "aus_cache": True}
    base = {"lat": lat, "lon": lon, "radius_m": int(radius_m), "quelle": QUELLE, "lizenz_url": LIZENZ_URL,
            "hinweis": HINWEIS, "aus_cache": False}
    try:
        pt = _query(f"POINT({lon:.6f} {lat:.6f})")
        dlat = radius_m / 111320.0
        dlon = radius_m / (111320.0 * max(0.05, math.cos(math.radians(lat))))
        x0, x1, y0, y1 = lon - dlon, lon + dlon, lat - dlat, lat + dlat
        box = _query(f"POLYGON(({x0:.6f} {y0:.6f},{x1:.6f} {y0:.6f},{x1:.6f} {y1:.6f},{x0:.6f} {y1:.6f},{x0:.6f} {y0:.6f}))")
    except RuntimeError as e:
        if hit:
            return {**{k: v for k, v in hit.items() if k != "_t"}, "aus_cache": True,
                    "fehler": f"{e} – zeige letzten Stand von {hit['abruf']}"}
        r = {**base, "ok": False, "am_spot": None, "umkreis": [], "abruf": None,
             "fehler": f"dipul-Abfrage fehlgeschlagen: {e}. Bitte direkt in der dipul-Karte prüfen."}
        r["kurz"] = _kurz(r)
        return r
    am = _uniq(pt)
    ks = {(z["layer"], z["name"]) for z in am}
    um = [z for z in _uniq(box) if (z["layer"], z["name"]) not in ks]
    r = {**base, "ok": True, "am_spot": am, "umkreis": um, "abruf": time.strftime("%H:%M"), "fehler": None}
    r["kurz"] = _kurz(r)
    with _lock:
        _cache[key] = {**r, "_t": now}
    return r


def text_lines(r: dict) -> list[str]:
    """Menschlich lesbare Zeilen für Desktop/Markdown."""
    if r.get("am_spot") is None:
        return [f"⚠ {r.get('fehler') or 'keine Daten'}"]
    out = []
    if r.get("fehler"):
        out.append(f"⚠ {r['fehler']}")
    fmt = lambda z: f"{z['art']}: {z['name']}" + (f" ({z['hoehe']})" if z["hoehe"] else "")  # noqa: E731
    if r["am_spot"]:
        out.append("Am Spot laut dipul-Daten:")
        out += [f"  • {fmt(z)}" for z in r["am_spot"]]
    else:
        out.append("Am Spot: kein geografisches Gebiet in den dipul-Daten gefunden.")
    if r["umkreis"]:
        out.append(f"Im Umkreis ~{r['radius_m']} m:")
        out += [f"  • {fmt(z)}" for z in r["umkreis"][:12]]
        if len(r["umkreis"]) > 12:
            out.append(f"  … und {len(r['umkreis']) - 12} weitere")
    return out
