"""Startet bei Bedarf den lokalen Web-Server (127.0.0.1:8767) und liefert die Karten-URL.

Plattformunabhängig (macOS/Windows/Linux): kein open/osascript, nur subprocess + urllib.
"""
from __future__ import annotations

import subprocess
import sys
import time
import urllib.request

from app import config

BASE = config.WEB_URL
MAP_URL = BASE + "/karte"


def is_up(timeout: float = 1.5) -> bool:
    try:
        with urllib.request.urlopen(BASE + "/health", timeout=timeout) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def ensure_server(wait_s: float = 15.0) -> str:
    """Prüft /health; startet sonst web/server.py losgelöst (Log: data/web.log). Gibt die Karten-URL zurück."""
    if is_up():
        return MAP_URL
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    log = open(config.DATA_DIR / "web.log", "ab")  # noqa: SIM115 – bleibt beim Kindprozess
    kw: dict = {"stdout": log, "stderr": log, "stdin": subprocess.DEVNULL, "cwd": str(config.PROJECT_DIR)}
    if sys.platform.startswith("win"):
        kw["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
    else:
        kw["start_new_session"] = True
    proc = subprocess.Popen([sys.executable, str(config.PROJECT_DIR / "web" / "server.py")], **kw)
    try:
        (config.DATA_DIR / "web.pid").write_text(str(proc.pid))
    except OSError:
        pass
    end = time.time() + wait_s
    while time.time() < end:
        if is_up(1.0):
            return MAP_URL
        if proc.poll() is not None:
            break
        time.sleep(0.4)
    raise RuntimeError("Web-Server startet nicht – siehe data/web.log")
