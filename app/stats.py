"""Flugstatistik (Roadmap Phase 8) – wird bei jedem Aufruf aus den echten Logbuch-Dateien neu berechnet.

Quellen: logs/*/flugtag.json, fluege.jsonl, wartung.jsonl, verlauf.jsonl, data/akkus.json, spots/*/profil.json.
Fehlende Angaben werden gezählt und als „keine Angabe“ ausgewiesen – nichts wird geschätzt oder aufgefüllt.
"""
from __future__ import annotations

import csv
import html
import io
from datetime import date, datetime

from app import batteries, logbook, settings

KA = "keine Angabe"
WIND_BINS = [(0, 2, "0–2"), (2, 4, "2–4"), (4, 6, "4–6"), (6, 8, "6–8"), (8, 99, "≥ 8")]
MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]


def _avg(v):
    v = [x for x in v if isinstance(x, (int, float))]
    return round(sum(v) / len(v), 1) if v else None


def _max(v):
    v = [x for x in v if isinstance(x, (int, float))]
    return max(v) if v else None


def load_days(cfg: dict | None = None, von: str = "", bis: str = "", spot: str = "", drohne: str = "") -> list[dict]:
    cfg = cfg or settings.load()
    base = logbook.logs_dir(cfg)
    days = []
    for f in sorted(base.glob("*/flugtag.json")):
        day = logbook._read_json(f)
        if not isinstance(day, dict) or "spot" not in day or not day.get("datum"):
            continue
        if (von and day["datum"] < von) or (bis and day["datum"] > bis):
            continue
        if spot and day["spot"].get("name") != spot:
            continue
        d = f.parent
        fl = logbook.flights(d)
        wa = logbook.maintenance(d)
        if drohne:
            fl = [x for x in fl if (x.get("drohne") or "") == drohne]
            wa = [x for x in wa if (x.get("drohne") or "") == drohne]
            if not fl and not wa:
                continue
        days.append({"ordner": d.name, "day": day, "fluege": fl, "wartung": wa,
                     "verlauf": logbook._read_jsonl(d / "verlauf.jsonl")})
    days.sort(key=lambda x: x["day"].get("start") or x["day"]["datum"])
    return days


def _streaks(dates: list[str]) -> dict:
    """Wochen-Serie: aufeinanderfolgende Kalenderwochen mit mind. einem Flugtag."""
    weeks = sorted({date.fromisoformat(d).isocalendar()[:2] for d in dates})
    if not weeks:
        return {"beste": 0, "aktuell": 0}

    def idx(w):
        return date.fromisocalendar(w[0], w[1], 1).toordinal() // 7
    best = cur = 1
    for a, b in zip(weeks, weeks[1:]):
        cur = cur + 1 if idx(b) - idx(a) == 1 else 1
        best = max(best, cur)
    today_w = idx(date.today().isocalendar()[:2])
    last = idx(weeks[-1])
    aktuell = cur if today_w - last <= 1 else 0
    return {"beste": best, "aktuell": aktuell}


def compute(cfg: dict | None = None, **flt) -> dict:
    cfg = cfg or settings.load()
    days = load_days(cfg, **flt)
    try:
        akkus = batteries.load()
        akku_err = None
    except ValueError as e:
        akkus, akku_err = [], str(e)
    all_fl = [dict(f, _datum=x["day"]["datum"], _spot=x["day"]["spot"].get("name"), _ordner=x["ordner"])
              for x in days for f in x["fluege"]]
    all_wa = [dict(w, _datum=w.get("datum") or x["day"]["datum"], _spot=x["day"]["spot"].get("name"),
                   _ordner=x["ordner"]) for x in days for w in x["wartung"]]
    durs = [f["dauer_s"] for f in all_fl if f.get("dauer_s")]

    # Monate
    monate: dict[str, dict] = {}
    for x in days:
        m = monate.setdefault(x["day"]["datum"][:7], {"flugtage": 0, "fluege": 0, "flugzeit_s": 0, "crashes": 0})
        m["flugtage"] += 1
        m["fluege"] += len(x["fluege"])
        m["flugzeit_s"] += sum(f["dauer_s"] for f in x["fluege"] if f.get("dauer_s"))
        m["crashes"] += sum(1 for f in x["fluege"] if f.get("ergebnis") == "crash")
    monate_l = [{"monat": k, "label": f"{MONATE[int(k[5:7]) - 1]} {k[:4]}", **v} for k, v in sorted(monate.items())]

    # Spots
    sp: dict[str, dict] = {}
    for x in days:
        s = x["day"]["spot"]
        r = sp.setdefault(s.get("name") or KA, {"spot": s.get("name") or KA, "spot_id": s.get("id"), "flugtage": 0,
                                                 "fluege": 0, "flugzeit_s": 0, "zuletzt": None, "crashes": 0})
        r["flugtage"] += 1
        r["fluege"] += len(x["fluege"])
        r["flugzeit_s"] += sum(f["dauer_s"] for f in x["fluege"] if f.get("dauer_s"))
        r["crashes"] += sum(1 for f in x["fluege"] if f.get("ergebnis") == "crash")
        r["zuletzt"] = max(r["zuletzt"] or "", x["day"]["datum"])
        r["spot_id"] = r["spot_id"] or s.get("id")
    spots_l = sorted(sp.values(), key=lambda r: (-r["flugtage"], -r["flugzeit_s"]))

    # Drohnen
    dr: dict[str, dict] = {}
    for f in all_fl:
        r = dr.setdefault(f.get("drohne") or KA, {"drohne": f.get("drohne") or KA, "fluege": 0, "flugzeit_s": 0,
                                                    "ohne_dauer": 0, "crashes": 0, "reparaturen": 0,
                                                    "seit_crash": 0, "zuletzt": None})
        r["fluege"] += 1
        if f.get("dauer_s"):
            r["flugzeit_s"] += f["dauer_s"]
        else:
            r["ohne_dauer"] += 1
        if f.get("ergebnis") == "crash":
            r["crashes"] += 1
            r["seit_crash"] = 0
        else:
            r["seit_crash"] += 1
        r["zuletzt"] = max(r["zuletzt"] or "", f["_datum"])
    for w in all_wa:
        r = dr.setdefault(w.get("drohne") or KA, {"drohne": w.get("drohne") or KA, "fluege": 0, "flugzeit_s": 0,
                                                    "ohne_dauer": 0, "crashes": 0, "reparaturen": 0,
                                                    "seit_crash": 0, "zuletzt": None})
        r["reparaturen"] += 1
    for r in dr.values():
        if not r["crashes"]:
            r["seit_crash"] = None   # nie gecrasht → „Flüge seit letztem Crash“ nicht sinnvoll
    drohnen_l = sorted(dr.values(), key=lambda r: -r["fluege"])

    # Akkus
    reg = {a["id"]: a for a in akkus}
    ak: dict[str, dict] = {}
    for a in akkus:
        ak[a["id"]] = {"akku": a["id"], "label": batteries.label(a), "im_register": True,
                       "ausgemustert": a.get("ausgemustert", False), "zyklen": 0, "flugzeit_s": 0, "dauern": [],
                       "zuletzt": None, "kaufdatum": a.get("kaufdatum")}
    for f in all_fl:
        k = f.get("akku")
        if not k:
            continue
        r = ak.setdefault(k, {"akku": k, "label": k, "im_register": k in reg, "ausgemustert": False, "zyklen": 0,
                              "flugzeit_s": 0, "dauern": [], "zuletzt": None, "kaufdatum": None})
        r["zyklen"] += 1
        if f.get("dauer_s"):
            r["flugzeit_s"] += f["dauer_s"]
            r["dauern"].append(f["dauer_s"])
        r["zuletzt"] = max(r["zuletzt"] or "", f["_datum"])
    akkus_l = []
    for r in ak.values():
        dd = r.pop("dauern")
        r["avg_s"] = round(sum(dd) / len(dd)) if dd else None
        r["hinweis"] = None
        if len(dd) >= 8:
            early, late = dd[: len(dd) // 2], dd[-4:]
            if sum(late) / len(late) < 0.8 * (sum(early) / len(early)):
                r["hinweis"] = "Flugzeit der letzten 4 Flüge > 20 % unter früher – müder Akku? Innenwiderstand prüfen."
        elif dd:
            r["hinweis"] = f"erst {len(dd)} Flug/Flüge mit Dauer – Trend ab 8"
        akkus_l.append(r)
    akkus_l.sort(key=lambda r: (r["ausgemustert"], -r["zyklen"], r["akku"]))
    ohne_akku = sum(1 for f in all_fl if not f.get("akku"))

    # Wetter der Flugtage
    ampel = {"gruen": 0, "gelb": 0, "rot": 0, KA: 0}
    hist = {lbl: 0 for *_, lbl in WIND_BINS}
    hist[KA] = 0
    winds, gusts, temps = [], [], []
    for x in days:
        st = x["day"].get("snapshot_start") or {}
        ampel[st.get("ampel") if st.get("ampel") in ampel else KA] += 1
        w = st.get("wind")
        if isinstance(w, (int, float)):
            for lo, hi, lbl in WIND_BINS:
                if lo <= w < hi:
                    hist[lbl] += 1
        else:
            hist[KA] += 1
        pts = x["verlauf"]
        winds += [p.get("wind") for p in pts]
        gusts += [p.get("boeen") for p in pts]
        temps += [p.get("temp") for p in pts]
    tv = [t for t in temps if isinstance(t, (int, float))]
    wetter = {"ampel": ampel, "wind_hist": hist, "wind_avg": _avg(winds), "wind_max": _max(winds),
              "boeen_avg": _avg(gusts), "boeen_max": _max(gusts),
              "temp_min": min(tv) if tv else None, "temp_max": max(tv) if tv else None,
              "messpunkte": sum(len(x["verlauf"]) for x in days)}

    # Entwicklung Ø-Flugzeit (gleitender Mittelwert über 5 Flüge mit Dauer)
    seq = [f for f in all_fl if f.get("dauer_s")]
    entw = []
    for i, f in enumerate(seq):
        win = [g["dauer_s"] for g in seq[max(0, i - 4): i + 1]]
        entw.append({"datum": f["_datum"], "dauer_s": f["dauer_s"], "gleitend_s": round(sum(win) / len(win)),
                     "drohne": f.get("drohne") or KA})
    m_avg = [{"monat": m["monat"], "label": m["label"],
              "avg_s": round(m["flugzeit_s"] / n) if (n := sum(1 for f in all_fl if f["_datum"][:7] == m["monat"]
                                                            and f.get("dauer_s"))) else None} for m in monate_l]

    # Rekorde
    longest = max(seq, key=lambda f: f["dauer_s"], default=None)
    most = max(days, key=lambda x: len(x["fluege"]), default=None)
    rekorde = {"laengster_flug": {"dauer_s": longest["dauer_s"], "datum": longest["_datum"], "spot": longest["_spot"],
                                  "drohne": longest.get("drohne")} if longest else None,
               "meiste_packs": {"anzahl": len(most["fluege"]), "datum": most["day"]["datum"],
                                "spot": most["day"]["spot"].get("name")} if most and most["fluege"] else None}

    # Wartung / Teile
    teile: dict[str, int] = {}
    for w in all_wa:
        teile[w["teil"]] = teile.get(w["teil"], 0) + int(w.get("anzahl") or 1)
    kosten = [w["kosten"] for w in all_wa if isinstance(w.get("kosten"), (int, float))]

    return {
        "erstellt": datetime.now().strftime("%d.%m.%Y %H:%M"), "filter": {k: v for k, v in flt.items() if v},
        "summen": {"flugtage": len(days), "fluege": len(all_fl), "flugzeit_s": sum(durs),
                   "fluege_ohne_dauer": len(all_fl) - len(durs), "avg_s": round(sum(durs) / len(durs)) if durs else None,
                   "crashes": sum(1 for f in all_fl if f.get("ergebnis") == "crash"),
                   "ohne_ergebnis": sum(1 for f in all_fl if not f.get("ergebnis")),
                   "reparaturen": len(all_wa), "kosten": round(sum(kosten), 2) if kosten else None,
                   "kosten_ohne_angabe": len(all_wa) - len(kosten), "ohne_akku": ohne_akku,
                   "flugtage_ohne_fluege": sum(1 for x in days if not x["fluege"])},
        "serie": _streaks([x["day"]["datum"] for x in days]),
        "monate": monate_l, "spots": spots_l, "drohnen": drohnen_l, "akkus": akkus_l, "akku_fehler": akku_err,
        "wetter": wetter, "entwicklung": entw, "monat_avg": m_avg, "rekorde": rekorde,
        "wartung": sorted(all_wa, key=lambda w: w["_datum"], reverse=True)[:50], "teile": teile,
        "drohnen_liste": sorted({f.get("drohne") for f in all_fl if f.get("drohne")}),
        "spot_liste": sorted({x["day"]["spot"].get("name") for x in days}),
        "hinweis": "Alle Zahlen aus deinen Logbuch-Dateien neu berechnet. Nicht Erfasstes = „keine Angabe“.",
    }


# ------------------------------------------------------------------ Export
def flights_csv(cfg: dict | None = None, **flt) -> str:
    """Eine Zeile pro Flug (Semikolon + UTF-8-BOM → öffnet direkt in deutschem Excel/LibreOffice)."""
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Datum", "Spot", "Region", "Start", "Dauer (s)", "Dauer (mm:ss)", "Zeitquelle", "Akku", "Drohne",
                "Ergebnis", "Notiz", "Ampel Tagesstart", "Wind Tagesstart (m/s)", "Böen Tagesstart (m/s)", "Ordner"])
    for x in load_days(cfg, **flt):
        st = x["day"].get("snapshot_start") or {}
        for f in x["fluege"]:
            d = f.get("dauer_s")
            w.writerow([x["day"]["datum"], x["day"]["spot"].get("name"), x["day"]["spot"].get("region") or "",
                        f.get("start") or "", d if d else "", f"{d // 60}:{d % 60:02d}" if d else KA,
                        f.get("quelle") or "", f.get("akku") or "", f.get("drohne") or "",
                        {"ok": "ok", "crash": "Crash"}.get(f.get("ergebnis"), KA), f.get("notiz") or "",
                        st.get("ampel") or KA, _de(st.get("wind")), _de(st.get("boeen")), x["ordner"]])
    return "\ufeff" + buf.getvalue()


def _de(v):
    return str(v).replace(".", ",") if isinstance(v, (int, float)) else ""


def print_html(s: dict) -> str:
    e = html.escape
    fd = logbook.fmt_dur
    su = s["summen"]

    def table(head, rows):
        return ("<table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>"
                + "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in r) + "</tr>" for r in rows) + "</table>")
    amp = s["wetter"]["ampel"]
    n_amp = sum(amp.values()) or 1
    body = f"""
<h1>📊 FPV-Flugstatistik</h1><div class=sub>FPV-Lagezentrum · erstellt {e(s['erstellt'])}
{(' · Filter: ' + e(', '.join(f'{k}={v}' for k, v in s['filter'].items()))) if s['filter'] else ''}</div>
<div class=kpi><div><b>{su['flugtage']}</b>Flugtage</div><div><b>{su['fluege']}</b>Flüge</div>
<div><b>{e(fd(su['flugzeit_s']) if su['flugzeit_s'] else KA)}</b>Flugzeit</div>
<div><b>{e(fd(su['avg_s']) if su['avg_s'] else KA)}</b>Ø pro Flug</div><div><b>{su['crashes']}</b>Crashes</div>
<div><b>{su['reparaturen']}</b>Reparaturen</div></div>
<p class=sub>Flüge ohne Dauer: {su['fluege_ohne_dauer']} · ohne Ergebnis: {su['ohne_ergebnis']} · ohne Akku: {su['ohne_akku']}
· Flugtage ohne erfasste Flüge: {su['flugtage_ohne_fluege']} · Wochen-Serie: beste {s['serie']['beste']}, aktuell {s['serie']['aktuell']}</p>
<h2>Flugtage pro Monat</h2>{table(['Monat', 'Flugtage', 'Flüge', 'Flugzeit', 'Crashes'],
    [[m['label'], m['flugtage'], m['fluege'], fd(m['flugzeit_s']) if m['flugzeit_s'] else KA, m['crashes']] for m in s['monate']])}
<h2>Häufigste Spots</h2>{table(['Spot', 'Flugtage', 'Flüge', 'Flugzeit', 'zuletzt'],
    [[x['spot'], x['flugtage'], x['fluege'], fd(x['flugzeit_s']) if x['flugzeit_s'] else KA, x['zuletzt']] for x in s['spots']])}
<h2>Drohnen</h2>{table(['Drohne', 'Flüge', 'Flugzeit', 'Crashes', 'Reparaturen', 'Flüge seit Crash'],
    [[x['drohne'], x['fluege'], fd(x['flugzeit_s']) if x['flugzeit_s'] else KA, x['crashes'], x['reparaturen'],
      '–' if x['seit_crash'] is None else x['seit_crash']] for x in s['drohnen']])}
<h2>Akkus</h2>{table(['Akku', 'Zyklen', 'Flugzeit', 'Ø Flug', 'zuletzt', 'Hinweis'],
    [[x['label'] + (' (ausgemustert)' if x['ausgemustert'] else '') + ('' if x['im_register'] else ' – nicht im Register'),
      x['zyklen'], fd(x['flugzeit_s']) if x['flugzeit_s'] else KA, fd(x['avg_s']) if x['avg_s'] else KA,
      x['zuletzt'] or '–', x['hinweis'] or ''] for x in s['akkus']])}
<h2>Wetter der Flugtage (Tagesstart-Snapshot)</h2>
{table(['Ampel', 'Flugtage', 'Anteil'], [[k, v, f"{100 * v / n_amp:.0f} %"] for k, v in amp.items()])}
<p>Wind beim Start (m/s): {e(' · '.join(f'{k}: {v}' for k, v in s['wetter']['wind_hist'].items()))}<br>
Verlauf: Ø Wind {s['wetter']['wind_avg'] if s['wetter']['wind_avg'] is not None else KA} m/s, max Böe
{s['wetter']['boeen_max'] if s['wetter']['boeen_max'] is not None else KA} m/s, Temperatur
{s['wetter']['temp_min'] if s['wetter']['temp_min'] is not None else KA} … {s['wetter']['temp_max'] if s['wetter']['temp_max'] is not None else KA} °C
({s['wetter']['messpunkte']} Messpunkte, Open-Meteo)</p>
<h2>Ø-Flugzeit je Monat</h2>{table(['Monat', 'Ø Flugzeit'], [[m['label'], fd(m['avg_s']) if m['avg_s'] else KA] for m in s['monat_avg']])}
<h2>Wartung & Reparaturen</h2>{table(['Datum', 'Teil', 'Anzahl', 'Drohne', 'Kosten', 'Notiz'],
    [[w['_datum'], w['teil'], w.get('anzahl') or 1, w.get('drohne') or KA,
      f"{w['kosten']:.2f} €".replace('.', ',') if w.get('kosten') is not None else KA, w.get('notiz') or ''] for w in s['wartung']])}
<p class=sub>{e(s['hinweis'])}</p>"""
    return f"""<!doctype html><html lang=de><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>FPV-Flugstatistik</title><style>
@page{{size:A4;margin:12mm}}body{{font:11pt/1.4 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#111;background:#fff;max-width:190mm;margin:0 auto;padding:10px}}
h1{{font-size:19pt;margin:0}}h2{{font-size:13pt;margin:16px 0 4px;border-bottom:1.5px solid #222}}.sub{{color:#555;font-size:9.5pt}}
table{{width:100%;border-collapse:collapse;font-size:9.5pt;break-inside:auto}}th,td{{text-align:left;padding:3px 5px;border-bottom:1px solid #ccc}}th{{background:#eee}}
tr{{break-inside:avoid}}.kpi{{display:grid;grid-template-columns:repeat(6,1fr);gap:6px;margin:10px 0}}.kpi div{{border:1.5px solid #222;border-radius:8px;padding:6px;text-align:center;font-size:9pt}}
.kpi b{{display:block;font-size:15pt}}.knopf{{margin:8px 0;padding:9px 14px;font:inherit;font-weight:700;border:0;border-radius:8px;background:#2f81f7;color:#fff}}
@media print{{.knopf{{display:none}}}}</style></head><body><button class=knopf onclick="window.print()">🖨 Drucken / Als PDF sichern</button>{body}</body></html>"""
