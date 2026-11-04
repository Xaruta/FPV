"""Logbuch & Flugtage (Roadmap Phase 6 / 6.5).

Ordner pro Flugtag:  <logs_dir>/JJJJ-MM-TT_Spot/
  flugtag.json   Kopf + Start-/End-Snapshot, Status offen|beendet
  flugtag.md     menschenlesbar
  verlauf.jsonl  Wetter-Messpunkte (nur echte Open-Meteo-Werte, je Messzeit höchstens einmal)
  notizen.jsonl  eigene Notizen mit Zeitstempel
  zusammenfassung.md  beim Beenden aus den echten Werten erzeugt
  medien/        Videos/Fotos legt man selbst ab – die App liest nur
<logs_dir>/index.json  Such-Index (jederzeit neu aufbaubar)
<logs_dir>/aktiv.json  Zeiger auf den laufenden Flugtag (geteilt von Desktop & Web)

Die App löscht oder verschiebt nie etwas im Logs-Ordner.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from app import config, settings, sun, weather

log = logging.getLogger("logbuch")
_LOCK = threading.Lock()
SCHEMA = 1
MEDIA_EXT = {".mp4", ".mov", ".avi", ".mkv", ".m4v", ".ts", ".jpg", ".jpeg", ".png", ".heic", ".webp", ".gif",
             ".dng", ".raw", ".bbl", ".bfl", ".srt", ".osd"}


# ------------------------------------------------------------------ Pfade & Helfer
def logs_dir(cfg: dict | None = None) -> Path:
    cfg = cfg or settings.load()
    raw = (cfg.get("logs_dir") or "").strip()
    p = Path(os.path.expandvars(raw)).expanduser() if raw else config.PROJECT_DIR / "logs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def safe_name(name: str) -> str:
    s = re.sub(r'[\\/:*?"<>|\x00-\x1f]+', "-", (name or "Spot").strip())
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"\s*-\s*", "-", s).strip(" .-") or "Spot"
    return s[:60]


def _read_json(p: Path, default=None):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return default


def _write_json(p: Path, obj) -> None:
    tmp = p.with_name(f".{p.name}.tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, p)


def _read_jsonl(p: Path) -> list[dict]:
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except FileNotFoundError:
        pass
    return out


def _append_jsonl(p: Path, obj) -> None:
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _day_dir(name: str, base: Path | None = None) -> Path:
    base = base or logs_dir()
    d = (base / name).resolve()
    if base.resolve() not in d.parents:
        raise ValueError("Ungültiger Flugtag-Ordner.")
    return d


# ------------------------------------------------------------------ Wetter-Snapshot
def _snapshot(spot: dict, cfg: dict, force: bool = True) -> dict | None:
    """Echter Open-Meteo-Abruf + Ampel + Sonnenstand. Bei Fehler: None (= „kein Snapshot“)."""
    try:
        w = weather.fetch(spot["lat"], spot["lon"], force=force)
    except Exception as e:  # noqa: BLE001
        log.warning("Kein Wetter-Snapshot: %s", e)
        return None
    a = weather.assess(w, cfg["thresholds"])
    return {
        "zeit": now_iso(), "messzeit": w.get("messzeit"), "quelle": "Open-Meteo",
        "ampel": a["stufe"], "ampel_titel": a["titel"], "gruende": a["gruende"],
        "wind": w.get("wind"), "boeen": w.get("boeen"), "richtung": w.get("richtung"),
        "richtung_txt": w.get("richtung_txt"), "temp": w.get("temp"), "gefuehlt": w.get("gefuehlt"),
        "sicht": w.get("sicht"), "wolken": w.get("wolken"), "regen": w.get("regen"), "wetter": w.get("wetter"),
        "sonnenaufgang": w.get("sonnenaufgang"), "sonnenuntergang": w.get("sonnenuntergang"),
        "sonne": sun.position(spot["lat"], spot["lon"]),
        "licht": _licht(spot),
    }


def _licht(spot: dict) -> dict | None:
    try:
        lt = sun.light(spot["lat"], spot["lon"])
        return {k: lt.get(k) for k in ("phase", "text", "untergang", "daemmerung_ende", "min_bis_untergang", "min_bis_dunkel")}
    except Exception:  # noqa: BLE001
        return None


def _point(s: dict) -> dict:
    keys = ("zeit", "messzeit", "ampel", "wind", "boeen", "richtung", "temp", "sicht", "wolken", "regen")
    p = {k: s.get(k) for k in keys}
    p["sonne_hoehe"] = s["sonne"]["hoehe"]
    p["sonne_azimut"] = s["sonne"]["azimut"]
    return p


# ------------------------------------------------------------------ aktiver Flugtag
def active(cfg: dict | None = None) -> dict | None:
    base = logs_dir(cfg)
    ptr = _read_json(base / "aktiv.json", {}) or {}
    name = ptr.get("ordner")
    if not name:
        return None
    day = _read_json(base / name / "flugtag.json")
    if not day or day.get("status") != "offen":
        return None
    return day


def _spot_hazards(name: str, cfg: dict) -> list[str]:
    try:
        from app import spots
        return spots.checklist_extras(spots.by_name(name, cfg))
    except Exception:  # noqa: BLE001
        return []


def start_day(cfg: dict | None = None) -> dict:
    cfg = cfg or settings.load()
    spot = settings.active_spot(cfg)
    if not spot:
        raise ValueError("Bitte zuerst einen Standort/Spot setzen.")
    with _LOCK:
        if active(cfg):
            raise ValueError("Es läuft schon ein Flugtag – erst beenden.")
        base = logs_dir(cfg)
        stem = f"{datetime.now():%Y-%m-%d}_{safe_name(spot['name'])}"
        name, i = stem, 2
        while (base / name).exists():
            name, i = f"{stem}_{i}", i + 1
        d = base / name
        (d / "medien").mkdir(parents=True)
        snap = _snapshot(spot, cfg)
        ck = cfg.get("checklist") or []
        day = {
            "schema": SCHEMA, "ordner": name, "status": "offen",
            "datum": f"{datetime.now():%Y-%m-%d}", "start": now_iso(), "ende": None,
            "spot": {k: spot.get(k) for k in ("id", "name", "lat", "lon", "region")},
            "spot_gefahren": _spot_hazards(spot["name"], cfg),
            "snapshot_start": snap, "snapshot_ende": None,
            "checkliste": {"erledigt": sum(1 for c in ck if c.get("done")), "gesamt": len(ck),
                           "offen": [c["text"] for c in ck if not c.get("done")]},
        }
        _write_json(d / "flugtag.json", day)
        if snap:
            _append_jsonl(d / "verlauf.jsonl", _point(snap))
        (d / "notizen.jsonl").touch()
        _write_md(d, day)
        _write_json(base / "aktiv.json", {"ordner": name, "seit": day["start"]})
        rebuild_index(cfg)
        log.info("Flugtag gestartet: %s (Snapshot: %s)", name, "ja" if snap else "nein")
        return day


def tick(cfg: dict | None = None) -> dict | None:
    """Neuen Messpunkt schreiben, wenn ein Flugtag läuft und der letzte Punkt alt genug ist.
    Doppelte Messzeiten (Desktop + Web gleichzeitig) werden übersprungen."""
    cfg = cfg or settings.load()
    day = active(cfg)
    if not day:
        return None
    d = logs_dir(cfg) / day["ordner"]
    pts = _read_jsonl(d / "verlauf.jsonl")
    min_s = max(5, int(cfg.get("verlauf_minuten", 15))) * 60
    if pts:
        try:
            last = datetime.fromisoformat(pts[-1]["zeit"]).timestamp()
        except (KeyError, ValueError):
            last = 0
        if time.time() - last < min_s - 30:
            return None
    spot = day["spot"]
    snap = _snapshot(spot, cfg, force=False)
    if not snap:
        return None
    with _LOCK:
        pts = _read_jsonl(d / "verlauf.jsonl")
        if pts and pts[-1].get("messzeit") == snap.get("messzeit"):
            return None
        p = _point(snap)
        _append_jsonl(d / "verlauf.jsonl", p)
    return p


def add_note(text: str, tags: list[str] | None = None, cfg: dict | None = None) -> dict:
    text = (text or "").strip()
    if not text:
        raise ValueError("Leere Notiz.")
    cfg = cfg or settings.load()
    day = active(cfg)
    if not day:
        raise ValueError("Kein Flugtag aktiv – erst „Flugtag starten“.")
    d = logs_dir(cfg) / day["ordner"]
    n = {"zeit": now_iso(), "text": text[:2000], "tags": [t.strip()[:30] for t in (tags or []) if t.strip()][:8]}
    with _LOCK:
        _append_jsonl(d / "notizen.jsonl", n)
        _write_md(d, day)
    rebuild_index(cfg)  # Notiz sofort durchsuchbar
    return n


def end_day(cfg: dict | None = None) -> dict:
    cfg = cfg or settings.load()
    with _LOCK:
        day = active(cfg)
        if not day:
            raise ValueError("Es läuft kein Flugtag.")
        base = logs_dir(cfg)
        d = base / day["ordner"]
        snap = _snapshot(day["spot"], cfg)
        if snap:
            pts = _read_jsonl(d / "verlauf.jsonl")
            if not pts or pts[-1].get("messzeit") != snap.get("messzeit"):
                _append_jsonl(d / "verlauf.jsonl", _point(snap))
        day.update({"status": "beendet", "ende": now_iso(), "snapshot_ende": snap})
        _write_json(d / "flugtag.json", day)
        (d / "zusammenfassung.md").write_text(summary_md(d, day), encoding="utf-8")
        _write_md(d, day)
        _write_json(base / "aktiv.json", {"ordner": None, "zuletzt": day["ordner"]})
    rebuild_index(cfg)
    log.info("Flugtag beendet: %s", day["ordner"])
    return day


# ------------------------------------------------------------------ Medien
def media(d: Path) -> list[dict]:
    out = []
    m = d / "medien"
    if not m.is_dir():
        return out
    pts = _read_jsonl(d / "verlauf.jsonl")
    for f in sorted(m.rglob("*")):
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in MEDIA_EXT:
            continue
        st = f.stat()
        mt = datetime.fromtimestamp(st.st_mtime).astimezone()
        near = None
        if pts:
            def dist(p):
                try:
                    return abs(datetime.fromisoformat(p["zeit"]).timestamp() - st.st_mtime)
                except (KeyError, ValueError):
                    return 1e12
            best = min(pts, key=dist)
            if dist(best) < 3 * 3600:
                near = {k: best.get(k) for k in ("zeit", "wind", "boeen", "ampel", "temp")}
        out.append({"datei": str(f.relative_to(m)), "groesse_mb": round(st.st_size / 1e6, 1),
                    "zeit": mt.isoformat(timespec="seconds"), "wetter": near})
    return out


# ------------------------------------------------------------------ Zusammenfassung & Markdown
def _stat(vals):
    v = [x for x in vals if isinstance(x, (int, float))]
    if not v:
        return None
    return {"min": min(v), "max": max(v), "avg": sum(v) / len(v), "n": len(v)}


def _hm(iso):
    try:
        return datetime.fromisoformat(iso).strftime("%H:%M")
    except (TypeError, ValueError):
        return "–"


def summary_data(d: Path, day: dict) -> dict:
    pts = _read_jsonl(d / "verlauf.jsonl")
    notes = _read_jsonl(d / "notizen.jsonl")
    med = media(d)
    amp = {}
    for p in pts:
        if p.get("ampel"):
            amp[p["ampel"]] = amp.get(p["ampel"], 0) + 1
    dur = None
    try:
        if day.get("ende"):
            dur = (datetime.fromisoformat(day["ende"]) - datetime.fromisoformat(day["start"])).total_seconds() / 60
    except (TypeError, ValueError):
        pass
    return {"punkte": len(pts), "wind": _stat([p.get("wind") for p in pts]),
            "boeen": _stat([p.get("boeen") for p in pts]), "temp": _stat([p.get("temp") for p in pts]),
            "sicht": _stat([p.get("sicht") for p in pts]), "ampel": amp, "notizen": notes, "medien": med,
            "dauer_min": dur}


def summary_md(d: Path, day: dict) -> str:
    s = summary_data(d, day)
    sp = day["spot"]
    L = [f"# Zusammenfassung Flugtag {day['datum']} – {sp['name']}", ""]
    L.append(f"- **Zeitraum:** {_hm(day['start'])}–{_hm(day.get('ende'))}"
             + (f" ({int(s['dauer_min'] // 60)} h {int(s['dauer_min'] % 60)} min)" if s["dauer_min"] is not None else ""))
    L.append(f"- **Spot:** {sp['name']}" + (f" · {sp['region']}" if sp.get("region") else "")
             + f" · {sp['lat']:.5f}, {sp['lon']:.5f}")
    if s["punkte"]:
        def fs(st, unit, nd=1):
            return f"min {st['min']:.{nd}f} / Ø {st['avg']:.{nd}f} / max {st['max']:.{nd}f} {unit}" if st else "keine Angabe"
        L.append(f"- **Wetter-Messpunkte:** {s['punkte']} (Open-Meteo)")
        L.append(f"- **Wind:** {fs(s['wind'], 'm/s')}")
        L.append(f"- **Böen:** {fs(s['boeen'], 'm/s')}")
        L.append(f"- **Temperatur:** {fs(s['temp'], '°C')}")
        if s["sicht"]:
            L.append(f"- **Sicht:** min {s['sicht']['min'] / 1000:.1f} km / max {s['sicht']['max'] / 1000:.1f} km")
        tot = sum(s["ampel"].values()) or 1
        names = {"gruen": "🟢 grün", "gelb": "🟡 gelb", "rot": "🔴 rot"}
        L.append("- **Ampel:** " + ", ".join(f"{names.get(k, k)} {100 * v // tot} %" for k, v in
                                               sorted(s["ampel"].items(), key=lambda kv: -kv[1])))
    else:
        L.append("- **Wetter:** kein Snapshot (kein erfolgreicher Abruf während des Flugtags)")
    st = day.get("snapshot_start") or {}
    if st.get("sonnenaufgang"):
        L.append(f"- **Sonne:** Aufgang {st['sonnenaufgang']} · Untergang {st.get('sonnenuntergang') or '–'}"
                 + (f" · dunkel ab {st['licht']['daemmerung_ende']}" if (st.get("licht") or {}).get("daemmerung_ende") else ""))
    ck = day.get("checkliste") or {}
    if ck:
        L.append(f"- **Preflight-Checkliste beim Start:** {ck.get('erledigt', 0)}/{ck.get('gesamt', 0)} erledigt")
    L.append(f"- **Notizen:** {len(s['notizen'])} · **Medien:** {len(s['medien'])} Datei(en) in `medien/`")
    fl, wa = flights(d), maintenance(d)
    if fl:
        known = [x["dauer_s"] for x in fl if x.get("dauer_s")]
        L.append(f"- **Flüge/Packs:** {len(fl)} · Flugzeit {fmt_dur(sum(known)) if known else 'keine Angabe'}"
                 + (f" (bei {len(fl) - len(known)} Flug/Flügen keine Dauer erfasst)" if known and len(known) < len(fl) else "")
                 + f" · Crashes {sum(1 for x in fl if x.get('ergebnis') == 'crash')}")
    if wa:
        L.append(f"- **Wartung/Reparatur:** " + "; ".join(f"{w['teil']}" + (f" ({w['drohne']})" if w.get("drohne") else "")
                                                       for w in wa))
    if s["notizen"]:
        L += ["", "## Notizen"] + [f"- {_hm(n['zeit'])} {n['text']}" + (f" _({', '.join(n['tags'])})_" if n.get("tags") else "")
                                   for n in s["notizen"]]
    if s["medien"]:
        L += ["", "## Medien"] + [f"- {m['datei']} ({m['groesse_mb']} MB, {_hm(m['zeit'])})"
                                  + (f" – Wind {m['wetter']['wind']}/{m['wetter']['boeen']} m/s" if m.get("wetter") else "")
                                  for m in s["medien"]]
    L += ["", "_Automatisch erzeugt aus gespeicherten Messwerten. Wetter-Orientierung, kein Rechtsrat – "
              "Geozonen siehe dipul._", ""]
    return "\n".join(L)


def _write_md(d: Path, day: dict) -> None:
    sp = day["spot"]
    st = day.get("snapshot_start")
    L = [f"# Flugtag {day['datum']} – {sp['name']}", "",
         f"- Status: **{day['status']}** · Start {_hm(day['start'])}" + (f" · Ende {_hm(day['ende'])}" if day.get("ende") else ""),
         f"- Spot: {sp['name']}" + (f" ({sp['region']})" if sp.get("region") else "") + f" · {sp['lat']:.5f}, {sp['lon']:.5f}",
         "", "## Wetter beim Start"]
    if st:
        L += [f"- Ampel: **{st['ampel_titel']}** – " + "; ".join(st["gruende"]),
              f"- Wind {st['wind']} m/s, Böen {st['boeen']} m/s aus {st['richtung_txt']} ({st['richtung']}°)",
              f"- {st['temp']} °C (gefühlt {st['gefuehlt']}), Sicht {(st['sicht'] or 0) / 1000:.1f} km, "
              f"Wolken {st['wolken']} %, {st['wetter']}",
              f"- Sonne: {st['sonne']['hoehe']}° über Horizont aus {st['sonne']['richtung']} ({st['sonne']['phase']})",
              *([f"- Licht: {st['licht']['text']}"] if st.get("licht") else []),
              f"- Quelle: Open-Meteo, Messzeit {st['messzeit']}"]
    else:
        L.append("- kein Snapshot (Wetterabruf fehlgeschlagen)")
    if day.get("spot_gefahren"):
        L += ["", "## Gefahrenstellen am Spot (aus dem Spot-Profil)"] + [f"- {g}" for g in day["spot_gefahren"]]
    notes = _read_jsonl(d / "notizen.jsonl")
    if notes:
        L += ["", "## Notizen"] + [f"- {_hm(n['zeit'])} {n['text']}" for n in notes]
    fl = flights(d)
    if fl:
        L += ["", "## Flüge / Packs"] + [
            f"- {i}. " + " · ".join(x for x in [
                f.get("start") or "", fmt_dur(f.get("dauer_s")), f"Akku {f['akku']}" if f.get("akku") else "",
                f.get("drohne") or "", {"ok": "ok", "crash": "💥 Crash"}.get(f.get("ergebnis"), "Ergebnis: keine Angabe"),
                f.get("notiz") or ""] if x) for i, f in enumerate(fl, 1)]
    wa = maintenance(d)
    if wa:
        L += ["", "## Wartung / Reparaturen"] + [
            f"- {w.get('datum') or ''} {w['teil']}" + (f" ×{w['anzahl']}" if (w.get("anzahl") or 1) > 1 else "")
            + (f" ({w['drohne']})" if w.get("drohne") else "")
            + (f" · {w['kosten']:.2f} €" if w.get("kosten") is not None else "") + (f" – {w['notiz']}" if w.get("notiz") else "")
            for w in wa]
    L += ["", "Medien (Videos/Fotos) einfach in den Ordner `medien/` legen.", ""]
    (d / "flugtag.md").write_text("\n".join(L), encoding="utf-8")


# ------------------------------------------------------------------ Index & Suche
def rebuild_index(cfg: dict | None = None) -> list[dict]:
    base = logs_dir(cfg)
    rows = []
    for f in sorted(base.glob("*/flugtag.json")):
        day = _read_json(f)
        if not isinstance(day, dict) or "spot" not in day:
            continue
        d = f.parent
        notes = _read_jsonl(d / "notizen.jsonl")
        pts = _read_jsonl(d / "verlauf.jsonl")
        st = day.get("snapshot_start") or {}
        gust = _stat([p.get("boeen") for p in pts])
        fl = flights(d)
        rows.append({
            "ordner": d.name, "datum": day.get("datum"), "status": day.get("status"),
            "start": day.get("start"), "ende": day.get("ende"),
            "spot": day["spot"].get("name"), "spot_id": day["spot"].get("id"), "region": day["spot"].get("region"),
            "ampel": st.get("ampel"), "wind": st.get("wind"), "boeen_max": gust["max"] if gust else None,
            "temp": st.get("temp"), "punkte": len(pts), "notizen": len(notes), "medien": len(media(d)),
            "text": " ".join(n.get("text", "") for n in notes)[:2000],
            "fluege": len(fl), "flugzeit_s": sum(x["dauer_s"] for x in fl if x.get("dauer_s")),
            "crashes": sum(1 for x in fl if x.get("ergebnis") == "crash"), "wartung": len(maintenance(d)),
        })
    rows.sort(key=lambda r: r.get("start") or "", reverse=True)
    _write_json(base / "index.json", {"erstellt": now_iso(), "flugtage": rows})
    return rows


def search(q: str = "", cfg: dict | None = None, limit: int = 100) -> list[dict]:
    base = logs_dir(cfg)
    idx = _read_json(base / "index.json")
    rows = idx.get("flugtage") if isinstance(idx, dict) else None
    if rows is None:
        rows = rebuild_index(cfg)
    words = [w for w in (q or "").lower().split() if w]
    out = []
    for r in rows:
        hay = " ".join(str(r.get(k) or "") for k in ("datum", "spot", "region", "text", "ampel", "ordner")).lower()
        if all(w in hay for w in words):
            out.append(r)
    return out[:limit]


def day_detail(name: str, cfg: dict | None = None) -> dict:
    d = _day_dir(name, logs_dir(cfg))
    day = _read_json(d / "flugtag.json")
    if not day:
        raise ValueError("Flugtag nicht gefunden.")
    return {"flugtag": day, "verlauf": _read_jsonl(d / "verlauf.jsonl"), "notizen": _read_jsonl(d / "notizen.jsonl"),
            "medien": media(d), "fluege": flights(d), "wartung": maintenance(d), "pfad": str(d)}


# ------------------------------------------------------------------ Ordner öffnen (plattformübergreifend)
def open_folder(path: Path) -> None:
    path = Path(path)
    path.mkdir(parents=True, exist_ok=True)
    if sys.platform.startswith("win"):
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_day(name: str | None, cfg: dict | None = None) -> Path:
    base = logs_dir(cfg)
    p = _day_dir(name, base) if name else base
    open_folder(p / "medien" if name and (p / "medien").is_dir() else p)
    return p


# ------------------------------------------------------------------ Flüge & Wartung (Phase 8)
# fluege.jsonl / wartung.jsonl werden nur angehängt. „Rückgängig“ hängt einen Storno-Eintrag an
# ({"storno": id}) – es wird nie eine Zeile gelöscht oder überschrieben.
ERGEBNISSE = ("ok", "crash")
ZEIT_QUELLEN = ("Stoppuhr", "OSD", "Blackbox", "Funke-Timer", "Erinnerung")


def parse_duration(txt) -> int | None:
    """'3:45' → 225 s · '4' → 240 s (Minuten) · '1:02:03' → 3723 s · leer → None (= keine Angabe)."""
    s = str(txt or "").strip().replace(",", ".")
    if not s:
        return None
    try:
        if ":" in s:
            parts = [float(x) for x in s.split(":")]
            if len(parts) > 3 or any(x < 0 for x in parts):
                raise ValueError
            sec = 0.0
            for x in parts:
                sec = sec * 60 + x
        else:
            sec = float(s) * 60
    except ValueError:
        raise ValueError(f"Flugdauer „{txt}“ nicht lesbar – bitte mm:ss oder Minuten.") from None
    if sec <= 0 or sec > 4 * 3600:
        raise ValueError("Flugdauer muss zwischen 1 s und 4 h liegen.")
    return int(round(sec))


def fmt_dur(sec) -> str:
    if sec is None:
        return "keine Angabe"
    sec = int(sec)
    h, m, s = sec // 3600, sec % 3600 // 60, sec % 60
    return f"{h} h {m:02d} min" if h else f"{m}:{s:02d} min"


def _eid() -> str:
    return f"{int(time.time() * 1000):x}{os.urandom(2).hex()}"


def _target_dir(ordner: str | None, cfg: dict) -> tuple[Path, dict]:
    base = logs_dir(cfg)
    if not ordner:
        day = active(cfg)
        if not day:
            raise ValueError("Kein Flugtag aktiv – Flugtag starten oder einen Tag im Logbuch wählen.")
        ordner = day["ordner"]
    d = _day_dir(ordner, base)
    day = _read_json(d / "flugtag.json")
    if not isinstance(day, dict):
        raise ValueError("Flugtag nicht gefunden.")
    return d, day


def _live(rows: list[dict]) -> list[dict]:
    dead = {r["storno"] for r in rows if r.get("storno")}
    return [r for r in rows if not r.get("storno") and r.get("id") not in dead]


def flights(d: Path) -> list[dict]:
    return _live(_read_jsonl(d / "fluege.jsonl"))


def maintenance(d: Path) -> list[dict]:
    return _live(_read_jsonl(d / "wartung.jsonl"))


def add_flight(data: dict, ordner: str | None = None, cfg: dict | None = None) -> dict:
    cfg = cfg or settings.load()
    d, day = _target_dir(ordner, cfg)
    erg = str(data.get("ergebnis") or "").lower()
    quelle = str(data.get("quelle") or "").strip()
    f = {
        "id": _eid(), "zeit": now_iso(),
        "start": str(data.get("start") or "").strip()[:5] or None,          # HH:MM, optional
        "dauer_s": parse_duration(data.get("dauer")),                       # None = keine Angabe
        "quelle": quelle if quelle in ZEIT_QUELLEN else None,
        "akku": str(data.get("akku") or "").strip()[:40] or None,
        "drohne": str(data.get("drohne") or "").strip()[:60] or None,
        "ergebnis": erg if erg in ERGEBNISSE else None,
        "notiz": str(data.get("notiz") or "").strip()[:500] or None,
    }
    with _LOCK:
        _append_jsonl(d / "fluege.jsonl", f)
    _after_change(d, cfg)
    return f


def add_maintenance(data: dict, ordner: str | None = None, cfg: dict | None = None) -> dict:
    cfg = cfg or settings.load()
    d, day = _target_dir(ordner, cfg)
    teil = str(data.get("teil") or "").strip()[:80]
    if not teil:
        raise ValueError("Bitte angeben, was repariert/getauscht wurde (z. B. Props, Arm, Kamera).")
    kosten = str(data.get("kosten") or "").strip().replace(",", ".").replace("€", "")
    try:
        kosten_v = round(float(kosten), 2) if kosten else None
    except ValueError:
        raise ValueError(f"Kosten „{data.get('kosten')}“ sind keine Zahl.") from None
    w = {"id": _eid(), "zeit": now_iso(), "datum": str(data.get("datum") or day.get("datum") or "")[:10],
         "teil": teil, "anzahl": int(data.get("anzahl") or 1) if str(data.get("anzahl") or "1").isdigit() else 1,
         "drohne": str(data.get("drohne") or "").strip()[:60] or None, "kosten": kosten_v,
         "notiz": str(data.get("notiz") or "").strip()[:500] or None}
    with _LOCK:
        _append_jsonl(d / "wartung.jsonl", w)
    _after_change(d, cfg)
    return w


def storno(kind: str, eid: str, ordner: str | None = None, cfg: dict | None = None) -> None:
    cfg = cfg or settings.load()
    d, _ = _target_dir(ordner, cfg)
    fn = {"flug": "fluege.jsonl", "wartung": "wartung.jsonl"}.get(kind)
    if not fn or not any(r.get("id") == eid for r in _read_jsonl(d / fn)):
        raise ValueError("Eintrag nicht gefunden.")
    with _LOCK:
        _append_jsonl(d / fn, {"storno": eid, "zeit": now_iso()})
    _after_change(d, cfg)


def _after_change(d: Path, cfg: dict) -> None:
    """Abgeleitete Markdown-Dateien + Index neu erzeugen (Rohdaten bleiben unangetastet)."""
    day = _read_json(d / "flugtag.json")
    if isinstance(day, dict):
        with _LOCK:
            try:
                _write_md(d, day)
                if day.get("status") == "beendet":
                    (d / "zusammenfassung.md").write_text(summary_md(d, day), encoding="utf-8")
            except (KeyError, TypeError, ValueError):
                pass   # unvollständiger alter Tag: Markdown bleibt wie es ist
    rebuild_index(cfg)
