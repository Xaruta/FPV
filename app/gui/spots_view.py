"""Desktop-Fenster der Spot-Datenbank (Phase 7): Profil-Editor und „Wo fliege ich heute?“."""
from __future__ import annotations

import json
import logging
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from app import config, logbook, spots
from app.gui import theme as T

log = logging.getLogger("gui.spots")
AMP = {"gruen": (T.OK, "🟢"), "gelb": (T.WARN, "🟡"), "rot": (T.ERR, "🔴"), None: (T.MUTED, "⚪")}
SORTS = {"Ampel + Nähe": "kombi", "Entfernung": "distanz", "Wetter": "wetter", "Bewertung": "bewertung",
         "Zuletzt geflogen": "zuletzt"}
BEW_LBL = {"gesamt": "⭐ Gesamt", "freestyle": "Freestyle", "cinematic": "Cinematic", "race": "Race",
           "ruhe": "Ruhe", "erreichbarkeit": "Erreichbarkeit"}


def _btn(m, text, cmd, kind="ghost", **kw):
    fg, hov = {"primary": (T.ACCENT, T.ACCENT_HOVER), "stop": (T.STOP, T.STOP_HOVER),
               "ok": ("#238636", "#2ea043"), "ghost": (T.GREY, T.GREY_HOVER)}[kind]
    kw.setdefault("height", 30)
    return ctk.CTkButton(m, text=text, command=cmd, fg_color=fg, hover_color=hov, font=T.font(12, "bold"),
                         corner_radius=9, **kw)


def _entry(m, width=160, ph=""):
    return ctk.CTkEntry(m, width=width, placeholder_text=ph, fg_color=T.BG, border_color=T.BORDER,
                        text_color=T.TEXT, font=T.font(13), height=30)


def _menu(m, values, width=130):
    return ctk.CTkOptionMenu(m, values=values, width=width, height=30, font=T.font(12), dropdown_font=T.font(12),
                             fg_color=T.BG, button_color=T.GREY, button_hover_color=T.GREY_HOVER)


def _text(m, h=80):
    return ctk.CTkTextbox(m, height=h, fg_color=T.BG, border_color=T.BORDER, border_width=1, text_color=T.TEXT,
                          font=T.font(13))


def _lbl(m, text, muted=True, **kw):
    return ctk.CTkLabel(m, text=text, font=T.font(12), text_color=T.MUTED if muted else T.TEXT, anchor="w", **kw)


def _set(e, v):
    e.delete(0, "end")
    if v not in (None, ""):
        e.insert(0, str(v))


def _open(url):
    webbrowser.open(url)


class ProfileEditor(ctk.CTkToplevel):
    """Profil eines Spots bearbeiten. on_saved(profile) wird nach dem Speichern/Import aufgerufen."""

    def __init__(self, master, profile: dict, cfg: dict, on_saved):
        super().__init__(master)
        self.cfg, self.on_saved, self.p = cfg, on_saved, profile
        self.title(f"Spot-Profil – {profile['name']}")
        self.geometry("820x700")
        self.configure(fg_color=T.BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)
        ctk.CTkLabel(self, text=f"🗂 {profile['name']}", font=T.font(20, "bold"), text_color=T.TEXT,
                     anchor="w").grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 0))
        tv = ctk.CTkTabview(self, fg_color=T.CARD, segmented_button_selected_color=T.ACCENT,
                            segmented_button_fg_color=T.GREY, text_color=T.TEXT)
        tv.grid(row=1, column=0, sticky="nsew", padx=12, pady=6)
        self._tab_allg(tv.add("Allgemein"))
        self._tab_gel(tv.add("Gelände"))
        self._tab_hind(tv.add("Hindernisse & Routen"))
        self._tab_gef(tv.add("Gefahren"))
        self._tab_funk(tv.add("Funk"))
        self._tab_bew(tv.add("Bewertung"))
        self._tab_med(tv.add("Medien & Teilen"))
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 12))
        self.msg = _lbl(bar, "")
        self.msg.pack(side="left", fill="x", expand=True)
        _btn(bar, "Schließen", self.destroy, width=100).pack(side="right")
        _btn(bar, "💾 Speichern", self.save, "ok", width=130).pack(side="right", padx=8)
        self.after(150, self.lift)

    # ---------------------------------------------------------------- Tabs
    def _scroll(self, tab):
        f = ctk.CTkScrollableFrame(tab, fg_color="transparent")
        f.pack(fill="both", expand=True)
        f.grid_columnconfigure(1, weight=1)
        return f

    def _row(self, f, r, label, widget):
        _lbl(f, label).grid(row=r, column=0, sticky="w", padx=(4, 10), pady=3)
        widget.grid(row=r, column=1, sticky="ew", pady=3)
        return widget

    def _tab_allg(self, tab):
        f, p = self._scroll(tab), self.p
        self.e_name = self._row(f, 0, "Name", _entry(f))
        self.e_lat = self._row(f, 1, "Breite (lat)", _entry(f))
        self.e_lon = self._row(f, 2, "Länge (lon)", _entry(f))
        self.e_reg = self._row(f, 3, "Region", _entry(f, ph="Ort, Landkreis, Bundesland"))
        self.e_hoehe = self._row(f, 4, "Höhe (m ü. NN)", _entry(f, ph="wird bei „Wo heute?“ aus Open-Meteo übernommen"))
        self.e_slat = self._row(f, 5, "Startplatz lat", _entry(f, ph="optional"))
        self.e_slon = self._row(f, 6, "Startplatz lon", _entry(f, ph="optional"))
        self.e_stxt = self._row(f, 7, "Start/Landung", _entry(f, ph="z. B. Feldweg-Ende, Parkplatz am Tor"))
        for e, v in ((self.e_name, p["name"]), (self.e_lat, p["lat"]), (self.e_lon, p["lon"]), (self.e_reg, p["region"]),
                     (self.e_hoehe, p["hoehe"]), (self.e_slat, p["startplatz"]["lat"]),
                     (self.e_slon, p["startplatz"]["lon"]), (self.e_stxt, p["startplatz"]["text"])):
            _set(e, v)
        lk = spots.links(p)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.grid(row=8, column=0, columnspan=2, sticky="w", pady=(12, 4))
        _btn(row, "🗺 dipul (Geozonen)", lambda: _open(lk["dipul"]), "primary", width=150).pack(side="left", padx=(0, 6))
        _btn(row, "🌍 OpenStreetMap", lambda: _open(lk["osm"]), width=130).pack(side="left", padx=(0, 6))
        _btn(row, "✈ OpenAIP", lambda: _open(lk["openaip"]), width=100).pack(side="left", padx=(0, 6))
        _btn(row, "📋 GPS kopieren", lambda: self._copy(lk["gps"]), width=120).pack(side="left")
        _lbl(f, "dipul/offizielle Quellen sind maßgeblich – das Profil ist nur deine Notiz, kein Rechtsrat.",
             wraplength=700).grid(row=9, column=0, columnspan=2, sticky="w", pady=4)

    def _copy(self, txt):
        self.clipboard_clear()
        self.clipboard_append(txt)
        self.msg.configure(text=f"GPS kopiert: {txt}", text_color=T.OK)

    def _tab_gel(self, tab):
        f, g = self._scroll(tab), self.p["gelaende"]
        tags = ctk.CTkFrame(f, fg_color="transparent")
        tags.grid(row=0, column=0, columnspan=2, sticky="w", pady=(2, 8))
        self.tag_vars = {}
        for i, t in enumerate(spots.GELAENDE_TAGS):
            v = ctk.BooleanVar(value=t in g["tags"])
            ctk.CTkCheckBox(tags, text=t, variable=v, font=T.font(12), text_color=T.TEXT, fg_color=T.ACCENT,
                            border_color=T.BORDER, width=110).grid(row=i // 5, column=i % 5, sticky="w", pady=2)
            self.tag_vars[t] = v
        self.g_e = {}
        for r, (k, lbl, ph) in enumerate((("untergrund", "Untergrund", "Gras, Kies, Asphalt …"),
                                           ("groesse", "Größe", "z. B. 200 × 100 m"),
                                           ("windschutz", "Windschutz/Lee", "Waldkante im Westen schützt bei W-Wind"),
                                           ("thermik", "Thermik", "mittags über dem Acker"),
                                           ("zugang", "Zugang/Parken", "Feldweg, 3 Parkplätze"),
                                           ("besucher", "Besucherverkehr", "Sonntags Spaziergänger")), start=1):
            self.g_e[k] = self._row(f, r, lbl, _entry(f, ph=ph))
            _set(self.g_e[k], g[k])
        _lbl(f, "Beschreibung").grid(row=7, column=0, sticky="nw", padx=(4, 10), pady=3)
        self.g_txt = _text(f, 110)
        self.g_txt.grid(row=7, column=1, sticky="ew", pady=3)
        self.g_txt.insert("1.0", g["text"])

    def _list_block(self, f, start_row, title, items, cols, add_label):
        """Dynamische Zeilenliste. cols = [(key, 'menu'|'entry'|'check', values/placeholder, width)]."""
        _lbl(f, title, muted=False).grid(row=start_row, column=0, columnspan=2, sticky="w", pady=(6, 2))
        box = ctk.CTkFrame(f, fg_color="transparent")
        box.grid(row=start_row + 1, column=0, columnspan=2, sticky="ew")
        rows: list[dict] = []

        def add(item=None):
            item = item or {}
            fr = ctk.CTkFrame(box, fg_color="transparent")
            fr.pack(fill="x", pady=2)
            w = {"_fr": fr}
            for key, kind, arg, width in cols:
                if kind == "menu":
                    m = _menu(fr, arg, width)
                    m.set(item.get(key) or arg[0])
                    w[key] = m
                elif kind == "check":
                    v = ctk.BooleanVar(value=bool(item.get(key, True)))
                    ctk.CTkCheckBox(fr, text=arg, variable=v, font=T.font(12), text_color=T.TEXT, fg_color=T.OK,
                                    border_color=T.BORDER, width=width).pack(side="left", padx=4)
                    w[key] = v
                    continue
                else:
                    m = _entry(fr, width, arg)
                    _set(m, item.get(key))
                    w[key] = m
                m.pack(side="left", padx=(0, 4), fill="x" if kind == "entry" and width > 200 else None,
                       expand=kind == "entry" and width > 200)
            ctk.CTkButton(fr, text="✕", width=26, height=26, fg_color="transparent", hover_color=T.GREY,
                          text_color=T.MUTED, command=lambda: (fr.destroy(), rows.remove(w))).pack(side="left")
            rows.append(w)

        for it in items:
            add(it)
        _btn(f, add_label, add, width=150).grid(row=start_row + 2, column=0, columnspan=2, sticky="w", pady=(2, 8))
        return rows

    def _tab_hind(self, tab):
        f = self._scroll(tab)
        self.h_rows = self._list_block(f, 0, "Hindernisse", self.p["hindernisse"],
                                       [("art", "menu", spots.HINDERNIS_ARTEN, 130),
                                        ("text", "entry", "Beschreibung / Lage", 380),
                                        ("hoehe_m", "entry", "Höhe m", 70)], "➕ Hindernis")
        _lbl(f, "Mögliche Flugrouten (eine pro Zeile)", muted=False).grid(row=3, column=0, columnspan=2, sticky="w",
                                                                         pady=(10, 2))
        self.r_txt = _text(f, 150)
        self.r_txt.grid(row=4, column=0, columnspan=2, sticky="ew")
        self.r_txt.insert("1.0", "\n".join(self.p["routen"]))

    def _tab_gef(self, tab):
        f = self._scroll(tab)
        self.gef_rows = self._list_block(f, 0, "Bekannte Gefahrenstellen – mit „Checkliste“ erscheinen sie vor dem Flug "
                                               "als Zusatzpunkt (hoch zuerst)", self.p["gefahren"],
                                         [("art", "menu", spots.GEFAHR_ARTEN, 130),
                                          ("text", "entry", "z. B. Kreisstraße 30 m östlich", 330),
                                          ("stufe", "menu", spots.STUFEN, 90),
                                          ("checkliste", "check", "Checkliste", 100)], "➕ Gefahrenstelle")

    def _tab_funk(self, tab):
        f, fu = self._scroll(tab), self.p["funk"]
        self.f_sys = self._row(f, 0, "Video-System", _menu(f, spots.FUNK_SYSTEME, 160))
        self.f_sys.set(fu["system"] if fu["system"] in spots.FUNK_SYSTEME else "")
        self.f_e = {}
        for r, (k, lbl, ph) in enumerate((("vtx_kanal", "VTX-Kanäle", "R3 gut, F4 stört"),
                                           ("stoerquellen", "Störquellen", "Hochspannung Nord, WLAN-Hof"),
                                           ("reichweite", "Reichweite/Abschattung", "hinter dem Wald im O schlecht"),
                                           ("link", "ELRS/Crossfire", "ELRS 250 Hz ok"),
                                           ("mobilfunk", "Mobilfunk", "Telekom 4G gut, Vodafone schwach")), start=1):
            self.f_e[k] = self._row(f, r, lbl, _entry(f, ph=ph))
            _set(self.f_e[k], fu[k])
        _lbl(f, "Notizen").grid(row=6, column=0, sticky="nw", padx=(4, 10), pady=3)
        self.f_txt = _text(f, 110)
        self.f_txt.grid(row=6, column=1, sticky="ew", pady=3)
        self.f_txt.insert("1.0", fu["text"])

    def _tab_bew(self, tab):
        f = self._scroll(tab)
        self.b_seg = {}
        for r, k in enumerate(spots.BEWERTUNG_KAT):
            s = ctk.CTkSegmentedButton(f, values=["–", "1", "2", "3", "4", "5"], font=T.font(12),
                                       selected_color=T.ACCENT, unselected_color=T.GREY)
            v = self.p["bewertung"][k]
            s.set(str(v) if v else "–")
            self._row(f, r, BEW_LBL[k], s)
            self.b_seg[k] = s
        st = spots.day_stats(self.p, self.cfg)
        _lbl(f, f"Flugtage an diesem Spot (Logbuch): {st['flugtage']} · zuletzt: {st['zuletzt'] or '–'}",
             muted=False).grid(row=7, column=0, columnspan=2, sticky="w", pady=(10, 4))
        _lbl(f, "Private Notizen (werden beim Export standardmäßig weggelassen)").grid(row=8, column=0, columnspan=2,
                                                                                       sticky="w", pady=(8, 2))
        self.n_txt = _text(f, 120)
        self.n_txt.grid(row=9, column=0, columnspan=2, sticky="ew")
        self.n_txt.insert("1.0", self.p["notizen"])

    def _tab_med(self, tab):
        f = self._scroll(tab)
        d = spots.media_dir(self.p["id"], self.cfg)
        n = len(spots.media(self.p["id"], self.cfg))
        _lbl(f, f"Spot-Medien (Übersichtsfotos, Parkplatz, Zufahrt): {n} Datei(en)\n{d}", muted=False,
             justify="left").grid(row=0, column=0, columnspan=2, sticky="w", pady=(4, 4))
        _btn(f, "📂 Spot-Medienordner öffnen", lambda: logbook.open_folder(d), "primary", width=220).grid(
            row=1, column=0, sticky="w", pady=4)
        _lbl(f, "Videos von Flugtagen liegen im jeweiligen Logbuch-Ordner (Logbuch-Karte → 📂).").grid(
            row=2, column=0, columnspan=2, sticky="w", pady=(0, 14))
        _lbl(f, "Teilen (für Freund-Kopie) – JSON ohne Medien:", muted=False).grid(row=3, column=0, columnspan=2,
                                                                                    sticky="w")
        self.priv = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(f, text="private Notizen mit exportieren", variable=self.priv, font=T.font(12),
                        text_color=T.TEXT, fg_color=T.ACCENT, border_color=T.BORDER).grid(row=4, column=0, sticky="w",
                                                                                           pady=4)
        row = ctk.CTkFrame(f, fg_color="transparent")
        row.grid(row=5, column=0, columnspan=2, sticky="w", pady=4)
        _btn(row, "⬆ Profil exportieren …", self.do_export, width=180).pack(side="left", padx=(0, 6))
        _btn(row, "⬇ Profil importieren …", self.do_import, width=180).pack(side="left")

    # ---------------------------------------------------------------- Aktionen
    def collect(self) -> dict:
        p = dict(self.p)
        p.update(name=self.e_name.get(), lat=self.e_lat.get(), lon=self.e_lon.get(), region=self.e_reg.get(),
                 hoehe=self.e_hoehe.get(),
                 startplatz={"lat": self.e_slat.get(), "lon": self.e_slon.get(), "text": self.e_stxt.get()})
        p["gelaende"] = {k: e.get() for k, e in self.g_e.items()}
        p["gelaende"]["tags"] = [t for t, v in self.tag_vars.items() if v.get()]
        p["gelaende"]["text"] = self.g_txt.get("1.0", "end").strip()
        p["hindernisse"] = [{"art": w["art"].get(), "text": w["text"].get(), "hoehe_m": w["hoehe_m"].get()}
                            for w in self.h_rows]
        p["routen"] = [x.strip() for x in self.r_txt.get("1.0", "end").splitlines() if x.strip()]
        p["gefahren"] = [{"art": w["art"].get(), "text": w["text"].get(), "stufe": w["stufe"].get(),
                          "checkliste": w["checkliste"].get()} for w in self.gef_rows]
        p["funk"] = {k: e.get() for k, e in self.f_e.items()}
        p["funk"]["system"] = self.f_sys.get()
        p["funk"]["text"] = self.f_txt.get("1.0", "end").strip()
        p["bewertung"] = {k: (0 if s.get() in ("–", "") else int(s.get())) for k, s in self.b_seg.items()}
        p["notizen"] = self.n_txt.get("1.0", "end").strip()
        return p

    def save(self):
        try:
            self.p = spots.save(self.collect(), self.cfg)
        except ValueError as e:
            self.msg.configure(text=f"⚠ {e}", text_color=T.ERR)
            return
        self.msg.configure(text=f"Gespeichert ({self.p['geaendert'][11:16]}).", text_color=T.OK)
        self.title(f"Spot-Profil – {self.p['name']}")
        self.on_saved(self.p)

    def do_export(self):
        fn = filedialog.asksaveasfilename(parent=self, title="Spot-Profil exportieren", defaultextension=".json",
                                          initialfile=f"spot-{self.p['id']}.json", filetypes=[("JSON", "*.json")])
        if not fn:
            return
        try:
            data = spots.export(self.p["id"], privat=self.priv.get(), cfg=self.cfg)
            Path(fn).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            self.msg.configure(text=f"Exportiert: {fn}", text_color=T.OK)
        except Exception as e:  # noqa: BLE001
            self.msg.configure(text=f"⚠ Export fehlgeschlagen: {e}", text_color=T.ERR)

    def do_import(self):
        fn = filedialog.askopenfilename(parent=self, title="Spot-Profil importieren", filetypes=[("JSON", "*.json")])
        if not fn:
            return
        try:
            p = spots.import_profile(json.loads(Path(fn).read_text(encoding="utf-8")), self.cfg)
        except Exception as e:  # noqa: BLE001
            self.msg.configure(text=f"⚠ Import fehlgeschlagen: {e}", text_color=T.ERR)
            return
        self.on_saved(None)
        messagebox.showinfo(config.APP_NAME, f"Spot „{p['name']}“ importiert.", parent=self)


class TodayWindow(ctk.CTkToplevel):
    """„🏆 Wo fliege ich heute?“ – echte Ampel je Spot (ein Open-Meteo-Abruf), sortierbar."""

    def __init__(self, master, cfg: dict, bg, on_activate):
        super().__init__(master)
        self.cfg, self.bg, self.on_activate = cfg, bg, on_activate
        self.title("Wo fliege ich heute?")
        self.geometry("900x560")
        self.configure(fg_color=T.BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 4))
        ctk.CTkLabel(top, text="🏆 Wo fliege ich heute?", font=T.font(20, "bold"), text_color=T.TEXT).pack(side="left")
        _btn(top, "🔄 Neu abrufen", lambda: self.load(True), width=120).pack(side="right")
        self.sort = _menu(top, list(SORTS), 150)
        self.sort.configure(command=lambda _v: self.load())
        self.sort.pack(side="right", padx=8)
        _lbl(top, "Sortierung").pack(side="right")
        self.meta = _lbl(self, "Lade …", wraplength=860, justify="left")
        self.meta.grid(row=1, column=0, sticky="ew", padx=18)
        self.lst = ctk.CTkScrollableFrame(self, fg_color=T.CARD, corner_radius=12)
        self.lst.grid(row=2, column=0, sticky="nsew", padx=12, pady=(6, 12))
        self.lst.grid_columnconfigure(1, weight=1)
        self.load()
        self.after(150, self.lift)

    def load(self, force=False):
        self.meta.configure(text="Hole aktuelles Wetter für alle Spots (Open-Meteo) …", text_color=T.MUTED)
        mode = SORTS[self.sort.get()]
        self.bg(lambda: spots.today(mode, force=force), self.show)

    def show(self, r, err):
        if not self.winfo_exists():
            return
        for ch in self.lst.winfo_children():
            ch.destroy()
        if err:
            self.meta.configure(text=f"⚠ {err}", text_color=T.ERR)
            return
        txt = f"Entfernung ab {r['ursprung']} · {r['quelle']}" + (f" · Abruf {r['abruf']}" if r["abruf"] else "")
        if r["fehler"]:
            txt = f"⚠ {r['fehler']} – Ampel unbekannt.\n" + txt
        self.meta.configure(text=txt + "\n" + r["hinweis"], text_color=T.ERR if r["fehler"] else T.MUTED)
        if not r["spots"]:
            _lbl(self.lst, "Noch keine Spots gespeichert.").grid(row=0, column=0, padx=10, pady=10)
            return
        for i, s in enumerate(r["spots"]):
            col, ico = AMP.get(s["ampel"], AMP[None])
            w = s["wetter"] or {}
            ctk.CTkLabel(self.lst, text=ico, font=T.font(22)).grid(row=i, column=0, padx=(10, 6), pady=6, sticky="n")
            info = (f"{s['name']}" + (f"  ·  {s['region'].split(',')[0]}" if s["region"] else ""))
            det = (f"{s['ampel_titel']} – {'; '.join(s['gruende'][:3])}\n"
                   + (f"Wind {w['wind']} / Böen {w['boeen']} m/s aus {w['richtung_txt']} · {w['temp']} °C · {w['wetter']}"
                      if w else "kein Wetter") +
                   (f"   ·   {s['distanz_km']} km" if s["distanz_km"] is not None else "") +
                   (f"   ·   {'★' * s['bewertung']}" if s["bewertung"] else "") +
                   f"   ·   {s['flugtage']} Flugtag(e)" + (f", zuletzt {s['zuletzt']}" if s["zuletzt"] else "") +
                   (f"   ·   ⚠ {s['gefahren_hoch']} hohe Gefahr(en)" if s["gefahren_hoch"] else ""))
            fr = ctk.CTkFrame(self.lst, fg_color="transparent")
            fr.grid(row=i, column=1, sticky="ew", pady=4)
            ctk.CTkLabel(fr, text=info, font=T.font(14, "bold"), text_color=col, anchor="w").pack(fill="x")
            ctk.CTkLabel(fr, text=det, font=T.font(12), text_color=T.TEXT, anchor="w", justify="left",
                         wraplength=560).pack(fill="x")
            b = ctk.CTkFrame(self.lst, fg_color="transparent")
            b.grid(row=i, column=2, padx=8, sticky="e")
            _btn(b, "Aktivieren", lambda n=s["name"]: self.on_activate(n), "primary", width=90).pack(pady=1)
            _btn(b, "🗺 dipul", lambda u=s["links"]["dipul"]: _open(u), width=90).pack(pady=1)
