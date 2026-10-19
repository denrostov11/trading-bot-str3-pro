# -*- coding: utf-8 -*-
"""Backtest-Treiber (Etappe A2): chronologischer Fenster-Replay je Symbol.
Validiert (synthetisch, ohne Netz): Warmup-Kerzen handeln NICHT, Fenster-Kerzen handeln,
Instrument-Sperre greift (nur EIN offener Trade je Variante), Daily wird ohne Crash eingespeist."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import backtest_run as BR
from engine.ledger import Ledger
from engine.tracker import PaperTradeStore
from engine.varstate import StateRegistry


class FakeLine:
    def __init__(self, i0, p0, i1, p1, kind, taps, breaking_bar):
        self.i0, self.p0, self.i1, self.p1 = i0, p0, i1, p1
        self.kind, self.taps, self.angle_deg = kind, list(taps), 12.0
        self.breaking_bar = breaking_bar
    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def make_1h(t0, n_hours, price=100.0):
    return pd.DataFrame([{"Time": t0 + pd.Timedelta(hours=i), "Open": price, "High": price + 0.5,
                          "Low": price - 0.5, "Close": price, "Volume": 100} for i in range(n_hours)])


def make_daily(t0, n_days, price=100.0):
    return pd.DataFrame([{"Time": t0 + pd.Timedelta(days=i), "Open": price, "High": price,
                          "Low": price, "Close": price, "Volume": 1000} for i in range(n_days)])


def _detect_every_candle(compat):
    """Feuert auf JEDER Kerze (LONG). Ziel ~106 (Pivots), Stop ~98 (Safety) -> handelbar."""
    n = len(compat); bb = n - 1
    action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)
    safety = FakeLine(0, 97, bb, 98, "support", [5, 25], breaking_bar=-1)
    return {"action": action, "safety": safety, "direction": "LONG", "atr_last": 2.0,
            "atr_series": pd.Series([2.0] * n), "pivots": ([], []),
            "pivot_prices": [106.0, 106.5], "n": n}


def test_backtest_symbol_window_vs_warmup(tmp_path):
    t0 = pd.Timestamp("2024-12-01", tz="UTC")
    h1 = make_1h(t0, 24 * 42)                          # 42 Tage stuendlich (Warmup + Fenster)
    daily = make_daily(pd.Timestamp("2024-06-01", tz="UTC"), 260)
    start = pd.Timestamp("2025-01-01", tz="UTC")
    end = pd.Timestamp("2025-01-11", tz="UTC")

    lg = Ledger(str(tmp_path / "l.json"))
    store = PaperTradeStore(str(tmp_path / "t.json"))
    state = StateRegistry(str(tmp_path / "s.json"))

    s = BR.run_symbol("X", "X-USD", "crypto", False, ["Str.3 Pro.1"], h1, daily, start, end,
                      lg, store, state, {"Str.3 Pro.1": "BE-0"}, detect_fn=_detect_every_candle)

    assert s["status"] == "OK"
    assert s["warmup_bars"] > 90 and s["window_bars"] > 0     # Historie da, Fenster vorhanden
    assert s["accepted"] > 5                                   # viele Signale im Fenster (jede Kerze)
    # Instrument-Sperre: trotz Dauer-Signal nur EIN offener Trade (flach -> schliesst nie)
    assert s["opened"] == 1
    assert len(store.trades) == 1
    tr = store.trades[0]
    assert tr.status in ("open", "pending_fill")
    # Einstieg liegt IM Fenster, nicht im Warmup
    assert pd.Timestamp(tr.signal_time) >= start


def test_backtest_no_data_quarantine(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    store = PaperTradeStore(str(tmp_path / "t.json"))
    state = StateRegistry(str(tmp_path / "s.json"))
    s = BR.run_symbol("X", "X-USD", "crypto", False, ["Str.3 Pro.1"], None, None,
                      "2025-01-01", "2026-06-30", lg, store, state, {"Str.3 Pro.1": "BE-0"})
    assert s["status"] == "NO_DATA_QUARANTINE"
