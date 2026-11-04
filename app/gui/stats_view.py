"""Desktop-Fenster für Phase 8: Flüge & Wartung eintragen, Flugstatistik (Canvas-Diagramme, ohne Zusatzpakete)."""
from __future__ import annotations

import logging
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app import batteries, config, logbook, stats
from app.gui import theme as T
from app.gui.spots_view import _btn, _entry, _lbl, _menu

log = logging.getLogger("gui.stats")
KA = stats.KA
ERG = {"Ergebnis?": "", "✅ ok": "ok", "💥 Crash": "crash"}
QUELLEN = ["Zeitquelle?", *logbook.ZEIT_QUELLEN]
AMPEL_COL = {"gruen": T.OK, "gelb": T.WARN, "rot": T.ERR}
AMPEL_TXT = {"gruen": "🟢 grün", "gelb": "🟡 gelb", "rot": "🔴 rot"}
fd = logbook.fmt_dur


def _d(s):
    return fd(s) if s else KA


def _eur(v):
    return f"{v:.2f} €".replace(".", ",") if isinstance(v, (int, float)) else KA


def _table(parent, head, rows, row0=0):
    f = ctk.CTkFrame(parent, fg_color=T.BG, corner_radius=8, border_width=1, border_color=T.BORDER)
    if not rows:
        _lbl(f, KA).grid(row=0, column=0, sticky="w", padx=8, pady=4)
        return f
    for j, h in enumerate(head):
        ctk.CTkLabel(f, text=h, font=T.font(11, "bold"), text_color=T.MUTED, anchor="w").grid(
            row=0, column=j, sticky="w", padx=6, pady=(4, 2))
    for i, r in enumerate(rows, 1):
        for j, c in enumerate(r):
            if isinstance(c, tuple):            # (text, color) oder (text, callback-button)
                if callable(c[1]):
                    _btn(f, c[0], c[1], width=30, height=22).grid(row=i, column=j, sticky="w", padx=4, pady=1)
                    continue
                txt, col = c
            else:
                txt, col = c, T.TEXT
            ctk.CTkLabel(f, text=str(txt), font=T.font(12), text_color=col, anchor="w", justify="left",
                         wraplength=300).grid(row=i, column=j, sticky="w", padx=6, pady=1)
    return f


def _bars(parent, items, h=150, fmt=str, colors=None):
    """items = [(label, value)] → einfaches Balkendiagramm auf tk.Canvas."""
    cv = tk.Canvas(parent, height=h, bg=T.BG, highlightthickness=1, highlightbackground=T.BORDER)

    def draw(_e=None):
        cv.delete("all")
        w = max(cv.winfo_width(), 240)
        if not items:
            cv.create_text(w / 2, h / 2, text=KA, fill=T.MUTED, font=("Helvetica", 11))
            return
        mx = max([v for _, v in items] + [1])
        slot = (w - 16) / len(items)
        bw = min(38, slot - 8)
        for i, (lab, v) in enumerate(items):
            x = 8 + i * slot + (slot - bw) / 2
            bh = (h - 46) * v / mx
            col = (colors[i] if colors else T.ACCENT)
            cv.create_rectangle(x, h - 26 - bh, x + bw, h - 26, fill=col, outline="")
            cv.create_text(x + bw / 2, h - 32 - bh, text=fmt(v), fill=T.TEXT, font=("Helvetica", 10))
            cv.create_text(x + bw / 2, h - 12, text=lab, fill=T.MUTED, font=("Helvetica", 9))
    cv.bind("<Configure>", draw)
    return cv


def _line(parent, pts, h=150):
    cv = tk.Canvas(parent, height=h, bg=T.BG, highlightthickness=1, highlightbackground=T.BORDER)

    def draw(_e=None):
        cv.delete("all")
        w = max(cv.winfo_width(), 240)
        if len(pts) < 2:
            cv.create_text(w / 2, h / 2, text="Erst 1 Flug mit Dauer – Verlauf ab 2 Flügen." if pts else KA,
                           fill=T.MUTED, font=("Helvetica", 11))
            return
        L, R, Tp, B = 44, 10, 10, 22
        mx = max(p["dauer_s"] for p in pts) * 1.1

        def x(i):
            return L + (w - L - R) * i / (len(pts) - 1)

        def y(v):
            return Tp + (h - Tp - B) * (1 - v / mx)
        for v in (mx / 2, mx / 1.1):
            cv.create_line(L, y(v), w - R, y(v), fill=T.BORDER)
            cv.create_text(L - 4, y(v), text=fd(v).replace(" min", ""), fill=T.MUTED, anchor="e", font=("Helvetica", 9))
        for i, p in enumerate(pts):
            cv.create_oval(x(i) - 2.5, y(p["dauer_s"]) - 2.5, x(i) + 2.5, y(p["dauer_s"]) + 2.5, fill=T.MUTED, outline="")
        cv.create_line(*[c for i, p in enumerate(pts) for c in (x(i), y(p["gleitend_s"]))], fill=T.ACCENT, width=2.5)
        cv.create_text(L, h - 8, text=pts[0]["datum"], fill=T.MUTED, anchor="w", font=("Helvetica", 9))
        cv.create_text(w - R, h - 8, text=pts[-1]["datum"], fill=T.MUTED, anchor="e", font=("Helvetica", 9))
        cv.create_text(w / 2, h - 8, text="● Einzelflug   — gleitender Ø (5 Flüge)", fill=T.MUTED, font=("Helvetica", 9))
    cv.bind("<Configure>", draw)
    return cv


class FlightsWindow(ctk.CTkToplevel):
    """Flüge (Packs) und Wartung für den aktiven oder einen beliebigen Flugtag eintragen."""

    def __init__(self, master, cfg: dict, bg, ordner: str | None, on_change=None):
        if not ordner:
            day = logbook.active(cfg)
            if not day:
                raise ValueError("Kein Flugtag aktiv – im Logbuch bei einem Tag auf ✈ klicken.")
            ordner = day["ordner"]
        logbook.day_detail(ordner, cfg)   # wirft ValueError bei ungültigem Ordner
        super().__init__(master)
        self.cfg, self.bg, self.on_change = cfg, bg, on_change
        self.ordner = ordner
        self.title("Flüge & Wartung")
        self.geometry("940x640")
        self.configure(fg_color=T.BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        self.head = ctk.CTkLabel(self, text="✈ …", font=T.font(19, "bold"), text_color=T.TEXT, anchor="w")
        self.head.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 2))
        body = ctk.CTkScrollableFrame(self, fg_color=T.CARD, corner_radius=12)
        body.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 12))
        body.grid_columnconfigure(0, weight=1)
        _lbl(body, "Ein Eintrag pro Akku-Pack. Leere Felder = „keine Angabe“ (wird nicht geschätzt). "
                   "Dauer als mm:ss oder Minuten.").grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 2))
        r1 = ctk.CTkFrame(body, fg_color="transparent")
        r1.grid(row=1, column=0, sticky="ew", padx=8)
        self.e_start = _entry(r1, 90, "Start HH:MM")
        self.e_dauer = _entry(r1, 110, "Dauer 3:45")
        self.m_quelle = _menu(r1, QUELLEN, 120)
        self.akkus = self._akku_ids()
        self.e_akku = ctk.CTkComboBox(r1, values=self.akkus or [""], width=120, height=30, font=T.font(12),
                                      fg_color=T.BG, border_color=T.BORDER, button_color=T.GREY)
        self.e_akku.set("")
        self.e_drohne = ctk.CTkComboBox(r1, values=self._drohnen() or [""], width=160, height=30, font=T.font(12),
                                        fg_color=T.BG, border_color=T.BORDER, button_color=T.GREY)
        self.e_drohne.set("")
        self.m_erg = _menu(r1, list(ERG), 110)
        for w_ in (self.e_start, self.e_dauer, self.m_quelle, _lbl(r1, "Akku"), self.e_akku, _lbl(r1, "Drohne"),
                   self.e_drohne, self.m_erg):
            w_.pack(side="left", padx=3, pady=4)
        r2 = ctk.CTkFrame(body, fg_color="transparent")
        r2.grid(row=2, column=0, sticky="ew", padx=8)
        r2.grid_columnconfigure(0, weight=1)
        self.e_fnotiz = _entry(r2, 400, "Notiz zum Flug (optional)")
        self.e_fnotiz.grid(row=0, column=0, sticky="ew", padx=3)
        self.e_fnotiz.bind("<Return>", lambda _e: self.add_flight())
        _btn(r2, "➕ Flug eintragen", self.add_flight, "ok", width=140).grid(row=0, column=1, padx=3)
        self.fl_box = ctk.CTkFrame(body, fg_color="transparent")
        self.fl_box.grid(row=3, column=0, sticky="ew", padx=8, pady=6)
        self.fl_box.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(body, text="🔧 Wartung / Reparatur", font=T.font(14, "bold"), text_color=T.TEXT, anchor="w").grid(
            row=4, column=0, sticky="ew", padx=10, pady=(10, 0))
        r3 = ctk.CTkFrame(body, fg_color="transparent")
        r3.grid(row=5, column=0, sticky="ew", padx=8)
        self.e_teil = ctk.CTkComboBox(r3, values=["Props", "Arm", "Motor", "Kamera", "Antenne", "VTX", "FC/ESC",
                                                  "Rahmen", "Akku-Stecker", "GoPro-Halter"], width=180, height=30,
                                      font=T.font(12), fg_color=T.BG, border_color=T.BORDER, button_color=T.GREY)
        self.e_teil.set("")
        self.e_anz = _entry(r3, 55, "Anz.")
        self.e_wdrohne = _entry(r3, 150, "Drohne")
        self.e_kosten = _entry(r3, 110, "Kosten € (opt.)")
        self.e_wnotiz = _entry(r3, 220, "Notiz (optional)")
        for w_ in (_lbl(r3, "Teil"), self.e_teil, self.e_anz, self.e_wdrohne, self.e_kosten, self.e_wnotiz):
            w_.pack(side="left", padx=3, pady=4)
        _btn(r3, "➕ Wartung", self.add_maint, "ok", width=110).pack(side="left", padx=3)
        self.wa_box = ctk.CTkFrame(body, fg_color="transparent")
        self.wa_box.grid(row=6, column=0, sticky="ew", padx=8, pady=6)
        self.msg = _lbl(body, "")
        self.msg.grid(row=7, column=0, sticky="ew", padx=10, pady=(0, 8))
        self.load()
        self.after(150, self.lift)

    def _akku_ids(self):
        try:
            return [a["id"] for a in batteries.load() if not a.get("ausgemustert")]
        except ValueError:
            return []

    def _drohnen(self):
        try:
            return stats.compute(self.cfg)["drohnen_liste"]
        except Exception:  # noqa: BLE001
            return []

    def load(self):
        try:
            det = logbook.day_detail(self.ordner, self.cfg)
        except ValueError as e:
            self.msg.configure(text=f"⚠ {e}", text_color=T.ERR)
            return
        d = det["flugtag"]
        self.head.configure(text=f"✈ {d['datum']} · {d['spot']['name']}"
                                 + ("  (läuft)" if d.get("status") == "offen" else "  (nachträglich)"))
        for box in (self.fl_box, self.wa_box):
            for ch in box.winfo_children():
                ch.destroy()
        E = {"ok": ("✅ ok", T.OK), "crash": ("💥 Crash", T.ERR)}
        fl = det["fluege"]
        rows = [[i, x.get("start") or "–", _d(x.get("dauer_s")) + (f" ({x['quelle']})" if x.get("quelle") else ""),
                 x.get("akku") or KA, x.get("drohne") or KA, E.get(x.get("ergebnis"), (KA, T.MUTED)),
                 (x.get("notiz") or "", T.MUTED), ("↩", lambda e=x["id"]: self.storno("flug", e))]
                for i, x in enumerate(fl, 1)]
        _table(self.fl_box, ["#", "Start", "Dauer", "Akku", "Drohne", "Ergebnis", "Notiz", ""], rows).grid(
            row=0, column=0, sticky="ew")
        if fl:
            _lbl(self.fl_box, f"{len(fl)} Flug/Flüge · Summe {_d(sum(x.get('dauer_s') or 0 for x in fl))}").grid(
                row=1, column=0, sticky="w")
        rows = [[w.get("datum") or "", w["teil"], w.get("anzahl") or 1, w.get("drohne") or KA, _eur(w.get("kosten")),
                 (w.get("notiz") or "", T.MUTED), ("↩", lambda e=w["id"]: self.storno("wartung", e))]
                for w in det["wartung"]]
        _table(self.wa_box, ["Datum", "Teil", "Anz.", "Drohne", "Kosten", "Notiz", ""], rows).grid(
            row=0, column=0, sticky="ew")
        self.msg.configure(text=f"Ordner: {det['pfad']}", text_color=T.MUTED)

    def _changed(self):
        self.load()
        if self.on_change:
            self.on_change()

    def add_flight(self):
        data = {"start": self.e_start.get(), "dauer": self.e_dauer.get(),
                "quelle": "" if self.m_quelle.get() == QUELLEN[0] else self.m_quelle.get(),
                "akku": self.e_akku.get(), "drohne": self.e_drohne.get(), "ergebnis": ERG[self.m_erg.get()],
                "notiz": self.e_fnotiz.get()}
        try:
            logbook.add_flight(data, self.ordner, self.cfg)
        except ValueError as e:
            messagebox.showerror("Flug eintragen", str(e), parent=self)
            return
        for e in (self.e_start, self.e_dauer, self.e_fnotiz):
            e.delete(0, "end")
        self.m_erg.set(list(ERG)[0])
        self._changed()

    def add_maint(self):
        data = {"teil": self.e_teil.get(), "anzahl": self.e_anz.get(), "drohne": self.e_wdrohne.get(),
                "kosten": self.e_kosten.get(), "notiz": self.e_wnotiz.get()}
        try:
            logbook.add_maintenance(data, self.ordner, self.cfg)
        except ValueError as e:
            messagebox.showerror("Wartung eintragen", str(e), parent=self)
            return
        self.e_teil.set("")
        for e in (self.e_anz, self.e_kosten, self.e_wnotiz):
            e.delete(0, "end")
        self._changed()

    def storno(self, kind, eid):
        if not messagebox.askyesno("Stornieren", "Eintrag stornieren?\n(Er bleibt als Storno in der Datei "
                                                 "nachvollziehbar, es wird nichts gelöscht.)", parent=self):
            return
        try:
            logbook.storno(kind, eid, self.ordner, self.cfg)
        except ValueError as e:
            messagebox.showerror("Stornieren", str(e), parent=self)
            return
        self._changed()


class StatsWindow(ctk.CTkToplevel):
    """📊 Flugstatistik – bei jedem Öffnen/Berechnen aus den echten Logbuch-Dateien neu berechnet."""

    def __init__(self, master, cfg: dict, bg):
        super().__init__(master)
        self.cfg, self.bg, self.s = cfg, bg, None
        self.title("Flugstatistik")
        self.geometry("1040x780")
        self.configure(fg_color=T.BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        ctk.CTkLabel(top, text="📊 Flugstatistik", font=T.font(20, "bold"), text_color=T.TEXT).pack(side="left")
        _btn(top, "🖨 Drucken", self.print_page, width=100).pack(side="right", padx=3)
        _btn(top, "⬇ CSV", self.save_csv, width=80).pack(side="right", padx=3)
        _btn(top, "📊 Berechnen", self.load, "primary", width=120).pack(side="right", padx=3)
        flt = ctk.CTkFrame(self, fg_color="transparent")
        flt.grid(row=1, column=0, sticky="ew", padx=16)
        self.e_von = _entry(flt, 110, "von JJJJ-MM-TT")
        self.e_bis = _entry(flt, 110, "bis JJJJ-MM-TT")
        self.m_spot = _menu(flt, ["alle Spots"], 160)
        self.m_drohne = _menu(flt, ["alle Drohnen"], 160)
        for w_ in (_lbl(flt, "Filter:"), self.e_von, self.e_bis, self.m_spot, self.m_drohne):
            w_.pack(side="left", padx=3)
        self.body = ctk.CTkScrollableFrame(self, fg_color=T.CARD, corner_radius=12)
        self.body.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 12))
        self.body.grid_columnconfigure((0, 1), weight=1, uniform="st")
        self.load()
        self.after(150, self.lift)

    def _flt(self):
        sp, dr = self.m_spot.get(), self.m_drohne.get()
        return {"von": self.e_von.get().strip(), "bis": self.e_bis.get().strip(),
                "spot": "" if sp == "alle Spots" else sp, "drohne": "" if dr == "alle Drohnen" else dr}

    def load(self):
        for ch in self.body.winfo_children():
            ch.destroy()
        _lbl(self.body, "Berechne aus den Logbuch-Dateien …").grid(row=0, column=0, sticky="w", padx=10, pady=10)
        flt = self._flt()
        self.bg(lambda: stats.compute(self.cfg, **flt), self.show)

    def show(self, s, err):
        if not self.winfo_exists():
            return
        for ch in self.body.winfo_children():
            ch.destroy()
        if err:
            ctk.CTkLabel(self.body, text=f"⚠ {err}", font=T.font(12), text_color=T.ERR).grid(row=0, column=0, sticky="w", padx=10, pady=10)
            return
        self.s = s
        self.m_spot.configure(values=["alle Spots", *s["spot_liste"]])
        self.m_drohne.configure(values=["alle Drohnen", *s["drohnen_liste"]])
        u, w, b = s["summen"], s["wetter"], self.body
        row = 0
        tiles = ctk.CTkFrame(b, fg_color="transparent")
        tiles.grid(row=row, column=0, columnspan=2, sticky="ew", padx=6, pady=(8, 2))
        kp = [("Flugtage", u["flugtage"], f"{u['flugtage_ohne_fluege']} ohne Flug-Einträge" if u["flugtage_ohne_fluege"] else ""),
              ("Flüge", u["fluege"], f"{u['fluege_ohne_dauer']} ohne Dauer" if u["fluege_ohne_dauer"] else ""),
              ("Flugzeit", _d(u["flugzeit_s"]), "nur erfasste Dauern"), ("Ø pro Flug", _d(u["avg_s"]), ""),
              ("Crashes", u["crashes"], f"{u['ohne_ergebnis']} ohne Ergebnis" if u["ohne_ergebnis"] else ""),
              ("Reparaturen", u["reparaturen"], _eur(u["kosten"]) if u["kosten"] is not None else "Kosten: " + KA)]
        for j, (lab, val, sub) in enumerate(kp):
            tiles.grid_columnconfigure(j, weight=1, uniform="k")
            t = ctk.CTkFrame(tiles, fg_color=T.BG, corner_radius=10, border_width=1, border_color=T.BORDER)
            t.grid(row=0, column=j, sticky="nsew", padx=3)
            for txt, fnt, col in ((lab, T.font(11), T.MUTED), (str(val), T.font(20, "bold"), T.TEXT), (sub or " ", T.font(10), T.MUTED)):
                ctk.CTkLabel(t, text=txt, font=fnt, text_color=col).pack(pady=1)
        row += 1
        rk = s["rekorde"]
        info = (f"{s['hinweis']}  ·  Wochen-Serie: beste {s['serie']['beste']}, aktuell {s['serie']['aktuell']}"
                + (f"  ·  Längster Flug {fd(rk['laengster_flug']['dauer_s'])} ({rk['laengster_flug']['datum']}, "
                   f"{rk['laengster_flug']['spot']})" if rk["laengster_flug"] else "")
                + (f"  ·  Meiste Packs: {rk['meiste_packs']['anzahl']} am {rk['meiste_packs']['datum']}" if rk["meiste_packs"] else ""))
        _lbl(b, info, wraplength=980, justify="left").grid(row=row, column=0, columnspan=2, sticky="ew", padx=10, pady=4)
        row += 1

        def sect(txt, r, c, span=1):
            ctk.CTkLabel(b, text=txt, font=T.font(13, "bold"), text_color=T.TEXT, anchor="w").grid(
                row=r, column=c, columnspan=span, sticky="ew", padx=10, pady=(10, 2))
        sect("Flugtage pro Monat", row, 0)
        sect("Flugzeit pro Monat (min)", row, 1)
        row += 1
        _bars(b, [(m["label"], m["flugtage"]) for m in s["monate"]]).grid(row=row, column=0, sticky="ew", padx=8)
        _bars(b, [(m["label"], round(m["flugzeit_s"] / 60)) for m in s["monate"]],
              colors=["#a371f7"] * len(s["monate"])).grid(row=row, column=1, sticky="ew", padx=8)
        row += 1
        sect("Wetter-Ampel der Flugtage (Tagesstart)", row, 0)
        sect("Entwicklung Flugzeit pro Flug", row, 1)
        row += 1
        left = ctk.CTkFrame(b, fg_color="transparent")
        left.grid(row=row, column=0, sticky="nsew", padx=8)
        left.grid_columnconfigure(0, weight=1)
        amp = w["ampel"]
        n = sum(amp.values()) or 1
        cv = tk.Canvas(left, height=24, bg=T.BG, highlightthickness=0)
        cv.grid(row=0, column=0, sticky="ew", pady=4)

        def draw_amp(_e=None, cv=cv):
            cv.delete("all")
            ww, x = max(cv.winfo_width(), 200), 0
            for k, v in amp.items():
                if v:
                    cv.create_rectangle(x, 0, x + ww * v / n, 24, fill=AMPEL_COL.get(k, "#484f58"), outline="")
                    x += ww * v / n
        cv.bind("<Configure>", draw_amp)
        _lbl(left, " · ".join(f"{AMPEL_TXT.get(k, '⚪ ' + k)}: {v} ({100 * v / n:.0f} %)" for k, v in amp.items()),
             wraplength=480, justify="left").grid(row=1, column=0, sticky="ew")
        _lbl(left, "Wind beim Start (m/s) → Anzahl Flugtage").grid(row=2, column=0, sticky="ew", pady=(6, 0))
        hist = list(w["wind_hist"].items())
        _bars(left, hist, h=130, colors=["#484f58" if k == KA else "#f0883e" for k, _ in hist]).grid(
            row=3, column=0, sticky="ew")
        _lbl(left, f"Verlauf: Ø Wind {w['wind_avg'] if w['wind_avg'] is not None else KA} m/s · max Böe "
                   f"{w['boeen_max'] if w['boeen_max'] is not None else KA} m/s · Temperatur "
                   f"{w['temp_min'] if w['temp_min'] is not None else KA} … {w['temp_max'] if w['temp_max'] is not None else KA} °C "
                   f"({w['messpunkte']} Messpunkte, Open-Meteo)", wraplength=480, justify="left").grid(
            row=4, column=0, sticky="ew")
        right = ctk.CTkFrame(b, fg_color="transparent")
        right.grid(row=row, column=1, sticky="nsew", padx=8)
        right.grid_columnconfigure(0, weight=1)
        _line(right, s["entwicklung"]).grid(row=0, column=0, sticky="ew", pady=4)
        _lbl(right, "Ø-Flugzeit je Monat").grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ma = [m for m in s["monat_avg"] if m["avg_s"]]
        _bars(right, [(m["label"], m["avg_s"]) for m in ma], h=130, fmt=lambda v: fd(v).replace(" min", ""),
              colors=[T.OK] * len(ma)).grid(row=2, column=0, sticky="ew")
        row += 1
        sect("🏆 Häufigste Spots", row, 0, 2)
        row += 1
        _table(b, ["Spot", "Flugtage", "Flüge", "Flugzeit", "Crashes", "zuletzt"],
               [[x["spot"], x["flugtage"], x["fluege"], _d(x["flugzeit_s"]), x["crashes"], x["zuletzt"]]
                for x in s["spots"]]).grid(row=row, column=0, columnspan=2, sticky="ew", padx=8)
        row += 1
        sect("🛸 Drohnen", row, 0, 2)
        row += 1
        _table(b, ["Drohne", "Flüge", "Flugzeit", "ohne Dauer", "Crashes", "Flüge seit Crash", "Reparaturen", "zuletzt"],
               [[x["drohne"], x["fluege"], _d(x["flugzeit_s"]), x["ohne_dauer"], x["crashes"],
                 "–" if x["seit_crash"] is None else x["seit_crash"], x["reparaturen"], x["zuletzt"] or "–"]
                for x in s["drohnen"]]).grid(row=row, column=0, columnspan=2, sticky="ew", padx=8)
        row += 1
        sect("🔋 Akkus (Register + aus Flügen)", row, 0, 2)
        row += 1
        if s["akku_fehler"]:
            ctk.CTkLabel(b, text=f"⚠ {s['akku_fehler']}", font=T.font(12), text_color=T.ERR).grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
            row += 1
        _table(b, ["Akku", "Zyklen (Flüge)", "Flugzeit", "Ø Flug", "zuletzt", "Hinweis"],
               [[x["label"] + (" (ausgemustert)" if x["ausgemustert"] else "") + ("" if x["im_register"] else " – nicht im Register"),
                 x["zyklen"], _d(x["flugzeit_s"]), _d(x["avg_s"]), x["zuletzt"] or "–",
                 (x["hinweis"] or "", T.WARN if (x["hinweis"] or "").startswith("Flugzeit") else T.MUTED)]
                for x in s["akkus"]]).grid(row=row, column=0, columnspan=2, sticky="ew", padx=8)
        row += 1
        if u["ohne_akku"]:
            _lbl(b, f"{u['ohne_akku']} Flug/Flüge ohne Akku-Angabe.").grid(row=row, column=0, columnspan=2, sticky="w", padx=10)
            row += 1
        ak = ctk.CTkFrame(b, fg_color="transparent")
        ak.grid(row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=4)
        self.a_id, self.a_z, self.a_mah = _entry(ak, 100, "Akku-ID"), _entry(ak, 70, "Zellen S"), _entry(ak, 80, "mAh")
        self.a_name, self.a_kauf = _entry(ak, 160, "Marke/Name"), _entry(ak, 120, "Kauf JJJJ-MM-TT")
        self.a_aus = ctk.CTkCheckBox(ak, text="ausgemustert", font=T.font(12), text_color=T.MUTED)
        for w_ in (self.a_id, self.a_z, self.a_mah, self.a_name, self.a_kauf, self.a_aus):
            w_.pack(side="left", padx=3)
        _btn(ak, "💾 Akku ins Register", self.save_akku, "ok", width=150).pack(side="left", padx=3)
        row += 1
        sect("🔧 Crashes & Reparaturen", row, 0, 2)
        row += 1
        _lbl(b, "Teile-Verbrauch: " + (" · ".join(f"{k} ×{v}" for k, v in s["teile"].items()) or KA)).grid(
            row=row, column=0, columnspan=2, sticky="w", padx=10)
        row += 1
        _table(b, ["Datum", "Teil", "Anz.", "Drohne", "Kosten", "Spot", "Notiz"],
               [[x["_datum"], x["teil"], x.get("anzahl") or 1, x.get("drohne") or KA, _eur(x.get("kosten")), x["_spot"],
                 (x.get("notiz") or "", T.MUTED)] for x in s["wartung"]]).grid(
            row=row, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 6))
        row += 1
        _lbl(b, f"Stand {s['erstellt']}").grid(row=row, column=0, columnspan=2, sticky="w", padx=10, pady=(0, 10))

    def save_akku(self):
        try:
            batteries.upsert({"id": self.a_id.get(), "zellen": self.a_z.get(), "mah": self.a_mah.get(),
                              "name": self.a_name.get(), "kaufdatum": self.a_kauf.get(),
                              "ausgemustert": bool(self.a_aus.get())})
        except ValueError as e:
            messagebox.showerror("Akku-Register", str(e), parent=self)
            return
        self.load()

    def save_csv(self):
        fn = filedialog.asksaveasfilename(parent=self, title="Flüge als CSV speichern", defaultextension=".csv",
                                          initialfile="fpv-fluege.csv", filetypes=[("CSV", "*.csv")])
        if not fn:
            return
        try:
            with open(fn, "w", encoding="utf-8", newline="") as f:
                f.write(stats.flights_csv(self.cfg, **self._flt()))
        except OSError as e:
            messagebox.showerror("CSV", str(e), parent=self)

    def print_page(self):
        s = self.s or stats.compute(self.cfg, **self._flt())
        f = config.DATA_DIR / "statistik-druck.html"
        f.write_text(stats.print_html(s), encoding="utf-8")
        webbrowser.open(f.resolve().as_uri())
