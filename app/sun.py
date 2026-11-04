"""Sonnenstand lokal berechnen (vereinfachte NOAA/Almanach-Formel, Genauigkeit ~0,5°) – keine API nötig."""
from __future__ import annotations

import math
from datetime import date, datetime, time as dtime, timedelta, timezone

from app import geo


def position(lat: float, lon: float, when: datetime | None = None) -> dict:
    when = (when or datetime.now(timezone.utc)).astimezone(timezone.utc)
    d = (when - datetime(2000, 1, 1, 12, tzinfo=timezone.utc)).total_seconds() / 86400.0
    g = math.radians((357.529 + 0.98560028 * d) % 360)
    q = (280.459 + 0.98564736 * d) % 360
    lam = math.radians(q + 1.915 * math.sin(g) + 0.020 * math.sin(2 * g))
    eps = math.radians(23.439 - 0.00000036 * d)
    ra = math.degrees(math.atan2(math.cos(eps) * math.sin(lam), math.cos(lam))) % 360
    dec = math.asin(math.sin(eps) * math.sin(lam))
    gmst = (18.697374558 + 24.06570982441908 * d) % 24
    ha = math.radians(((gmst * 15 + lon) - ra + 540) % 360 - 180)
    la = math.radians(lat)
    elev = math.degrees(math.asin(math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha)))
    az = (math.degrees(math.atan2(-math.sin(ha), math.tan(dec) * math.cos(la) - math.sin(la) * math.cos(ha))) + 360) % 360
    if elev > 6:
        phase = "Tag"
    elif elev > -0.833:
        phase = "tief stehende Sonne (Gegenlicht!)"
    elif elev > -6:
        phase = "bürgerliche Dämmerung"
    else:
        phase = "dunkel"
    return {"hoehe": round(elev, 1), "azimut": round(az), "richtung": geo.dir_text(az), "phase": phase}


# ------------------------------------------------------------------ Dämmerung & „noch X min Licht“ (v1.7)
# Zeiten werden aus position() selbst bestimmt (Nulldurchgang der Sonnenhöhe, 10-min-Raster + Bisektion) –
# so stimmen Phase, Zeiten und Countdown immer überein, auch an Polartagen (dann None).
HORIZON = -0.833        # Sonnenauf-/-untergang (Refraktion + Sonnenradius)
CIVIL = -6.0            # Ende/Beginn der bürgerlichen Dämmerung
LOW_SUN = 6.0           # darunter: tief stehende Sonne, Gegenlicht
LIGHT_WARN_MIN = 30     # Ampel gelb, wenn Sonnenuntergang näher als so viele Minuten


def _cross(lat, lon, t0: datetime, t1: datetime, alt: float, rising: bool) -> datetime | None:
    step = timedelta(minutes=10)
    t, h = t0, position(lat, lon, t0)["hoehe"] - alt
    while t < t1:
        t2 = min(t + step, t1)
        h2 = _elev(lat, lon, t2) - alt
        if (h < 0 <= h2) if rising else (h >= 0 > h2):
            a, b = t, t2
            for _ in range(14):     # ~ 4 s genau
                m = a + (b - a) / 2
                hm = _elev(lat, lon, m) - alt
                if (hm < 0) == rising:
                    a = m
                else:
                    b = m
            return b
        t, h = t2, h2
    return None


def _elev(lat, lon, when):
    return position(lat, lon, when)["hoehe"]


def times(lat: float, lon: float, day: date | None = None) -> dict:
    """Lokale Zeiten (Zeitzone des Rechners) für einen Kalendertag: daemmerung_beginn, aufgang, untergang, daemmerung_ende."""
    day = day or datetime.now().date()
    t0 = datetime.combine(day, dtime(0, 0)).astimezone()
    t1 = t0 + timedelta(days=1)
    return {"daemmerung_beginn": _cross(lat, lon, t0, t1, CIVIL, True),
            "aufgang": _cross(lat, lon, t0, t1, HORIZON, True),
            "untergang": _cross(lat, lon, t0, t1, HORIZON, False),
            "daemmerung_ende": _cross(lat, lon, t0, t1, CIVIL, False)}


def _hm(t: datetime | None) -> str | None:
    return t.astimezone().strftime("%H:%M") if t else None


def _dur(minutes: float) -> str:
    m = max(0, int(round(minutes)))
    return f"{m} min" if m < 60 else f"{m // 60} h {m % 60:02d} min"


def light(lat: float, lon: float, now: datetime | None = None) -> dict:
    """Lichtlage am Spot jetzt: Phase, Zeiten heute, Countdown. Alles lokal berechnet (keine API)."""
    now = (now or datetime.now().astimezone()).astimezone()
    p = position(lat, lon, now)
    today = times(lat, lon, now.date())
    tomorrow = times(lat, lon, now.date() + timedelta(days=1))
    up, down = today["aufgang"], today["untergang"]
    dusk, dawn = today["daemmerung_ende"], today["daemmerung_beginn"]
    mins = lambda t: (t - now).total_seconds() / 60 if t else None  # noqa: E731
    elev = p["hoehe"]
    r = {"hoehe": elev, "azimut": p["azimut"], "richtung": p["richtung"],
         "aufgang": _hm(up), "untergang": _hm(down), "daemmerung_beginn": _hm(dawn), "daemmerung_ende": _hm(dusk),
         "min_bis_untergang": None, "min_bis_dunkel": None, "min_bis_hell": None, "warnung": None}
    if elev >= HORIZON:
        r["phase"] = "tief" if elev < LOW_SUN else "tag"
        m_down = mins(down) if down and down > now else None
        m_dark = mins(dusk) if dusk and dusk > now else None
        r["min_bis_untergang"], r["min_bis_dunkel"] = m_down, m_dark
        if m_down is None:
            r["text"] = "☀ Sonne geht heute nicht mehr unter"
            r["kurz"] = "☀ Tag"
        else:
            r["text"] = f"☀ noch {_dur(m_down)} Licht bis Sonnenuntergang {r['untergang']}" + (
                f" · dunkel ab {r['daemmerung_ende']} (noch {_dur(m_dark)})" if m_dark is not None else "")
            r["kurz"] = f"☀ {_dur(m_down)}"
        if r["phase"] == "tief":
            r["text"] += f" · ⚠ tief stehende Sonne aus {p['richtung']} – Gegenlicht"
        if m_down is not None and m_down <= LIGHT_WARN_MIN:
            r["warnung"] = f"Sonnenuntergang in {_dur(m_down)} ({r['untergang']}) – Licht wird knapp"
        r["gegenlicht"] = r["phase"] == "tief"   # nur Hinweis, nicht ampelrelevant
    elif elev >= CIVIL:
        evening = now.hour >= 12
        r["phase"] = "daemmerung_abend" if evening else "daemmerung_morgen"
        if evening:
            m_dark = mins(dusk) if dusk and dusk > now else None
            r["min_bis_dunkel"] = m_dark
            r["text"] = "🌇 Bürgerliche Dämmerung" + (f" – noch {_dur(m_dark)} bis dunkel ({r['daemmerung_ende']})"
                                                       if m_dark is not None else "")
            r["kurz"] = f"🌇 {_dur(m_dark)}" if m_dark is not None else "🌇 Dämmerung"
            r["warnung"] = "Dämmerung – Sonne untergegangen, Sicht/Kontrast nehmen schnell ab"
        else:
            m_up = mins(up) if up and up > now else None
            r["min_bis_hell"] = m_up
            r["text"] = "🌅 Morgendämmerung" + (f" – Sonnenaufgang in {_dur(m_up)} ({r['aufgang']})" if m_up is not None else "")
            r["kurz"] = "🌅 Dämmerung"
            r["warnung"] = "Morgendämmerung – noch wenig Licht"
    else:
        r["phase"] = "nacht"
        nxt = dawn if dawn and dawn > now else tomorrow["daemmerung_beginn"]
        nup = up if up and up > now else tomorrow["aufgang"]
        r["min_bis_hell"] = mins(nup)
        r["text"] = "🌙 Nacht" + (f" – Dämmerung ab {_hm(nxt)}" if nxt else "") + (f", Sonnenaufgang {_hm(nup)}" if nup else "")
        r["kurz"] = "🌙 Nacht"
        r["warnung"] = "Nacht – Nachtflug nur mit Beleuchtung & nach geltenden Regeln (dipul/LBA)"
    for k in ("min_bis_untergang", "min_bis_dunkel", "min_bis_hell"):
        if r[k] is not None:
            r[k] = int(round(r[k]))
    return r
