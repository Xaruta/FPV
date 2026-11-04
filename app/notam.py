"""NOTAM – Platzhalter.

Geprüft am 01.11.2026 (zweimal, zuletzt mit Phase 4 / v1.5): Es gibt keine freie, schlüssellose NOTAM-API
(FAA NOTAM API → HTTP 401 ohne Client-ID/Secret, aviationweather.gov hat keinen NOTAM-Endpunkt → 404,
FAA-NOTAM-Search blockt automatisierte Abrufe, EAD/DFS nur mit Login bzw. ohne API). Daher werden hier
bewusst KEINE NOTAM-Daten erzeugt. Siehe ROADMAP.md, Phase 4.
"""
from __future__ import annotations

STATUS = "folgt"
HINT = ("NOTAM: folgt. Aktuelle NOTAMs bitte offiziell prüfen – z. B. in der dipul-Karte "
        "(Ebene „Temporäre Beschränkungen“) oder über den AIS der DFS.")
LINKS = [("DFS AIS-Portal", "https://aip.dfs.de/basicAIP/")]
