# -*- coding: utf-8 -*-
"""Trade-Chart: rendert ein 4h-Chartbild mit Trendlinien + Trade-Levels. Prueft nur, dass ein
valides, nicht-leeres PNG entsteht (Darstellungsschicht, keine Handelslogik)."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import trade_chart as TC


class FakeLine:
    def __init__(self, i0, p0, i1, p1, kind, taps, breaking_bar):
        self.i0, self.p0, self.i1, self.p1 = i0, p0, i1, p1
        self.kind, self.taps, self.breaking_bar = kind, list(taps), breaking_bar
    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def _compat(n=120):
    t0 = pd.Timestamp("2025-06-01", tz="UTC")
    rows = [{"Time": t0 + pd.Timedelta(hours=4 * i), "Open": 100 + (i % 5), "High": 102 + (i % 5),
             "Low": 98 + (i % 5), "Close": 100 + (i % 5), "Volume": 100} for i in range(n)]
    return pd.DataFrame(rows)


def test_render_trade_chart(tmp_path):
    df = _compat(120)
    action = FakeLine(10, 96, 118, 104, "support", [10, 40, 80], breaking_bar=119)   # LONG-Bruch
    safety = FakeLine(10, 108, 118, 106, "resistance", [15, 55], breaking_bar=-1)
    out = str(tmp_path / "trade.png")
    p = TC.render_trade_chart(df, "Bitcoin", "BTC-USD", action, safety, "LONG",
                              entry=104.0, stop=99.0, target=112.0, out_path=out, variant="Str.3 Pro.1")
    assert os.path.exists(p) and os.path.getsize(p) > 5000       # nicht-leeres PNG


def test_render_without_safety(tmp_path):
    df = _compat(90)
    action = FakeLine(5, 104, 88, 96, "resistance", [5, 30, 60], breaking_bar=89)
    out = str(tmp_path / "t2.png")
    p = TC.render_trade_chart(df, "X", "X-USD", action, None, "SHORT",
                              entry=96.0, stop=101.0, target=88.0, out_path=out)
    assert os.path.exists(p) and os.path.getsize(p) > 3000
