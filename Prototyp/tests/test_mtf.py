# -*- coding: utf-8 -*-
"""mtf-Paket: Woche/Monat-Aggregation, No-Look-ahead, Parameter-Skalierung, Zeit-Mapping, Top-down, C+-Spur."""
import os, sys
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mtf import data as D, params as PR, lines as L, topdown as TD, cplus_overlay as CO


def _daily(start="2026-01-05", n=70, base=100.0):
    t = pd.date_range(start, periods=n, freq="D", tz="UTC")
    o = base + np.arange(n, dtype=float)
    return D.with_end(pd.DataFrame({"Time": t, "Open": o, "High": o + 2, "Low": o - 1, "Close": o + 1, "Volume": 10.0}),
                      pd.Timedelta(days=1))


def _h1(start="2026-01-01", hours=24 * 120, base=100.0):
    t = pd.date_range(start, periods=hours, freq="h", tz="UTC")
    o = base + np.sin(np.arange(hours) / 20.0) * 5 + np.arange(hours) * 0.01
    return D.with_end(pd.DataFrame({"Time": t, "Open": o, "High": o + 0.5, "Low": o - 0.5, "Close": o + 0.1, "Volume": 5.0}),
                      pd.Timedelta(hours=1))


# ------------------------------------------------------------------ Aggregation Woche / Monat
def test_week_aggregation_ohlc_and_bounds():
    d = _daily("2026-01-05", 21)                      # Mo 05.01. ... 3 volle Wochen
    w = D.aggregate_week(d)
    assert len(w) == 3
    first = w.iloc[0]
    assert first["Time"] == pd.Timestamp("2026-01-05", tz="UTC") and first["End"] == pd.Timestamp("2026-01-12", tz="UTC")
    assert first["Open"] == d["Open"].iloc[0] and first["Close"] == d["Close"].iloc[6]
    assert first["High"] == d["High"].iloc[:7].max() and first["Low"] == d["Low"].iloc[:7].min()
    assert first["Volume"] == 70.0


def test_week_starts_monday_even_if_data_starts_midweek():
    d = _daily("2026-01-07", 10)                      # Mittwoch
    w = D.aggregate_week(d)
    assert w["Time"].iloc[0] == pd.Timestamp("2026-01-05", tz="UTC")
    assert all(t.weekday() == 0 for t in w["Time"])


def test_month_aggregation():
    d = _daily("2026-01-20", 50)                      # 20.01. .. 10.03.
    m = D.aggregate_month(d)
    assert list(m["Time"].dt.month) == [1, 2, 3]
    jan = m.iloc[0]
    assert jan["End"] == pd.Timestamp("2026-02-01", tz="UTC")
    sub = d[d["Time"] < pd.Timestamp("2026-02-01", tz="UTC")]
    assert jan["Open"] == sub["Open"].iloc[0] and jan["Close"] == sub["Close"].iloc[-1] and jan["High"] == sub["High"].max()


# ------------------------------------------------------------------ No-Look-ahead
def test_closed_until_has_no_future_bars():
    d = _daily("2026-01-05", 60)
    cut = pd.Timestamp("2026-02-10 08:00", tz="UTC")
    for df in (d, D.aggregate_week(d), D.aggregate_month(d)):
        c = D.closed_until(df, cut)
        assert (c["End"] <= cut).all()
    # laufende Woche/Monat ist NICHT abgeschlossen
    assert D.closed_until(D.aggregate_month(d), cut)["Time"].iloc[-1] < pd.Timestamp("2026-02-01", tz="UTC")
    assert D.closed_until(D.aggregate_week(d), cut)["End"].iloc[-1] <= pd.Timestamp("2026-02-10", tz="UTC")


def test_timeframes_unchanged_when_future_data_changes():
    h1, daily = _h1(), None
    daily = D.aggregate_week(_daily("2026-01-01", 120))[0:0]              # leer; Tage aus 1h bauen
    daily = D.daily_from_1h(h1)
    cut = pd.Timestamp("2026-03-10 12:00", tz="UTC")
    base = D.build_timeframes(h1, daily, cut)
    h1b, db = h1.copy(), daily.copy()
    h1b.loc[h1b["Time"] >= cut, ["Open", "High", "Low", "Close"]] = 9999.0      # Zukunft veraendern
    db.loc[db["Time"] >= cut.normalize(), ["Open", "High", "Low", "Close"]] = 9999.0
    alt = D.build_timeframes(h1b, db, cut)
    for tf in ("1h", "4h", "D", "W", "M"):
        pd.testing.assert_frame_equal(base[tf]["closed"], alt[tf]["closed"])
        assert (base[tf]["closed"]["End"] <= cut).all()
        pb, pa = base[tf]["partial"], alt[tf]["partial"]
        assert (pb is None) == (pa is None)
        if pb:
            assert pb["High"] == pa["High"] and pb["Close"] == pa["Close"] and pb["End"] > cut


def test_partial_candle_uses_only_data_up_to_cutoff():
    h1 = _h1()
    cut = pd.Timestamp("2026-03-10 12:00", tz="UTC")
    p = D.partial_candle(h1, "D", cut)
    sub = h1[(h1["Time"] >= pd.Timestamp("2026-03-10", tz="UTC")) & (h1["End"] <= cut)]
    assert p["Open"] == sub["Open"].iloc[0] and p["Close"] == sub["Close"].iloc[-1] and p["High"] == sub["High"].max()
    assert p["End"] == pd.Timestamp("2026-03-11", tz="UTC") and p["partial"]
    # am Periodenende gibt es keine unfertige Kerze mehr
    assert D.partial_candle(h1, "D", pd.Timestamp("2026-03-11 00:00", tz="UTC")) is None


# ------------------------------------------------------------------ Parameter-Skalierung
def test_scaled_params_reproduce_4h_original_and_scale_down():
    s = pytest.importorskip("scan_100")
    P4 = PR.scaled("4h")
    assert (P4.min_duration, P4.max_apex, P4.angle_bars, P4.min_spacing, P4.k) == (s.MIN_DURATION, s.MAX_APEX_BARS, s.THREE_MONTH_BARS, s.MIN_SPACING, s.PIVOT_K)
    assert P4.safety_age_months == s.MAX_SAFETY_TAP_AGE_MONTHS
    assert PR.scaled("1h").min_duration == 90
    D_, W_, M_ = PR.scaled("D"), PR.scaled("W"), PR.scaled("M")
    assert D_.min_duration > W_.min_duration > M_.min_duration >= 10
    assert D_.max_apex > W_.max_apex > M_.max_apex
    assert M_.min_duration == 12 and W_.min_duration == 26 and D_.min_duration == 60
    assert M_.k == 2 and W_.k == 3 and M_.min_spacing >= 3
    assert (D_.safety_age_months, W_.safety_age_months, M_.safety_age_months) == (16, 48, 96)


def test_scan_params_context_restores_constants():
    s = pytest.importorskip("scan_100")
    before = (s.MIN_DURATION, s.MAX_APEX_BARS, s.THREE_MONTH_BARS, s.MIN_SPACING, s.MAX_SAFETY_TAP_AGE_MONTHS, s.PIVOT_K)
    with PR.scan_params("M"):
        assert s.MIN_DURATION == 12 and s.MAX_APEX_BARS == 24 and s.PIVOT_K == 2
    assert (s.MIN_DURATION, s.MAX_APEX_BARS, s.THREE_MONTH_BARS, s.MIN_SPACING, s.MAX_SAFETY_TAP_AGE_MONTHS, s.PIVOT_K) == before


def test_param_table_has_all_columns():
    md = PR.param_table_md()
    assert "| Parameter | 4h-Original | Tag | Woche | Monat | 1h | Regel |" in md and "MIN_DURATION" in md


# ------------------------------------------------------------------ Linien: nichts erfinden
def test_no_line_when_too_little_history_or_flat_prices():
    short = D.aggregate_month(_daily("2026-01-05", 90))
    c = L.detect_context(short, "M")
    assert c.action is None and "zu wenig Historie" in c.reason
    n = 90                                              # streng steigende Preise: keine Pivots -> keine Linie
    x = np.arange(n, dtype=float)
    ramp = pd.DataFrame({"Time": pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC"), "Open": 100 + x, "High": 100.5 + x,
                         "Low": 99.5 + x, "Close": 100.2 + x, "Volume": 1.0})
    ramp["End"] = ramp["Time"] + pd.Timedelta(days=1)
    c = L.detect_context(ramp, "D")
    assert c.action is None and c.safety is None and c.reason == "keine gültige Linie nach unseren Regeln"


def test_line_bias_by_slope():
    s = pytest.importorskip("scan_100")
    up = s.Line("support", 0, 100.0, 50, 110.0); up.angle_deg = 20
    dn = s.Line("resistance", 0, 110.0, 50, 100.0); dn.angle_deg = 20
    fl = s.Line("support", 0, 100.0, 50, 100.1); fl.angle_deg = 0.5
    assert L.line_bias(up) == "up" and L.line_bias(dn) == "down" and L.line_bias(fl) == "flat"


def test_line_values_at_times_mixed_time_units():
    s = pytest.importorskip("scan_100")
    t4 = pd.Series(pd.date_range("2026-01-01", periods=10, freq="4h", tz="UTC")).astype("datetime64[s, UTC]")
    df = pd.DataFrame({"Time": t4})
    ln = s.Line("support", 0, 100.0, 9, 109.0)                  # +1 je 4h-Kerze
    q = pd.Series(pd.date_range("2026-01-01 08:00", periods=3, freq="2h", tz="UTC")).astype("datetime64[us, UTC]")
    v = L.line_values_at_times(ln, df, q)
    assert np.allclose(v, [102.0, 102.5, 103.0])
    # rechts der letzten Kerze wird fortgesetzt (Index-Verlaengerung)
    far = pd.Series([pd.Timestamp("2026-01-02 16:00", tz="UTC")])
    assert L.line_values_at_times(ln, df, far)[0] == pytest.approx(110.0, abs=1e-9)


# ------------------------------------------------------------------ Top-down
class _C:
    def __init__(self, bias, kind="support", taps=3, reason=""):
        s = pytest.importorskip("scan_100")
        self.action = None if bias is None else s.Line(kind, 0, 1.0, 5, 2.0)
        if self.action:
            self.action.taps = list(range(taps))
        self.bias, self.kind, self.reason = bias, "A+", reason or "keine gültige Linie nach unseren Regeln"


def test_topdown_counts_and_texts():
    ctx = {"M": _C("up"), "W": _C("down", "resistance"), "D": _C(None), "1h": _C("up")}
    r = TD.evaluate("LONG", ctx, signal_taps=5)
    assert r["items"]["M"]["supports"] is True and r["items"]["W"]["supports"] is False and r["items"]["D"]["supports"] is None
    assert r["count"] == 2 and r["total"] == 4                 # Monat + 4h
    assert "keine gültige Linie nach unseren Regeln" in r["items"]["D"]["text"]
    assert "widerspricht" in r["items"]["W"]["text"]
    assert "2 von 4" in TD.headline(r)
    rs = TD.evaluate("SHORT", ctx, signal_taps=5)
    assert rs["items"]["W"]["supports"] is True and rs["count"] == 2
    flat = TD.evaluate("LONG", {**ctx, "M": _C("flat")}, signal_taps=3)
    assert flat["items"]["M"]["supports"] is None


# ------------------------------------------------------------------ C+-Spur
def _bars(rows, pre=3):
    a = np.array([(130, 130, 130, 130)] * pre + list(rows), dtype=float)
    return a[:, 0], a[:, 1], a[:, 2], a[:, 3], pre


def test_cplus_trace_long_matches_reference_scenario():
    rows = [(100, 110, 99, 108), (108, 120, 107, 116), (116, 135, 125, 130), (130, 131, 123, 128), (128, 129, 121, 126),
            (126, 127, 112, 124), (124, 128, 118, 126), (126, 129, 120, 127), (127, 130, 122, 128), (128, 128, 105, 108),
            (107, 110, 100, 103)]
    O, H, Lw, C, _ = _bars(rows)
    tr = CO.trace("LONG", O, H, Lw, C, lambda i: 90.0, 3, 100.0, 10.0, 5.0, 1.0)
    assert tr["stage2_idx"] == 4 and tr["swings"][0]["pivot_idx"] == 8 and tr["swings"][0]["pivot_price"] == 112
    assert tr["profit_steps"][-1]["level"] == pytest.approx(109.5)
    assert tr["exit"]["outcome"] == "GEWINNSCHWELLE_CLOSE" and tr["exit"]["price"] == 107 and tr["exit"]["idx"] == 13


def test_cplus_trace_short_is_mirror_of_long():
    rows = [(100, 110, 99, 108), (108, 120, 107, 116), (116, 135, 125, 130), (130, 131, 123, 128), (128, 129, 121, 126),
            (126, 127, 112, 124), (124, 128, 118, 126), (126, 129, 120, 127), (127, 130, 122, 128), (128, 128, 105, 108),
            (107, 110, 100, 103)]
    O, H, Lw, C, _ = _bars(rows)
    long = CO.trace("LONG", O, H, Lw, C, lambda i: 90.0, 3, 100.0, 10.0, 5.0, 1.0)
    # Spiegelung um 260: Preis' = 260 - Preis; Hoch' = 260 - Tief; Tief' = 260 - Hoch
    k = 260.0
    sh = CO.trace("SHORT", k - O, k - Lw, k - H, k - C, lambda i: k - 90.0, 3, k - 100.0, 10.0, 5.0, 1.0)
    assert sh["exit"]["idx"] == long["exit"]["idx"] and sh["exit"]["price"] == pytest.approx(k - long["exit"]["price"])
    assert sh["stage2_idx"] == long["stage2_idx"] and len(sh["swings"]) == len(long["swings"])
