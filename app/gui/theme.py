"""Farben & Schriften – dunkles Theme."""
from __future__ import annotations

import customtkinter as ctk

# Grundfarben (GitHub-Dark-angelehnt)
BG        = "#0b0f14"
CARD      = "#161b22"
CARD_HOV  = "#1c232c"
BORDER    = "#30363d"
TEXT      = "#e6edf3"
MUTED     = "#8b949e"

ACCENT       = "#2f81f7"
ACCENT_HOVER = "#1f6feb"
OK    = "#3fb950"
WARN  = "#d29922"
ERR   = "#f85149"
STOP  = "#da3633"
STOP_HOVER = "#b62324"
GREY  = "#373e47"
GREY_HOVER = "#444c56"

STATE_COLOR = {"ok": OK, "idle": WARN, "off": ERR}


def font(size: int = 13, weight: str = "normal") -> ctk.CTkFont:
    return ctk.CTkFont(size=size, weight=weight)


def mono(size: int = 12) -> ctk.CTkFont:
    return ctk.CTkFont(family="Menlo", size=size)
