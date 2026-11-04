"""Hauptfenster des FPV-Lagezentrums – Spots, Wetter-Ampel, Flugradar, Checkliste, dipul-Hinweis."""
from __future__ import annotations

import logging
import math
import queue
import random
import threading
import tkinter as tk
import webbrowser
from tkinter import messagebox

import customtkinter as ctk

from app import config, dipul, export, geo, logbook, metar, notam, opensky, settings, spots, sun, weather, webmap
from app.gui import theme as T
from app.gui.spots_view import ProfileEditor, TodayWindow
from app.gui.stats_view import FlightsWindow, StatsWindow

log = logging.getLogger("gui")

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

AMPEL = {"gruen": (T.OK, "🟢"), "gelb": (T.WARN, "🟡"), "rot": (T.ERR, "🔴"), None: (T.MUTED, "⚪")}
MOTIVATION = [
    "Jeder Pro-Pilot hat mal mit Gras im Prop angefangen. 🌱",
    "Ein Akku mehr geht immer. 🔋",
    "Heute ist ein guter Tag für einen sauberen Power-Loop. 🔁",
    "Checkliste fertig = entspannter Flug. 😎",
    "Smooth is fast. 🏁",
    "Tief fliegen, hoch motiviert. 🚀",
]


def _btn(master, text, cmd, kind="ghost", **kw):
    fg, hov = {"primary": (T.ACCENT, T.ACCENT_HOVER), "stop": (T.STOP, T.STOP_HOVER),
               "ok": ("#238636", "#2ea043"), "ghost": (T.GREY, T.GREY_HOVER)}[kind]
    kw.setdefault("height", 32)
    return ctk.CTkButton(master, text=text, command=cmd, fg_color=fg, hover_color=hov,
                         font=T.font(12, "bold"), corner_radius=9, **kw)


def _card(master):
    return ctk.CTkFrame(master, fg_color=T.CARD, corner_radius=14, border_width=1, border_color=T.BORDER)


def _title(card, text, row=0, col=0, span=1):
    ctk.CTkLabel(card, text=text, font=T.font(15, "bold"), text_color=T.TEXT, anchor="w").grid(
        row=row, column=col, columnspan=span, sticky="w", padx=16, pady=(14, 6))


def _entry(master, width=120, ph=""):
    return ctk.CTkEntry(master, width=width, placeholder_text=ph, fg_color=T.BG, border_color=T.BORDER,
                        text_color=T.TEXT, font=T.font(13), height=32)


def _fmt(v, nd=1, unit=""):
    if v is None:
        return "–"
    return f"{v:.{nd}f}{unit}" if isinstance(v, (int, float)) else str(v)


class MainWindow(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{config.APP_NAME}")
        self.geometry("1180x940")
        self.minsize(980, 720)
        self.configure(fg_color=T.BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        try:
            spots.migrate()   # Phase 7: Spot-Profile anlegen (bestehende Spots bleiben erhalten)
        except Exception:  # noqa: BLE001
            log.exception("Spot-Migration fehlgeschlagen")
        self.cfg = settings.load()
        self.spot_hazards: list[str] = []
        self.q: queue.Queue = queue.Queue()
        self.weather: dict | None = None
        self.radar: dict | None = None
        self.geo_hits: list[dict] = []
        self.hit_region: tuple | None = None
        self._radar_job = None
        self._light = None
        self.ops = {"spot": "📍 –", "ampel": "⚪ …", "licht": ""}

        self._build_header()
        body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=14, pady=(4, 4))
        body.grid_columnconfigure((0, 1), weight=1, uniform="c")
        self._build_spot(body)
        self._build_ampel(body)
        self._build_weather(body)
        self._build_radar(body)
        self._build_checklist(body)
        self._build_side(body)
        self._build_logbook(body)
        self._build_footer()

        self._load_spot_into_fields()
        self.after(100, self._poll_queue)
        self.after(300, self.refresh_all)
        self.after(800, self.refresh_logbook)
        self.after(60_000, self._log_tick)

    # ------------------------------------------------------------------ Hintergrund-Arbeit
    def _bg(self, fn, done):
        def run():
            try:
                res, err = fn(), None
            except Exception as e:  # noqa: BLE001
                log.warning("Hintergrundfehler: %s", e)
                res, err = None, str(e)
            self.q.put((done, res, err))
        threading.Thread(target=run, daemon=True).start()

    def _poll_queue(self):
        try:
            while True:
                done, res, err = self.q.get_nowait()
                try:
                    done(res, err)
                except Exception:  # noqa: BLE001
                    log.exception("UI-Update fehlgeschlagen")
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _save(self):
        try:
            settings.save(self.cfg)
        except OSError as e:
            messagebox.showerror(config.APP_NAME, f"Einstellungen konnten nicht gespeichert werden:\n{e}")

    def _spot(self):
        return settings.active_spot(self.cfg)

    # ------------------------------------------------------------------ Kopf
    def _build_header(self):
        head = ctk.CTkFrame(self, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", padx=22, pady=(18, 6))
        head.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(head, text="🛸  FPV-Lagezentrum", font=T.font(26, "bold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w")
        self.sub_lbl = ctk.CTkLabel(head, text="Wetter-Ampel · Flugradar · Spots · Preflight-Check",
                                    font=T.font(13), text_color=T.MUTED, anchor="w")
        self.sub_lbl.grid(row=1, column=0, sticky="w")
        right = ctk.CTkFrame(head, fg_color="transparent")
        right.grid(row=0, column=1, rowspan=2, sticky="e")
        self.spot_menu = ctk.CTkOptionMenu(right, values=["–"], command=self._on_spot_select, width=190, height=34,
                                           font=T.font(13, "bold"), dropdown_font=T.font(13), fg_color=T.GREY,
                                           button_color=T.ACCENT, button_hover_color=T.ACCENT_HOVER)
        self.spot_menu.grid(row=0, column=0, padx=(0, 8))
        _btn(right, "🔄 Aktualisieren", lambda: self.refresh_all(force=True), "primary", width=140).grid(
            row=0, column=1, padx=(0, 8))
        _btn(right, "🌐 Web", lambda: webbrowser.open(config.WEB_URL), width=80).grid(row=0, column=2)

    # ------------------------------------------------------------------ Standort / Spots
    def _build_spot(self, body):
        c = _card(body)
        c.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)
        c.grid_columnconfigure(1, weight=1)
        _title(c, "📍 Standort / Spots", span=3)
        ctk.CTkLabel(c, text="Ort suchen", font=T.font(12), text_color=T.MUTED).grid(row=1, column=0, sticky="w", padx=16)
        self.e_search = _entry(c, ph="z. B. Hannover oder Flugplatz-Ort")
        self.e_search.grid(row=1, column=1, sticky="ew", padx=(0, 8), pady=3)
        self.e_search.bind("<Return>", lambda _e: self.do_geocode())
        _btn(c, "🔎 Suchen", self.do_geocode, width=100).grid(row=1, column=2, padx=(0, 16), pady=3)
        self.hit_menu = ctk.CTkOptionMenu(c, values=["(noch keine Suche)"], command=self._on_hit, height=30,
                                          font=T.font(12), dropdown_font=T.font(12), fg_color=T.BG,
                                          button_color=T.GREY, button_hover_color=T.GREY_HOVER)
        self.hit_menu.grid(row=2, column=1, columnspan=2, sticky="ew", padx=(0, 16), pady=3)

        for i, (lbl, attr, ph) in enumerate((("Spot-Name", "e_name", "Haus, Field, Wiese …"),
                                              ("Breite (lat)", "e_lat", "52.3705"),
                                              ("Länge (lon)", "e_lon", "9.7332")), start=3):
            ctk.CTkLabel(c, text=lbl, font=T.font(12), text_color=T.MUTED).grid(row=i, column=0, sticky="w", padx=16)
            e = _entry(c, ph=ph)
            e.grid(row=i, column=1, columnspan=2, sticky="ew", padx=(0, 16), pady=3)
            setattr(self, attr, e)
        row = ctk.CTkFrame(c, fg_color="transparent")
        row.grid(row=6, column=0, columnspan=3, sticky="ew", padx=16, pady=(8, 4))
        _btn(row, "💾 Spot speichern", self.save_spot, "ok", width=140).pack(side="left", padx=(0, 6))
        _btn(row, "🗑 Löschen", self.delete_spot, "stop", width=100).pack(side="left", padx=(0, 6))
        _btn(row, "🗺 dipul-Karte", self.open_dipul, "primary", width=120).pack(side="left")
        row2 = ctk.CTkFrame(c, fg_color="transparent")
        row2.grid(row=8, column=0, columnspan=3, sticky="ew", padx=16, pady=(0, 14))
        _btn(row2, "🗂 Spot-Profil", self.open_profile, width=130).pack(side="left", padx=(0, 6))
        _btn(row2, "🏆 Wo fliege ich heute?", self.open_today, "primary", width=180).pack(side="left", padx=(0, 6))
        _btn(row2, "⬇ Import …", self.import_profile, width=100).pack(side="left", padx=(0, 6))
        _btn(row2, "🗺 Karte öffnen", self.open_map, "primary", width=130).pack(side="left")
        self.spot_info = ctk.CTkLabel(c, text="", font=T.font(12), text_color=T.MUTED, anchor="w", justify="left",
                                      wraplength=480)
        self.spot_info.grid(row=7, column=0, columnspan=3, sticky="ew", padx=16, pady=(2, 6))

    def _refresh_spot_menu(self):
        names = [s["name"] for s in self.cfg["spots"]]
        self.spot_menu.configure(values=names or ["– kein Spot –"])
        sp = self._spot()
        self.spot_menu.set(sp["name"] if sp else "– kein Spot –")

    def _load_spot_into_fields(self):
        self._refresh_spot_menu()
        sp = self._spot()
        for e in (self.e_name, self.e_lat, self.e_lon):
            e.delete(0, "end")
        try:
            self.spot_hazards = spots.checklist_extras(spots.by_name(sp["name"], self.cfg)) if sp else []
        except Exception:  # noqa: BLE001
            self.spot_hazards = []
        if hasattr(self, "ck_fr"):
            self._render_checklist()
        if sp:
            self.e_name.insert(0, sp["name"])
            self.e_lat.insert(0, f"{sp['lat']}")
            self.e_lon.insert(0, f"{sp['lon']}")
            self.spot_info.configure(text=f"Aktiv: {sp['name']}  ({sp['lat']:.5f}, {sp['lon']:.5f})", text_color=T.MUTED)
            self.ops_set("spot", f"📍 {sp['name']}")
            if hasattr(self, "w_light"):
                self.refresh_light()
            if hasattr(self, "dz_lbl"):
                self.refresh_dipul()
        else:
            self.spot_info.configure(text="⚠ Bitte Standort setzen: Ort suchen oder Koordinaten eintragen, "
                                          "dann „Spot speichern“.", text_color=T.WARN)

    def _on_spot_select(self, name):
        if any(s["name"] == name for s in self.cfg["spots"]):
            self.cfg["active"] = name
            self._save()
            self._load_spot_into_fields()
            self.refresh_all()

    def do_geocode(self):
        q = self.e_search.get().strip()
        if len(q) < 2:
            self.spot_info.configure(text="Bitte einen Ortsnamen eingeben.", text_color=T.WARN)
            return
        self.spot_info.configure(text=f"Suche „{q}“ …", text_color=T.MUTED)

        def done(res, err):
            if err:
                self.spot_info.configure(text=f"Suche fehlgeschlagen: {err}", text_color=T.ERR)
                return
            self.geo_hits = res or []
            if not self.geo_hits:
                self.spot_info.configure(text=f"Nichts gefunden für „{q}“.", text_color=T.WARN)
                self.hit_menu.configure(values=["(keine Treffer)"]); self.hit_menu.set("(keine Treffer)")
                return
            labels = [h["label"] for h in self.geo_hits]
            self.hit_menu.configure(values=labels)
            self.hit_menu.set(labels[0])
            self._on_hit(labels[0])
        self._bg(lambda: geo.geocode(q), done)

    def _on_hit(self, label):
        for h in self.geo_hits:
            if h["label"] == label:
                if not self.e_name.get().strip() or self.e_name.get().strip() in [x["name"] for x in self.geo_hits]:
                    self.e_name.delete(0, "end"); self.e_name.insert(0, h["name"])
                self.e_lat.delete(0, "end"); self.e_lat.insert(0, f"{h['lat']:.5f}")
                self.e_lon.delete(0, "end"); self.e_lon.insert(0, f"{h['lon']:.5f}")
                self.hit_region = (round(h["lat"], 5), round(h["lon"], 5), h["label"])
                self.spot_info.configure(text=f"Gefunden: {h['label']} – mit „Spot speichern“ übernehmen.",
                                         text_color=T.OK)

    def save_spot(self):
        try:
            lat = float(self.e_lat.get().replace(",", "."))
            lon = float(self.e_lon.get().replace(",", "."))
            reg = None
            if self.hit_region and abs(self.hit_region[0] - lat) < 0.01 and abs(self.hit_region[1] - lon) < 0.01:
                reg = self.hit_region[2]
            settings.upsert_spot(self.cfg, self.e_name.get(), lat, lon, reg)
        except ValueError as e:
            self.spot_info.configure(text=f"Ungültige Koordinaten: {e}", text_color=T.ERR)
            return
        self._save()
        try:
            spots.migrate(self.cfg)   # ID + Profil für neuen Spot, Koordinaten ins Profil
            self._save()
        except Exception:  # noqa: BLE001
            log.exception("Spot-Profil nicht angelegt")
        self._load_spot_into_fields()
        self.refresh_all(force=True)

    def delete_spot(self):
        sp = self._spot()
        if not sp:
            return
        if messagebox.askyesno(config.APP_NAME, f"Spot „{sp['name']}“ wirklich entfernen?"):
            settings.remove_spot(self.cfg, sp["name"])
            self._save()
            self._load_spot_into_fields()
            self.refresh_all()

    # ------------------------------------------------------------------ Spot-Datenbank (Phase 7)
    def _reload_after_profile(self, _p=None):
        self._save()   # Editor arbeitet auf self.cfg (Name/Koordinaten/Import) → jetzt speichern
        self._load_spot_into_fields()

    def open_profile(self):
        sp = self._spot()
        if not sp:
            self.spot_info.configure(text="Erst einen Spot speichern.", text_color=T.WARN)
            return
        try:
            prof = spots.by_name(sp["name"], self.cfg) or spots.normalize(sp)
            self.cfg = settings.load()
        except ValueError as e:
            messagebox.showerror(config.APP_NAME, str(e))
            return
        ProfileEditor(self, prof, self.cfg, self._reload_after_profile)

    def open_today(self):
        TodayWindow(self, self.cfg, self._bg, self._activate_spot)

    def open_map(self):
        """Öffnet die Leaflet-Karte der Web-Oberfläche (startet den lokalen Web-Server bei Bedarf)."""
        self.spot_info.configure(text="🗺 Öffne Karte … (starte ggf. lokalen Web-Server auf 127.0.0.1:8767)",
                                 text_color=T.MUTED)

        def done(url, err):
            if err:
                self.spot_info.configure(text=f"⚠ Karte: {err}", text_color=T.ERR)
                return
            webbrowser.open(url)
            self.spot_info.configure(text=f"🗺 Karte im Browser geöffnet: {url}", text_color=T.MUTED)
        self._bg(webmap.ensure_server, done)

    def _activate_spot(self, name):
        self.cfg = settings.load()
        self._on_spot_select(name)

    def import_profile(self):
        from tkinter import filedialog
        import json as _json
        from pathlib import Path as _P
        fn = filedialog.askopenfilename(title="Spot-Profil importieren", filetypes=[("JSON", "*.json")])
        if not fn:
            return
        try:
            p = spots.import_profile(_json.loads(_P(fn).read_text(encoding="utf-8")), self.cfg)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(config.APP_NAME, f"Import fehlgeschlagen: {e}")
            return
        self._save()
        self._load_spot_into_fields()
        self.spot_info.configure(text=f"Spot „{p['name']}“ importiert – im Menü oben auswählbar.", text_color=T.OK)

    def open_dipul(self):
        sp = self._spot()
        webbrowser.open(geo.dipul_url(sp["lat"], sp["lon"]) if sp else config.DIPUL_HOME)

    # ------------------------------------------------------------------ Ampel
    def _build_ampel(self, body):
        c = _card(body)
        c.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)
        c.grid_columnconfigure(0, weight=1)
        _title(c, "🚦 Flug-Ampel")
        self.amp_big = ctk.CTkLabel(c, text="⚪  Kein Standort", font=T.font(30, "bold"), text_color=T.MUTED, anchor="w")
        self.amp_big.grid(row=1, column=0, sticky="ew", padx=16, pady=(4, 6))
        self.amp_bar = ctk.CTkFrame(c, height=8, corner_radius=4, fg_color=T.GREY)
        self.amp_bar.grid(row=2, column=0, sticky="ew", padx=16)
        self.amp_reasons = ctk.CTkLabel(c, text="", font=T.font(13), text_color=T.TEXT, anchor="w", justify="left",
                                        wraplength=480)
        self.amp_reasons.grid(row=3, column=0, sticky="ew", padx=16, pady=(10, 4))
        self.amp_sun = ctk.CTkLabel(c, text="", font=T.font(12), text_color=T.MUTED, anchor="w")
        self.amp_sun.grid(row=4, column=0, sticky="ew", padx=16)
        ctk.CTkLabel(c, text="Nur Wetter-Orientierung. Maßgeblich für Geozonen & Regeln sind dipul/DFS und LBA.",
                     font=T.font(11), text_color=T.MUTED, anchor="w", wraplength=480, justify="left").grid(
            row=5, column=0, sticky="ew", padx=16, pady=(6, 14))

    # ------------------------------------------------------------------ Wetter
    def _build_weather(self, body):
        c = _card(body)
        c.grid(row=1, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        c.grid_columnconfigure(tuple(range(7)), weight=1)
        _title(c, "🌤 Wetter am Spot", span=5)
        self.w_meta = ctk.CTkLabel(c, text="", font=T.font(12), text_color=T.MUTED, anchor="e")
        self.w_meta.grid(row=0, column=5, columnspan=2, sticky="e", padx=16)

        self.compass = tk.Canvas(c, width=120, height=120, bg=T.CARD, highlightthickness=0)
        self.compass.grid(row=1, column=0, rowspan=2, padx=(16, 4), pady=4)
        self.tiles = {}
        spec = [("wind", "Wind", "m/s"), ("boeen", "Böen", "m/s"), ("richtung", "Richtung", ""),
                ("temp", "Temperatur", "°C"), ("regen", "Regen", "mm"), ("sicht", "Sicht", "km")]
        for i, (k, lbl, unit) in enumerate(spec, start=1):
            f = ctk.CTkFrame(c, fg_color=T.BG, corner_radius=12, border_width=1, border_color=T.BORDER)
            f.grid(row=1, column=i, sticky="nsew", padx=4, pady=4)
            ctk.CTkLabel(f, text=lbl, font=T.font(12), text_color=T.MUTED).pack(pady=(8, 0))
            v = ctk.CTkLabel(f, text="–", font=T.font(30, "bold"), text_color=T.TEXT)
            v.pack()
            u = ctk.CTkLabel(f, text=unit, font=T.font(11), text_color=T.MUTED)
            u.pack(pady=(0, 8))
            self.tiles[k] = (v, u)
        self.w_line = ctk.CTkLabel(c, text="", font=T.font(13), text_color=T.TEXT, anchor="w")
        self.w_line.grid(row=2, column=1, columnspan=6, sticky="ew", padx=6)
        self.hours_fr = ctk.CTkFrame(c, fg_color="transparent")
        self.hours_fr.grid(row=3, column=0, columnspan=7, sticky="ew", padx=16, pady=(6, 4))
        self.w_light = ctk.CTkLabel(c, text="", font=T.font(13, "bold"), text_color=T.TEXT, anchor="w", justify="left",
                                    wraplength=1050)
        self.w_light.grid(row=4, column=0, columnspan=7, sticky="ew", padx=16, pady=(2, 14))
        self._draw_compass(None)

    def _draw_compass(self, from_deg):
        cv = self.compass
        cv.delete("all")
        cx = cy = 60
        r = 48
        cv.create_oval(cx - r, cy - r, cx + r, cy + r, outline=T.BORDER, width=2)
        for txt, ang in (("N", 0), ("O", 90), ("S", 180), ("W", 270)):
            a = math.radians(ang)
            cv.create_text(cx + (r - 10) * math.sin(a), cy - (r - 10) * math.cos(a), text=txt, fill=T.MUTED,
                           font=("Helvetica", 10, "bold"))
        if from_deg is None:
            cv.create_text(cx, cy, text="?", fill=T.MUTED, font=("Helvetica", 18, "bold"))
            return
        to = math.radians((from_deg + 180) % 360)
        x1, y1 = cx - 30 * math.sin(to), cy + 30 * math.cos(to)
        x2, y2 = cx + 30 * math.sin(to), cy - 30 * math.cos(to)
        cv.create_line(x1, y1, x2, y2, fill=T.ACCENT, width=5, arrow="last", arrowshape=(14, 16, 6))

    def _update_weather(self, w, err):
        sp = self._spot()
        if err or not w:
            self.w_meta.configure(text=f"⚠ Wetter: {err or 'keine Daten'}", text_color=T.ERR)
            self._set_ampel(None, [f"Wetter nicht verfügbar: {err}"] if err else ["Bitte Standort setzen."])
            return
        self.weather = w
        th = self.cfg["thresholds"]
        a = weather.assess(w, th)
        col_w = T.ERR if (w["wind"] or 0) >= th["wind_max"] else T.WARN if (w["wind"] or 0) >= th["wind_warn"] else T.OK
        col_g = T.ERR if (w["boeen"] or 0) >= th["gust_max"] else T.WARN if (w["boeen"] or 0) >= th["gust_warn"] else T.OK
        self.tiles["wind"][0].configure(text=_fmt(w["wind"]), text_color=col_w)
        self.tiles["boeen"][0].configure(text=_fmt(w["boeen"]), text_color=col_g)
        self.tiles["richtung"][0].configure(text=f"{w['pfeil']} {w['richtung_txt']}")
        self.tiles["richtung"][1].configure(text=f"aus {_fmt(w['richtung'], 0, '°')}")
        self.tiles["temp"][0].configure(text=_fmt(w["temp"]))
        self.tiles["temp"][1].configure(text=f"°C · gefühlt {_fmt(w['gefuehlt'], 0)}")
        self.tiles["regen"][0].configure(text=_fmt(w["regen"]))
        self.tiles["sicht"][0].configure(text=_fmt((w["sicht"] or 0) / 1000 if w["sicht"] is not None else None, 1))
        self._draw_compass(w["richtung"])
        self.w_line.configure(text=f"{w['wetter'].capitalize()} · Wolken {_fmt(w['wolken'], 0, ' %')} · "
                                   f"Luftfeuchte {_fmt(w['feuchte'], 0, ' %')} · Höhe {_fmt(w['hoehe'], 0, ' m')}")
        self.w_meta.configure(text=f"Open-Meteo · Messung {w['messzeit']} · Abruf {w['abruf']}", text_color=T.MUTED)
        for ch in self.hours_fr.winfo_children():
            ch.destroy()
        for i, h in enumerate(w["stunden"][:8]):
            g = h["boeen"] or 0
            col = T.ERR if g >= th["gust_max"] else T.WARN if g >= th["gust_warn"] else T.OK
            f = ctk.CTkFrame(self.hours_fr, fg_color=T.BG, corner_radius=10, border_width=1, border_color=T.BORDER)
            f.grid(row=0, column=i, sticky="ew", padx=3)
            self.hours_fr.grid_columnconfigure(i, weight=1)
            ctk.CTkLabel(f, text=h["zeit"], font=T.font(11, "bold"), text_color=T.MUTED).pack(pady=(4, 0))
            ctk.CTkLabel(f, text=f"{geo.wind_arrow(h['richtung'])} {_fmt(h['wind'], 0)}/{_fmt(h['boeen'], 0)}",
                         font=T.font(13, "bold"), text_color=col).pack()
            ctk.CTkLabel(f, text=f"{_fmt(h['temp'], 0, '°')} · ☔{_fmt(h['regen_pct'], 0, '%')}", font=T.font(11),
                         text_color=T.MUTED).pack(pady=(0, 4))
        self._set_ampel(a["stufe"], a["gruende"], a["titel"])
        sun_ = []
        if w.get("sonnenaufgang"):
            sun_.append(f"🌅 Aufgang {w['sonnenaufgang']}")
        if w.get("sonnenuntergang"):
            sun_.append(f"🌇 Untergang {w['sonnenuntergang']}")
        lt = self.refresh_light()
        if lt and lt.get("daemmerung_ende"):
            sun_.append(f"🌆 dunkel ab {lt['daemmerung_ende']}")
        self.amp_sun.configure(text="   ".join(sun_) if sun_ else "")
        if sp:
            log.info("Wetter %s: %s", sp["name"], a["stufe"])

    def _set_ampel(self, lvl, reasons, title=None):
        col, dot = AMPEL.get(lvl, AMPEL[None])
        self.amp_big.configure(text=f"{dot}  {title or 'Keine Bewertung'}", text_color=col)
        self.amp_bar.configure(fg_color=col)
        self.amp_reasons.configure(text="\n".join(f"• {r}" for r in reasons))
        self.ops_set("ampel", f"{dot} {title or 'Keine Bewertung'}")

    # ------------------------------------------------------------------ Ops-Streifen & Licht
    def ops_set(self, key, text):
        self.ops[key] = text
        self.sub_lbl.configure(text="   │   ".join(v for v in (self.ops["spot"], self.ops["ampel"],
                                                             self.ops["licht"]) if v))

    def refresh_dipul(self, force=False):
        """Geografische Gebiete am Spot über den offiziellen dipul-WFS (Hinweis, kein Rechtsrat)."""
        sp = self._spot()
        if not sp:
            self.dz_lbl.configure(text="", text_color=T.MUTED)
            return
        self.dz_lbl.configure(text="🗺 Frage dipul-Geodaten am Spot ab …", text_color=T.MUTED)
        lat, lon, name = sp["lat"], sp["lon"], sp["name"]

        def done(r, err):
            cur = self._spot()
            if not cur or cur["name"] != name:
                return
            if err or not r:
                self.dz_lbl.configure(text=f"⚠ dipul-Abfrage: {err or 'keine Antwort'} – bitte dipul-Karte nutzen.",
                                      text_color=T.ERR)
                return
            hart = [z for z in (r["am_spot"] or []) if not z["info_only"]]
            col = T.ERR if r["am_spot"] is None else (T.WARN if hart or r.get("fehler") else T.TEXT)
            self.dz_lbl.configure(text="\n".join(dipul.text_lines(r)), text_color=col)
            self.dz_src.configure(text=(f"Quelle Geodaten: {r['quelle']} (Lizenz ↗)"
                                        + (f" · Abruf {r['abruf']}" if r.get("abruf") else "")
                                        + (" · Cache" if r.get("aus_cache") else "")
                                        + f"\n{r['hinweis']}"))
        self._bg(lambda: dipul.check(lat, lon, force=force), done)

    def refresh_light(self):
        """Lichtlage lokal berechnen (≈1 ms) – jede Minute neu, damit der Countdown läuft."""
        sp = self._spot()
        if not sp:
            self.w_light.configure(text="")
            return None
        lt = sun.light(sp["lat"], sp["lon"])
        warn = lt["phase"] in ("nacht", "daemmerung_abend", "daemmerung_morgen") or lt.get("warnung") or lt.get("gegenlicht")
        times_ = " · ".join(x for x in (
            f"Dämmerung ab {lt['daemmerung_beginn']}" if lt["daemmerung_beginn"] else "",
            f"🌅 {lt['aufgang']}" if lt["aufgang"] else "", f"🌇 {lt['untergang']}" if lt["untergang"] else "",
            f"dunkel ab {lt['daemmerung_ende']}" if lt["daemmerung_ende"] else "") if x)
        self.w_light.configure(text=f"{lt['text']}\nHeute: {times_} (lokal berechnet)",
                               text_color=T.WARN if warn else T.TEXT)
        self.ops_set("licht", lt["kurz"])
        self._light = lt
        return lt

    # ------------------------------------------------------------------ Radar
    def _build_radar(self, body):
        c = _card(body)
        c.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        c.grid_columnconfigure(0, weight=1)
        top = ctk.CTkFrame(c, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        top.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(top, text="✈ Flugradar (OpenSky)", font=T.font(15, "bold"), text_color=T.TEXT).grid(row=0, column=0)
        self.r_meta = ctk.CTkLabel(top, text="", font=T.font(12), text_color=T.MUTED, anchor="e")
        self.r_meta.grid(row=0, column=1, sticky="e", padx=8)
        self.auto_var = ctk.BooleanVar(value=bool(self.cfg.get("radar_auto", True)))
        ctk.CTkSwitch(top, text=f"Auto ({self.cfg.get('radar_interval', 60)} s)", variable=self.auto_var,
                      command=self._on_auto, font=T.font(12), progress_color=T.ACCENT).grid(row=0, column=2, padx=8)
        _btn(top, "🔄 Radar", lambda: self.refresh_radar(force=True), width=90).grid(row=0, column=3)

        cols = [("Rufzeichen", 110), ("Distanz", 80), ("Peilung", 70), ("Höhe", 90), ("Tempo", 90), ("Kurs", 70),
                ("Steigen", 80), ("Herkunft", 130), ("Hinweis", 110)]
        self.r_cols = cols
        hdr = ctk.CTkFrame(c, fg_color=T.BG, corner_radius=8)
        hdr.grid(row=1, column=0, sticky="ew", padx=16)
        for i, (t, w) in enumerate(cols):
            hdr.grid_columnconfigure(i, minsize=w, weight=1)
            ctk.CTkLabel(hdr, text=t, font=T.font(12, "bold"), text_color=T.MUTED, anchor="w").grid(
                row=0, column=i, sticky="w", padx=6, pady=4)
        self.r_list = ctk.CTkScrollableFrame(c, fg_color="transparent", height=230)
        self.r_list.grid(row=2, column=0, sticky="ew", padx=10, pady=(2, 4))
        for i, (_t, w) in enumerate(cols):
            self.r_list.grid_columnconfigure(i, minsize=w, weight=1)
        ctk.CTkLabel(c, text="Daten: The OpenSky Network (opensky-network.org) – nur Flugzeuge mit Transponder/ADS-B; "
                             "Hubschrauber, Segler & Drohnen fehlen oft. Augen auf!", font=T.font(11),
                     text_color=T.MUTED, anchor="w", wraplength=1000, justify="left").grid(
            row=3, column=0, sticky="ew", padx=16, pady=(0, 14))

    def _on_auto(self):
        self.cfg["radar_auto"] = bool(self.auto_var.get())
        self._save()
        self._schedule_radar()

    def _schedule_radar(self):
        if self._radar_job:
            self.after_cancel(self._radar_job)
            self._radar_job = None
        if self.auto_var.get() and self._spot():
            self._radar_job = self.after(int(self.cfg.get("radar_interval", 60)) * 1000, self.refresh_radar)

    def _update_radar(self, r, err):
        self._schedule_radar()
        for ch in self.r_list.winfo_children():
            ch.destroy()
        if err or not r:
            self.r_meta.configure(text=f"⚠ {err or 'keine Daten'}", text_color=T.ERR)
            return
        self.radar = r
        planes = r["flugzeuge"]
        rest = f" · Kontingent übrig: {r['rest']}" if r.get("rest") is not None else ""
        cache = " (Cache)" if r.get("aus_cache") else ""
        box = r.get("box", self.cfg.get("radar_box_deg", 0.5))
        if r.get("fehler"):
            self.r_meta.configure(text=f"⚠ {r['fehler']}", text_color=T.WARN)
        else:
            self.r_meta.configure(text=f"{len(planes)} Luftfahrzeuge · Box ±{box}° · Abruf {r.get('abruf') or '–'}"
                                       f"{cache}{rest}", text_color=T.MUTED)
        if not planes:
            msg = ("Gerade keine Flugzeuge mit Transponder in der Nähe (±{0}° ≈ {1} km). Das ist gut – "
                   "oder OpenSky hat hier wenig Empfänger. Trotzdem: Himmel beobachten!").format(box, int(box * 111))
            ctk.CTkLabel(self.r_list, text=msg if not r.get("fehler") else r["fehler"], font=T.font(13),
                         text_color=T.MUTED, wraplength=900, justify="left").grid(row=0, column=0, columnspan=9,
                                                                                  sticky="w", padx=6, pady=10)
            return
        for row, p in enumerate(planes[:60]):
            hint = opensky.alt_class(p)
            col = T.ERR if hint == "TIEF & NAH" else T.WARN if hint == "tief" else T.TEXT
            vals = [p["rufzeichen"], f"{p['dist_km']:.1f} km", p["peilung"],
                    "Boden" if p["boden"] else _fmt(p["hoehe_m"], 0, " m"), _fmt(p["speed_kmh"], 0, " km/h"),
                    _fmt(p["kurs"], 0, "°"), _fmt(p["steig"], 1, " m/s"), p["land"] or "–", hint]
            for i, v in enumerate(vals):
                ctk.CTkLabel(self.r_list, text=v, font=T.mono(12) if i in (0, 3, 4) else T.font(12),
                             text_color=col if i in (0, 3, 8) else T.TEXT, anchor="w").grid(
                    row=row, column=i, sticky="w", padx=6, pady=1)

    # ------------------------------------------------------------------ Checkliste
    def _build_checklist(self, body):
        c = _card(body)
        c.grid(row=3, column=0, sticky="nsew", padx=6, pady=6)
        c.grid_columnconfigure(0, weight=1)
        _title(c, "✅ Preflight-Checkliste")
        self.ck_prog = ctk.CTkProgressBar(c, height=10, progress_color=T.OK, fg_color=T.GREY)
        self.ck_prog.grid(row=1, column=0, sticky="ew", padx=16)
        self.ck_lbl = ctk.CTkLabel(c, text="", font=T.font(13, "bold"), text_color=T.TEXT, anchor="w", wraplength=480,
                                   justify="left")
        self.ck_lbl.grid(row=2, column=0, sticky="ew", padx=16, pady=(6, 4))
        self.ck_fr = ctk.CTkFrame(c, fg_color="transparent")
        self.ck_fr.grid(row=3, column=0, sticky="ew", padx=12)
        self.ck_fr.grid_columnconfigure(0, weight=1)
        add = ctk.CTkFrame(c, fg_color="transparent")
        add.grid(row=4, column=0, sticky="ew", padx=16, pady=(6, 14))
        add.grid_columnconfigure(0, weight=1)
        self.e_ck = _entry(add, ph="Eigener Punkt, z. B. „Kamera-Winkel 30°“")
        self.e_ck.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.e_ck.bind("<Return>", lambda _e: self.ck_add())
        _btn(add, "➕", self.ck_add, width=40).grid(row=0, column=1, padx=(0, 6))
        _btn(add, "↺ Zurücksetzen", self.ck_reset, width=120).grid(row=0, column=2, padx=(0, 6))
        _btn(add, "🖨 Drucken", self.print_checklist, width=100).grid(row=0, column=3)
        self._render_checklist()

    def _render_checklist(self):
        for ch in self.ck_fr.winfo_children():
            ch.destroy()
        items = self.cfg["checklist"]
        for i, it in enumerate(items):
            var = ctk.BooleanVar(value=bool(it.get("done")))
            cb = ctk.CTkCheckBox(self.ck_fr, text=it["text"], variable=var, font=T.font(13), text_color=T.TEXT,
                                 fg_color=T.OK, hover_color="#2ea043", border_color=T.BORDER,
                                 command=lambda i=i, v=var: self.ck_toggle(i, v.get()))
            cb.grid(row=i, column=0, sticky="w", padx=4, pady=2)
            ctk.CTkButton(self.ck_fr, text="✕", width=26, height=22, fg_color="transparent", hover_color=T.GREY,
                          text_color=T.MUTED, command=lambda i=i: self.ck_del(i)).grid(row=i, column=1, padx=4)
        for j, hz in enumerate(self.spot_hazards):
            ctk.CTkLabel(self.ck_fr, text=hz, font=T.font(13), text_color=T.WARN, anchor="w").grid(
                row=len(items) + j, column=0, columnspan=2, sticky="w", padx=8, pady=1)
        done = sum(1 for it in items if it.get("done"))
        n = len(items) or 1
        self.ck_prog.set(done / n)
        if items and done == len(items):
            self.ck_lbl.configure(text=f"🚀 {done}/{len(items)} – Bereit zum Abheben! Viel Spaß & sauber landen.",
                                  text_color=T.OK)
        else:
            self.ck_lbl.configure(text=f"{done}/{len(items)} erledigt · {random.choice(MOTIVATION)}", text_color=T.TEXT)

    def ck_toggle(self, i, val):
        self.cfg["checklist"][i]["done"] = bool(val)
        self._save(); self._render_checklist()

    def ck_del(self, i):
        self.cfg["checklist"].pop(i)
        self._save(); self._render_checklist()

    def ck_add(self):
        t = self.e_ck.get().strip()
        if t:
            self.cfg["checklist"].append({"text": t, "done": False})
            self.e_ck.delete(0, "end")
            self._save(); self._render_checklist()

    def ck_reset(self):
        for it in self.cfg["checklist"]:
            it["done"] = False
        self._save(); self._render_checklist()

    # ------------------------------------------------------------------ dipul, NOTAM, Grenzwerte
    def _build_side(self, body):
        side = ctk.CTkFrame(body, fg_color="transparent")
        side.grid(row=3, column=1, sticky="nsew", padx=0, pady=0)
        side.grid_columnconfigure(0, weight=1)

        d = _card(side)
        d.grid(row=0, column=0, sticky="ew", padx=6, pady=6)
        d.grid_columnconfigure(0, weight=1)
        _title(d, "🗺 dipul / EASA – Hinweis")
        ctk.CTkLabel(d, text=("Ob und wie du an diesem Spot fliegen darfst (Geozonen, Kontrollzonen, Naturschutz, "
                              "Wohngebiete …), zeigt verbindlich nur die offizielle Karte der DFS auf dipul. "
                              "Unten steht nur ein Hinweis aus den dipul-Geodaten – keine Prüfung, keine Rechtsberatung. Offene Kategorie: "
                              "max. 120 m, Sichtflug (bei FPV mit Spotter), EU-Kompetenznachweis & e-ID beachten."),
                     font=T.font(12), text_color=T.TEXT, anchor="w", justify="left", wraplength=470).grid(
            row=1, column=0, sticky="ew", padx=16)
        self.dz_lbl = ctk.CTkLabel(d, text="Geozonen-Hinweis: wird geladen …", font=T.font(12), text_color=T.MUTED,
                                   anchor="w", justify="left", wraplength=470)
        self.dz_lbl.grid(row=3, column=0, sticky="ew", padx=16, pady=(8, 0))
        self.dz_src = ctk.CTkLabel(d, text="", font=T.font(11), text_color=T.MUTED, anchor="w", justify="left",
                                   wraplength=470, cursor="hand2")
        self.dz_src.grid(row=4, column=0, sticky="ew", padx=16, pady=(2, 0))
        self.dz_src.bind("<Button-1>", lambda _e: webbrowser.open(dipul.LIZENZ_URL))
        row = ctk.CTkFrame(d, fg_color="transparent")
        row.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 0))
        _btn(row, "🔄 Geozonen prüfen", lambda: self.refresh_dipul(force=True), width=140).pack(side="right")
        ctk.CTkFrame(d, fg_color="transparent", height=10).grid(row=5, column=0)
        _btn(row, "🗺 dipul-Karte am Spot", self.open_dipul, "primary", width=170).pack(side="left", padx=(0, 6))
        _btn(row, "dipul.de", lambda: webbrowser.open(config.DIPUL_HOME), width=80).pack(side="left", padx=(0, 6))
        _btn(row, "OpenAIP", lambda: webbrowser.open(config.OPENAIP_MAP), width=80).pack(side="left")

        mc = _card(side)
        mc.grid(row=1, column=0, sticky="ew", padx=6, pady=6)
        mc.grid_columnconfigure(0, weight=1)
        mtop = ctk.CTkFrame(mc, fg_color="transparent")
        mtop.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        mtop.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(mtop, text="🛫 Flugplatz-Wetter (METAR/TAF)", font=T.font(15, "bold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="w")
        _btn(mtop, "🔄", lambda: self.refresh_metar(force=True), width=40).grid(row=0, column=1)
        self.m_head = ctk.CTkLabel(mc, text="lade …", font=T.font(14, "bold"), text_color=T.TEXT, anchor="w",
                                   justify="left", wraplength=470)
        self.m_head.grid(row=1, column=0, sticky="ew", padx=16)
        self.m_body = ctk.CTkLabel(mc, text="", font=T.font(12), text_color=T.TEXT, anchor="w", justify="left",
                                   wraplength=470)
        self.m_body.grid(row=2, column=0, sticky="ew", padx=16, pady=(2, 0))
        self.m_raw = ctk.CTkLabel(mc, text="", font=T.mono(11), text_color=T.MUTED,
                                  anchor="w", justify="left", wraplength=470)
        self.m_raw.grid(row=3, column=0, sticky="ew", padx=16, pady=(4, 0))
        ctk.CTkLabel(mc, text="⚠ " + metar.HINWEIS + " Quelle: aviationweather.gov", font=T.font(11),
                     text_color=T.MUTED, anchor="w", justify="left", wraplength=470).grid(
            row=4, column=0, sticky="ew", padx=16, pady=(6, 14))

        n = _card(side)
        n.grid(row=3, column=0, sticky="ew", padx=6, pady=6)
        n.grid_columnconfigure(0, weight=1)
        _title(n, "📄 NOTAM: folgt")
        ctk.CTkLabel(n, text=notam.HINT, font=T.font(12), text_color=T.MUTED, anchor="w", justify="left",
                     wraplength=470).grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 14))

        g = _card(side)
        g.grid(row=4, column=0, sticky="ew", padx=6, pady=6)
        _title(g, "⚙ Grenzwerte (Ampel)", span=4)
        self.th_entries = {}
        spec = [("wind_warn", "Wind gelb ab", "m/s"), ("wind_max", "Wind rot ab", "m/s"),
                ("gust_warn", "Böen gelb ab", "m/s"), ("gust_max", "Böen rot ab", "m/s"),
                ("precip_max", "Regen rot ab", "mm"), ("vis_min", "Sicht rot unter", "m"),
                ("temp_min", "Kalt (gelb) unter", "°C")]
        for i, (k, lbl, unit) in enumerate(spec):
            r, col = 1 + i // 2, (i % 2) * 2
            ctk.CTkLabel(g, text=f"{lbl} ({unit})", font=T.font(12), text_color=T.MUTED).grid(
                row=r, column=col, sticky="w", padx=(16, 4), pady=2)
            e = _entry(g, width=70)
            e.insert(0, f"{self.cfg['thresholds'][k]:g}")
            e.grid(row=r, column=col + 1, sticky="w", padx=(0, 8), pady=2)
            self.th_entries[k] = e
        _btn(g, "💾 Grenzwerte speichern", self.save_thresholds, "ok", width=180).grid(
            row=5, column=0, columnspan=4, sticky="w", padx=16, pady=(8, 14))

    def save_thresholds(self):
        try:
            for k, e in self.th_entries.items():
                self.cfg["thresholds"][k] = float(e.get().replace(",", "."))
        except ValueError:
            messagebox.showerror(config.APP_NAME, "Bitte nur Zahlen eintragen.")
            return
        self._save()
        if self.weather:
            self._update_weather(self.weather, None)

    # ------------------------------------------------------------------ Fuß
    def _build_footer(self):
        f = ctk.CTkFrame(self, fg_color="transparent")
        f.grid(row=2, column=0, sticky="ew", padx=22, pady=(0, 10))
        ctk.CTkLabel(f, text=f"Daten: Open-Meteo (CC BY 4.0) · OpenSky Network · aviationweather.gov · Web: {config.WEB_URL} · "
                             f"Einstellungen: {config.SETTINGS_FILE.name}", font=T.font(11),
                     text_color=T.MUTED).pack(side="left")

    # ------------------------------------------------------------------ Aktualisieren
    def refresh_all(self, force=False):
        sp = self._spot()
        if not sp:
            self._set_ampel(None, ["Bitte zuerst einen Standort setzen (links: Ort suchen → Spot speichern)."],
                            "Kein Standort")
            self.r_meta.configure(text="Bitte Standort setzen.", text_color=T.WARN)
            return
        lat, lon = sp["lat"], sp["lon"]
        self.w_meta.configure(text="lade Wetter …", text_color=T.MUTED)
        self._bg(lambda: weather.fetch(lat, lon, force=force), self._update_weather)
        self.refresh_radar(force=force)
        self.refresh_metar(force=force)

    def refresh_metar(self, force=False):
        sp = self._spot()
        if not sp:
            self.m_head.configure(text="Bitte Standort setzen.", text_color=T.WARN)
            return
        lat, lon = sp["lat"], sp["lon"]
        self.m_head.configure(text="frage aviationweather.gov …", text_color=T.MUTED)
        self._bg(lambda: metar.fetch(lat, lon, force=force), self._update_metar)

    def _update_metar(self, r, err):
        if err:
            self.m_head.configure(text=f"⚠ METAR: {err} – keine Daten angezeigt.", text_color=T.ERR)
            self.m_body.configure(text="")
            self.m_raw.configure(text="")
            return
        m, st, taf = r.get("metar"), r.get("station"), r.get("taf")
        lines = []
        if r.get("fehler"):
            lines.append("⚠ " + r["fehler"])
        if m and st:
            self.m_head.configure(text=f"{m['id']} {st['name']} · {st['dist_km']:g} km {st['peilung']} vom Spot",
                                  text_color=T.TEXT)
            alt = f"Meldung {m['zeit']} Uhr · vor {m['alter_min']} min" + (" – VERALTET" if m["veraltet"] else "")
            lines += [alt + (" · AUTO" if m.get("auto") else ""),
                      f"💨 Wind: {m['wind']}", f"👁 Sicht: {m['sicht']}", f"🌦 Wetter: {m['wetter']}",
                      f"☁ Wolken: {m['wolken']}",
                      f"🌡 {_fmt(m['temp'], 0)} °C / Taupunkt {_fmt(m['taupunkt'], 0)} °C · ⏲ QNH {_fmt(m['qnh'], 0)} hPa"]
            if m.get("kategorie_text"):
                lines.append(f"✈ {m['kategorie_text']}")
            raw = m["roh"]
        else:
            self.m_head.configure(text="Kein aktuelles METAR", text_color=T.WARN)
            raw = ""
        if taf:
            lines.append(f"\nTAF {taf['id']} · gültig {taf['gueltig']}")
            lines += [f"  {p['art']} {p['von']}–{p['bis']}: {p['text']}" for p in taf["perioden"][:5]]
            raw += ("\n" if raw else "") + taf["roh"]
        w = [x for x in r.get("weitere") or [] if x.get("hat_metar")][:3]
        if w:
            lines.append("\nWeitere: " + " · ".join(f"{x['id']} {x['dist_km']:g} km, QNH {_fmt(x['qnh'], 0)}" for x in w))
        lines.append(f"Abruf {r.get('abruf') or '–'}" + (" (Cache)" if r.get("aus_cache") else ""))
        self.m_body.configure(text="\n".join(lines), text_color=T.ERR if (r.get("fehler") and not m) else T.TEXT)
        self.m_raw.configure(text=raw)

    def refresh_radar(self, force=False):
        sp = self._spot()
        if not sp:
            return
        lat, lon, box = sp["lat"], sp["lon"], self.cfg.get("radar_box_deg", 0.5)
        self.r_meta.configure(text="frage OpenSky …", text_color=T.MUTED)
        self._bg(lambda: opensky.fetch(lat, lon, box, force=force), self._update_radar)


# ====================================================================== Logbuch (Phase 6 / 6.5)
def _logbook_methods():
    def _build_logbook(self, body):
        c = _card(body)
        c.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)
        c.grid_columnconfigure((0, 1), weight=1, uniform="lb")
        _title(c, "📒 Flugtag & Logbuch", span=2)
        # links: laufender Flugtag
        left = ctk.CTkFrame(c, fg_color="transparent")
        left.grid(row=1, column=0, sticky="nsew", padx=(16, 8), pady=(0, 14))
        left.grid_columnconfigure(0, weight=1)
        self.fd_status = ctk.CTkLabel(left, text="…", font=T.font(14, "bold"), text_color=T.TEXT, anchor="w",
                                      justify="left", wraplength=500)
        self.fd_status.grid(row=0, column=0, sticky="ew")
        row = ctk.CTkFrame(left, fg_color="transparent")
        row.grid(row=1, column=0, sticky="ew", pady=6)
        self.fd_start = _btn(row, "▶ Flugtag starten", self.fd_start_cb, "ok", width=140)
        self.fd_start.pack(side="left", padx=(0, 6))
        self.fd_end = _btn(row, "■ Flugtag beenden", self.fd_end_cb, "stop", width=140)
        self.fd_end.pack(side="left", padx=(0, 6))
        _btn(row, "📂 Ordner öffnen", self.fd_open_cb, width=130).pack(side="left")
        row_b = ctk.CTkFrame(left, fg_color="transparent")
        row_b.grid(row=5, column=0, sticky="ew", pady=(6, 0))
        self.fd_fl = _btn(row_b, "✈ Flüge & Wartung", lambda: self.open_flights(None), "primary", width=150)
        self.fd_fl.pack(side="left", padx=(0, 6))
        _btn(row_b, "📊 Statistik", self.open_stats, width=120).pack(side="left")
        nrow = ctk.CTkFrame(left, fg_color="transparent")
        nrow.grid(row=2, column=0, sticky="ew", pady=(2, 4))
        nrow.grid_columnconfigure(0, weight=1)
        self.e_note = _entry(nrow, ph="Notiz zu Bedingungen, z. B. „Böen hinter der Baumreihe“")
        self.e_note.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.e_note.bind("<Return>", lambda _e: self.fd_note_cb())
        self.tag_menu = ctk.CTkOptionMenu(nrow, values=["– Tag –", "böig", "thermisch", "nass", "Störungen", "voll",
                                                        "perfekt", "Crash"], width=110, height=32, font=T.font(12),
                                          fg_color=T.GREY, button_color=T.GREY, button_hover_color=T.GREY_HOVER)
        self.tag_menu.grid(row=0, column=1, padx=(0, 6))
        _btn(nrow, "➕ Notiz", self.fd_note_cb, width=80).grid(row=0, column=2)
        self.chart = tk.Canvas(left, height=130, bg=T.BG, highlightthickness=1, highlightbackground=T.BORDER)
        self.chart.grid(row=3, column=0, sticky="ew", pady=(6, 2))
        self.chart.bind("<Configure>", lambda _e: self._draw_chart())
        self.fd_notes = ctk.CTkLabel(left, text="", font=T.font(12), text_color=T.MUTED, anchor="w", justify="left",
                                     wraplength=500)
        self.fd_notes.grid(row=4, column=0, sticky="ew")
        self._chart_pts: list[dict] = []
        # rechts: Suche im Logbuch
        right = ctk.CTkFrame(c, fg_color="transparent")
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=(0, 14))
        right.grid_columnconfigure(0, weight=1)
        srow = ctk.CTkFrame(right, fg_color="transparent")
        srow.grid(row=0, column=0, sticky="ew")
        srow.grid_columnconfigure(0, weight=1)
        self.e_lsearch = _entry(srow, ph="Logbuch durchsuchen: Datum, Spot, Region, Notiz …")
        self.e_lsearch.grid(row=0, column=0, sticky="ew", padx=(0, 6))
        self.e_lsearch.bind("<Return>", lambda _e: self.refresh_logbook())
        _btn(srow, "🔎", self.refresh_logbook, width=40).grid(row=0, column=1, padx=(0, 6))
        _btn(srow, "↻ Index", self.fd_reindex_cb, width=80).grid(row=0, column=2)
        self.lb_list = ctk.CTkScrollableFrame(right, fg_color=T.BG, height=210, corner_radius=10,
                                              border_width=1, border_color=T.BORDER)
        self.lb_list.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        self.lb_list.grid_columnconfigure(0, weight=1)
        self.lb_path = ctk.CTkLabel(right, text="", font=T.font(11), text_color=T.MUTED, anchor="w")
        self.lb_path.grid(row=2, column=0, sticky="ew", pady=(4, 0))

    def refresh_logbook(self):
        q = self.e_lsearch.get().strip() if hasattr(self, "e_lsearch") else ""

        def work():
            cfg = settings.load()
            day = logbook.active(cfg)
            det = logbook.day_detail(day["ordner"], cfg) if day else None
            return {"day": day, "det": det, "rows": logbook.search(q, cfg), "base": str(logbook.logs_dir(cfg))}
        self._bg(work, self._update_logbook)

    def _update_logbook(self, r, err):
        if err or not r:
            self.fd_status.configure(text=f"⚠ Logbuch: {err}", text_color=T.ERR)
            return
        day, det = r["day"], r["det"]
        self.lb_path.configure(text=f"Logs-Ordner: {r['base']}")
        if day:
            st = day.get("snapshot_start")
            snap = (f"Start-Wetter: {st['ampel_titel']}, Wind {st['wind']}/{st['boeen']} m/s, {st['temp']} °C"
                    if st else "Start-Wetter: kein Snapshot")
            try:
                snap += f"\nLicht: {sun.light(day['spot']['lat'], day['spot']['lon'])['text']}"
            except Exception:  # noqa: BLE001
                pass
            self.fd_status.configure(text=f"🟢 Flugtag läuft: {day['spot']['name']} seit {logbook._hm(day['start'])}\n{snap}",
                                     text_color=T.OK)
            self.fd_start.configure(state="disabled"); self.fd_end.configure(state="normal")
            self.fd_fl.configure(state="normal")
            self._chart_pts = det["verlauf"]
            notes = det["notizen"][-4:]
            self.fd_notes.configure(text=(f"Messpunkte: {len(det['verlauf'])} · Medien: {len(det['medien'])} · "
                                          f"Notizen: {len(det['notizen'])}\n")
                                    + "\n".join(f"{logbook._hm(n['zeit'])}  {n['text']}"
                                                + (f"  [{', '.join(n['tags'])}]" if n.get("tags") else "") for n in notes))
        else:
            self.fd_status.configure(text="⚪ Kein Flugtag aktiv – „▶ Flugtag starten“ legt Ordner, Wetter-Snapshot "
                                          "und Verlauf an.", text_color=T.MUTED)
            self.fd_start.configure(state="normal"); self.fd_end.configure(state="disabled")
            self.fd_fl.configure(state="disabled")
            self._chart_pts = []
            self.fd_notes.configure(text="")
        self._draw_chart()
        for ch in self.lb_list.winfo_children():
            ch.destroy()
        rows = r["rows"]
        if not rows:
            ctk.CTkLabel(self.lb_list, text="Noch keine Flugtage gefunden." if not self.e_lsearch.get().strip()
                         else "Keine Treffer.", font=T.font(12), text_color=T.MUTED).grid(row=0, column=0, sticky="w",
                                                                                         padx=8, pady=8)
        dots = {"gruen": "🟢", "gelb": "🟡", "rot": "🔴"}
        for i, x in enumerate(rows[:80]):
            txt = (f"{x['datum']}  {dots.get(x.get('ampel'), '⚪')}  {x['spot']}"
                   + (f" · {x['region'].split(',')[0]}" if x.get("region") else "")
                   + (f"   ·  ✈ {x['fluege']} · {logbook.fmt_dur(x.get('flugzeit_s'))}"
                      + (f" · 💥{x['crashes']}" if x.get("crashes") else "") if x.get("fluege") else "")
                   + f"   ·  {x['notizen']} Notiz(en) · {x['medien']} Medien"
                   + (" · läuft" if x.get("status") == "offen" else ""))
            ctk.CTkLabel(self.lb_list, text=txt, font=T.font(12), text_color=T.TEXT, anchor="w").grid(
                row=i, column=0, sticky="ew", padx=8, pady=1)
            _btn(self.lb_list, "✈", lambda o=x["ordner"]: self.open_flights(o), width=32, height=24).grid(
                row=i, column=3, padx=(2, 6))
            _btn(self.lb_list, "📂", lambda o=x["ordner"]: self._open_day(o), width=32, height=24).grid(
                row=i, column=1, padx=2)
            _btn(self.lb_list, "📄", lambda o=x["ordner"]: self._open_md(o), width=32, height=24).grid(
                row=i, column=2, padx=2)

    def _draw_chart(self):
        cv = self.chart
        cv.delete("all")
        w, h = max(cv.winfo_width(), 200), max(cv.winfo_height(), 100)
        pts = [p for p in self._chart_pts if isinstance(p.get("boeen"), (int, float))]
        th = self.cfg["thresholds"]
        if len(pts) < 1:
            cv.create_text(w / 2, h / 2, text="Wind-/Böenverlauf erscheint hier, sobald ein Flugtag läuft "
                                              f"(Messpunkt alle {self.cfg.get('verlauf_minuten', 15)} min).",
                           fill=T.MUTED, font=("Helvetica", 11))
            return
        top = max(th["gust_max"] + 2, max(p["boeen"] for p in pts) + 1)
        L, R, Tp, B = 34, 10, 10, 20

        def y(v):
            return Tp + (h - Tp - B) * (1 - v / top)

        def x(i):
            return L + (w - L - R) * (i / max(len(pts) - 1, 1))
        for v, col in ((th["gust_warn"], T.WARN), (th["gust_max"], T.ERR)):
            cv.create_line(L, y(v), w - R, y(v), fill=col, dash=(4, 3))
            cv.create_text(L - 4, y(v), text=f"{v:g}", fill=col, anchor="e", font=("Helvetica", 9))
        cv.create_text(L - 4, y(0), text="0", fill=T.MUTED, anchor="e", font=("Helvetica", 9))
        for key, col in (("wind", T.ACCENT), ("boeen", "#f0883e")):
            xy = []
            for i, p in enumerate(pts):
                if isinstance(p.get(key), (int, float)):
                    xy += [x(i), y(p[key])]
            if len(xy) >= 4:
                cv.create_line(*xy, fill=col, width=2, smooth=True)
            for j in range(0, len(xy), 2):
                cv.create_oval(xy[j] - 2.5, xy[j + 1] - 2.5, xy[j] + 2.5, xy[j + 1] + 2.5, fill=col, outline="")
        cv.create_text(L, h - 8, text=logbook._hm(pts[0].get("zeit")), fill=T.MUTED, anchor="w", font=("Helvetica", 9))
        cv.create_text(w - R, h - 8, text=logbook._hm(pts[-1].get("zeit")), fill=T.MUTED, anchor="e", font=("Helvetica", 9))
        cv.create_text(w / 2, h - 8, text="— Wind   — Böen (m/s)", fill=T.MUTED, font=("Helvetica", 9))

    def fd_start_cb(self):
        self.fd_status.configure(text="Starte Flugtag, hole Wetter-Snapshot …", text_color=T.MUTED)
        self._save()

        def done(res, err):
            if err:
                messagebox.showwarning(config.APP_NAME, err)
            self.refresh_logbook()
        self._bg(lambda: logbook.start_day(), done)

    def fd_end_cb(self):
        if not messagebox.askyesno(config.APP_NAME, "Flugtag beenden und Zusammenfassung erstellen?"):
            return

        def done(res, err):
            if err:
                messagebox.showwarning(config.APP_NAME, err)
            else:
                self._open_md(res["ordner"], "zusammenfassung.md")
            self.refresh_logbook()
        self._bg(lambda: logbook.end_day(), done)

    def fd_note_cb(self):
        t = self.e_note.get().strip()
        if not t:
            return
        tag = self.tag_menu.get()
        tags = [] if tag.startswith("–") else [tag]

        def done(res, err):
            if err:
                messagebox.showwarning(config.APP_NAME, err)
            else:
                self.e_note.delete(0, "end"); self.tag_menu.set("– Tag –")
            self.refresh_logbook()
        self._bg(lambda: logbook.add_note(t, tags), done)

    def fd_open_cb(self):
        day = logbook.active()
        self._open_day(day["ordner"] if day else None)

    def fd_reindex_cb(self):
        self._bg(lambda: logbook.rebuild_index(), lambda r, e: self.refresh_logbook())

    def _open_day(self, name):
        try:
            logbook.open_day(name)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(config.APP_NAME, f"Ordner konnte nicht geöffnet werden:\n{e}")

    def _open_md(self, name, fname=None):
        d = logbook.logs_dir() / name
        f = d / (fname or ("zusammenfassung.md" if (d / "zusammenfassung.md").exists() else "flugtag.md"))
        try:
            _open_file(f)
        except Exception as e:  # noqa: BLE001
            messagebox.showerror(config.APP_NAME, f"Datei konnte nicht geöffnet werden:\n{e}")

    def _log_tick(self):
        def done(res, err):
            if res:
                self.refresh_logbook()
        self._bg(lambda: logbook.tick(), done)

        try:
            self.refresh_light()
            if logbook.active(self.cfg):
                self.refresh_logbook()
        except Exception:  # noqa: BLE001
            log.exception("Licht")
        self.after(60_000, self._log_tick)

    def open_flights(self, ordner):
        try:
            FlightsWindow(self, self.cfg, self._bg, ordner, on_change=self.refresh_logbook)
        except ValueError as e:
            messagebox.showinfo(config.APP_NAME, str(e))

    def open_stats(self):
        StatsWindow(self, self.cfg, self._bg)

    def print_checklist(self):
        a = weather.assess(self.weather, self.cfg["thresholds"]) if self.weather else None
        self._save()
        f = config.DATA_DIR / "checkliste-druck.html"
        f.write_text(export.checklist_html(self.cfg, a), encoding="utf-8")
        webbrowser.open(f.resolve().as_uri())

    # alle oben definierten Funktionen als Methoden an MainWindow hängen
    for k, v in list(locals().items()):
        if callable(v):
            setattr(MainWindow, k, v)


def _open_file(f):
    import os
    import subprocess
    import sys
    if sys.platform.startswith("win"):
        os.startfile(str(f))  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", "-t", str(f)] if f.suffix == ".md" else ["open", str(f)])  # .md im Texteditor
    else:
        subprocess.Popen(["xdg-open", str(f)])


_logbook_methods()
