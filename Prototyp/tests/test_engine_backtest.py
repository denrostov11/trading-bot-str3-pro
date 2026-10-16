# -*- coding: utf-8 -*-
"""Backtest-Fundament (Etappe 1): historische Datenbeschaffung/Einfrieren + look-ahead-freie
Daily-Bereitstellung. Zusaetzlich der Nachweis, dass Pro.2 (Daily-EMA200) mit verdrahteten
Daily-Daten AUSWERTBAR ist (PASS/FAIL statt NOT_EVALUABLE) -> EMA200 ist backtestbar."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import backtest_data as BD
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
    return pd.DataFrame([{"Time": t0 + pd.Timedelta(hours=i), "Open": price, "High": price + 1,
                          "Low": price - 1, "Close": price, "Volume": 100 + i} for i in range(n_hours)])


def _mem_ledger():
    lg = Ledger.__new__(Ledger)
    lg.path = ":mem:"; lg.candidates = []; lg.variant_evals = []; lg._save = lambda: None
    return lg


# ---------- daily_asof: kein Look-ahead ----------
def test_daily_asof_excludes_current_and_future_days():
    days = pd.date_range("2025-01-01", periods=5, freq="D", tz="UTC")
    ddf = pd.DataFrame({"Time": days, "Open": 1, "High": 1, "Low": 1,
                        "Close": range(5), "Volume": 1})
    # Replay-Zeitpunkt 03.01. 12:00 -> nur 01.01. + 02.01. sind abgeschlossen
    sl = BD.daily_asof(ddf, pd.Timestamp("2025-01-03T12:00", tz="UTC"))
    got = list(pd.to_datetime(sl["Time"], utc=True).dt.strftime("%Y-%m-%d"))
    assert got == ["2025-01-01", "2025-01-02"]


# ---------- Einfrieren ist reproduzierbar (idempotent, ohne Netz) ----------
def test_fetch_and_freeze_idempotent(tmp_path):
    def dl1h(sym):
        return make_1h(50)
    def dl1d(sym):
        days = pd.date_range("2024-01-01", periods=300, freq="D", tz="UTC")
        return pd.DataFrame({"Time": days, "Open": 1, "High": 1, "Low": 1, "Close": 1, "Volume": 1})
    d = BD.fetch_and_freeze("BTC-USD", str(tmp_path), dl_1h=dl1h, dl_1d=dl1d)
    assert d["1h"] is not None and len(d["1h"]) == 50
    assert d["1d"] is not None and len(d["1d"]) == 300
    # zweiter Aufruf liest eingefroren -> Downloader darf gar nicht mehr aufgerufen werden
    def boom(sym):
        raise AssertionError("eingefrorene Daten duerfen nicht neu geladen werden")
    d2 = BD.fetch_and_freeze("BTC-USD", str(tmp_path), dl_1h=boom, dl_1d=boom)
    assert len(d2["1h"]) == 50 and len(d2["1d"]) == 300


def test_fetch_and_freeze_marks_missing_as_none(tmp_path):
    def dl_ok(sym):
        return make_1h(40)
    def dl_fail(sym):
        raise ValueError("keine Daten")
    d = BD.fetch_and_freeze("X", str(tmp_path), dl_1h=dl_ok, dl_1d=dl_fail)
    assert d["1h"] is not None and d["1d"] is None      # fehlend -> None (quarantaene), kein Absturz


# ---------- EMA200 ist backtestbar: Pro.2 wird mit Daily-Daten auswertbar ----------
def _daily_uptrend(n=260, start=100.0, step=0.1):
    days = pd.date_range("2025-06-01", periods=n, freq="D", tz="UTC")
    close = [start + i * step for i in range(n)]              # steigend -> Close > EMA200
    return pd.DataFrame({"Time": days, "Open": close, "High": close, "Low": close,
                         "Close": close, "Volume": 1000})


def test_pro2_ema200_evaluable_with_daily():
    lg = _mem_ledger()

    def detect(compat):
        n = len(compat); bb = n - 1
        action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)   # LONG
        safety = FakeLine(0, 85, bb, 88, "support", [5, 25], breaking_bar=-1)
        return {"action": action, "safety": safety, "direction": "LONG", "atr_last": 2.0,
                "atr_series": pd.Series([2.0] * n), "pivots": ([], []),
                "pivot_prices": [300, 301], "n": n}

    # OHNE Daily -> Pro.2 NOT_EVALUABLE
    r0 = O.analyze_instrument("X", "X-USD", "crypto", False, ["Str.3 Pro.2"], _mem_ledger(),
                              downloader=lambda s, t: make_1h(120 * 4), detect_fn=detect,
                              now=pd.Timestamp("2026-07-24", tz="UTC"))
    assert r0["variants"]["Str.3 Pro.2"] == "NOT_EVALUABLE"

    # MIT Daily (Aufwaerts) -> Pro.2 PASS (LONG in Richtung Daily-EMA200)
    r1 = O.analyze_instrument("X", "X-USD", "crypto", False, ["Str.3 Pro.2"], lg,
                              downloader=lambda s, t: make_1h(120 * 4), detect_fn=detect,
                              daily_df=_daily_uptrend(), now=pd.Timestamp("2026-07-24", tz="UTC"))
    assert r1["variants"]["Str.3 Pro.2"] == "PASS"
