"""Druckbare Checkliste (helles HTML mit Print-CSS, A4). PDF über „Drucken → Als PDF sichern“ im Browser."""
from __future__ import annotations

import html
from datetime import datetime

from app import config, geo, settings

CSS = """
@page{size:A4;margin:14mm}*{box-sizing:border-box}
body{font:13pt/1.4 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif;color:#111;background:#fff;margin:0 auto;max-width:190mm;padding:10px}
h1{font-size:20pt;margin:0 0 2px}.sub{color:#555;font-size:10.5pt;margin-bottom:10px}
.kopf{display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;border:1.5px solid #222;border-radius:8px;padding:8px 12px;margin-bottom:12px;font-size:11pt}
.kopf b{display:inline-block;min-width:68px}.linie{border-bottom:1px solid #999;display:inline-block;min-width:120px}
ol{list-style:none;padding:0;margin:0}li{display:flex;gap:12px;align-items:flex-start;padding:7px 0;border-bottom:1px solid #ddd;break-inside:avoid}
.box{flex:0 0 22px;height:22px;border:2px solid #222;border-radius:4px;text-align:center;font-weight:800;line-height:18px}
.notiz{margin-top:14px;border:1.5px solid #222;border-radius:8px;padding:8px 12px;min-height:45mm}
.fuss{margin-top:10px;font-size:9pt;color:#555}
.knopf{margin:10px 0;padding:10px 16px;font:inherit;font-weight:700;border:0;border-radius:8px;background:#2f81f7;color:#fff;cursor:pointer}
@media print{.knopf{display:none}body{padding:0}}
"""


def checklist_html(cfg: dict | None = None, ampel: dict | None = None, leer: bool = False) -> str:
    cfg = cfg or settings.load()
    sp = settings.active_spot(cfg)
    items = cfg.get("checklist") or []
    e = html.escape
    spot_txt = e(sp["name"]) + (f" · {e(sp['region'])}" if sp and sp.get("region") else "") if sp else '<span class=linie></span>'
    coords = f"{sp['lat']:.5f}, {sp['lon']:.5f}" if sp else '<span class=linie></span>'
    amp = f"{e(ampel['titel'])} ({'; '.join(e(g) for g in ampel['gruende'][:3])})" if ampel else '<span class=linie></span>'
    lis = "".join(f"<li><span class=box>{'✓' if (it.get('done') and not leer) else ''}</span><span>{e(it['text'])}</span></li>"
                  for it in items)
    try:  # Gefahrenstellen aus dem Spot-Profil (Phase 7) als Zusatzpunkte
        from app import spots
        extra = spots.checklist_extras(spots.active_profile(cfg))
    except Exception:  # noqa: BLE001
        extra = []
    if extra:
        lis += "<li style='border-bottom:0;padding-top:12px'><b>Spot-Gefahren (aus dem Spot-Profil):</b></li>" + "".join(
            f"<li><span class=box></span><span>{e(x)}</span></li>" for x in extra)
    dipul = geo.dipul_url(sp["lat"], sp["lon"]) if sp else config.DIPUL_HOME
    return f"""<!doctype html><html lang=de><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Preflight-Checkliste – FPV-Lagezentrum</title><style>{CSS}</style></head><body>
<button class=knopf onclick="window.print()">🖨 Drucken / Als PDF sichern</button>
<h1>✅ FPV Preflight-Checkliste</h1><div class=sub>FPV-Lagezentrum · erstellt {datetime.now():%d.%m.%Y %H:%M}</div>
<div class=kopf><div><b>Datum</b> <span class=linie></span></div><div><b>Pilot</b> <span class=linie></span></div>
<div><b>Spot</b> {spot_txt}</div><div><b>Koord.</b> {coords}</div>
<div><b>Wetter</b> {amp}</div><div><b>Drohne</b> <span class=linie></span></div></div>
<ol>{lis}</ol>
<div class=notiz><b>Notizen / Akkus / Flüge:</b></div>
<div class=fuss>Wetter-Ampel = Orientierung, kein Rechtsrat. Geozonen & Regeln verbindlich nur in der dipul-Karte der DFS:
{e(dipul)}</div></body></html>"""
