"""Karten-Seite /karte (Roadmap Phase 2) – Leaflet liegt lokal unter web/vendor/leaflet (BSD-2, v1.9.4)."""

MAP_PAGE = r'''<!doctype html><html lang=de><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><meta name=theme-color content="#0b0f14">
<title>FPV-Lagezentrum – Karte</title><link rel=stylesheet href="/vendor/leaflet/leaflet.css">
<style>
:root{--bg:#0b0f14;--card:#161b22;--bd:#30363d;--tx:#e6edf3;--mu:#8b949e;--acc:#2f81f7;--ok:#3fb950;--warn:#d29922;--err:#f85149}
html,body{margin:0;height:100%;background:var(--bg);color:var(--tx);font:14px/1.4 -apple-system,"Segoe UI",Helvetica,Arial,sans-serif}
#map{position:absolute;inset:0;background:#0b0f14}
.darktiles{filter:invert(1) hue-rotate(180deg) brightness(.92) contrast(.88) saturate(.7)}
.bar{position:absolute;z-index:1000;top:10px;left:56px;right:10px;display:flex;flex-wrap:wrap;gap:6px;align-items:center;pointer-events:none}
.bar>*{pointer-events:auto}
.pill{background:rgba(22,27,34,.93);border:1px solid var(--bd);border-radius:10px;padding:6px 10px}
button{background:#373e47;color:var(--tx);border:0;border-radius:9px;padding:7px 11px;font:inherit;font-weight:700;cursor:pointer;min-height:34px}
button:hover{background:#444c56}button.pri{background:var(--acc)}a{color:#58a6ff}
h1{font-size:16px;margin:0}.mu{color:var(--mu)}.ok{color:var(--ok)}.warn{color:var(--warn)}.err{color:var(--err)}
#msg{position:absolute;z-index:1000;left:10px;right:10px;bottom:26px;display:flex;flex-direction:column;gap:6px;pointer-events:none}
#msg>div{pointer-events:auto;max-width:720px}
.banner{background:rgba(70,20,20,.95);border:1px solid var(--err);color:#ffd7d5;border-radius:10px;padding:8px 12px;font-weight:700}
.leg{display:inline-flex;gap:8px;flex-wrap:wrap;font-size:12px}.leg i{display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:3px;vertical-align:-1px}
.leaflet-popup-content-wrapper,.leaflet-popup-tip,.leaflet-tooltip{background:#161b22;color:var(--tx);border:1px solid var(--bd)}
.leaflet-tooltip:before{display:none}.leaflet-popup-content{margin:10px 12px;font-size:13px;min-width:220px}
.leaflet-container a.leaflet-popup-close-button{color:var(--mu)}
.leaflet-control-layers,.leaflet-bar a{background:#161b22;color:var(--tx);border-color:var(--bd)}
.leaflet-control-attribution{background:rgba(11,15,20,.8)!important;color:var(--mu)}.leaflet-control-attribution a{color:#58a6ff}
.ring{color:#58a6ff;font:700 11px sans-serif;text-align:center;text-shadow:0 0 3px #000}
.plane{background:none;border:0}.plane svg{filter:drop-shadow(0 0 2px #000)}
.pp b{font-size:14px}.pp .sec{margin-top:6px}.pp button{min-height:28px;padding:3px 8px;margin:4px 4px 0 0}
</style></head><body><div id=map></div>
<div class=bar>
 <div class=pill><h1>🗺 FPV-Lagezentrum · Karte</h1><div class=mu id=sub>…</div></div>
 <button class=pri onclick="radar(1)">🔄 Radar</button>
 <label class=pill><input type=checkbox id=auto checked onchange="autoT()"> Live (60 s)</label>
 <button onclick="ampeln()">🚦 Ampeln holen</button><button onclick="center()">⌖ Spot</button>
 <a href="/"><button>← Lagezentrum</button></a>
 <div class="pill leg"><span><i style="background:#f85149"></i>&lt; 600 m</span><span><i style="background:#f0883e"></i>&lt; 1500 m</span>
 <span><i style="background:#d29922"></i>&lt; 3000 m</span><span><i style="background:#58a6ff"></i>höher</span><span><i style="background:#8b949e"></i>Boden/?</span></div>
</div>
<div id=msg><div class=pill id=rmeta>Radar: …</div><div class="pill mu" style="font-size:12px">Flugzeuge: OpenSky Network – nur Transponder/ADS-B; Hubschrauber, Segler &amp; Drohnen fehlen oft. Geozonen &amp; Regeln: nur die
 <a id=dipul target=_blank rel=noopener href="https://www.dipul.de/homepage/de/">dipul-Karte</a> ist maßgeblich – diese Karte ist kein Rechtsrat.</div></div>
<script src="/vendor/leaflet/leaflet.js"></script>
<script>
const $=id=>document.getElementById(id);
const esc=s=>String(s??"").replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const AC={gruen:"#3fb950",gelb:"#d29922",rot:"#f85149"},AN={gruen:"🟢",gelb:"🟡",rot:"🔴"},ST={hoch:"🔴",mittel:"🟠",niedrig:"🟡"};
const map=L.map("map",{zoomControl:true,preferCanvas:false}).setView([51.2,10.4],6);
// CARTO verlangt inzwischen einen API-Key → OSM-Standardkacheln, für den Dark-Look per CSS-Filter invertiert
const OSMATT='&copy; <a href="https://www.openstreetmap.org/copyright" target=_blank>OpenStreetMap</a>-Mitwirkende';
const dark=L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,className:"darktiles",attribution:OSMATT}).addTo(map);
const osm=L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:OSMATT});
// Offizieller dipul-WMS (DFS/BMDV), Lizenz CC BY-ND 4.0 – unverändert eingeblendet, standardmäßig AUS (Rate-Limit schonen)
const DIPUL_LAYERS="flugbeschraenkungsgebiete,kontrollzonen,flughaefen,flugplaetze,temporaere_betriebseinschraenkungen,modellflugplaetze,militaerische_anlagen,justizvollzugsanstalten,labore,behoerden,diplomatische_vertretungen,internationale_organisationen,polizei,sicherheitsbehoerden,kraftwerke,umspannwerke,stromleitungen,windkraftanlagen,industrieanlagen,krankenhaeuser,wohngrundstuecke,freibaeder,bundesautobahnen,bundesstrassen,bahnanlagen,binnenwasserstrassen,seewasserstrassen,schifffahrtsanlagen,nationalparks,naturschutzgebiete,ffh-gebiete,vogelschutzgebiete".split(",").map(x=>"dipul:"+x).join(",");
const gDipul=L.tileLayer.wms("https://uas-betrieb.de/geoservices/dipul/wms",{layers:DIPUL_LAYERS,format:"image/png",transparent:true,version:"1.3.0",opacity:.75,minZoom:9,maxZoom:19,
 attribution:'Geozonen: <a href="https://dipul.de/homepage/de/informationen/geografische-gebiete/wfs-wms/" target=_blank rel=noopener>dipul, CC-BY-ND 4.0</a> (Hinweis, verbindlich nur dipul-Karte)'});
const gSpots=L.layerGroup().addTo(map),gRoutes=L.layerGroup().addTo(map),gRings=L.layerGroup().addTo(map),gPlanes=L.layerGroup().addTo(map),gTracks=L.layerGroup().addTo(map),gAir=L.layerGroup().addTo(map);
L.control.layers({"Dunkel (OSM, invertiert)":dark,"OpenStreetMap hell":osm},{"Spots":gSpots,"Flugrouten":gRoutes,"Radius 1/5/10 km":gRings,"Flugzeuge":gPlanes,"Spuren":gTracks,"Flugplätze (METAR)":gAir,"dipul-Geozonen (offiziell, ab Zoom 9)":gDipul},{collapsed:true}).addTo(map);
L.control.scale({imperial:false}).addTo(map);
if(new URLSearchParams(location.search).has("dipul"))gDipul.addTo(map);  // /karte?dipul=1 → Geozonen direkt an
let SP=null,ACT=null,timer=null,first=true,BOX=null;
async function api(p,b){const r=await fetch(p,b?{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(b)}:{});
 const j=await r.json();if(!r.ok)throw new Error(j.error||r.status);return j}
function altCol(p){if(p.boden||p.hoehe_m==null)return"#8b949e";const h=p.hoehe_m;return h<600?"#f85149":h<1500?"#f0883e":h<3000?"#d29922":"#58a6ff"}
function planeIcon(p){const c=altCol(p),k=p.kurs??0;
 return L.divIcon({className:"plane",iconSize:[26,26],iconAnchor:[13,13],html:`<svg width=26 height=26 viewBox="-13 -13 26 26" style="transform:rotate(${k}deg)"><path d="M0,-11 L2,-3 L10,2 L10,4 L2,2 L1.5,8 L4,10 L4,11.5 L0,10.5 L-4,11.5 L-4,10 L-1.5,8 L-2,2 L-10,4 L-10,2 L-2,-3 Z" fill="${c}" stroke="#0b0f14" stroke-width=1 /></svg>`})}
function center(){if(ACT)map.setView([ACT.lat,ACT.lon],10)}
function popup(s){const w=s.ampel?`<div class=sec>${AN[s.ampel]} <b style="color:${AC[s.ampel]}">${esc(s.ampel_titel)}</b> <span class=mu>(Stand ${esc(s.messzeit||"?")})</span><br>${esc(s.gruende.join("; "))}${s.wind!=null?`<br>Wind ${s.wind} / Böen ${s.boeen} m/s`:""}</div>`:`<div class="sec mu">Ampel: noch nicht abgerufen</div>`;
 const rt=s.routen.length?`<div class=sec><b>Flugrouten</b><br>${s.routen.map(r=>`• ${esc(r.text)}${r.punkte?" <span class=ok>(auf Karte)</span>":""}`).join("<br>")}</div>`:"";
 const gf=s.gefahren.length?`<div class=sec><b>Gefahren</b><br>${s.gefahren.map(g=>`${ST[g.stufe]||"•"} ${esc(g.art)}${g.text?": "+esc(g.text):""}`).join("<br>")}</div>`:"";
 return `<div class=pp><b>${esc(s.name)}</b>${s.aktiv?' <span class=ok>· aktiv</span>':""}<div class=mu>${esc(s.region.split(",").slice(0,2).join(","))}${s.hoehe!=null?` · ${Math.round(s.hoehe)} m ü. NN`:""}</div>${w}
 <div class="sec mu">${s.lat.toFixed(5)}, ${s.lon.toFixed(5)} · ${s.flugtage} Flugtag(e)${s.zuletzt?", zuletzt "+s.zuletzt:""}${s.bewertung?" · "+"★".repeat(s.bewertung):""}${s.gelaende.length?"<br>"+esc(s.gelaende.join(", ")):""}${s.hindernisse?` · ${s.hindernisse} Hindernis(se)`:""}</div>${gf}${rt}
 <div class=sec><a href="${esc(s.links.dipul)}" target=_blank rel=noopener>dipul</a> · <a href="${esc(s.links.osm)}" target=_blank rel=noopener>OSM</a> · <a href="${esc(s.links.openaip)}" target=_blank rel=noopener>OpenAIP</a></div>
 ${s.aktiv?"":`<button onclick="activate('${esc(s.name).replace(/'/g,"&#39;")}')">Als aktiven Spot setzen</button>`}</div>`}
async function spotsLoad(){try{const r=await api("/api/karte/spots");SP=r.spots;ACT=r.aktiv;gSpots.clearLayers();gRoutes.clearLayers();
 for(const s of SP){const col=AC[s.ampel]||"#8b949e";
  const m=L.circleMarker([s.lat,s.lon],{radius:s.aktiv?11:8,color:s.aktiv?"#e6edf3":"#0b0f14",weight:s.aktiv?3:2,fillColor:col,fillOpacity:.95}).bindPopup(popup(s),{maxWidth:340});
  m.bindTooltip(`${esc(s.name)}${s.ampel?" · "+AN[s.ampel]:""}`,{direction:"top",offset:[0,-8]});m.addTo(gSpots);
  if(s.startplatz)L.circleMarker(s.startplatz,{radius:4,color:"#a371f7",weight:2,fillOpacity:.6}).bindTooltip("Start/Landeplatz "+esc(s.name)+(s.startplatz_text?": "+esc(s.startplatz_text):"")).addTo(gSpots);
  for(const rt of s.routen)if(rt.punkte)L.polyline(rt.punkte,{color:"#a371f7",weight:3,dashArray:"6 5"}).bindTooltip(esc(s.name)+": "+esc(rt.text.slice(0,80))).addTo(gRoutes)}
 gRings.clearLayers();BOX=null;if(ACT){for(const km of[1,5,10]){L.circle([ACT.lat,ACT.lon],{radius:km*1000,color:"#58a6ff",weight:1.6,opacity:.9,fill:false,dashArray:"5 5",interactive:false}).addTo(gRings);
   L.marker([ACT.lat+km/111.2,ACT.lon],{interactive:false,icon:L.divIcon({className:"ring",iconSize:[40,14],iconAnchor:[20,7],html:km+" km"})}).addTo(gRings)}
  $("dipul").href=SP.find(s=>s.aktiv)?.links.dipul||$("dipul").href}
 $("sub").innerHTML=ACT?`Zentrum: <b>${esc(ACT.name)}</b> · ${SP.length} Spot(s)${r.wetter_abruf?` · Ampel ${r.wetter_abruf}`:` · <span class=warn>${esc(r.wetter_hinweis)}</span>`}`:`<span class=warn>Kein aktiver Spot – im Lagezentrum einen Spot speichern.</span>`;
 if(first&&ACT){first=false;map.setView([ACT.lat,ACT.lon],10)}else if(first&&SP.length){first=false;map.fitBounds(SP.map(s=>[s.lat,s.lon]),{maxZoom:11})}}
 catch(e){$("sub").innerHTML=`<span class=err>⚠ Spots: ${esc(e.message)}</span>`}}
async function activate(n){try{await api("/api/active",{name:n});first=true;await spotsLoad();radar(1)}catch(e){alert(e.message)}}
async function ampeln(){$("sub").textContent="Hole aktuelles Wetter für alle Spots (Open-Meteo) …";try{const r=await api("/api/spots/heute?sort=kombi");if(r.fehler)alert(r.fehler)}catch(e){alert(e.message)}spotsLoad()}
async function radar(force){try{const r=await api("/api/karte/radar"+(force?"?force=1":""));gPlanes.clearLayers();gTracks.clearLayers();
 if(BOX)gRings.removeLayer(BOX);BOX=null;if(r.box&&ACT){const b=r.box;BOX=L.rectangle([[ACT.lat-b,ACT.lon-b],[ACT.lat+b,ACT.lon+b]],{color:"#8b949e",weight:1,dashArray:"2 6",fill:false,interactive:false}).addTo(gRings)}
 for(const p of r.flugzeuge){const tip=`<b>${esc(p.rufzeichen)}</b> ${p.land?"<span class=mu>("+esc(p.land)+")</span>":""}<br>Höhe ${p.boden?"am Boden":p.hoehe_m!=null?p.hoehe_m+" m":"?"} · ${p.dist_km} km ${esc(p.peilung||"")}<br>${p.speed_kmh!=null?p.speed_kmh+" km/h":"? km/h"} · Kurs ${p.kurs!=null?p.kurs+"°":"?"}${p.steig!=null?" · "+p.steig+" m/s":""}${p.hinweis?`<br><b class=err>${esc(p.hinweis)}</b>`:""}<br><span class=mu>Position vor ${p.alter_s} s</span>`;
  L.marker([p.lat,p.lon],{icon:planeIcon(p),zIndexOffset:p.hinweis=="TIEF & NAH"?1000:0}).bindTooltip(tip,{direction:"top",offset:[0,-10]}).addTo(gPlanes);
  const tr=r.spuren[p.icao24];if(tr&&tr.length>1)L.polyline(tr,{color:altCol(p),weight:1.5,opacity:.6,interactive:false}).addTo(gTracks)}
 const low=r.flugzeuge.filter(p=>p.hinweis=="TIEF & NAH").length;
 $("rmeta").innerHTML=(r.fehler?`<div class=banner>⚠ ${esc(r.fehler)}${r.flugzeuge.length?" – zeige letzten gespeicherten Stand.":" – keine Flugzeuge angezeigt."}</div>`:"")+
  `✈ ${r.flugzeuge.length} Luftfahrzeug(e) in ±${r.box}° um ${esc(r.zentrum||"–")}${low?` · <b class=err>${low}× TIEF &amp; NAH</b>`:""} · ${r.abruf?"Abruf "+r.abruf:"kein Abruf"}${r.aus_cache?" (Cache)":""}${r.rest!=null?" · OpenSky-Rest "+r.rest:""}`}
 catch(e){gPlanes.clearLayers();$("rmeta").innerHTML=`<div class=banner>⚠ Radar: ${esc(e.message)} – keine Flugzeuge angezeigt.</div>`}}
function autoT(){clearInterval(timer);if($("auto").checked)timer=setInterval(()=>{if(!document.hidden)radar()},60000)}
async function airports(){try{const r=await api("/api/metar");gAir.clearLayers();
 const icon=(main)=>L.divIcon({className:"plane",iconSize:[26,26],iconAnchor:[13,13],html:`<div style="width:24px;height:24px;border-radius:6px;background:${main?"#1f6feb":"#30363d"};border:2px solid #fff;color:#fff;font:700 13px sans-serif;display:flex;align-items:center;justify-content:center">🛫</div>`});
 const st=r.station,m=r.metar;
 if(st&&m)L.marker([st.lat,st.lon],{icon:icon(true),zIndexOffset:500}).bindPopup(`<div class=pp><b>🛫 ${esc(m.id)} ${esc(st.name)}</b><br><span class=mu>${st.dist_km} km ${esc(st.peilung)} vom Spot · METAR ${esc(m.zeit)} (vor ${m.alter_min} min)${m.veraltet?" – veraltet":""}</span>
  <div class=sec>💨 ${esc(m.wind)}<br>👁 ${esc(m.sicht)} · 🌦 ${esc(m.wetter)}<br>☁ ${esc(m.wolken)}<br>⏲ QNH <b>${m.qnh??"–"} hPa</b> · 🌡 ${m.temp??"–"} °C</div>
  <div class="sec mu" style="font-size:11px">${esc(m.roh)}</div><div class="sec mu" style="font-size:11px">⚠ Flugplatz-Wetter ≠ Spot-Wetter. Quelle: aviationweather.gov</div></div>`).addTo(gAir);
 for(const w of r.weitere||[])L.marker([w.lat,w.lon],{icon:icon(false)}).bindTooltip(`<b>${esc(w.id)}</b> ${esc(w.name)}<br>${w.dist_km} km ${esc(w.peilung)}<br>${w.hat_metar?esc(w.wind)+" · QNH "+(w.qnh??"–")+" · vor "+w.alter_min+" min":"kein aktuelles METAR"}`,{direction:"top"}).addTo(gAir);
}catch(e){/* METAR-Layer optional – Fehler stehen im Lagezentrum */}}
spotsLoad().then(()=>{radar();airports()});autoT();
</script></body></html>'''
