"""Akku-Register (Roadmap Phase 8) in data/akkus.json.

Ein Akku wird nie gelöscht, nur auf „ausgemustert“ gesetzt – alte Flüge verweisen weiter auf seine ID.
Zyklen/Flugzeit werden NICHT hier gespeichert, sondern in stats.py aus den fluege.jsonl berechnet.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
import threading

from app import config

FILE = config.DATA_DIR / "akkus.json"
_LOCK = threading.Lock()


def load() -> list[dict]:
    try:
        data = json.loads(FILE.read_text(encoding="utf-8"))
        return [a for a in data.get("akkus", []) if isinstance(a, dict) and a.get("id")]
    except FileNotFoundError:
        return []
    except Exception as e:  # noqa: BLE001 – kaputte Datei nie überschreiben
        raise ValueError(f"{FILE} ist nicht lesbar ({e}) – bitte prüfen.") from e


def _save(items: list[dict]) -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=config.DATA_DIR, prefix=".akkus_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump({"akkus": items}, f, ensure_ascii=False, indent=2)
    os.replace(tmp, FILE)


def _int(v, lo, hi, name):
    s = str(v or "").strip()
    if not s:
        return None
    if not s.isdigit() or not lo <= int(s) <= hi:
        raise ValueError(f"{name}: bitte eine Zahl zwischen {lo} und {hi}.")
    return int(s)


def upsert(data: dict) -> dict:
    """Akku anlegen oder ändern. id = kurze Kennung, die auf dem Pack steht (z. B. „A1“ oder „6S-1300-03“)."""
    aid = str(data.get("id") or "").strip()[:40]
    if not aid or not re.fullmatch(r"[\w.\-+# äöüÄÖÜß]+", aid):
        raise ValueError("Akku-ID fehlt oder enthält ungültige Zeichen (z. B. „A1“, „6S-1300-03“).")
    kauf = str(data.get("kaufdatum") or "").strip()
    if kauf and not re.fullmatch(r"\d{4}-\d{2}(-\d{2})?", kauf):
        raise ValueError("Kaufdatum bitte als JJJJ-MM-TT oder JJJJ-MM.")
    item = {"id": aid, "name": str(data.get("name") or "").strip()[:60],
            "zellen": _int(data.get("zellen"), 1, 12, "Zellen (S)"), "mah": _int(data.get("mah"), 50, 50000, "mAh"),
            "kaufdatum": kauf or None, "notiz": str(data.get("notiz") or "").strip()[:300],
            "ausgemustert": bool(data.get("ausgemustert"))}
    with _LOCK:
        items = load()
        items = [item if a["id"] == aid else a for a in items] if any(a["id"] == aid for a in items) else items + [item]
        _save(items)
    return item


def label(a: dict) -> str:
    bits = [a["id"]]
    if a.get("zellen") or a.get("mah"):
        bits.append(f"{a.get('zellen') or '?'}S {a.get('mah') or '?'} mAh")
    if a.get("name"):
        bits.append(a["name"])
    return " · ".join(bits)
