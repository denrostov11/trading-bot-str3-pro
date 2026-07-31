# -*- coding: utf-8 -*-
"""S1 Charakterisierungstest: friert das AKTUELLE Erkennungsverhalten (scan_100.find_lines) auf einem
festen Realdaten-Fixture ein. Jeder spaetere Umbau der Erkennung muss identische Ergebnisse liefern
(nachgewiesene Gleichwertigkeit), BEVOR Altcode entfernt wird (MIGRATION_PLAN S1)."""
import os, sys, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FIX = os.path.join(os.path.dirname(__file__), "fixtures", "btc_4h_fixture.csv")
GOLD = os.path.join(os.path.dirname(__file__), "fixtures", "btc_4h_golden.json")


def _top(lines, s100):
    if not lines:
        return None
    l = max(lines, key=lambda x: x.score)
    return {"taps": len(l.taps), "angle": round(l.angle_deg, 1), "breaking_bar": l.breaking_bar,
            "aplus": bool(s100.is_aplus(l))}


def test_detection_matches_golden():
    import scan_100 as s100
    compat = pd.read_csv(FIX)
    compat["Time"] = pd.to_datetime(compat["Time"], utc=True)
    golden = json.load(open(GOLD, encoding="utf-8"))

    a = s100.atr(compat); piv = s100.pivots(compat)
    sup = s100.find_lines(compat, "support", a, piv)
    res = s100.find_lines(compat, "resistance", a, piv)
    got = {"bars": len(compat), "n_support": len(sup), "n_resistance": len(res),
           "top_support": _top(sup, s100), "top_resistance": _top(res, s100)}
    assert got == golden, f"Erkennung weicht vom Golden-Output ab:\n{got}\n!=\n{golden}"
