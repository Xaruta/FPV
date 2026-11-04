#!/usr/bin/env python3
"""FPV-Lagezentrum Web – gleiche Funktionen wie das Desktop-Programm, handytauglich.

Lauscht NUR auf 127.0.0.1:8767, kein Passwort. Von außen höchstens per „tailscale serve“ im Tailnet
(siehe README), NIE Funnel. Nur Standardbibliothek – läuft auf macOS, Linux, Windows.
  python web/server.py
"""
from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app import batteries, config, dipul, export, geo, logbook, mapdata, metar, notam, opensky, settings, spots, stats, sun, weather  # noqa: E402
from web.karte import MAP_PAGE  # noqa: E402

log = logging.getLogger("web")
HOST, PORT = config.WEB_HOST, int(os.environ.get("FPVWEB_PORT", config.WEB_PORT))
ALLOWED_HOSTS = {f"127.0.0.1:{PORT}", f"localhost:{PORT}"}
if config.TS_HOST:
    ALLOWED_HOSTS |= {config.TS_HOST, f"{config.TS_HOST}:443", f"{config.TS_HOST}:{PORT}"}
SLOCK = threading.Lock()

CSS = """
:root{color-scheme:dark;--bg:#0b0f14;--card:#161b22;--bd:#30363d;--tx:#e6edf3;--mu:#8b949e;--ac:#2f81f7;
--ok:#3fb950;--warn:#d29922;--err:#f85149}*{box-sizing:border-box}html{overflow-x:hidden}
body{margin:0 auto;font:15px/1.45 -apple-system,system-ui,"Segoe UI",sans-serif;background:var(--bg);color:var(--tx);
padding:14px;max-width:1100px}
h1{font-size:22px;margin:4px 0 2px}.sub{color:var(--mu);font-size:13px;margin-bottom:6px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:0 12px}@media(max-width:760px){.grid{grid-template-columns:1fr}}
.full{grid-column:1/-1}
.card{background:var(--card);border:1px solid var(--bd);border-radius:14px;padding:12px 14px;margin:6px 0;min-width:0}
.lbl{font-weight:700;font-size:16px;margin:2px 0 8px}.mu{color:var(--mu);font-size:13px}
input,select{font:inherit;width:100%;padding:9px;border-radius:10px;border:1px solid var(--bd);background:var(--bg);color:var(--tx)}
button{font:inherit;font-weight:600;min-height:40px;border:0;border-radius:10px;padding:8px 12px;color:#fff;background:#373e47;cursor:pointer}
button.pri{background:var(--ac)}button.ok{background:#238636;color:#fff}button.stop{background:#da3633}
.row{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:4px 0}.row>*{flex:1 1 120px;min-width:0}
.amp{font-size:28px;font-weight:800}.bar{height:8px;border-radius:4px;background:#373e47;margin:6px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(110px,1fr));gap:8px}
.tile{background:var(--bg);border:1px solid var(--bd);border-radius:12px;padding:8px;text-align:center}
.tile .v{font-size:30px;font-weight:800}.tile .u{color:var(--mu);font-size:12px}
.hours{display:grid;grid-template-columns:repeat(auto-fit,minmax(80px,1fr));gap:6px;margin-top:8px}
.hours div{background:var(--bg);border:1px solid var(--bd);border-radius:10px;padding:4px;text-align:center;font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}th{color:var(--mu);text-align:left;font-weight:600}
th,td{padding:5px 6px;border-bottom:1px solid var(--bd);white-space:nowrap}.tw{overflow-x:auto}
.ck label{display:flex;gap:8px;align-items:flex-start;padding:4px 0}.ck input{width:auto;margin-top:3px;accent-color:var(--ok)}
.ck .x{background:none;min-height:0;padding:0 6px;color:var(--mu);margin-left:auto}
a{color:var(--ac)}.ok{color:var(--ok)}.warn{color:var(--warn)}.err{color:var(--err)}
#arrow{transition:transform .4s}
details{border:1px solid var(--bd);border-radius:10px;padding:6px 10px;margin:6px 0;background:var(--bg)}
summary{cursor:pointer;font-weight:700;padding:4px 0}textarea{font:inherit;width:100%;min-height:70px;padding:9px;border-radius:10px;
border:1px solid var(--bd);background:var(--card);color:var(--tx)}details input,details select{background:var(--card)}
.tag{display:inline-flex;gap:4px;align-items:center;margin:2px 8px 2px 0}.tag input{width:auto}
.sp{display:flex;gap:10px;align-items:flex-start;padding:8px 0;border-bottom:1px solid var(--bd)}.sp .i{font-size:24px}
.sp .b{flex:1;min-width:0}.sp .a{display:flex;flex-direction:column;gap:4px}.sp .a button{min-height:32px;padding:4px 10px}
.hz{color:var(--warn);padding:3px 0}
"""

# ---- Phase 8: Flüge/Wartung + Statistik (raw strings, werden in PAGE eingesetzt)
# ---- Phase 4: METAR/TAF (raw strings, werden in PAGE eingesetzt)
METAR_HTML = r'''<div class=card><div class=row><div class=lbl style="flex:1">🛫 Flugplatz-Wetter (METAR/TAF)</div>
 <button style="flex:0 0 auto" onclick="metarLoad(1)">🔄</button></div><div id=metar class=mu>lade …</div></div>'''
METAR_JS = r'''
async function metarLoad(force){const el=$("metar");try{const r=await api("/api/metar"+(force?"?force=1":""));
 let h=r.fehler?`<div class=err style="margin-bottom:6px">⚠ ${esc(r.fehler)}</div>`:"";const m=r.metar,st=r.station;
 if(m&&st){h+=`<div style="color:var(--tx)"><b style="font-size:17px">${esc(m.id)}</b> ${esc(st.name)} · ${st.dist_km} km ${esc(st.peilung)} vom Spot</div>
  <div class=${m.veraltet?"warn":"mu"}>Meldung ${esc(m.zeit)} Uhr · vor ${m.alter_min} min${m.veraltet?" – veraltet!":""}${m.auto?" · automatisch (AUTO)":""}</div>
  <table style="width:100%;margin:6px 0;color:var(--tx);font-size:14px">
  <tr><td class=mu>💨 Wind</td><td>${esc(m.wind)}</td></tr><tr><td class=mu>👁 Sicht</td><td>${esc(m.sicht)}</td></tr>
  <tr><td class=mu>🌦 Wetter</td><td>${esc(m.wetter)}</td></tr><tr><td class=mu>☁ Wolken</td><td>${esc(m.wolken)}</td></tr>
  <tr><td class=mu>🌡 Temp/Taup.</td><td>${m.temp??"–"} °C / ${m.taupunkt??"–"} °C</td></tr>
  <tr><td class=mu>⏲ QNH</td><td><b>${m.qnh??"–"} hPa</b></td></tr>
  ${m.kategorie?`<tr><td class=mu>✈ Kategorie</td><td>${esc(m.kategorie_text||m.kategorie)}</td></tr>`:""}</table>
  <code style="display:block;white-space:pre-wrap;font-size:12px;color:var(--mu)">${esc(m.roh)}</code>`}
 const t=r.taf;if(t){h+=`<details style="margin-top:6px"><summary>TAF ${esc(t.id)}${st&&t.id!=st.id?` (${t.dist_km} km ${esc(t.peilung)})`:""} · gültig ${esc(t.gueltig)}</summary>`+
  t.perioden.map(p=>`<div style="margin:3px 0"><b>${esc(p.art)}</b> <span class=mu>${esc(p.von)}–${esc(p.bis)}</span><br>${esc(p.text)}</div>`).join("")+
  `<code style="display:block;white-space:pre-wrap;font-size:12px;color:var(--mu)">${esc(t.roh)}</code></details>`}
 else if(r.station||r.weitere&&r.weitere.length)h+=`<div class=mu>Kein TAF bei den nächsten Plätzen.</div>`;
 const w=(r.weitere||[]).filter(x=>x.hat_metar);if(w.length)h+=`<details><summary>Weitere Plätze</summary>`+w.map(x=>`<div>${esc(x.id)} ${esc(x.name)} · ${x.dist_km} km ${esc(x.peilung)} · ${esc(x.wind)} · QNH ${x.qnh??"–"} · vor ${x.alter_min} min</div>`).join("")+`</details>`;
 h+=`<div class=mu style="margin-top:6px;font-size:12px">⚠ ${esc(r.hinweis)} Quelle: aviationweather.gov${r.abruf?" · Abruf "+esc(r.abruf):""}${r.aus_cache?" (Cache)":""}</div>`;
 el.innerHTML=h}catch(e){el.innerHTML=`<span class=err>⚠ METAR: ${esc(e.message)} – keine Daten angezeigt.</span>`}}
setInterval(()=>{if(!document.hidden)metarLoad()},600000);
'''

STATS_HTML = r'''<div class="card full" id=flcard style="display:none"><div class=row><div class=lbl style="flex:1" id=fltitle>✈ Flüge &amp; Wartung</div>
 <button style="flex:0 0 auto" onclick="$('flcard').style.display='none'">✕</button></div>
 <div class=mu>Ein Eintrag pro Akku-Pack. Leere Felder = „keine Angabe“ (wird nicht geschätzt). Dauer als mm:ss oder Minuten.</div>
 <div class=row><input id=fl_start placeholder="Start HH:MM" style="flex:0 0 105px"><input id=fl_dauer placeholder="Dauer z. B. 3:45" style="flex:0 0 130px">
 <select id=fl_quelle style="flex:0 0 130px"><option value="">Zeitquelle?</option><option>Stoppuhr</option><option>OSD</option><option>Blackbox</option><option>Funke-Timer</option><option>Erinnerung</option></select>
 <input id=fl_akku list=dl_akku placeholder="Akku-ID (A1 …)" style="flex:0 0 130px"><input id=fl_drohne list=dl_drohne placeholder="Drohne / Setup">
 <select id=fl_erg style="flex:0 0 110px"><option value="">Ergebnis?</option><option value=ok>✅ ok</option><option value=crash>💥 Crash</option></select></div>
 <div class=row><input id=fl_notiz placeholder="Notiz zum Flug (optional)" onkeydown="if(event.key=='Enter')flAdd()"><button class=ok style="flex:0 0 auto" onclick="flAdd()">➕ Flug eintragen</button></div>
 <div id=fllist class=tw></div>
 <div class=lbl style="margin-top:10px">🔧 Wartung / Reparatur</div>
 <div class=row><input id=wa_teil list=dl_teil placeholder="Teil / Arbeit (Props, Arm, Motor …)"><input id=wa_anz placeholder="Anz." style="flex:0 0 60px" inputmode=numeric>
 <input id=wa_drohne list=dl_drohne placeholder="Drohne" style="flex:0 0 150px"><input id=wa_kosten placeholder="Kosten € (opt.)" style="flex:0 0 120px" inputmode=decimal></div>
 <div class=row><input id=wa_notiz placeholder="Notiz (optional)" onkeydown="if(event.key=='Enter')waAdd()"><button class=ok style="flex:0 0 auto" onclick="waAdd()">➕ Wartung eintragen</button></div>
 <div id=walist class=tw></div><div id=flmsg class=mu></div>
 <datalist id=dl_akku></datalist><datalist id=dl_drohne></datalist><datalist id=dl_teil><option>Props</option><option>Arm</option><option>Motor</option><option>Kamera</option><option>Antenne</option><option>VTX</option><option>FC/ESC</option><option>Rahmen</option><option>Akku-Stecker</option><option>GoPro-Halter</option></datalist></div>
<div class="card full" id=stcard><div class=row><div class=lbl style="flex:1">📊 Flugstatistik</div>
 <input id=st_von type=date title="von" style="flex:0 0 150px"><input id=st_bis type=date title="bis" style="flex:0 0 150px">
 <select id=st_spot style="flex:0 0 150px"><option value="">alle Spots</option></select><select id=st_drohne style="flex:0 0 150px"><option value="">alle Drohnen</option></select>
 <button class=pri style="flex:0 0 auto" onclick="stLoad()">📊 Berechnen</button><button style="flex:0 0 auto" onclick="stExp('csv')">⬇ CSV</button>
 <button style="flex:0 0 auto" onclick="stExp('druck')">🖨 Druck</button></div>
 <div id=stbody class=mu>„📊 Berechnen“ wertet alle Flugtage, Flüge und Wartungen im Logbuch neu aus.</div></div>'''

STATS_JS = r'''
let FLO=null,ST=null;const KA="keine Angabe";
const dur=s=>{if(!s)return KA;s=Math.round(s);const h=Math.floor(s/3600),m=Math.floor(s%3600/60),x=s%60;return h?`${h} h ${String(m).padStart(2,"0")} min`:`${m}:${String(x).padStart(2,"0")} min`};
const dq=s=>s==null?"":String(s).replace(/'/g,"&#39;");
async function flOpen(o){FLO=o||null;const c=$("flcard");c.style.display="";c.scrollIntoView({behavior:"smooth"});await flLoad()}
async function flLoad(){try{const r=await api("/api/fluege"+(FLO?"?ordner="+encodeURIComponent(FLO):""));FLO=r.ordner;const d=r.flugtag;
 $("fltitle").textContent=`✈ Flüge & Wartung – ${d.datum} · ${d.spot.name}${d.status=="offen"?" (läuft)":" (nachträglich)"}`;
 $("dl_akku").innerHTML=r.akkus.map(a=>`<option value="${dq(a.id)}">${esc(a.label)}</option>`).join("");
 $("dl_drohne").innerHTML=r.drohnen.map(x=>`<option value="${dq(x)}">`).join("");
 const E={ok:"✅ ok",crash:"💥 Crash"};
 $("fllist").innerHTML=r.fluege.length?`<table><tr><th>#</th><th>Start</th><th>Dauer</th><th>Akku</th><th>Drohne</th><th>Ergebnis</th><th>Notiz</th><th></th></tr>`+r.fluege.map((x,i)=>`<tr><td>${i+1}</td><td>${esc(x.start||"–")}</td><td>${dur(x.dauer_s)}${x.quelle?` <span class=mu>(${esc(x.quelle)})</span>`:""}</td><td>${esc(x.akku||KA)}</td><td>${esc(x.drohne||KA)}</td><td>${E[x.ergebnis]||KA}</td><td class=mu>${esc(x.notiz||"")}</td><td><button style="min-height:28px;padding:2px 8px" title="Eintrag stornieren (bleibt in der Datei erhalten)" onclick="flStorno('flug','${x.id}')">↩</button></td></tr>`).join("")+`</table><div class=mu>${r.fluege.length} Flug/Flüge · Summe ${dur(r.fluege.reduce((a,x)=>a+(x.dauer_s||0),0))}</div>`:`<div class=mu>Noch keine Flüge eingetragen.</div>`;
 $("walist").innerHTML=r.wartung.length?`<table><tr><th>Datum</th><th>Teil</th><th>Anz.</th><th>Drohne</th><th>Kosten</th><th>Notiz</th><th></th></tr>`+r.wartung.map(w=>`<tr><td>${esc(w.datum||"")}</td><td>${esc(w.teil)}</td><td>${w.anzahl||1}</td><td>${esc(w.drohne||KA)}</td><td>${w.kosten!=null?w.kosten.toFixed(2).replace(".",",")+" €":KA}</td><td class=mu>${esc(w.notiz||"")}</td><td><button style="min-height:28px;padding:2px 8px" onclick="flStorno('wartung','${w.id}')">↩</button></td></tr>`).join("")+"</table>":`<div class=mu>Keine Wartung an diesem Tag.</div>`;
 $("flmsg").textContent="Ordner: "+r.ordner}catch(e){$("fllist").innerHTML=`<span class=err>⚠ ${esc(e.message)}</span>`;$("walist").innerHTML=""}}
async function flAdd(){const g=k=>$("fl_"+k).value.trim();try{await api("/api/flug",{ordner:FLO,start:g("start"),dauer:g("dauer"),quelle:g("quelle"),akku:g("akku"),drohne:g("drohne"),ergebnis:g("erg"),notiz:g("notiz")});
 for(const k of["start","dauer","notiz","erg"])$("fl_"+k).value="";await flLoad();logSearch()}catch(e){alert(e.message)}}
async function waAdd(){const g=k=>$("wa_"+k).value.trim();try{await api("/api/wartung",{ordner:FLO,teil:g("teil"),anzahl:g("anz"),drohne:g("drohne"),kosten:g("kosten"),notiz:g("notiz")});
 for(const k of["teil","anz","kosten","notiz"])$("wa_"+k).value="";await flLoad();logSearch()}catch(e){alert(e.message)}}
async function flStorno(kind,id){if(!confirm("Eintrag stornieren? (Er bleibt als Storno in der Datei nachvollziehbar.)"))return;try{await api("/api/storno",{kind,id,ordner:FLO});await flLoad();logSearch()}catch(e){alert(e.message)}}
function stQ(){const p=new URLSearchParams();for(const k of["von","bis","spot","drohne"]){const v=$("st_"+k).value;if(v)p.set(k,v)}return p.toString()}
function stExp(a){window.open((a=="csv"?"/api/statistik.csv?":"/druck/statistik?")+stQ(),"_blank")}
function bars(items,val,lab,col,fmt){if(!items.length)return `<div class=mu>${KA}</div>`;const W=Math.max(320,items.length*46),H=150,B=30,mx=Math.max(1,...items.map(val)),bw=Math.min(36,(W-10)/items.length-8);
 return `<svg viewBox="0 0 ${W} ${H}" style="width:100%;max-width:${W}px;height:${H}px">`+items.map((it,i)=>{const v=val(it),h=(H-B-16)*v/mx,x=8+i*(W-10)/items.length;
 return `<rect x=${x} y=${H-B-h} width=${bw} height=${h} rx=3 fill="${typeof col=="function"?col(it):col}"/><text x=${x+bw/2} y=${H-B-h-4} fill="#e6edf3" font-size=10 text-anchor=middle>${fmt?fmt(v):v}</text><text x=${x+bw/2} y=${H-B+13} fill="#8b949e" font-size=9 text-anchor=middle>${esc(lab(it))}</text>`}).join("")+"</svg>"}
function line(pts){if(pts.length<2)return `<div class=mu>${pts.length?"Erst 1 Flug mit Dauer – Verlauf ab 2 Flügen.":KA}</div>`;const W=520,H=150,L=40,R=8,T=10,B=20,mx=Math.max(...pts.map(p=>p.dauer_s))*1.1,
 x=i=>L+(W-L-R)*i/(pts.length-1),y=v=>T+(H-T-B)*(1-v/mx);let s=`<svg viewBox="0 0 ${W} ${H}" style="width:100%;height:${H}px">`;
 for(const v of[mx/2,mx/1.1])s+=`<line x1=${L} x2=${W-R} y1=${y(v)} y2=${y(v)} stroke="#30363d"/><text x=${L-4} y=${y(v)+3} fill="#8b949e" font-size=9 text-anchor=end>${dur(v).replace(" min","")}</text>`;
 s+=pts.map((p,i)=>`<circle cx=${x(i)} cy=${y(p.dauer_s)} r=2.5 fill="#8b949e"><title>${p.datum} · ${dur(p.dauer_s)} · ${esc(p.drohne)}</title></circle>`).join("");
 s+=`<polyline fill=none stroke="#2f81f7" stroke-width=2.5 points="${pts.map((p,i)=>x(i)+","+y(p.gleitend_s)).join(" ")}"/>`;
 return s+`<text x=${L} y=${H-5} fill="#8b949e" font-size=9>${pts[0].datum}</text><text x=${W-R} y=${H-5} fill="#8b949e" font-size=9 text-anchor=end>${pts[pts.length-1].datum}</text><text x=290 y=${H-5} fill="#8b949e" font-size=9 text-anchor=middle>● Einzelflug  — gleitender Ø (5 Flüge)</text></svg>`}
function tbl(h,rows){return rows.length?`<div class=tw><table><tr>${h.map(x=>`<th>${x}</th>`).join("")}</tr>${rows.map(r=>`<tr>${r.map(c=>`<td>${c}</td>`).join("")}</tr>`).join("")}</table></div>`:`<div class=mu>${KA}</div>`}
async function stLoad(){$("stbody").textContent="Berechne aus den Logbuch-Dateien …";try{const s=await api("/api/statistik?"+stQ());ST=s;const u=s.summen,w=s.wetter;
 const keep=(id,list,all)=>{const v=$(id).value;$(id).innerHTML=`<option value="">${all}</option>`+list.map(x=>`<option${x==v?" selected":""}>${esc(x)}</option>`).join("")};
 keep("st_spot",s.spot_liste,"alle Spots");keep("st_drohne",s.drohnen_liste,"alle Drohnen");
 const T=(l,v,sub)=>`<div class=tile><div class=u>${l}</div><div class=v style="font-size:22px">${v}</div><div class=u>${sub||"&nbsp;"}</div></div>`;
 const AC={gruen:"#3fb950",gelb:"#d29922",rot:"#f85149"},AN={gruen:"🟢 grün",gelb:"🟡 gelb",rot:"🔴 rot"},na=Object.values(w.ampel).reduce((a,b)=>a+b,0)||1;
 let h=`<div class=tiles>${T("Flugtage",u.flugtage,u.flugtage_ohne_fluege?u.flugtage_ohne_fluege+" ohne Flug-Einträge":"")}${T("Flüge",u.fluege,u.fluege_ohne_dauer?u.fluege_ohne_dauer+" ohne Dauer":"")}
  ${T("Flugzeit",u.flugzeit_s?dur(u.flugzeit_s):KA,"nur erfasste Dauern")}${T("Ø pro Flug",u.avg_s?dur(u.avg_s):KA)}${T("Crashes",u.crashes,u.ohne_ergebnis?u.ohne_ergebnis+" ohne Ergebnis":"")}
  ${T("Reparaturen",u.reparaturen,u.kosten!=null?u.kosten.toFixed(2).replace(".",",")+" €"+(u.kosten_ohne_angabe?" (+"+u.kosten_ohne_angabe+" o. A.)":""):"Kosten: "+KA)}</div>
  <div class=mu style="margin:6px 0">${esc(s.hinweis)} · Wochen-Serie: beste ${s.serie.beste}, aktuell ${s.serie.aktuell}${s.rekorde.laengster_flug?` · Längster Flug ${dur(s.rekorde.laengster_flug.dauer_s)} (${s.rekorde.laengster_flug.datum}, ${esc(s.rekorde.laengster_flug.spot)})`:""}${s.rekorde.meiste_packs?` · Meiste Packs: ${s.rekorde.meiste_packs.anzahl} am ${s.rekorde.meiste_packs.datum}`:""}</div>
  <div class=grid><div><div class=lbl>Flugtage pro Monat</div>${bars(s.monate,m=>m.flugtage,m=>m.label,"#2f81f7")}</div>
  <div><div class=lbl>Flugzeit pro Monat (min)</div>${bars(s.monate,m=>Math.round(m.flugzeit_s/60),m=>m.label,"#a371f7")}</div>
  <div><div class=lbl>Wetter-Ampel der Flugtage (Tagesstart)</div><div style="display:flex;height:22px;border-radius:6px;overflow:hidden;margin:8px 0">${Object.entries(w.ampel).filter(e=>e[1]).map(([k,v])=>`<div title="${AN[k]||k}: ${v}" style="flex:${v};background:${AC[k]||"#484f58"}"></div>`).join("")}</div>
   <div class=mu>${Object.entries(w.ampel).map(([k,v])=>`${AN[k]||"⚪ "+k}: ${v} (${Math.round(100*v/na)} %)`).join(" · ")}</div>
   <div class=lbl style="margin-top:8px">Wind beim Start (m/s) → Flugtage</div>${bars(Object.entries(w.wind_hist).map(([k,v])=>({k,v})),e=>e.v,e=>e.k,e=>e.k==KA?"#484f58":"#f0883e")}
   <div class=mu>Verlauf: Ø Wind ${w.wind_avg??KA} m/s · max Böe ${w.boeen_max??KA} m/s · Temperatur ${w.temp_min??KA} … ${w.temp_max??KA} °C (${w.messpunkte} Messpunkte, Open-Meteo)</div></div>
  <div><div class=lbl>Entwicklung Flugzeit pro Flug</div>${line(s.entwicklung)}<div class=lbl style="margin-top:6px">Ø-Flugzeit je Monat</div>${bars(s.monat_avg.filter(m=>m.avg_s),m=>Math.round(m.avg_s),m=>m.label,"#3fb950",v=>dur(v).replace(" min",""))}</div></div>
  <div class=lbl style="margin-top:10px">🏆 Häufigste Spots</div>${tbl(["Spot","Flugtage","Flüge","Flugzeit","Crashes","zuletzt"],s.spots.map(x=>[`<b>${esc(x.spot)}</b>`,x.flugtage,x.fluege,x.flugzeit_s?dur(x.flugzeit_s):KA,x.crashes,x.zuletzt]))}
  <div class=lbl style="margin-top:10px">🛸 Drohnen</div>${tbl(["Drohne","Flüge","Flugzeit","ohne Dauer","Crashes","Flüge seit Crash","Reparaturen","zuletzt"],s.drohnen.map(x=>[esc(x.drohne),x.fluege,x.flugzeit_s?dur(x.flugzeit_s):KA,x.ohne_dauer,x.crashes,x.seit_crash==null?"–":x.seit_crash,x.reparaturen,x.zuletzt||"–"]))}
  <div class=lbl style="margin-top:10px">🔋 Akkus</div>${s.akku_fehler?`<div class=err>⚠ ${esc(s.akku_fehler)}</div>`:""}${tbl(["Akku","Zyklen (Flüge)","Flugzeit","Ø Flug","zuletzt","Hinweis"],s.akkus.map(x=>[esc(x.label)+(x.ausgemustert?" <span class=mu>(ausgemustert)</span>":"")+(x.im_register?"":` <button style="min-height:26px;padding:1px 6px" onclick="akReg('${dq(x.akku)}')">➕ Register</button>`),x.zyklen,x.flugzeit_s?dur(x.flugzeit_s):KA,x.avg_s?dur(x.avg_s):KA,x.zuletzt||"–",x.hinweis?`<span class=${x.hinweis.startsWith("Flugzeit")?"warn":"mu"}>${esc(x.hinweis)}</span>`:""]))}
  ${u.ohne_akku?`<div class=mu>${u.ohne_akku} Flug/Flüge ohne Akku-Angabe.</div>`:""}
  <div class=row><input id=ak_id placeholder="Akku-ID" style="flex:0 0 110px"><input id=ak_z placeholder="Zellen S" style="flex:0 0 80px" inputmode=numeric><input id=ak_mah placeholder="mAh" style="flex:0 0 80px" inputmode=numeric>
  <input id=ak_name placeholder="Marke/Name"><input id=ak_kauf placeholder="Kauf JJJJ-MM-TT" style="flex:0 0 140px"><label class=mu style="flex:0 0 auto"><input type=checkbox id=ak_aus style="width:auto"> ausgemustert</label>
  <button class=ok style="flex:0 0 auto" onclick="akSave()">💾 Akku ins Register</button></div>
  <div class=lbl style="margin-top:10px">🔧 Crashes &amp; Reparaturen</div><div class=mu>${Object.keys(s.teile).length?"Teile-Verbrauch: "+Object.entries(s.teile).map(([k,v])=>`${esc(k)} ×${v}`).join(" · "):"Teile-Verbrauch: "+KA}</div>
  ${tbl(["Datum","Teil","Anz.","Drohne","Kosten","Spot","Notiz"],s.wartung.map(x=>[x._datum,esc(x.teil),x.anzahl||1,esc(x.drohne||KA),x.kosten!=null?x.kosten.toFixed(2).replace(".",",")+" €":KA,esc(x._spot),esc(x.notiz||"")]))}
  <div class=mu style="margin-top:6px">Stand ${esc(s.erstellt)}</div>`;$("stbody").className="";$("stbody").innerHTML=h}catch(e){$("stbody").innerHTML=`<span class=err>⚠ ${esc(e.message)}</span>`}}
function akReg(id){$("ak_id").value=id;$("ak_z").focus()}
async function akSave(){const g=k=>$("ak_"+k).value.trim();try{await api("/api/akku",{id:g("id"),zellen:g("z"),mah:g("mah"),name:g("name"),kaufdatum:g("kauf"),ausgemustert:$("ak_aus").checked});stLoad()}catch(e){alert(e.message)}}
'''

PAGE = """<!doctype html><html lang=de><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta name=theme-color content="#0b0f14">
<title>FPV-Lagezentrum</title><style>__CSS__</style></head><body>
<div class=row style="align-items:flex-end"><div style="flex:3 1 260px"><h1>🛸 FPV-Lagezentrum</h1>
<div class=sub id=sub>Wetter-Ampel · Flugradar · Spots · Preflight-Check</div></div>
<select id=spotsel onchange="setActive(this.value)" style="flex:1 1 160px"></select>
<button class=pri style="flex:0 0 auto" onclick="loadAll(1)">🔄 Aktualisieren</button>
<button style="flex:0 0 auto" onclick="location.href='/karte'">🗺 Karte</button></div>
<div class=grid>
<div class=card><div class=lbl>📍 Standort / Spots</div>
 <div class=row><input id=q placeholder="Ort suchen, z. B. Hannover" onkeydown="if(event.key=='Enter')geo()"><button style="flex:0 0 auto" onclick="geo()">🔎 Suchen</button></div>
 <select id=hits onchange="pickHit()" style="display:none"></select>
 <div class=row><input id=sname placeholder="Spot-Name (Haus, Field …)"></div>
 <div class=row><input id=slat placeholder="Breite (lat)" inputmode=decimal><input id=slon placeholder="Länge (lon)" inputmode=decimal></div>
 <div class=row><button class=ok onclick="saveSpot()">💾 Spot speichern</button><button class=stop onclick="delSpot()">🗑 Löschen</button>
 <button onclick="here()">📱 Mein Standort</button></div>
 <div class=row><button onclick="profOpen()">🗂 Spot-Profil</button><button class=pri onclick="heute()">🏆 Wo fliege ich heute?</button></div>
 <div id=spotmsg class=mu></div></div>
<div class=card><div class=lbl>🚦 Flug-Ampel</div><div class=amp id=amp>⚪ …</div><div class=bar id=bar></div>
 <div id=reasons></div><div class=mu id=sun style="margin-top:6px"></div>
 <div class=mu style="margin-top:6px">Nur Wetter-Orientierung. Maßgeblich für Geozonen &amp; Regeln sind dipul/DFS und LBA.</div></div>
<div class="card full"><div class=row><div class=lbl style="flex:1">🌤 Wetter am Spot</div><div class=mu id=wmeta style="text-align:right"></div></div>
 <div class=tiles>
  <div class=tile><svg width=70 height=70 viewBox="-50 -50 100 100"><circle r=44 fill=none stroke="#30363d" stroke-width=3 />
   <text y=-30 fill="#8b949e" font-size=13 text-anchor=middle font-weight=bold>N</text><text y=40 fill="#8b949e" font-size=13 text-anchor=middle>S</text>
   <g id=arrow><line y1=26 y2=-20 stroke="#2f81f7" stroke-width=7 /><polygon points="0,-34 -12,-14 12,-14" fill="#2f81f7"/></g></svg>
   <div class=u id=dirtxt>–</div></div>
  <div class=tile><div class=u>Wind</div><div class=v id=t_wind>–</div><div class=u>m/s</div></div>
  <div class=tile><div class=u>Böen</div><div class=v id=t_gust>–</div><div class=u>m/s</div></div>
  <div class=tile><div class=u>Temperatur</div><div class=v id=t_temp>–</div><div class=u id=t_feel>°C</div></div>
  <div class=tile><div class=u>Regen</div><div class=v id=t_rain>–</div><div class=u>mm</div></div>
  <div class=tile><div class=u>Sicht</div><div class=v id=t_vis>–</div><div class=u>km</div></div>
 </div><div id=wline class=mu style="margin-top:6px"></div><div class=hours id=hours></div>
 <div id=wlight style="margin-top:8px;font-weight:600"></div><div id=wlight2 class=mu style="font-size:12px"></div></div>
<div class="card full"><div class=row><div class=lbl style="flex:1">✈ Flugradar (OpenSky)</div>
 <label class=mu style="flex:0 0 auto"><input type=checkbox id=auto style="width:auto" onchange="saveAuto()"> Auto (60 s)</label>
 <button style="flex:0 0 auto" onclick="radar(1)">🔄 Radar</button></div><div class=mu id=rmeta></div>
 <div class=tw><table><thead><tr><th>Rufzeichen</th><th>Distanz</th><th>Peilung</th><th>Höhe</th><th>Tempo</th><th>Kurs</th><th>Steigen</th><th>Herkunft</th><th>Hinweis</th></tr></thead>
 <tbody id=rbody></tbody></table></div>
 <div class=mu style="margin-top:6px">Daten: The OpenSky Network – nur Luftfahrzeuge mit Transponder/ADS-B. Hubschrauber, Segler &amp; Drohnen fehlen oft. Augen auf!</div></div>
<div class=card><div class=lbl>✅ Preflight-Checkliste</div><div class=bar><div id=ckbar style="height:8px;border-radius:4px;background:var(--ok);width:0"></div></div>
 <div id=cklbl style="font-weight:700"></div><div class=ck id=ck></div>
 <div class=row><input id=cknew placeholder="Eigener Punkt …" onkeydown="if(event.key=='Enter')ckAdd()"><button style="flex:0 0 auto" onclick="ckAdd()">➕</button>
 <button style="flex:0 0 auto" onclick="ckReset()">↺ Zurücksetzen</button>
 <a href="/druck/checkliste" target=_blank style="flex:0 0 auto"><button>🖨 Drucken</button></a></div></div>
<div>
 <div class=card><div class=lbl>🗺 dipul / EASA – Hinweis</div>
  <div>Ob und wie du an diesem Spot fliegen darfst (Geozonen, Kontrollzonen, Naturschutz, Wohngebiete …), zeigt verbindlich nur die
  offizielle Karte der DFS auf dipul. Unten steht nur ein <b>Hinweis</b> aus den dipul-Geodaten – keine Prüfung, keine Rechtsberatung. Offene Kategorie: max. 120 m,
  Sichtflug (bei FPV mit Spotter), EU-Kompetenznachweis &amp; e-ID beachten.</div>
  <div class=row style="margin-top:8px"><a id=dipul target=_blank rel=noopener><button class=pri style="width:100%">🗺 dipul-Karte am Spot</button></a>
  <a href="https://www.dipul.de/homepage/de/" target=_blank rel=noopener>dipul.de</a>
  <a href="https://www.openaip.net/map" target=_blank rel=noopener>OpenAIP</a>
  <button style="flex:0 0 auto" onclick="dzLoad(1)">🔄 Geozonen prüfen</button></div>
  <div id=dz class=mu style="margin-top:8px">Geozonen-Hinweis: wird geladen …</div>
  <div id=dzsrc class=mu style="margin-top:4px;font-size:12px"></div></div>
__METARHTML__
 <div class=card><div class=lbl>📄 NOTAM: folgt</div><div class=mu id=notam></div></div>
 <div class=card><div class=lbl>⚙ Grenzwerte (Ampel)</div><div id=th class=row></div>
  <button class=ok onclick="saveTh()">💾 Grenzwerte speichern</button></div>
</div>
<div class="card full" id=heutecard style="display:none"><div class=row><div class=lbl style="flex:1">🏆 Wo fliege ich heute?</div>
 <select id=hsort onchange="heute()" style="flex:0 0 170px"><option value=kombi>Ampel + Nähe</option><option value=distanz>Entfernung</option>
 <option value=wetter>Wetter</option><option value=bewertung>Bewertung</option><option value=zuletzt>Zuletzt geflogen</option></select>
 <label class=mu style="flex:0 0 auto"><input type=checkbox id=hgps style="width:auto" onchange="heute()"> ab Gerätestandort</label>
 <button style="flex:0 0 auto" onclick="heute(1)">🔄</button></div><div class=mu id=hmeta></div><div id=hlist></div></div>
<div class="card full" id=profcard style="display:none"><div class=row><div class=lbl style="flex:1" id=proftitle>🗂 Spot-Profil</div>
 <button style="flex:0 0 auto" onclick="$('profcard').style.display='none'">✕</button></div><div id=prof></div>
 <div class=row><button class=ok onclick="profSave()">💾 Profil speichern</button><span id=profmsg class=mu></span></div></div>
<div class="card full"><div class=lbl>📒 Flugtag &amp; Logbuch</div>
 <div class=grid>
 <div><div id=fdstat style="font-weight:700">…</div>
  <div class=row style="margin-top:6px"><button class=ok id=fdstart onclick="fdStart()">▶ Flugtag starten</button>
  <button class=stop id=fdend onclick="fdEnd()">■ Flugtag beenden</button><button onclick="openDir(FD&&FD.ordner)">📂 Ordner öffnen</button>
  <button class=pri id=fdfl onclick="flOpen(null)">✈ Flüge &amp; Wartung</button></div>
  <div class=row><input id=note placeholder="Notiz zu Bedingungen …" onkeydown="if(event.key=='Enter')fdNote()">
  <select id=ntag style="flex:0 0 110px"><option value="">– Tag –</option><option>böig</option><option>thermisch</option><option>nass</option>
  <option>Störungen</option><option>voll</option><option>perfekt</option><option>Crash</option></select>
  <button style="flex:0 0 auto" onclick="fdNote()">➕ Notiz</button></div>
  <svg id=chart viewBox="0 0 520 130" style="width:100%;height:130px;background:var(--bg);border:1px solid var(--bd);border-radius:10px"></svg>
  <div class=mu id=fdnotes></div></div>
 <div><div class=row><input id=ls placeholder="Logbuch durchsuchen: Datum, Spot, Region, Notiz …" onkeydown="if(event.key=='Enter')logSearch()">
  <button style="flex:0 0 auto" onclick="logSearch()">🔎</button><button style="flex:0 0 auto" onclick="reindex()">↻ Index</button></div>
  <div id=lbl class=tw style="max-height:260px;overflow-y:auto"></div><div class=mu id=lbpath></div></div>
 </div></div>
__STATSHTML__
</div>
<div class=mu style="margin:10px 0">Daten: Open-Meteo (CC BY 4.0) · OpenSky Network · läuft lokal auf diesem Rechner</div>
<script>
const $=id=>document.getElementById(id);let S={},HITS=[],timer=null;
const TH=[["wind_warn","Wind gelb ab (m/s)"],["wind_max","Wind rot ab (m/s)"],["gust_warn","Böen gelb ab (m/s)"],["gust_max","Böen rot ab (m/s)"],
["precip_max","Regen rot ab (mm)"],["vis_min","Sicht rot unter (m)"],["temp_min","Kalt (gelb) unter (°C)"]];
const MOT=["Jeder Pro-Pilot hat mal mit Gras im Prop angefangen. 🌱","Ein Akku mehr geht immer. 🔋","Smooth is fast. 🏁","Tief fliegen, hoch motiviert. 🚀","Checkliste fertig = entspannter Flug. 😎"];
const f=(v,n=1)=>v==null?"–":Number(v).toFixed(n);
const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function api(p,b){const r=await fetch(p,b?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}:{});
 const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
function spot(){return (S.spots||[]).find(s=>s.name==S.active)||(S.spots||[])[0]}
function renderState(){const sel=$("spotsel");sel.innerHTML=(S.spots||[]).map(s=>`<option ${s.name==S.active?"selected":""}>${esc(s.name)}</option>`).join("")||"<option>– kein Spot –</option>";
 const sp=spot();if(sp){$("sname").value=sp.name;$("slat").value=sp.lat;$("slon").value=sp.lon;$("spotmsg").textContent=`Aktiv: ${sp.name} (${f(sp.lat,5)}, ${f(sp.lon,5)})`;$("spotmsg").className="mu";
  opsSet("spot","📍 "+sp.name)}
 else{$("spotmsg").textContent="⚠ Bitte Standort setzen: Ort suchen oder Koordinaten eintragen, dann „Spot speichern“.";$("spotmsg").className="warn"}
 $("dipul").href=S.dipul_url;$("notam").textContent=S.notam;$("auto").checked=!!S.radar_auto;
 $("th").innerHTML=TH.map(([k,l])=>`<label class=mu style="flex:1 1 45%">${l}<input id=th_${k} value="${S.thresholds[k]}" inputmode=decimal></label>`).join("");
 renderCk()}
function renderCk(){const it=S.checklist||[],d=it.filter(x=>x.done).length;
 $("ck").innerHTML=it.map((x,i)=>`<label><input type=checkbox ${x.done?"checked":""} onchange="ckT(${i},this.checked)"><span>${esc(x.text)}</span><button class=x onclick="event.preventDefault();ckDel(${i})">✕</button></label>`).join("");
 $("ckbar").style.width=(it.length?100*d/it.length:0)+"%";
 $("cklbl").innerHTML=it.length&&d==it.length?`<span class=ok>🚀 ${d}/${it.length} – Bereit zum Abheben! Viel Spaß &amp; sauber landen.</span>`:`${d}/${it.length} erledigt · ${MOT[Math.floor(Math.random()*MOT.length)]}`;
 if((S.gefahren||[]).length)$("ck").innerHTML+=`<div class=mu style="margin-top:6px">Gefahrenstellen aus dem Spot-Profil:</div>`+S.gefahren.map(g=>`<div class=hz>${esc(g)}</div>`).join("")}
async function saveCk(){try{S=await api("/api/checklist",{items:S.checklist});renderCk()}catch(e){alert(e.message)}}
function ckT(i,v){S.checklist[i].done=v;saveCk()} function ckDel(i){S.checklist.splice(i,1);saveCk()}
function ckAdd(){const t=$("cknew").value.trim();if(t){S.checklist.push({text:t,done:false});$("cknew").value="";saveCk()}}
function ckReset(){S.checklist.forEach(x=>x.done=false);saveCk()}
async function geo(){const q=$("q").value.trim();if(q.length<2)return;$("spotmsg").textContent="Suche …";
 try{HITS=(await api("/api/geocode?q="+encodeURIComponent(q))).treffer;const h=$("hits");
  if(!HITS.length){$("spotmsg").textContent="Nichts gefunden.";h.style.display="none";return}
  h.innerHTML=HITS.map((x,i)=>`<option value=${i}>${esc(x.label)}</option>`).join("");h.style.display="";pickHit()}catch(e){$("spotmsg").textContent="Suche fehlgeschlagen: "+e.message}}
function pickHit(){const x=HITS[$("hits").value||0];if(!x)return;$("sname").value=x.name;$("slat").value=x.lat.toFixed(5);$("slon").value=x.lon.toFixed(5);
 HITREG=x;$("spotmsg").textContent=`Gefunden: ${x.label} – mit „Spot speichern“ übernehmen.`;$("spotmsg").className="ok"}
function here(){if(!navigator.geolocation){alert("Standort im Browser nicht verfügbar.");return}
 navigator.geolocation.getCurrentPosition(p=>{$("slat").value=p.coords.latitude.toFixed(5);$("slon").value=p.coords.longitude.toFixed(5);
 $("spotmsg").textContent="Gerätestandort übernommen – Namen eintragen und speichern."},e=>alert("Kein Standort: "+e.message))}
async function saveSpot(){try{const la=parseFloat(String($("slat").value).replace(",",".")),lo=parseFloat(String($("slon").value).replace(",","."));
 const reg=HITREG&&Math.abs(HITREG.lat-la)<0.01&&Math.abs(HITREG.lon-lo)<0.01?HITREG.label:null;
 S=await api("/api/spot",{name:$("sname").value,lat:$("slat").value,lon:$("slon").value,region:reg});renderState();loadAll(1)}catch(e){$("spotmsg").textContent="Fehler: "+e.message;$("spotmsg").className="err"}}
async function delSpot(){const sp=spot();if(sp&&confirm(`Spot „${sp.name}“ wirklich entfernen?`)){S=await api("/api/spot/delete",{name:sp.name});renderState();loadAll()}}
async function setActive(n){S=await api("/api/active",{name:n});renderState();loadAll()}
async function saveTh(){const t={};for(const[k]of TH)t[k]=$("th_"+k).value;try{S=await api("/api/thresholds",t);renderState();weather()}catch(e){alert(e.message)}}
async function saveAuto(){S=await api("/api/auto",{on:$("auto").checked});sched()}
function amp(a){const c={gruen:"var(--ok)",gelb:"var(--warn)",rot:"var(--err)"}[a?.stufe]||"var(--mu)",d={gruen:"🟢",gelb:"🟡",rot:"🔴"}[a?.stufe]||"⚪";
 $("amp").textContent=`${d} ${a?.titel||"Kein Standort"}`;$("amp").style.color=c;$("bar").style.background=c;
 $("reasons").innerHTML=(a?.gruende||["Bitte zuerst einen Standort setzen."]).map(r=>"• "+esc(r)).join("<br>");opsSet("ampel",`${d} ${a?.titel||"Kein Standort"}`)}
function col(v,w,m){return v>=m?"err":v>=w?"warn":"ok"}
async function weather(force){if(!spot()){amp(null);return}$("wmeta").textContent="lade Wetter …";
 try{const r=await api("/api/weather"+(force?"?force=1":"")),w=r.wetter,t=S.thresholds;amp(r.ampel);
  $("t_wind").textContent=f(w.wind);$("t_wind").className="v "+col(w.wind,t.wind_warn,t.wind_max);
  $("t_gust").textContent=f(w.boeen);$("t_gust").className="v "+col(w.boeen,t.gust_warn,t.gust_max);
  $("t_temp").textContent=f(w.temp);$("t_feel").textContent=`°C · gefühlt ${f(w.gefuehlt,0)}`;$("t_rain").textContent=f(w.regen);
  $("t_vis").textContent=w.sicht==null?"–":f(w.sicht/1000);$("arrow").style.transform=`rotate(${(w.richtung+180)%360}deg)`;
  $("dirtxt").textContent=`aus ${w.richtung_txt} (${f(w.richtung,0)}°)`;
  $("wline").textContent=`${w.wetter} · Wolken ${f(w.wolken,0)} % · Luftfeuchte ${f(w.feuchte,0)} % · Höhe ${f(w.hoehe,0)} m`;
  $("wmeta").textContent=`Open-Meteo · Messung ${w.messzeit} · Abruf ${w.abruf}`;
  $("sun").textContent=(w.sonnenaufgang?`🌅 Aufgang ${w.sonnenaufgang}   `:"")+(w.sonnenuntergang?`🌇 Untergang ${w.sonnenuntergang}   `:"")+(r.ampel.licht&&r.ampel.licht.daemmerung_ende?`🌆 dunkel ab ${r.ampel.licht.daemmerung_ende}`:"");
  $("hours").innerHTML=w.stunden.slice(0,8).map(h=>`<div><b class=mu>${h.zeit}</b><br><b class=${col(h.boeen,t.gust_warn,t.gust_max)}>${f(h.wind,0)}/${f(h.boeen,0)}</b> m/s<br><span class=mu>${f(h.temp,0)}° · ☔${f(h.regen_pct,0)}%</span></div>`).join("")
 }catch(e){$("wmeta").innerHTML=`<span class=err>⚠ Wetter: ${esc(e.message)}</span>`;amp({stufe:null,titel:"Keine Bewertung",gruende:["Wetter nicht verfügbar: "+e.message]})}}
async function radar(force){sched();if(!spot()){$("rmeta").textContent="Bitte Standort setzen.";return}$("rmeta").textContent="frage OpenSky …";
 try{const r=await api("/api/radar"+(force?"?force=1":"")),p=r.flugzeuge;
  $("rmeta").innerHTML=r.fehler?`<span class=warn>⚠ ${esc(r.fehler)}</span>`:`${p.length} Luftfahrzeuge · Box ±${r.box}° · Abruf ${r.abruf||"–"}${r.aus_cache?" (Cache)":""}${r.rest!=null?" · Kontingent übrig: "+r.rest:""}`;
  $("rbody").innerHTML=p.length?p.slice(0,60).map(a=>{const c=a.hinweis=="TIEF & NAH"?"err":a.hinweis=="tief"?"warn":"";
   return `<tr class=${c}><td><b>${esc(a.rufzeichen)}</b></td><td>${f(a.dist_km)} km</td><td>${a.peilung}</td><td>${a.boden?"Boden":f(a.hoehe_m,0)+" m"}</td><td>${f(a.speed_kmh,0)} km/h</td><td>${f(a.kurs,0)}°</td><td>${f(a.steig)} m/s</td><td>${esc(a.land)}</td><td>${a.hinweis}</td></tr>`}).join("")
   :`<tr><td colspan=9 class=mu style="white-space:normal">${r.fehler?esc(r.fehler):`Gerade keine Flugzeuge mit Transponder in der Nähe (±${r.box}° ≈ ${Math.round(r.box*111)} km). Das ist gut – oder OpenSky hat hier wenig Empfänger. Trotzdem: Himmel beobachten!`}</td></tr>`
 }catch(e){$("rmeta").innerHTML=`<span class=err>⚠ ${esc(e.message)}</span>`}}
function sched(){clearTimeout(timer);if(S.radar_auto)timer=setTimeout(()=>{if(!document.hidden)radar();else sched()},(S.radar_interval||60)*1000)}
async function loadAll(force){S=await api("/api/state");renderState();weather(force);radar(force);metarLoad(force);lichtLoad();dzLoad(force)}
async function dzLoad(force){const el=$("dz"),src=$("dzsrc");if(!spot()){el.textContent="";src.textContent="";return}
 el.className="mu";el.textContent="🗺 Frage dipul-Geodaten am Spot ab …";
 try{const r=await api("/api/dipul"+(force?"?force=1":""));
  const f=z=>`${esc(z.art)}: ${esc(z.name)}${z.hoehe?` <span class=mu>(${esc(z.hoehe)})</span>`:""}`;
  if(r.am_spot==null){el.className="err";el.textContent="⚠ "+(r.fehler||"keine Daten");src.textContent=r.hinweis||"";return}
  const hart=r.am_spot.filter(z=>!z.info_only);el.className=hart.length||r.fehler?"warn":"";
  el.innerHTML=(r.fehler?`<div class=err>⚠ ${esc(r.fehler)}</div>`:"")+
   (r.am_spot.length?`<b>Am Spot laut dipul-Daten:</b><br>${r.am_spot.map(z=>"• "+f(z)).join("<br>")}`:"<b>Am Spot:</b> kein geografisches Gebiet in den dipul-Daten gefunden.")+
   (r.umkreis.length?`<br><b>Im Umkreis ~${r.radius_m} m:</b><br><span class=mu>${r.umkreis.slice(0,12).map(z=>"• "+f(z)).join("<br>")}${r.umkreis.length>12?`<br>… und ${r.umkreis.length-12} weitere`:""}</span>`:"");
  src.innerHTML=`Quelle Geodaten: <a href="${esc(r.lizenz_url)}" target=_blank rel=noopener>${esc(r.quelle)}</a>${r.abruf?" · Abruf "+esc(r.abruf):""}${r.aus_cache?" (Cache)":""}<br>${esc(r.hinweis)}`}
 catch(e){el.className="err";el.textContent="⚠ dipul-Abfrage: "+e.message+" – bitte dipul-Karte nutzen."}}
const OPS={spot:"",ampel:"",licht:""};let LICHT=null;
function opsSet(k,v){OPS[k]=v;$("sub").textContent=[OPS.spot,OPS.ampel,OPS.licht].filter(x=>x).join("  │  ")}
async function lichtLoad(){if(!spot())return;try{const l=await api("/api/licht");LICHT=l;
 const warn=["nacht","daemmerung_abend","daemmerung_morgen"].includes(l.phase)||l.warnung||l.gegenlicht;
 $("wlight").textContent=l.text;$("wlight").className=warn?"warn":"";
 $("wlight2").textContent="Heute: "+[l.daemmerung_beginn&&"Dämmerung ab "+l.daemmerung_beginn,l.aufgang&&"🌅 "+l.aufgang,
  l.untergang&&"🌇 "+l.untergang,l.daemmerung_ende&&"dunkel ab "+l.daemmerung_ende].filter(x=>x).join(" · ")+" (lokal berechnet)";
 opsSet("licht",l.kurz)}catch(e){$("wlight").innerHTML=`<span class=err>⚠ Licht: ${esc(e.message)}</span>`}}
setInterval(()=>{if(!document.hidden)lichtLoad()},60000);

let P=null,PO=null;
const GTAGS=["Wiese","Feld","Wald","Industrie","Bando","Hügel","Wasser","Strand","Park","Sandgrube"];
const v=(id)=>$(id)?$(id).value:"";
const inp=(id,val,ph="")=>`<input id=${id} value="${esc(val??"")}" placeholder="${esc(ph)}">`;
const lab=(t,h)=>`<label class=mu style="display:block;margin:4px 0">${t}${h}</label>`;
const opt=(arr,sel)=>arr.map(o=>`<option ${o==sel?"selected":""}>${esc(o)}</option>`).join("");
async function profOpen(id){try{const r=await api("/api/spotprofil"+(id?"?id="+encodeURIComponent(id):""));P=r.profil;PO=r;profRender();
 $("profcard").style.display="";$("profcard").scrollIntoView({behavior:"smooth"})}catch(e){alert(e.message)}}
function hRow(h,i){return `<div class=row data-h><select style="flex:0 0 130px">${opt(PO.optionen.hindernisse,h.art)}</select><input value="${esc(h.text)}" placeholder="Beschreibung / Lage" style="flex:3 1 200px"><input value="${esc(h.hoehe_m??"")}" placeholder="Höhe m" style="flex:0 0 80px" inputmode=decimal><button style="flex:0 0 auto" onclick="this.parentNode.remove()">✕</button></div>`}
function gRow(g){return `<div class=row data-g><select style="flex:0 0 130px">${opt(PO.optionen.gefahren,g.art)}</select><input value="${esc(g.text)}" placeholder="z. B. Kreisstraße 30 m östlich" style="flex:3 1 200px"><select style="flex:0 0 100px">${opt(PO.optionen.stufen,g.stufe||"mittel")}</select><label class=tag style="flex:0 0 auto"><input type=checkbox ${g.checkliste!==false?"checked":""}> Checkliste</label><button style="flex:0 0 auto" onclick="this.parentNode.remove()">✕</button></div>`}
function stars(k,val){return `<div class=row><span style="flex:0 0 130px">${PO.optionen.bewertung_lbl[k]}</span><select id=b_${k} style="flex:0 0 90px">${[0,1,2,3,4,5].map(n=>`<option value=${n} ${n==val?"selected":""}>${n?"★".repeat(n):"–"}</option>`).join("")}</select></div>`}
function profRender(){const p=P,g=p.gelaende,f=p.funk,L=PO.links;$("proftitle").textContent="🗂 Spot-Profil: "+p.name;
 $("prof").innerHTML=`<details open><summary>Allgemein &amp; GPS</summary><div class=grid><div>${lab("Name",inp("p_name",p.name))}${lab("Region",inp("p_region",p.region,"Ort, Landkreis, Bundesland"))}${lab("Höhe (m ü. NN)",inp("p_hoehe",p.hoehe,"kommt bei „Wo heute?“ aus Open-Meteo"))}</div>
 <div>${lab("Breite (lat)",inp("p_lat",p.lat))}${lab("Länge (lon)",inp("p_lon",p.lon))}<div class=row>${inp("p_slat",p.startplatz.lat,"Startplatz lat")}${inp("p_slon",p.startplatz.lon,"Startplatz lon")}</div>${inp("p_stxt",p.startplatz.text,"Start/Landung: z. B. Feldweg-Ende")}</div></div>
 <div class=row><a href="${L.dipul}" target=_blank rel=noopener><button class=pri style="width:100%">🗺 dipul</button></a><a href="${L.osm}" target=_blank rel=noopener><button style="width:100%">🌍 OSM</button></a>
 <a href="${L.openaip}" target=_blank rel=noopener><button style="width:100%">✈ OpenAIP</button></a><button onclick="navigator.clipboard&&navigator.clipboard.writeText('${L.gps}');this.textContent='✓ kopiert'">📋 ${L.gps}</button></div>
 <div class=mu>dipul/offizielle Quellen sind maßgeblich – das Profil ist nur deine Notiz, kein Rechtsrat.</div></details>
 <details><summary>Gelände</summary><div>${GTAGS.map(t=>`<label class=tag><input type=checkbox data-tag="${t}" ${g.tags.includes(t)?"checked":""}>${t}</label>`).join("")}</div>
 <div class=grid><div>${lab("Untergrund",inp("g_untergrund",g.untergrund,"Gras, Kies …"))}${lab("Größe",inp("g_groesse",g.groesse,"200 × 100 m"))}${lab("Windschutz/Lee",inp("g_windschutz",g.windschutz))}</div>
 <div>${lab("Thermik",inp("g_thermik",g.thermik))}${lab("Zugang/Parken",inp("g_zugang",g.zugang))}${lab("Besucherverkehr",inp("g_besucher",g.besucher))}</div></div>${lab("Beschreibung",`<textarea id=g_text>${esc(g.text)}</textarea>`)}</details>
 <details><summary>Hindernisse &amp; Flugrouten</summary><div id=hlist2>${p.hindernisse.map(hRow).join("")}</div><button onclick="$('hlist2').insertAdjacentHTML('beforeend',hRow({art:'Bäume',text:''}))">➕ Hindernis</button>
 ${lab("Mögliche Flugrouten (eine pro Zeile)",`<textarea id=p_routen>${esc(p.routen.join("\\n"))}</textarea>`)}</details>
 <details><summary>Gefahrenstellen (${p.gefahren.length})</summary><div class=mu>Mit „Checkliste“ erscheinen sie vor dem Flug als Zusatzpunkt (hoch zuerst).</div><div id=glist>${p.gefahren.map(gRow).join("")}</div>
 <button onclick="$('glist').insertAdjacentHTML('beforeend',gRow({art:'Straße',text:'',stufe:'mittel'}))">➕ Gefahrenstelle</button></details>
 <details><summary>Empfang &amp; Funk</summary><div class=grid><div>${lab("Video-System",`<select id=f_system>${opt(PO.optionen.funk,f.system)}</select>`)}${lab("VTX-Kanäle",inp("f_vtx_kanal",f.vtx_kanal,"R3 gut, F4 stört"))}${lab("Störquellen",inp("f_stoerquellen",f.stoerquellen))}</div>
 <div>${lab("Reichweite/Abschattung",inp("f_reichweite",f.reichweite))}${lab("ELRS/Crossfire",inp("f_link",f.link))}${lab("Mobilfunk",inp("f_mobilfunk",f.mobilfunk))}</div></div>${lab("Notizen",`<textarea id=f_text>${esc(f.text)}</textarea>`)}</details>
 <details><summary>Bewertung ${p.bewertung.gesamt?"★".repeat(p.bewertung.gesamt):""}</summary>${PO.optionen.bewertung.map(k=>stars(k,p.bewertung[k])).join("")}
 <div class=mu>Flugtage an diesem Spot: ${PO.stats.flugtage} · zuletzt: ${PO.stats.zuletzt||"–"}</div>${lab("Private Notizen (beim Export standardmäßig weggelassen)",`<textarea id=p_notizen>${esc(p.notizen)}</textarea>`)}</details>
 <details><summary>Medien &amp; Teilen</summary><div class=mu>Spot-Medien: ${PO.medien.length} Datei(en) · ${esc(PO.medien_pfad)}</div>
 <div class=row><button onclick="api('/api/spotprofil/medien',{id:P.id}).catch(e=>alert(e.message))">📂 Spot-Medienordner öffnen</button>
 <a href="/api/spotprofil/export?id=${encodeURIComponent(p.id)}"><button style="width:100%">⬆ Export (ohne private Notizen)</button></a>
 <a href="/api/spotprofil/export?id=${encodeURIComponent(p.id)}&privat=1"><button style="width:100%">⬆ Export inkl. Notizen</button></a></div>
 <div class=row><label class=mu>⬇ Profil importieren (.json)<input type=file accept=".json,application/json" onchange="profImport(this.files[0])"></label></div></details>`}
function profCollect(){const p=JSON.parse(JSON.stringify(P));
 Object.assign(p,{name:v("p_name"),region:v("p_region"),hoehe:v("p_hoehe"),lat:v("p_lat"),lon:v("p_lon"),routen:v("p_routen").split("\\n").map(s=>s.trim()).filter(Boolean),notizen:v("p_notizen"),
  startplatz:{lat:v("p_slat"),lon:v("p_slon"),text:v("p_stxt")}});
 p.gelaende={tags:[...document.querySelectorAll("[data-tag]")].filter(x=>x.checked).map(x=>x.dataset.tag)};
 for(const k of ["untergrund","groesse","windschutz","thermik","zugang","besucher","text"])p.gelaende[k]=v("g_"+k);
 p.funk={};for(const k of ["system","vtx_kanal","stoerquellen","reichweite","link","mobilfunk","text"])p.funk[k]=v("f_"+k);
 p.bewertung={};for(const k of PO.optionen.bewertung)p.bewertung[k]=+v("b_"+k);
 p.hindernisse=[...document.querySelectorAll("[data-h]")].map(r=>{const e=r.querySelectorAll("select,input");return{art:e[0].value,text:e[1].value,hoehe_m:e[2].value}});
 p.gefahren=[...document.querySelectorAll("[data-g]")].map(r=>{const e=r.querySelectorAll("select,input");return{art:e[0].value,text:e[1].value,stufe:e[2].value,checkliste:e[3].checked}});return p}
async function profSave(){try{const r=await api("/api/spotprofil",{profil:profCollect()});P=r.profil;PO=r;S=r.state;renderState();profRender();
 $("profmsg").className="ok";$("profmsg").textContent="Gespeichert "+P.geaendert.slice(11,16)}catch(e){$("profmsg").className="err";$("profmsg").textContent="⚠ "+e.message}}
async function profImport(file){if(!file)return;try{const data=JSON.parse(await file.text());const r=await api("/api/spotprofil/import",{data});S=r.state;renderState();
 alert("Spot „"+r.profil.name+"“ importiert.");profOpen(r.profil.id)}catch(e){alert("Import fehlgeschlagen: "+e.message)}}
async function heute(force){const c=$("heutecard");c.style.display="";$("hmeta").textContent="Hole aktuelles Wetter für alle Spots (Open-Meteo) …";
 let q="/api/spots/heute?sort="+$("hsort").value+(force?"&force=1":"");
 if($("hgps").checked&&navigator.geolocation){try{const pos=await new Promise((ok,no)=>navigator.geolocation.getCurrentPosition(ok,no,{timeout:8000}));
  q+=`&lat=${pos.coords.latitude}&lon=${pos.coords.longitude}`}catch(e){$("hmeta").textContent="Gerätestandort nicht verfügbar – nehme aktiven Spot."}}
 try{const r=await api(q),D={gruen:"🟢",gelb:"🟡",rot:"🔴"},C={gruen:"ok",gelb:"warn",rot:"err"};
  $("hmeta").innerHTML=(r.fehler?`<span class=err>⚠ ${esc(r.fehler)} – Ampel unbekannt.</span><br>`:"")+`Entfernung ab ${esc(r.ursprung)} · ${esc(r.quelle)}${r.abruf?" · Abruf "+r.abruf:""}<br>${esc(r.hinweis)}`;
  $("hlist").innerHTML=r.spots.length?r.spots.map(s=>{const w=s.wetter;return `<div class=sp><div class=i>${D[s.ampel]||"⚪"}</div><div class=b><b class=${C[s.ampel]||"mu"}>${esc(s.name)}</b>${s.region?` <span class=mu>· ${esc(s.region.split(",")[0])}</span>`:""}
   <div>${esc(s.ampel_titel)} – ${esc(s.gruende.slice(0,3).join("; "))}</div><div class=mu>${w?`Wind ${f(w.wind)} / Böen ${f(w.boeen)} m/s aus ${esc(w.richtung_txt)} · ${f(w.temp,0)} °C · ${esc(w.wetter)}`:"kein Wetter"}${s.distanz_km!=null?` · ${s.distanz_km} km`:""}${s.bewertung?" · "+"★".repeat(s.bewertung):""} · ${s.flugtage} Flugtag(e)${s.zuletzt?", zuletzt "+s.zuletzt:""}${s.gefahren_hoch?` · <span class=warn>⚠ ${s.gefahren_hoch} hohe Gefahr(en)</span>`:""}</div></div>
   <div class=a><button class=pri onclick="setActive(${esc(JSON.stringify(s.name))})">Aktivieren</button><button onclick="profOpen(${esc(JSON.stringify(s.id))})">🗂 Profil</button><a href="${s.links.dipul}" target=_blank rel=noopener><button style="width:100%">🗺 dipul</button></a></div></div>`}).join("")
  :`<div class=mu>Noch keine Spots gespeichert.</div>`}catch(e){$("hmeta").innerHTML=`<span class=err>⚠ ${esc(e.message)}</span>`}}
let FD=null,HITREG=null;
async function fd(){try{const r=await api("/api/flugtag");FD=r.aktiv;const d=r.detail;$("lbpath").textContent="Logs-Ordner: "+r.pfad;
 if(FD){const s=FD.snapshot_start;$("fdstat").innerHTML=`<span class=ok>🟢 Flugtag läuft: ${esc(FD.spot.name)} seit ${FD.start.slice(11,16)}</span><br><span class=mu>${s?`Start-Wetter: ${esc(s.ampel_titel)}, Wind ${s.wind}/${s.boeen} m/s, ${s.temp} °C`:"Start-Wetter: kein Snapshot"}${r.licht?`<br>Licht: ${esc(r.licht.text)}`:""}</span>`;
  $("fdstart").disabled=true;$("fdend").disabled=false;$("fdfl").disabled=false;
  $("fdnotes").innerHTML=`Messpunkte: ${d.verlauf.length} · Medien: ${d.medien.length} · Notizen: ${d.notizen.length}<br>`+d.notizen.slice(-4).map(n=>`${n.zeit.slice(11,16)} ${esc(n.text)}${n.tags.length?" ["+esc(n.tags.join(", "))+"]":""}`).join("<br>");
  chart(d.verlauf)}else{$("fdstat").innerHTML=`<span class=mu>⚪ Kein Flugtag aktiv – „▶ Flugtag starten“ legt Ordner, Wetter-Snapshot und Verlauf an.</span>`;
  $("fdstart").disabled=false;$("fdend").disabled=true;$("fdfl").disabled=true;$("fdnotes").textContent="";chart([])}}catch(e){$("fdstat").innerHTML=`<span class=err>⚠ ${esc(e.message)}</span>`}}
function chart(pts){const t=S.thresholds,W=520,H=130,L=30,R=8,T=8,B=18,c=$("chart");pts=pts.filter(p=>p.boeen!=null);
 if(!pts.length){c.innerHTML=`<text x=260 y=68 fill="#8b949e" font-size=12 text-anchor=middle>Wind-/Böenverlauf erscheint hier, sobald ein Flugtag läuft.</text>`;return}
 const top=Math.max(t.gust_max+2,...pts.map(p=>p.boeen+1)),y=v=>T+(H-T-B)*(1-v/top),x=i=>L+(W-L-R)*(i/Math.max(pts.length-1,1));
 let s="";for(const[v,col]of[[t.gust_warn,"#d29922"],[t.gust_max,"#f85149"]])s+=`<line x1=${L} x2=${W-R} y1=${y(v)} y2=${y(v)} stroke="${col}" stroke-dasharray="4 3"/><text x=${L-4} y=${y(v)+3} fill="${col}" font-size=9 text-anchor=end>${v}</text>`;
 for(const[k,col]of[["wind","#2f81f7"],["boeen","#f0883e"]]){const P=pts.map((p,i)=>`${x(i)},${y(p[k]??0)}`);s+=`<polyline fill=none stroke="${col}" stroke-width=2 points="${P.join(" ")}"/>`+P.map(q=>`<circle r=2.5 fill="${col}" cx=${q.split(",")[0]} cy=${q.split(",")[1]} />`).join("")}
 s+=`<text x=${L} y=${H-5} fill="#8b949e" font-size=9>${pts[0].zeit.slice(11,16)}</text><text x=${W-R} y=${H-5} fill="#8b949e" font-size=9 text-anchor=end>${pts[pts.length-1].zeit.slice(11,16)}</text><text x=260 y=${H-5} fill="#8b949e" font-size=9 text-anchor=middle>— Wind (blau)  — Böen (orange) m/s</text>`;c.innerHTML=s}
async function fdStart(){$("fdstat").textContent="Starte Flugtag, hole Wetter-Snapshot …";try{await api("/api/flugtag/start",{})}catch(e){alert(e.message)}fd();logSearch()}
async function fdEnd(){if(!confirm("Flugtag beenden und Zusammenfassung erstellen?"))return;try{const r=await api("/api/flugtag/ende",{});alert(r.zusammenfassung)}catch(e){alert(e.message)}fd();logSearch()}
async function fdNote(){const t=$("note").value.trim();if(!t)return;try{await api("/api/flugtag/notiz",{text:t,tags:$("ntag").value?[$("ntag").value]:[]});$("note").value="";$("ntag").value=""}catch(e){alert(e.message)}fd()}
async function openDir(o){try{await api("/api/oeffnen",{ordner:o||null})}catch(e){alert(e.message)}}
async function reindex(){await api("/api/log/reindex",{});logSearch()}
async function logSearch(){try{const r=await api("/api/log?q="+encodeURIComponent($("ls").value.trim())),D={gruen:"🟢",gelb:"🟡",rot:"🔴"};
 $("lbl").innerHTML=r.flugtage.length?"<table>"+r.flugtage.map(x=>`<tr><td>${x.datum}</td><td>${D[x.ampel]||"⚪"}</td><td><b>${esc(x.spot)}</b>${x.region?`<br><span class=mu>${esc(x.region.split(",")[0])}</span>`:""}</td><td class=mu>${x.fluege?x.fluege+" Flug · "+dur(x.flugzeit_s)+(x.crashes?" · 💥"+x.crashes:"")+"<br>":""}${x.notizen} Notiz · ${x.medien} Medien${x.status=="offen"?" · läuft":""}</td><td><button style="min-height:30px;padding:2px 8px" title="Flüge &amp; Wartung eintragen" onclick="flOpen('${esc(x.ordner).replace(/'/g,"\\'")}')">✈</button> <button style="min-height:30px;padding:2px 8px" onclick="openDir('${esc(x.ordner).replace(/'/g,"\\'")}')">📂</button> <a target=_blank href="/log/${encodeURIComponent(x.ordner)}"><button style="min-height:30px;padding:2px 8px">📄</button></a></td></tr>`).join("")+"</table>"
 :`<div class=mu style="padding:8px">${$("ls").value.trim()?"Keine Treffer.":"Noch keine Flugtage gefunden."}</div>`}catch(e){$("lbl").innerHTML=`<span class=err>${esc(e.message)}</span>`}}
__STATSJS__
__METARJS__
loadAll();fd();logSearch();setInterval(()=>{if(!document.hidden)fd()},60000);setInterval(()=>{if(!document.hidden)weather()},300000);
</script></body></html>"""


def _state() -> dict:
    s = settings.load()
    sp = settings.active_spot(s)
    s["active"] = sp["name"] if sp else None
    s["dipul_url"] = geo.dipul_url(sp["lat"], sp["lon"]) if sp else config.DIPUL_HOME
    s["notam"] = notam.HINT
    try:
        s["gefahren"] = spots.checklist_extras(spots.by_name(sp["name"], s)) if sp else []
    except Exception:  # noqa: BLE001
        s["gefahren"] = []
    return s


def _profile_payload(p: dict) -> dict:
    return {"profil": p, "links": spots.links(p), "stats": spots.day_stats(p),
            "medien": spots.media(p["id"]), "medien_pfad": str(spots.media_dir(p["id"])),
            "optionen": {"hindernisse": spots.HINDERNIS_ARTEN, "gefahren": spots.GEFAHR_ARTEN, "stufen": spots.STUFEN,
                         "funk": spots.FUNK_SYSTEME, "bewertung": spots.BEWERTUNG_KAT,
                         "bewertung_lbl": {"gesamt": "⭐ Gesamt", "freestyle": "Freestyle", "cinematic": "Cinematic",
                                           "race": "Race", "ruhe": "Ruhe", "erreichbarkeit": "Erreichbarkeit"}}}


class H(BaseHTTPRequestHandler):
    server_version = "FPV-Lagezentrum"

    def log_message(self, fmt, *a):
        log.info("%s %s", self.address_string(), fmt % a)

    def _host_ok(self):
        return (self.headers.get("Host") or "") in ALLOWED_HOSTS

    def _send(self, code, body: bytes, ctype, extra: dict | None = None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        for k, val in (extra or {}).items():
            self.send_header(k, val)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

    def do_GET(self):  # noqa: N802
        if not self._host_ok():
            return self._json({"error": "Host nicht erlaubt"}, 403)
        u = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(u.query)
        force = qs.get("force", ["0"])[0] == "1"
        if u.path == "/":
            page = (PAGE.replace("__CSS__", CSS).replace("__STATSHTML__", STATS_HTML).replace("__STATSJS__", STATS_JS)
                    .replace("__METARHTML__", METAR_HTML).replace("__METARJS__", METAR_JS))
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        if u.path == "/karte":
            return self._send(200, MAP_PAGE.encode("utf-8"), "text/html; charset=utf-8")
        if u.path.startswith("/vendor/leaflet/"):
            base = (Path(__file__).resolve().parent / "vendor" / "leaflet").resolve()
            f = (base / urllib.parse.unquote(u.path[len("/vendor/leaflet/"):])).resolve()
            ct = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8", ".png": "image/png"}
            if base not in f.parents or f.suffix not in ct or not f.is_file():
                return self._json({"error": "nicht gefunden"}, 404)
            return self._send(200, f.read_bytes(), ct[f.suffix], {"Cache-Control": "max-age=86400"})
        if u.path == "/api/karte/spots":
            try:
                return self._json(mapdata.spot_layer())
            except Exception as e:  # noqa: BLE001
                log.exception("Karten-Spots")
                return self._json({"error": str(e)}, 500)
        if u.path == "/api/karte/radar":
            s = settings.load()
            sp = settings.active_spot(s)
            if not sp:
                return self._json({"error": "Kein aktiver Spot – erst einen Spot speichern."}, 400)
            try:
                r = dict(opensky.fetch(sp["lat"], sp["lon"], s.get("radar_box_deg", 0.5), force=force))
            except Exception as e:  # noqa: BLE001 – ehrlich melden, keine Ersatzdaten
                return self._json({"error": f"OpenSky: {e}"}, 502)
            for p in r["flugzeuge"]:
                p["hinweis"] = opensky.alt_class(p)
            r["spuren"] = mapdata.update_tracks(r) if not r.get("fehler") else {}
            r["zentrum"] = sp["name"]
            r["box"] = r.get("box") or min(max(float(s.get("radar_box_deg", 0.5)), 0.1), 2.0)
            return self._json(r)
        if u.path == "/api/metar":
            sp = settings.active_spot(settings.load())
            if not sp:
                return self._json({"error": "Kein aktiver Spot – erst einen Spot speichern."}, 400)
            try:
                r = dict(metar.fetch(sp["lat"], sp["lon"], force=force))
            except Exception as e:  # noqa: BLE001 – ehrlich melden, keine Ersatzdaten
                log.exception("METAR")
                return self._json({"error": f"METAR: {e}"}, 502)
            r["zentrum"] = sp["name"]
            return self._json(r)
        if u.path == "/health":
            return self._json({"ok": True, "app": config.APP_NAME, "version": config.APP_VERSION})
        if u.path == "/api/state":
            return self._json(_state())
        if u.path == "/api/geocode":
            try:
                return self._json({"treffer": geo.geocode(qs.get("q", [""])[0])})
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 502)
        if u.path in ("/api/weather", "/api/radar"):
            s = settings.load()
            sp = settings.active_spot(s)
            if not sp:
                return self._json({"error": "Bitte Standort setzen."}, 400)
            try:
                if u.path == "/api/weather":
                    w = weather.fetch(sp["lat"], sp["lon"], force=force)
                    return self._json({"wetter": {k: v for k, v in w.items() if k != "_t"},
                                       "ampel": weather.assess(w, s["thresholds"]), "spot": sp})
                r = opensky.fetch(sp["lat"], sp["lon"], s.get("radar_box_deg", 0.5), force=force)
                for p in r["flugzeuge"]:
                    p["hinweis"] = opensky.alt_class(p)
                return self._json(r)
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 502)
        if u.path == "/api/spots/heute":
            try:
                lat = float(qs["lat"][0]) if "lat" in qs else None
                lon = float(qs["lon"][0]) if "lon" in qs else None
                return self._json(spots.today(qs.get("sort", ["kombi"])[0], lat, lon, force=force))
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if u.path in ("/api/spotprofil", "/api/spotprofil/export"):
            try:
                sid = qs.get("id", [""])[0]
                p = spots.load(sid) if sid else spots.active_profile()
                if not p:
                    return self._json({"error": "Spot-Profil nicht gefunden – erst einen Spot speichern."}, 404)
                if u.path == "/api/spotprofil":
                    return self._json(_profile_payload(p))
                data = json.dumps(spots.export(p["id"], privat=qs.get("privat", ["0"])[0] == "1"),
                                  ensure_ascii=False, indent=2).encode("utf-8")
                return self._send(200, data, "application/json; charset=utf-8",
                                  {"Content-Disposition": f'attachment; filename="spot-{p["id"]}.json"'})
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if u.path == "/druck/checkliste":
            s = settings.load()
            sp = settings.active_spot(s)
            amp = None
            if sp:
                try:
                    amp = weather.assess(weather.fetch(sp["lat"], sp["lon"]), s["thresholds"])
                except Exception:  # noqa: BLE001 – Druck auch ohne Wetter
                    amp = None
            return self._send(200, export.checklist_html(s, amp, leer=qs.get("leer", ["0"])[0] == "1").encode("utf-8"),
                              "text/html; charset=utf-8")
        if u.path == "/api/flugtag":
            s = settings.load()
            day = logbook.active(s)
            det = logbook.day_detail(day["ordner"], s) if day else None
            lt = sun.light(day["spot"]["lat"], day["spot"]["lon"]) if day else None
            return self._json({"aktiv": day, "detail": det, "pfad": str(logbook.logs_dir(s)), "licht": lt})
        if u.path == "/api/dipul":
            sp = settings.active_spot(settings.load())
            if not sp:
                return self._json({"error": "Kein aktiver Spot"}, 400)
            try:
                r = dipul.check(sp["lat"], sp["lon"], force=force)
            except Exception as e:  # noqa: BLE001 – ehrlich melden, nichts erfinden
                log.exception("dipul")
                return self._json({"error": f"dipul: {e}"}, 502)
            return self._json({**r, "spot": sp["name"]})
        if u.path == "/api/licht":
            sp = settings.active_spot(settings.load())
            if not sp:
                return self._json({"error": "Kein aktiver Spot"}, 400)
            return self._json({**sun.light(sp["lat"], sp["lon"]), "spot": sp["name"]})
        if u.path in ("/api/statistik", "/api/statistik.csv", "/druck/statistik"):
            flt = {k: qs.get(k, [""])[0][:60] for k in ("von", "bis", "spot", "drohne")}
            try:
                if u.path == "/api/statistik.csv":
                    return self._send(200, stats.flights_csv(**flt).encode("utf-8"), "text/csv; charset=utf-8",
                                      {"Content-Disposition": 'attachment; filename="fpv-fluege.csv"'})
                s = stats.compute(**flt)
                if u.path == "/api/statistik":
                    return self._json(s)
                return self._send(200, stats.print_html(s).encode("utf-8"), "text/html; charset=utf-8")
            except Exception as e:  # noqa: BLE001
                log.exception("Statistik-Fehler")
                return self._json({"error": str(e)}, 500)
        if u.path == "/api/fluege":
            try:
                s = settings.load()
                o = qs.get("ordner", [""])[0] or (logbook.active(s) or {}).get("ordner")
                if not o:
                    return self._json({"error": "Kein Flugtag aktiv – im Logbuch bei einem Tag auf ✈ klicken."}, 400)
                det = logbook.day_detail(o, s)
                try:
                    ak = [{"id": a["id"], "label": batteries.label(a)} for a in batteries.load() if not a.get("ausgemustert")]
                except ValueError:
                    ak = []
                st = stats.compute(s)
                return self._json({"ordner": o, "flugtag": det["flugtag"], "fluege": det["fluege"],
                                   "wartung": det["wartung"], "akkus": ak, "drohnen": st["drohnen_liste"]})
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
        if u.path == "/api/log":
            return self._json({"flugtage": logbook.search(qs.get("q", [""])[0])})
        if u.path.startswith("/log/"):
            name = urllib.parse.unquote(u.path[5:])
            try:
                det = logbook.day_detail(name)
                d = Path(det["pfad"])
                f = d / "zusammenfassung.md" if (d / "zusammenfassung.md").exists() else d / "flugtag.md"
                body = f.read_text(encoding="utf-8")
            except Exception as e:  # noqa: BLE001
                return self._json({"error": str(e)}, 404)
            import html as _h
            page = (f"<!doctype html><html lang=de><meta charset=utf-8><meta name=viewport content='width=device-width,"
                    f"initial-scale=1'><title>{_h.escape(name)}</title><style>{CSS}pre{{white-space:pre-wrap;"
                    f"font:14px/1.5 Menlo,Consolas,monospace}}</style><div class=card><pre>{_h.escape(body)}</pre></div>")
            return self._send(200, page.encode("utf-8"), "text/html; charset=utf-8")
        return self._json({"error": "nicht gefunden"}, 404)

    def do_POST(self):  # noqa: N802
        if not self._host_ok():
            return self._json({"error": "Host nicht erlaubt"}, 403)
        try:
            n = int(self.headers.get("Content-Length") or 0)
            if n > 200_000:
                raise ValueError("zu groß")
            b = json.loads(self.rfile.read(n) or b"{}")
        except Exception as e:  # noqa: BLE001
            return self._json({"error": f"ungültige Anfrage: {e}"}, 400)
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/spotprofil"):
            try:
                if path == "/api/spotprofil/medien":
                    d = spots.media_dir(str(b.get("id") or ""))
                    logbook.open_folder(d)
                    return self._json({"pfad": str(d)})
                with SLOCK:
                    s = settings.load()
                    if path == "/api/spotprofil":
                        p = spots.save(b.get("profil") or {}, s)
                    elif path == "/api/spotprofil/import":
                        p = spots.import_profile(b.get("data"), s)
                    else:
                        return self._json({"error": "nicht gefunden"}, 404)
                    settings.save(s)
                return self._json({**_profile_payload(p), "state": _state()})
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                log.exception("Spot-Profil-Fehler")
                return self._json({"error": str(e)}, 500)
        if path in ("/api/flug", "/api/wartung", "/api/storno", "/api/akku"):
            try:
                o = str(b.get("ordner") or "") or None
                if path == "/api/flug":
                    return self._json({"flug": logbook.add_flight(b, o)})
                if path == "/api/wartung":
                    return self._json({"wartung": logbook.add_maintenance(b, o)})
                if path == "/api/storno":
                    logbook.storno(str(b.get("kind") or ""), str(b.get("id") or ""), o)
                    return self._json({"ok": True})
                return self._json({"akku": batteries.upsert(b)})
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                log.exception("Flug/Wartung-Fehler")
                return self._json({"error": str(e)}, 500)
        if path.startswith("/api/flugtag/") or path in ("/api/oeffnen", "/api/log/reindex"):
            try:
                if path == "/api/flugtag/start":
                    return self._json({"flugtag": logbook.start_day()})
                if path == "/api/flugtag/ende":
                    day = logbook.end_day()
                    d = logbook.logs_dir() / day["ordner"]
                    return self._json({"flugtag": day, "zusammenfassung": (d / "zusammenfassung.md").read_text(encoding="utf-8")})
                if path == "/api/flugtag/notiz":
                    tags = b.get("tags") if isinstance(b.get("tags"), list) else []
                    return self._json({"notiz": logbook.add_note(str(b.get("text") or ""), [str(x) for x in tags])})
                if path == "/api/oeffnen":
                    o = b.get("ordner")
                    return self._json({"pfad": str(logbook.open_day(str(o) if o else None))})
                if path == "/api/log/reindex":
                    return self._json({"flugtage": len(logbook.rebuild_index())})
            except ValueError as e:
                return self._json({"error": str(e)}, 400)
            except Exception as e:  # noqa: BLE001
                log.exception("Logbuch-Fehler")
                return self._json({"error": str(e)}, 500)
            return self._json({"error": "nicht gefunden"}, 404)
        with SLOCK:
            s = settings.load()
            try:
                if path == "/api/spot":
                    settings.upsert_spot(s, str(b.get("name") or ""), float(str(b.get("lat")).replace(",", ".")),
                                         float(str(b.get("lon")).replace(",", ".")), b.get("region") or None)
                    spots.migrate(s)   # ID + Profil anlegen bzw. Koordinaten ins Profil übernehmen
                elif path == "/api/spot/delete":
                    settings.remove_spot(s, str(b.get("name") or ""))
                elif path == "/api/active":
                    if any(x["name"] == b.get("name") for x in s["spots"]):
                        s["active"] = b.get("name")
                elif path == "/api/checklist":
                    items = b.get("items") or []
                    s["checklist"] = [{"text": str(i.get("text"))[:200], "done": bool(i.get("done"))}
                                      for i in items if isinstance(i, dict) and str(i.get("text") or "").strip()][:60]
                elif path == "/api/thresholds":
                    for k in settings.DEFAULT_THRESHOLDS:
                        if k in b:
                            s["thresholds"][k] = float(str(b[k]).replace(",", "."))
                elif path == "/api/auto":
                    s["radar_auto"] = bool(b.get("on"))
                else:
                    return self._json({"error": "nicht gefunden"}, 404)
            except (ValueError, TypeError) as e:
                return self._json({"error": f"Ungültige Eingabe: {e}"}, 400)
            settings.save(s)
        return self._json(_state())


def _ticker():
    """Schreibt während eines laufenden Flugtags Wetter-Messpunkte (auch wenn nur das Web läuft)."""
    while True:
        time.sleep(60)
        try:
            logbook.tick()
        except Exception as e:  # noqa: BLE001
            log.warning("Verlauf-Messpunkt fehlgeschlagen: %s", e)


def main():
    try:
        spots.migrate()   # Phase 7: Spot-Profile aus settings.json anlegen (nichts geht verloren)
    except Exception:  # noqa: BLE001
        log.exception("Spot-Migration fehlgeschlagen")
    threading.Thread(target=_ticker, daemon=True).start()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    srv = ThreadingHTTPServer((HOST, PORT), H)
    srv.daemon_threads = True
    log.info("FPV-Lagezentrum Web läuft: http://%s:%d", HOST, PORT)
    srv.serve_forever()


if __name__ == "__main__":
    main()
