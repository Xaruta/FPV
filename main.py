#!/usr/bin/env python3
"""FPV-Lagezentrum – Wetter, Flugradar, Spots, Preflight-Checkliste. Start: .venv/bin/python main.py
Läuft auf macOS, Linux und Windows (Python 3.11+, customtkinter)."""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from app import config


def setup_logging() -> None:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(config.LOG_FILE, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.basicConfig(level=logging.INFO, handlers=[h, logging.StreamHandler()])


def single_instance():
    """Nur ein Fenster gleichzeitig – plattformunabhängig (fcntl bzw. msvcrt)."""
    f = open(config.LOCK_FILE, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def main() -> int:
    setup_logging()
    lock = single_instance()
    if lock is None:
        try:
            import tkinter
            from tkinter import messagebox
            r = tkinter.Tk(); r.withdraw()
            messagebox.showinfo(config.APP_NAME, "Das FPV-Lagezentrum läuft bereits.")
            r.destroy()
        except Exception:  # noqa: BLE001
            print("FPV-Lagezentrum läuft bereits.")
        return 1
    from app.gui.main_window import MainWindow
    logging.getLogger("main").info("Start %s %s", config.APP_NAME, config.APP_VERSION)
    MainWindow().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
