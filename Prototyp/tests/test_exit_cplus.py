# -*- coding: utf-8 -*-
"""Tests des C+-Ausstiegs (engine/exit_cplus.py): Einzelstufen, Short gespiegelt, Aufholen nach Ausfall,
Persistenz und Regression gegen die Referenzimplementierung (80 Trades aus einzeltrades_pro1.csv)."""
import os, sys, csv, json, copy
import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import exit_cplus as X          # noqa: E402
from engine import tracker as T             # noqa: E402

LINE = lambda j: 90.0                       # flache Safety Line, E=100, risk=10, ATR=5, Kosten=1
PRE = 3


def mk(rows, pre=PRE, short=False):
    """rows: (O,H,L,C) ab der Einstiegskerze (LONG-Raum); davor `pre` neutrale Kerzen weit oberhalb.
    short=True spiegelt an 200 (echte Short-Preise): p' = 200 - p, Hoch/Tief vertauscht."""
    a = [(130, 130, 130, 130)] * pre + list(rows)
    A = np.array(a, dtype=float)
    O, H, L, C = A[:, 0], A[:, 1], A[:, 2], A[:, 3]
    if short:
        O, C = 200 - O, 200 - C
        H, L = 200 - A[:, 2], 200 - A[:, 1]
    t = list(pd.date_range("2026-10-01", periods=len(A), freq="4h", tz="UTC"))
    return t, O, H, L, C


def run(rows, short=False, state=None, upto=None):
    t, O, H, L, C = mk(rows, short=short)
    n = len(O) if upto is None else upto
    line = (lambda j: 200 - 90.0) if short else LINE
    st = state if state is not None else X.new_state()
    ev = X.advance(st, "SHORT" if short else "LONG", t[:n], O[:n], H[:n], L[:n], C[:n], line, PRE,
                   200 - 100.0 if short else 100.0, 10.0, 5.0, 1.0)
    return st, ev


# ---------------------------------------------------------------- Grundausstieg
def test_close_beyond_line_exits_next_open():
    st, _ = run([(100, 105, 95, 100), (100, 102, 88, 89), (87, 90, 85, 88)])
    assert st["exit"]["outcome"] == X.OUT_LINE and st["exit"]["price"] == 87 and st["exit"]["idx"] == PRE + 2


def test_wick_below_line_does_not_exit():
    st, _ = run([(100, 105, 95, 100), (100, 102, 88, 95), (95, 99, 94, 97)])    # Docht 88 < 90, Close 95
    assert st["exit"] is None and st["pending"] is None


def test_close_signal_on_last_bar_waits_for_next_open():
    st, _ = run([(100, 105, 95, 100), (100, 102, 88, 89)])                      # Signal, naechste Kerze fehlt
    assert st["exit"] is None and st["pending"]["outcome"] == X.OUT_LINE
    t, O, H, L, C = mk([(100, 105, 95, 100), (100, 102, 88, 89), (87, 90, 85, 88)])
    ev = X.advance(st, "LONG", t, O, H, L, C, LINE, PRE, 100.0, 10.0, 5.0, 1.0)
    assert st["exit"]["price"] == 87 and ev and ev[-1]["kind"] == X.EV_EXIT


# ---------------------------------------------------------------- Notfallnetz
def test_net_intrabar_and_gap():
    st, _ = run([(100, 105, 95, 100), (100, 102, 84, 86)])                       # Netz = 85, Tief 84
    assert st["exit"]["outcome"] == X.OUT_NET and st["exit"]["price"] == 85
    st, _ = run([(100, 105, 95, 100), (80, 82, 78, 79)])                         # Luecke: Open 80 < Netz
    assert st["exit"]["outcome"] == X.OUT_NET and st["exit"]["price"] == 80


# ---------------------------------------------------------------- Stufe 2 / 3
ROWS_STAGE3 = [(100, 110, 99, 108),     # e   : Close +8 (<+15)
               (108, 120, 107, 116),    # +1  : Close 116 >= 115 -> Stufe 2, Schwelle 101
               (116, 135, 125, 130),
               (130, 131, 123, 128),
               (128, 129, 121, 126),
               (126, 127, 112, 124),    # +5  : Swing-Tief 112
               (124, 128, 118, 126),
               (126, 129, 120, 127),
               (127, 130, 122, 128),    # +8  : Swing bestaetigt -> Schwelle 109,5
               (128, 128, 105, 108),    # +9  : Close 108 < 109,5 -> Ausstieg am Open der naechsten
               (107, 110, 100, 103)]


def test_stage1_nothing_below_1_5r():
    rows = [(100, 112, 99, 105), (105, 112, 104, 108), (108, 111, 100, 106), (106, 109, 96, 100),
            (100, 108, 98, 104), (104, 110, 101, 107), (107, 111, 103, 108)]
    st, ev = run(rows)
    assert not st["stage2"] and not st["stage3"] and st["exit"] is None and st["P"] is None and ev == []


def test_stage2_sets_breakeven_plus_costs():
    st, ev = run(ROWS_STAGE3[:2])
    assert st["stage2"] and not st["stage3"] and st["P"] == 101.0              # Einstand 100 + Kosten 1
    assert [e["kind"] for e in ev] == [X.EV_STAGE2] and ev[0]["level"] == 101.0


def test_stage2_uses_close_not_wick():
    rows = [(100, 125, 99, 108), (108, 116, 107, 110)]                           # Hoch 125 (+2,5R), Close nur +8/+10
    st, _ = run(rows)
    assert not st["stage2"]


def test_stage3_swing_and_profit_close():
    st, ev = run(ROWS_STAGE3)
    assert st["stage2"] and st["stage3"]
    assert st["exit"]["outcome"] == X.OUT_PROFIT and st["exit"]["price"] == 107 and st["exit"]["idx"] == PRE + 10
    kinds = [e["kind"] for e in ev]
    assert kinds == [X.EV_STAGE2, X.EV_TRAIL, X.EV_EXIT]
    trail = ev[1]
    assert abs(trail["level"] - 109.5) < 1e-9 and trail["swing_price"] == 112


def test_stage3_needs_stage2():
    # Swing-Struktur ohne vorherige Stufe 2 (Close nie >= +15)
    rows = [(100, 112, 99, 110), (110, 114, 109, 112), (112, 130, 111, 113), (113, 118, 108, 112), (112, 118, 104, 112),
            (112, 116, 111, 113), (113, 117, 112, 114), (114, 118, 113, 114), (114, 118, 113, 114)]
    st, _ = run(rows)
    assert not st["stage2"] and not st["stage3"]


def test_pullback_below_1_atr_is_no_swing():
    rows = [(100, 110, 99, 108), (108, 120, 107, 116), (116, 121, 115, 119), (119, 122, 116, 120),
            (120, 123, 117, 121), (121, 122, 119, 120), (120, 123, 118, 121), (121, 124, 119, 122),
            (122, 125, 120, 123)]
    st, _ = run(rows)
    assert st["stage2"] and not st["stage3"] and st["P"] == 101.0                # Ruecksetzer < 1 ATR


def test_threshold_only_moves_in_profit_direction():
    st, _ = run(ROWS_STAGE3[:9])
    p = st["P"]
    # spaeter tieferes (schlechteres) Tief darf die Schwelle nicht senken
    more = ROWS_STAGE3[:9] + [(128, 129, 119, 127), (127, 129, 118, 126), (126, 130, 117, 127), (127, 130, 119, 128)]
    st2, _ = run(more)
    assert st2["P"] >= p


# ---------------------------------------------------------------- Short gespiegelt
@pytest.mark.parametrize("rows", [
    [(100, 105, 95, 100), (100, 102, 88, 89), (87, 90, 85, 88)],
    [(100, 105, 95, 100), (100, 102, 84, 86)],
    [(100, 105, 95, 100), (80, 82, 78, 79)],
    ROWS_STAGE3,
])
def test_short_is_mirror_of_long(rows):
    stl, evl = run(rows)
    sts, evs = run(rows, short=True)
    assert (stl["exit"] is None) == (sts["exit"] is None)
    if stl["exit"]:
        assert stl["exit"]["outcome"] == sts["exit"]["outcome"]
        assert stl["exit"]["idx"] == sts["exit"]["idx"]
        assert abs((200 - sts["exit"]["price"]) - stl["exit"]["price"]) < 1e-9
    assert stl["stage2"] == sts["stage2"] and stl["stage3"] == sts["stage3"]
    assert [e["kind"] for e in evl] == [e["kind"] for e in evs]
    for a, b in zip(evl, evs):
        if "level" in a:
            assert abs((200 - b["level"]) - a["level"]) < 1e-9


# ---------------------------------------------------------------- Aufholen nach Ausfall
@pytest.mark.parametrize("short", [False, True])
def test_catch_up_equals_single_run_for_every_split(short):
    full, ev_full = run(ROWS_STAGE3, short=short)
    t, O, H, L, C = mk(ROWS_STAGE3, short=short)
    for cut in range(PRE + 1, len(O)):
        st = X.new_state()
        line = (lambda j: 200 - 90.0) if short else LINE
        d = "SHORT" if short else "LONG"
        E = 100.0 if not short else 100.0
        ev1 = X.advance(st, d, t[:cut], O[:cut], H[:cut], L[:cut], C[:cut], line, PRE, E, 10.0, 5.0, 1.0)
        st = json.loads(json.dumps(st))                                            # Persistenz-Roundtrip (Ausfall)
        ev2 = X.advance(st, d, t, O, H, L, C, line, PRE, E, 10.0, 5.0, 1.0)
        assert st["exit"] == full["exit"], cut
        assert st["stage2"] == full["stage2"] and st["stage3"] == full["stage3"] and st["P"] == full["P"]
        assert [e["id"] for e in ev1 + ev2] == [e["id"] for e in ev_full]


def test_no_lookahead_future_bars_do_not_change_past():
    t, O, H, L, C = mk(ROWS_STAGE3)
    for cut in range(PRE + 1, len(O)):
        a = X.new_state()
        X.advance(a, "LONG", t[:cut], O[:cut], H[:cut], L[:cut], C[:cut], LINE, PRE, 100.0, 10.0, 5.0, 1.0)
        # Zukunft veraendern: bis `cut` muss alles identisch bleiben
        O2, H2, L2, C2 = O.copy(), H.copy(), L.copy(), C.copy()
        O2[cut:], H2[cut:], L2[cut:], C2[cut:] = 50.0, 200.0, 1.0, 150.0
        b = X.new_state()
        X.advance(b, "LONG", t[:cut], O2[:cut], H2[:cut], L2[:cut], C2[:cut], LINE, PRE, 100.0, 10.0, 5.0, 1.0)
        assert a == b


def test_closed_state_is_final_and_idempotent():
    st, _ = run(ROWS_STAGE3)
    snap = copy.deepcopy(st)
    t, O, H, L, C = mk(ROWS_STAGE3)
    assert X.advance(st, "LONG", t, O, H, L, C, LINE, PRE, 100.0, 10.0, 5.0, 1.0) == []
    assert st == snap


def test_frame_change_rebuilds_without_duplicate_events():
    st, ev = run(ROWS_STAGE3[:5])
    t, O, H, L, C = mk(ROWS_STAGE3[:5])
    st["last_time"] = "2000-01-01T00:00:00+00:00"          # Frame passt nicht mehr (z. B. Cache veraendert)
    ev2 = X.advance(st, "LONG", t, O, H, L, C, LINE, PRE, 100.0, 10.0, 5.0, 1.0)
    assert ev2 == [] and len([e for e in st["events"] if e["kind"] == X.EV_STAGE2]) == 1


def test_make_line_fn_relative_anchor():
    fn = X.make_line_fn({"d0": -10, "p0": 100.0, "d1": -2, "p1": 108.0}, signal_idx=50)
    assert abs(fn(40) - 100.0) < 1e-9 and abs(fn(48) - 108.0) < 1e-9 and abs(fn(54) - 114.0) < 1e-9


def test_result_uses_tracker_formulas():
    st, _ = run([(100, 105, 95, 100), (100, 102, 88, 89), (87, 90, 85, 88)])
    r = X.result_for_trade(st, "LONG", "fx", 5.0, 100.0, 90.0)
    assert r["status"] == "closed" and r["outcome"] == X.OUT_LINE
    slip = 2 * T.SLIP_ATR_PER_SIDE * 5.0
    exp_net = (87 - 100) / 10.0 - (slip + T.cost_fraction("fx") * (100 + 87)) / 10.0
    assert abs(r["netto_r"] - round(exp_net, 3)) < 1e-9


# ---------------------------------------------------------------- Regression gegen die Referenz (80 Trades)
ANALYSE = os.path.join(os.path.dirname(ROOT), "Analysen", "cplus_pro1")
DATA = os.path.join(ANALYSE, "daten_kopie")
CSV_PATH = os.path.join(ANALYSE, "einzeltrades_pro1.csv")


def _num(s):
    return None if s in ("", None) else float(str(s).replace(",", "."))


@pytest.mark.skipif(not (os.path.exists(CSV_PATH) and os.path.exists(os.path.join(DATA, "trades.json"))),
                    reason="Referenzdaten (Analysen/cplus_pro1) nicht vorhanden")
def test_regression_80_trades_match_reference():
    from engine import aggregate_4h

    def safe(s):
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s)

    frames = {}

    def fin(sym):
        if sym not in frames:
            df = pd.read_csv(os.path.join(DATA, "data_cache", safe(sym) + "__1h.csv"))
            frames[sym] = aggregate_4h.final_only(aggregate_4h.aggregate(df)).reset_index(drop=True)
        return frames[sym]

    trades = [t for t in json.load(open(os.path.join(DATA, "trades.json"), encoding="utf-8"))
              if t["strategy_id"] == "Str.3 Pro.1"]
    led = json.load(open(os.path.join(DATA, "ledger.json"), encoding="utf-8"))
    cand = {c["parent_signal_id"]: c for c in led["candidates"]}
    ref = {}
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            ref[(row["symbol"], row["signal_utc"])] = row
    n_checked = n_closed = 0
    for t in trades:
        key = (t["symbol"], t["signal_time"])
        if key not in ref:
            continue                                                                # pending_fill (nicht in der CSV)
        row = ref[key]
        f4 = fin(t["symbol"])
        times = pd.to_datetime(f4["Time"], utc=True)
        k = int(times[times == pd.Timestamp(t["signal_time"])].index[0])
        e = k + 1
        sn = cand[t["parent_signal_id"]]["snapshot"]
        i0, p0, i1, p1 = sn["safety_anchor"][:4]
        stop0 = float(t["stop_initial"])
        bb_then = i0 + (stop0 - p0) * (i1 - i0) / (p1 - p0) - 4 if p1 != p0 else float(k)
        d = 0 if abs(bb_then - k) < 0.4 else int(round(k - bb_then))
        bb_i = k - d
        line = X.make_line_fn({"d0": i0 - bb_i, "p0": p0, "d1": i1 - bb_i, "p1": p1}, k)
        a = float(sn["atr"])
        r_t = t.get("result") or {}
        E = float(r_t["entry_open"]) if r_t.get("entry_open") is not None else float(t["entry_price"])
        risk = abs(E - stop0)
        cost = X.cost_price_for(t["direction"], t["asset_class"], a, E)
        st = X.new_state()
        X.advance(st, t["direction"], list(times), f4["Open"].values, f4["High"].values, f4["Low"].values,
                  f4["Close"].values, line, e, E, risk, a, cost)
        res = X.result_for_trade(st, t["direction"], t["asset_class"], a, E, stop0)
        n_checked += 1
        assert res["status"] == row["C+_status"], key
        assert int(row["C+_stufe2"]) == int(st["stage2"]) and int(row["C+_stufe3"]) == int(st["stage3"]), key
        if row["C+_status"] == "closed":
            n_closed += 1
            assert res["outcome"] == row["C+_ausstieg"], key
            assert abs(res["netto_r"] - _num(row["C+_netto_r"])) < 0.0011, key
            assert abs(res["net_return_pct"] - _num(row["C+_netto_pct"])) < 0.0011, key
            assert abs(float(st["exit"]["price"]) - _num(row["C+_exit_preis"])) < 1e-4 * abs(E), key
    assert n_checked == 80, n_checked
    assert n_closed > 30
