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
    assert (D_.safety_age_months, W_.safety_age_months, M_.safety_age_months) == (22, 48, 96)   # Tag: 504 Kalendertage statt 360
    assert (D_.max_apex, W_.max_apex, M_.max_apex) == (180, 78, 36)                              # halbes Fenster (v2), 4h/1h: 180


def test_scan_params_context_restores_constants():
    s = pytest.importorskip("scan_100")
    before = (s.MIN_DURATION, s.MAX_APEX_BARS, s.THREE_MONTH_BARS, s.MIN_SPACING, s.MAX_SAFETY_TAP_AGE_MONTHS, s.PIVOT_K)
    with PR.scan_params("M"):
        assert s.MIN_DURATION == 12 and s.MAX_APEX_BARS == 36 and s.PIVOT_K == 2
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


# =====================================================================================================================
# v2: Zeitlimit, keine Daten, Live-Modus, Bias-Regel, Signatur-Stabilitaet
# =====================================================================================================================
import inspect, re, time
from mtf import budget as B, fastlines as FL, trade_pdf as TP, telegram_text as TT


def _ohlc(n, kind="walk", tf_days=1, seed=1, start="2024-01-01"):
    t = pd.date_range(start, periods=n, freq=f"{tf_days}D", tz="UTC")
    rng = np.random.default_rng(seed)
    if kind == "flat":
        o = np.full(n, 100.0); h = l = c = o.copy()
    else:
        o = 100 + np.cumsum(rng.normal(0, 1, n)); c = o + rng.normal(0, 0.3, n); h = np.maximum(o, c) + 1; l = np.minimum(o, c) - 1
    d = pd.DataFrame({"Time": t, "Open": o, "High": np.maximum.reduce([o, h, c]), "Low": np.minimum.reduce([o, l, c]), "Close": c, "Volume": 1.0})
    d["End"] = d["Time"] + pd.Timedelta(days=tf_days)
    return d


# ------------------------------------------------------------------ schnelle, begrenzte Linien-Suche
@pytest.mark.parametrize("tf,n,seed", [("D", 400, 1), ("W", 200, 2), ("1h", 600, 3)])
def test_fast_find_lines_identical_to_scan100(tf, n, seed):
    s = pytest.importorskip("scan_100")
    df = _ohlc(n, seed=seed)
    P = PR.scaled(tf)
    with PR.scan_params(tf):
        a = s.atr(df); piv = s.pivots(df, k=P.k)
        for kind in ("support", "resistance"):
            ref = s.find_lines(df, kind, a, piv)
            new, info = FL.find_lines_fast(df, kind, a, piv, P)          # ohne scan_params-Patch
            key = lambda l: (l.kind, l.i0, l.i1, l.p0, l.p1, tuple(l.taps), l.breaking_bar, l.duration, round(l.score, 9))
            assert [key(x) for x in ref] == [key(x) for x in new]
            assert not info["truncated"]


def test_flat_data_is_bounded_in_time_and_size():
    """Flache Daten: sehr viele gleiche Pivots. Original braucht Minuten; hier harte Obergrenze (Pivots/Kandidaten)."""
    df = _ohlc(400, "flat")
    t0 = time.time()
    c = L.detect_context(df, "D", deadline=B.Deadline(30))
    assert time.time() - t0 < 15
    assert c.extra["search"]["truncated"] and max(c.extra["search"]["pivots"]) > FL.MAX_PIVOTS
    assert c.extra["search"]["pairs"] <= FL.MAX_PIVOTS * (FL.MAX_PIVOTS - 1)       # beide Seiten zusammen


def test_search_budget_exceeded_gives_no_line_but_context():
    df = _ohlc(400)
    c = L.detect_context(df, "D", deadline=B.Deadline(0.0))
    assert c.timeout and c.action is None and c.safety is None and "Zeitbudget" in c.reason
    assert c.df is not None and len(c.df) == 360                    # Kerzen bleiben sichtbar
    r = TD.evaluate_tf("LONG", c, "D")
    assert r["supports"] is None and "Zeitbudget" in r["text"]


def test_no_data_context():
    c = L.detect_context(None, "W")
    assert c.no_data and c.action is None and c.reason == "keine Daten"
    c = L.detect_context(D.empty_frame(), "M")
    assert c.no_data
    r = TD.evaluate_tf("SHORT", c, "M")
    assert r["supports"] is None and "keine Daten" in r["text"] and r["verdict"] == "neutral"


# ------------------------------------------------------------------ Bias-Regel (Struktur + Lage + Bruch)
def test_structure_rule():
    st = TD.structure
    assert st([100, 110, 120], [90, 95, 100], 0.1)[0] == 2
    assert st([120, 110, 100], [100, 95, 90], 0.1)[0] == -2
    assert st([100, 110, 120], [90, 90.05, 90.0], 0.1)[0] == 1              # Tiefs innerhalb 0,1 ATR = gleich
    assert st([120, 110, 100], [90, 90, 90], 0.1)[0] == -1
    assert st([100, 110, 120], [100, 95, 90], 0.1)[0] == 0                  # Ausweitung
    assert st([120, 110, 100], [90, 95, 100], 0.1)[0] == 0                  # Verengung
    assert st([100], [90, 95], 0.1)[0] == 0 and "zu wenige" in st([100], [90, 95], 0.1)[1]


def test_position_and_break_rule():
    pos = TD.position
    assert pos({"bias": "up"}, None)[0] == 1 and pos({"bias": "flat"}, None)[0] == 1
    assert pos({"bias": "down"}, None)[0] == 0                              # fallende Unterstuetzung zaehlt nicht
    assert pos(None, {"bias": "down"})[0] == -1 and pos(None, {"bias": "flat"})[0] == -1
    assert pos(None, {"bias": "up"})[0] == 0                                # steigender Widerstand zaehlt nicht
    assert pos({"bias": "up"}, {"bias": "down"})[0] == 0                    # Keil/Range
    assert TD.line_break({"kind": "resistance", "bars_ago": 2}, "W")[0] == 1
    assert TD.line_break({"kind": "support", "bars_ago": 0}, "D")[0] == -1
    assert TD.line_break(None, "D") == (0, "")


def _inp(highs, lows, sup=None, res=None, brk=None):
    return {"highs": highs, "lows": lows, "tol": 0.1, "atr": 1.0, "last": 100.0, "support": sup, "resistance": res, "break": brk}


def test_assess_thresholds_and_verdicts():
    up = TD.assess(_inp([100, 110, 120], [90, 95, 100], sup={"bias": "up", "taps": 3}), "M")
    assert up["score"] == 3 and up["bias"] == "up"
    # Struktur allein (+2) reicht fuer Trend; Lage allein (+1) nicht
    assert TD.assess(_inp([100, 110, 120], [90, 95, 100]), "W")["bias"] == "up"
    assert TD.assess(_inp([100, 100, 100], [90, 90, 90], sup={"bias": "up"}), "W")["bias"] == "neutral"
    # Struktur +2 gegen Widerstand (-1) = +1 -> neutral
    assert TD.assess(_inp([100, 110, 120], [90, 95, 100], res={"bias": "down"}), "D")["bias"] == "neutral"
    # Lage + Bruch (+1 +1) = Trend
    both = TD.assess(_inp([100, 100, 100], [90, 90, 90], sup={"bias": "flat"}, brk={"kind": "resistance", "bars_ago": 1}), "D")
    assert both["score"] == 2 and both["bias"] == "up"
    down = TD.assess(_inp([120, 110, 100], [100, 95, 90], res={"bias": "down"}), "M")
    assert down["bias"] == "down" and down["score"] == -3


def _ctx_with(inputs, tf="M", action=True, reason=""):
    s = pytest.importorskip("scan_100")
    c = L.Ctx(tf=tf)
    c.extra["bias_in"] = inputs
    if action:
        c.action = s.Line("support", 0, 1.0, 5, 2.0); c.action.taps = [0, 1, 2]
    c.reason = reason
    return c


def test_evaluate_long_short_mirror_with_text_and_neutral():
    upc = _ctx_with(_inp([100, 110, 120], [90, 95, 100], sup={"bias": "up", "taps": 3}), "M")
    dnc = _ctx_with(_inp([120, 110, 100], [100, 95, 90], res={"bias": "down", "taps": 3}), "W")
    neu = _ctx_with(_inp([100, 100, 100], [90, 90, 90]), "D")
    ctx = {"M": upc, "W": dnc, "D": neu, "1h": upc}
    rl = TD.evaluate("LONG", ctx, signal_taps=5)
    it = rl["items"]
    assert (it["M"]["supports"], it["W"]["supports"], it["D"]["supports"]) == (True, False, None)
    assert (it["M"]["verdict"], it["W"]["verdict"], it["D"]["verdict"]) == ("stützt", "widerspricht", "neutral")
    assert rl["count"] == 2 and rl["neutral"] == 1 and rl["against"] == 1 and "2 von 4" in TD.headline(rl)
    # Begruendung: ein Satz mit Punkten und den Teilregeln
    assert "höhere Hochs und höhere Tiefs" in it["M"]["text"] and "(+3)" in it["M"]["text"] and "steigender Unterstützung" in it["M"]["text"]
    assert "tiefere Hochs und tiefere Tiefs" in it["W"]["text"] and "fallendem Widerstand" in it["W"]["text"]
    assert it["1h"]["supports"] is None and "nicht mitgezählt" in it["1h"]["text"]            # 1h nur zur Verfeinerung
    rs = TD.evaluate("SHORT", ctx, signal_taps=5)
    assert (rs["items"]["M"]["supports"], rs["items"]["W"]["supports"]) == (False, True) and rs["count"] == 2


def test_bias_inputs_from_real_lines_are_causal():
    """Die Bias-Eingaben entstehen nur aus abgeschlossenen Kerzen: Aenderung NACH dem Fenster aendert nichts."""
    df = _ohlc(400, seed=5)
    a = L.detect_context(df, "D")
    df2 = pd.concat([df, _ohlc(5, seed=9, start="2025-03-01")], ignore_index=True)
    b = L.detect_context(df2.iloc[:400], "D")
    assert a.extra["bias_in"] == b.extra["bias_in"]
    assert set(a.extra["bias_in"]) == {"highs", "lows", "tol", "atr", "last", "support", "resistance", "break"}
    assert len(a.extra["bias_in"]["highs"]) <= L.N_SWINGS


# ------------------------------------------------------------------ Trade-PDF: Live-Modus, keine Daten, Zeitlimit
def _synthetic(hours=24 * 70, signal="2026-03-05T08:00:00+00:00"):
    t = pd.date_range("2026-01-01", periods=hours, freq="h", tz="UTC")
    rng = np.random.default_rng(7)
    o = 100 + np.cumsum(rng.normal(0, 0.15, hours))
    h1 = D.with_end(pd.DataFrame({"Time": t, "Open": o, "High": o + 0.2, "Low": o - 0.2, "Close": o + rng.normal(0, 0.05, hours), "Volume": 1.0}),
                    pd.Timedelta(hours=1))
    trade = {"symbol": "TEST-USD", "direction": "LONG", "signal_time": signal, "strategy_id": "Str.3 Pro.1", "asset_class": "crypto",
             "stop_initial": 98.0, "target": 103.0, "entry_price": 100.5, "entry_time": "2026-03-05T12:00:00+00:00",
             "parent_signal_id": "PSIG-test"}
    return h1, trade


def _pages(path):
    return len(re.findall(rb"/Type /Page(?!s)", open(path, "rb").read()))


def test_live_mode_no_outcome_no_data_pdf_and_texts(tmp_path):
    """Live: kein outcome, keine C+-Auswertung, keine Tages-/Snapshot-Daten -> PDF mit 3 Seiten entsteht trotzdem."""
    h1, trade = _synthetic()
    live = {"price": 101.2, "time": "2026-03-05T13:00:00+00:00"}
    A = TP.analyse(trade, None, h1, None, 0.0005, c_plus={}, live_info=live)
    assert A["post"] is None and A["cplus"] is None and A["ist"] is None
    assert A["ctxs"]["M"].no_data and A["ctxs"]["W"].no_data and A["ctxs"]["D"].no_data
    assert any("M: keine Daten" in w for w in A["warnings"])
    assert A["target"] is None and A["c_plus"]["stage2_r"] == 1.5                         # C+: kein festes Ziel
    assert A["stage2_price"] == pytest.approx(A["E"] + 1.5 * A["risk"])
    out = str(tmp_path / "live.pdf")
    desc = TT.description(A)
    TP.make_trade_pdf(out, A, desc)
    assert os.path.getsize(out) < 1_000_000 and _pages(out) == 3
    assert not os.path.exists(out + ".part")
    # Beschreibung/Telegram: alle geforderten Angaben
    tg = TT.telegram_draft(A)
    for s_ in ("Str.3 Pro.1", "TEST-USD", "LONG", "05.03.2026 13:00 MEZ", "100,5", "98", "kein festes Ziel", "C+", "+1,5R",
               "1R = ", "ATR", "Top-down:", "Grund:", "Aktuell: Kurs 101,2", "Paper-Trading - keine echte Order"):
        assert s_ in tg, s_
    assert len(tg) <= TT.TG_LIMIT
    for s_ in ("Schluss 05.03.2026 13:00 MEZ", "gebucht", "kein festes Ziel", "Aktuell", "Top-down", "Paper-Trading"):
        assert s_ in desc, s_
    assert "MUSTER" not in desc and "MUSTER" not in tg


def test_live_info_derived_values_and_optional():
    h1, trade = _synthetic()
    A = TP.analyse(trade, None, h1, None, 0.0005)
    assert A["live_info"] is None and "Aktuell" not in TT.description(A)                  # ohne live_info nichts erfunden
    assert A["target"] == 103.0 and "Ziel: 103" in TT.telegram_draft(A)
    A = TP.analyse(trade, None, h1, None, 0.0005, live_info={"price": 101.5})
    li = A["live_info"]
    assert li["r_now"] == pytest.approx((101.5 - 100.5) / 2.5) and li["dist_stop"] == pytest.approx(3.5) and li["dist_target"] == pytest.approx(1.5)
    short = dict(trade, direction="SHORT", stop_initial=103.0, target=97.0)
    li = TP.analyse(short, None, h1, None, 0.0005, live_info={"price": 99.5})["live_info"]
    assert li["r_now"] == pytest.approx(0.4) and li["dist_stop"] == pytest.approx(3.5)


def test_pending_entry_uses_signal_close_and_marks_expected():
    h1, trade = _synthetic()
    pend = dict(trade, entry_price=0.0, entry_time="", status="pending_fill")
    A = TP.analyse(pend, None, h1, None, 0.0005)
    assert not A["entry_booked"] and A["E"] == pytest.approx(float(A["f4"]["Close"].iloc[-1]))
    assert "erwartet" in TT.telegram_draft(A)


def test_missing_signal_candle_still_makes_pdf(tmp_path):
    h1, trade = _synthetic()
    late = dict(trade, signal_time="2026-04-20T08:00:00+00:00")                            # nach den vorhandenen Daten
    A = TP.analyse(late, None, h1, None, 0.0005)
    assert not A["f4_ok"] and any("Signalkerze" in w for w in A["warnings"])
    out = str(tmp_path / "x.pdf")
    TP.make_trade_pdf(out, A, TT.description(A))
    assert _pages(out) == 3


def test_empty_inputs_do_not_raise_in_build_timeframes():
    for h1, daily in ((None, None), (D.empty_frame(), D.empty_frame())):
        tfs = D.build_timeframes(h1, daily, pd.Timestamp("2026-03-05 08:00", tz="UTC"))
        assert set(tfs) == {"1h", "4h", "D", "W", "M"}
        assert all(len(v["closed"]) == 0 and v["partial"] is None for v in tfs.values())


def test_total_time_limit_raises_and_leaves_no_file(tmp_path):
    h1, trade = _synthetic()
    with pytest.raises(B.MtfTimeout):
        TP.analyse(trade, None, h1, None, 0.0005, max_seconds=0.0)                         # Limit sofort erreicht
    A = TP.analyse(trade, None, h1, None, 0.0005)
    out = str(tmp_path / "t.pdf")
    A["max_seconds"], A["elapsed"] = 5.0, 5.5                                              # Analyse hat das Budget schon verbraucht
    with pytest.raises(B.MtfTimeout):
        TP.make_trade_pdf(out, A, "x")
    with pytest.raises(B.MtfTimeout):
        TP.make_trade_pdf(out, A, "x", max_seconds=0.0)
    assert not os.path.exists(out) and not os.path.exists(out + ".part")
    A["elapsed"] = 0.0
    TP.make_trade_pdf(out, A, "x", max_seconds=60)                                         # mit Budget klappt es
    assert os.path.exists(out)


def test_default_time_limit_is_60_seconds():
    assert B.TOTAL_SECONDS == 60.0 and B.PER_TF_SECONDS <= 10
    h1, trade = _synthetic()
    assert TP.analyse(trade, None, h1, None, 0.0005)["max_seconds"] == 60.0


def test_make_pdf_aborts_between_pages_when_budget_runs_out(tmp_path, monkeypatch):
    """Budget laeuft WAEHREND der Erzeugung ab -> MtfTimeout nach der laufenden Seite, keine Teildatei."""
    h1, trade = _synthetic()
    A = TP.analyse(trade, None, h1, None, 0.0005)
    real = TP.draw_chart

    def slow(ax, spec):
        time.sleep(0.4)
        return real(ax, spec)
    monkeypatch.setattr(TP, "draw_chart", slow)
    out = str(tmp_path / "slow.pdf")
    t0 = time.time()
    with pytest.raises(B.MtfTimeout):
        TP.make_trade_pdf(out, A, "x", max_seconds=1.0)
    assert time.time() - t0 < 4 and not os.path.exists(out) and not os.path.exists(out + ".part")


def test_chart_error_does_not_destroy_pdf(tmp_path, monkeypatch):
    h1, trade = _synthetic()
    A = TP.analyse(trade, None, h1, None, 0.0005)
    real = TP.draw_chart

    def boom(ax, spec):
        if spec["tf"] == "W":
            raise RuntimeError("kaputt")
        return real(ax, spec)
    monkeypatch.setattr(TP, "draw_chart", boom)
    out = str(tmp_path / "e.pdf")
    TP.make_trade_pdf(out, A, "x")
    assert _pages(out) == 3 and any("W: Chart nicht darstellbar" in w for w in A["warnings"])


# ------------------------------------------------------------------ Signatur-Stabilitaet (Aufrufer: anderer Agent)
def test_public_signatures_are_backward_compatible():
    sa = inspect.signature(TP.analyse)
    assert list(sa.parameters)[:5] == ["trade", "snapshot", "h1", "daily", "fee_fraction"]
    for name in ("c_plus", "live_info", "muster", "max_seconds"):
        p = sa.parameters[name]
        assert p.default is None or p.default is False
        assert p.kind is inspect.Parameter.KEYWORD_ONLY
    sm = inspect.signature(TP.make_trade_pdf)
    assert list(sm.parameters)[:3] == ["out_path", "A", "description"]
    assert sm.parameters["label"].default is None and sm.parameters["max_seconds"].default is None
    assert list(inspect.signature(TP.add_outcome).parameters)[:2] == ["A", "ist"]
    for fn in (TT.description, TT.telegram_draft):
        assert list(inspect.signature(fn).parameters) == ["A"]
    assert TT.telegram_text is TT.telegram_draft
    assert list(inspect.signature(L.detect_context).parameters)[:2] == ["df_closed", "tf"]
    assert list(inspect.signature(TD.evaluate).parameters)[:3] == ["direction", "ctxs", "signal_line_kind"]
    assert list(inspect.signature(D.load_daily).parameters)[:2] == ["symbol", "h1"]


# ------------------------------------------------------------------ Zeit, Cache
def test_german_time_dst_boundaries():
    f = TP.fde_de
    assert f("2026-08-17 08:00") == "17.08.2026 10:00 MESZ"
    assert f("2026-01-15 08:00") == "15.01.2026 09:00 MEZ"
    assert f("2026-03-29 00:59") == "29.03.2026 01:59 MEZ" and f("2026-03-29 01:00") == "29.03.2026 03:00 MESZ"
    assert f("2026-10-25 00:59") == "25.10.2026 02:59 MESZ" and f("2026-10-25 01:00") == "25.10.2026 02:00 MEZ"


def test_cache_dir_configurable_and_failed_fetch_not_repeated(tmp_path, monkeypatch):
    calls = []

    def fail(sym):
        calls.append(sym)
        return None
    d1, src = D.load_daily("XYZ-USD", cache_dir=str(tmp_path / "c"), frozen_dir=str(tmp_path / "f"), fetch_fn=fail)
    assert d1 is None and src == "keine" and len(calls) == 1
    D.load_daily("XYZ-USD", cache_dir=str(tmp_path / "c"), frozen_dir=str(tmp_path / "f"), fetch_fn=fail)
    assert len(calls) == 1                                                                 # Yahoo sparsam: kein Wiederholen
    good = _ohlc(300).drop(columns="End").set_index("Time")
    d2, src = D.load_daily("ABC-USD", cache_dir=str(tmp_path / "c2"), frozen_dir=str(tmp_path / "f"), fetch_fn=lambda s: good)
    assert src == "yahoo_max" and len(d2) == 300 and os.path.exists(tmp_path / "c2" / "ABC-USD__1d.csv")
    d3, src = D.load_daily("ABC-USD", cache_dir=str(tmp_path / "c2"), fetch_fn=fail)
    assert src == "mtf_cache" and len(d3) == 300
    monkeypatch.setattr(D, "MTF_CACHE", str(tmp_path / "c3"))
    assert D.set_cache_dir(str(tmp_path / "c4")) == str(tmp_path / "c4") and D.MTF_CACHE == str(tmp_path / "c4")


def test_load_daily_extends_stale_cache_with_1h(tmp_path):
    h1 = _synthetic(hours=24 * 70)[0]
    old = _ohlc(30, start="2026-01-01").drop(columns="End")
    os.makedirs(tmp_path / "c")
    old.to_csv(tmp_path / "c" / "S__1d.csv", index=False)
    d, src = D.load_daily("S", h1=h1, cache_dir=str(tmp_path / "c"))
    assert src == "mtf_cache" and d["End"].iloc[-1] > pd.Timestamp("2026-02-15", tz="UTC") and d["Time"].is_monotonic_increasing
    assert not d["Time"].duplicated().any()


# ------------------------------------------------------------------ Integration mit echten Muster-Daten (falls vorhanden)
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "Analysen", "cplus_pro1", "daten_kopie")


@pytest.mark.skipif(not (os.path.exists(os.path.join(_SRC, "trades.json")) and os.path.exists(os.path.join(D.MTF_CACHE, "SOL-USD__1d.csv"))),
                    reason="Muster-Daten nicht vorhanden")
def test_real_sample_sol_pdf_under_limits(tmp_path):
    import json
    trades = [t for t in json.load(open(os.path.join(_SRC, "trades.json"), encoding="utf-8")) if t["strategy_id"] == "Str.3 Pro.1"]
    cand = {c["parent_signal_id"]: c for c in json.load(open(os.path.join(_SRC, "ledger.json"), encoding="utf-8"))["candidates"]}
    t = next(x for x in trades if x["symbol"] == "SOL-USD" and x["signal_time"].startswith("2026-08-17T04"))
    h1 = D.load_1h(os.path.join(_SRC, "data_cache", "SOL-USD__1h.csv"))
    daily, _ = D.load_daily("SOL-USD", h1=h1, allow_fetch=False)
    t0 = time.time()
    A = TP.analyse(t, cand[t["parent_signal_id"]]["snapshot"], h1, daily, 0.0005)
    out = str(tmp_path / "sol.pdf")
    TP.make_trade_pdf(out, A, TT.description(A))
    assert time.time() - t0 < 60 and os.path.getsize(out) < 1_000_000 and _pages(out) == 3
    assert A["action"] is not None and A["safety"] is not None and A["f4_ok"]
    assert A["td"]["items"]["M"]["verdict"] in ("stützt", "neutral", "widerspricht")


# ------------------------------------------------------------------ keine globale Veraenderung von scan_100 (Datenintegritaet)
@pytest.mark.parametrize("tf,n", [("D", 420), ("W", 220), ("M", 90), ("1h", 700)])
@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_context_selection_identical_to_scan100_reference(tf, n, seed):
    """detect_context (parametrisiert, ohne scan_100-Konstanten zu patchen) waehlt Action und Safety wie die kanonischen
    scan_100-Funktionen mit gepatchten Konstanten (Referenz)."""
    s = pytest.importorskip("scan_100")
    df = _ohlc(n, seed=seed, tf_days=1)
    P = PR.scaled(tf)
    ctx = L.detect_context(df, tf)
    work = df.tail(P.window).reset_index(drop=True)
    if len(df) < P.min_bars:
        pytest.skip("zu wenig Historie fuer diesen Zeitrahmen")
    with PR.scan_params(tf):
        a = s.atr(work); piv = s.pivots(work, k=P.k)
        sup = s.find_lines(work, "support", a, piv); res = s.find_lines(work, "resistance", a, piv)
        nn = len(work); last = float(work["Close"].iloc[-1]); al = max(float(a.iloc[-1]), 1e-12)
        ok = [l for l in sup + res if l.breaking_bar < 0 and ((l.kind == "support" and l.value_at(nn - 1) <= last) or
                                                             (l.kind == "resistance" and l.value_at(nn - 1) >= last))]
        dist = lambda l: abs(l.value_at(nn - 1) - last) / al
        aplus = [l for l in ok if s.is_aplus(l)]
        act = min(aplus, key=lambda l: (dist(l), -l.score)) if aplus else (max(ok, key=lambda l: (l.i1, -dist(l))) if ok else None)
        saf = s.pick_safety(act, res if act.kind == "support" else sup, work, a) if act is not None else None
    key = lambda l: None if l is None else (l.kind, l.i0, l.i1, l.p0, l.p1, tuple(l.taps))
    assert key(ctx.action) == key(act) and key(ctx.safety) == key(saf)


def test_detection_never_patches_scan100_constants():
    """Waehrend der Analyse darf KEIN Attribut von scan_100 gesetzt werden (der Engine-Code im selben Prozess sieht sonst
    zeitweise fremde Werte)."""
    import types
    s = pytest.importorskip("scan_100")

    class Guard(types.ModuleType):
        def __setattr__(self, name, value):
            raise AssertionError(f"scan_100.{name} wurde veraendert")
    s.__class__ = Guard
    try:
        for tf, n in (("D", 420), ("W", 220), ("M", 90), ("1h", 700)):
            L.detect_context(_ohlc(n, seed=2), tf)
        h1, trade = _synthetic()
        TP.analyse(trade, None, h1, None, 0.0005)
    finally:
        types.ModuleType.__setattr__(s, "__class__", types.ModuleType)
