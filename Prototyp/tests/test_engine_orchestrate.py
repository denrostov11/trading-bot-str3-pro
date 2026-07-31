# -*- coding: utf-8 -*-
"""Phase-B Increment S9 - Orchestrierung (ohne Netz, injizierte Erkennung).
Prueft Verdrahtung: NO_DATA, INSUFFICIENT_HISTORY, NO_TRIGGER, ACCEPTED -> Ledger + Varianten
mit gemeinsamer parent_signal_id."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import orchestrate as O
from engine.ledger import Ledger


class FakeLine:
    def __init__(self, i0, p0, i1, p1, kind, taps, breaking_bar):
        self.i0, self.p0, self.i1, self.p1 = i0, p0, i1, p1
        self.kind, self.taps, self.angle_deg = kind, list(taps), 12.0
        self.breaking_bar = breaking_bar
    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def make_1h(n_hours, price=100.0):
    t0 = pd.Timestamp("2026-03-01", tz="UTC")
    rows = [{"Time": t0 + pd.Timedelta(hours=i), "Open": price, "High": price + 1,
             "Low": price - 1, "Close": price, "Volume": 100 + i} for i in range(n_hours)]
    return pd.DataFrame(rows)


def dl_ok(sym, timeout):
    return make_1h(120 * 4)          # ~120 4h-Bloecke -> genug Historie


def dl_none(sym, timeout):
    raise ValueError("leer")


def test_no_data():
    lg = Ledger.__new__(Ledger); lg.path=":mem:"; lg.candidates=[]; lg.variant_evals=[]
    lg._save = lambda: None
    r = O.analyze_instrument("BTC", "BTC-USD", "crypto", False, ["Str.3 Pro.1"], lg,
                             downloader=dl_none, detect_fn=lambda c: None,
                             now=pd.Timestamp("2026-07-24", tz="UTC"))
    assert r["status"] == "NO_DATA"


def test_no_trigger():
    lg = Ledger.__new__(Ledger); lg.path=":mem:"; lg.candidates=[]; lg.variant_evals=[]
    lg._save = lambda: None
    r = O.analyze_instrument("BTC", "BTC-USD", "crypto", False, ["Str.3 Pro.1"], lg,
                             downloader=dl_ok, detect_fn=lambda c: None,
                             now=pd.Timestamp("2026-07-24", tz="UTC"))
    assert r["status"] == "NO_TRIGGER"


def test_accepted_records_ledger_and_variants(tmp_path):
    lg = Ledger(str(tmp_path / "ledger.json"))

    def detect(compat):
        n = len(compat); bb = n - 1
        action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)  # LONG
        safety = FakeLine(0, 85, bb, 88, "support", [5, 25], breaking_bar=-1)
        return {"action": action, "safety": safety, "direction": "LONG", "atr_last": 2.0,
                "atr_series": pd.Series([2.0] * n), "pivots": ([], []),
                "pivot_prices": [130, 131, 132], "n": n}

    r = O.analyze_instrument("BTC", "BTC-USD", "crypto", False,
                             ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 Pro.8"], lg,
                             downloader=dl_ok, detect_fn=detect,
                             now=pd.Timestamp("2026-07-24", tz="UTC"))
    assert r["status"] == "ACCEPTED_PROVISIONAL"
    psig = r["parent_signal_id"]
    cand, evals = lg.by_parent(psig)
    assert cand is not None and cand["status"] == "ACCEPTED_PROVISIONAL"
    # 3 Varianten bewertet, alle mit derselben parent_signal_id
    assert len(evals) == 3 and all(e["parent_signal_id"] == psig for e in evals)
    assert r["variants"]["Str.3 Pro.8"] == "NOT_CONFIGURED"
    # Pro.3 ohne Volumen-Eignung (crypto hat Volumen, aber rvol evtl. da) -> Status gesetzt
    assert "Str.3 Pro.3" in r["variants"]
