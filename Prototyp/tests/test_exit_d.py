# -*- coding: utf-8 -*-
"""Variante "Str.3 D" (Docht-Stop, am Zwischentief nachgezogen): Einheitentests, Short gespiegelt, Aufholen nach Ausfall,
Zyklus-Integration, Meldungen, Bericht und Regression gegen die D-Spalten der 80 Referenz-Trades."""
import os, sys, csv, json, copy
import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from engine import exit_d as XD            # noqa: E402
from engine import exit_cplus as XC        # noqa: E402
from engine import cycle as CY             # noqa: E402
from engine import tracker as T            # noqa: E402
from engine import variants as VAR         # noqa: E402
from engine.varstate import StateRegistry  # noqa: E402

LINE = lambda j: 90.0                       # flache Safety Line; E=100, risk=10, ATR=5 -> Linien-Stop 89,5
PRE = 3


def mk(rows, pre=PRE, short=False):
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
    st = state if state is not None else XD.new_state()
    ev = XD.advance(st, "SHORT" if short else "LONG", t[:n], O[:n], H[:n], L[:n], C[:n], line, PRE, 100.0, 10.0, 5.0)
    return st, ev


ROWS_SWING = [(100, 110, 99, 108), (108, 120, 107, 116), (116, 135, 125, 130), (130, 131, 123, 128),
              (128, 129, 121, 126), (126, 127, 112, 124), (124, 128, 118, 126), (126, 129, 120, 127),
              (127, 130, 122, 128), (128, 128, 105, 108), (107, 110, 100, 103)]
# Swing-Struktur OHNE +1,5R (Schluss nie >= 115): bei C+ gibt es keine Stufe 3, bei D wird trotzdem nachgezogen
ROWS_NO_STAGE2 = [(100, 112, 99, 110), (110, 114, 109, 112), (112, 130, 111, 113), (113, 118, 108, 112), (112, 118, 104, 112),
                  (112, 116, 111, 113), (113, 117, 112, 114), (114, 118, 113, 114), (114, 118, 113, 114)]


def test_wick_through_the_stop_triggers_executed_at_stop_price():
    st, ev = run([(100, 105, 95, 100), (100, 102, 89.4, 95)])                       # Docht 89,4 <= Stop 89,5, Schluss 95
    assert st["exit"]["outcome"] == XD.OUT_STOP and st["exit"]["price"] == 89.5 and st["exit"]["idx"] == PRE + 1
    assert [e["kind"] for e in ev] == [XC.EV_EXIT]


def test_no_touch_no_exit():
    st, ev = run([(100, 105, 95, 100), (100, 102, 89.6, 95), (95, 99, 94, 97)])
    assert st["exit"] is None and ev == []


def test_gap_beyond_stop_executes_at_open():
    st, _ = run([(100, 105, 95, 100), (80, 82, 78, 79)])
    assert st["exit"]["price"] == 80 and st["exit"]["outcome"] == XD.OUT_STOP


def test_trailing_at_confirmed_swing_then_stop():
    st, ev = run(ROWS_SWING)
    assert st["stage3"] and st["exit"]["outcome"] == XD.OUT_STOP
    assert abs(st["exit"]["price"] - 109.5) < 1e-9 and st["exit"]["idx"] == PRE + 9          # Tief 105 beruehrt Stop 109,5
    trail = [e for e in ev if e["kind"] == XC.EV_TRAIL]
    # Tief 99 (-> 96,5), dann das hoehere Tief 112 (-> 109,5); 107 ist kein Fraktal (99 liegt davor)
    assert [round(e["level"], 6) for e in trail] == [96.5, 109.5] and trail[1]["swing_price"] == 112


def test_swing_trailing_needs_no_stage2():
    st, ev = run(ROWS_NO_STAGE2)
    assert st["stage3"] and abs(st["SW"] - 101.5) < 1e-9 and st["exit"] is None            # 104 - 0,5 ATR
    c = XC.new_state()
    t, O, H, L, C = mk(ROWS_NO_STAGE2)
    XC.advance(c, "LONG", t, O, H, L, C, LINE, PRE, 100.0, 10.0, 5.0, 1.0)
    assert not c["stage2"] and not c["stage3"]                                               # C+ zieht hier NICHT nach


def test_pullback_below_1_atr_is_no_swing():
    rows = [(100.5 + i, 103 + i, 100 + i, 102 + i) for i in range(10)]                  # steigend, Ruecksetzer je Kerze nur 3 < 5
    st, _ = run(rows)
    assert not st["stage3"] and st["SW"] is None


def test_stop_only_moves_in_profit_direction():
    st, _ = run(ROWS_SWING[:9])
    sw = st["SW"]
    more = ROWS_SWING[:9] + [(128, 129, 119, 127), (127, 129, 118, 126), (126, 130, 117, 127), (127, 130, 119, 128)]
    st2, _ = run(more)
    assert st2["SW"] >= sw


def test_no_fixed_target_runs_far_beyond_old_targets():
    rows = [(100 + 10 * i, 100 + 10 * i + 12, 100 + 10 * i - 2, 100 + 10 * i + 10) for i in range(1, 12)]
    st, _ = run(rows)
    assert st["exit"] is None                                                                # kein Ziel -> laeuft weiter


@pytest.mark.parametrize("rows", [
    [(100, 105, 95, 100), (100, 102, 89.4, 95)],
    [(100, 105, 95, 100), (80, 82, 78, 79)],
    ROWS_SWING, ROWS_NO_STAGE2,
])
def test_short_is_mirror_of_long(rows):
    stl, evl = run(rows)
    sts, evs = run(rows, short=True)
    assert (stl["exit"] is None) == (sts["exit"] is None)
    if stl["exit"]:
        assert stl["exit"]["idx"] == sts["exit"]["idx"] and stl["exit"]["outcome"] == sts["exit"]["outcome"]
        assert abs((200 - sts["exit"]["price"]) - stl["exit"]["price"]) < 1e-9
    assert stl["stage3"] == sts["stage3"]
    assert [e["kind"] for e in evl] == [e["kind"] for e in evs]
    for a, b in zip(evl, evs):
        if "level" in a:
            assert abs((200 - b["level"]) - a["level"]) < 1e-9


@pytest.mark.parametrize("short", [False, True])
def test_catch_up_equals_single_run_for_every_split(short):
    full, ev_full = run(ROWS_SWING, short=short)
    t, O, H, L, C = mk(ROWS_SWING, short=short)
    line = (lambda j: 200 - 90.0) if short else LINE
    d = "SHORT" if short else "LONG"
    for cut in range(PRE + 1, len(O)):
        st = XD.new_state()
        ev1 = XD.advance(st, d, t[:cut], O[:cut], H[:cut], L[:cut], C[:cut], line, PRE, 100.0, 10.0, 5.0)
        st = json.loads(json.dumps(st))                                          # Persistenz-Roundtrip (Ausfall)
        ev2 = XD.advance(st, d, t, O, H, L, C, line, PRE, 100.0, 10.0, 5.0)
        assert st["exit"] == full["exit"] and st["SW"] == full["SW"], cut
        assert [e["id"] for e in ev1 + ev2] == [e["id"] for e in ev_full], cut


def test_no_lookahead():
    t, O, H, L, C = mk(ROWS_SWING)
    for cut in range(PRE + 1, len(O)):
        a = XD.new_state()
        XD.advance(a, "LONG", t[:cut], O[:cut], H[:cut], L[:cut], C[:cut], LINE, PRE, 100.0, 10.0, 5.0)
        O2, H2, L2, C2 = O.copy(), H.copy(), L.copy(), C.copy()
        O2[cut:], H2[cut:], L2[cut:], C2[cut:] = 50.0, 200.0, 1.0, 150.0
        b = XD.new_state()
        XD.advance(b, "LONG", t[:cut], O2[:cut], H2[:cut], L2[:cut], C2[:cut], LINE, PRE, 100.0, 10.0, 5.0)
        assert a == b


def test_closed_state_final_and_frame_change_rebuild():
    st, _ = run(ROWS_SWING)
    snap = copy.deepcopy(st)
    t, O, H, L, C = mk(ROWS_SWING)
    assert XD.advance(st, "LONG", t, O, H, L, C, LINE, PRE, 100.0, 10.0, 5.0) == [] and st == snap
    st, _ = run(ROWS_SWING[:5])
    st["last_time"] = "2000-01-01T00:00:00+00:00"
    t, O, H, L, C = mk(ROWS_SWING[:5])
    assert XD.advance(st, "LONG", t, O, H, L, C, LINE, PRE, 100.0, 10.0, 5.0) == []     # Neuaufbau ohne Doppel-Ereignisse


def test_result_uses_tracker_formulas_and_no_cplus_keys():
    st, _ = run([(100, 105, 95, 100), (100, 102, 89.4, 95)])
    r = XD.result_for_trade(st, "LONG", "fx", 5.0, 100.0, 90.0)
    slip = 2 * T.SLIP_ATR_PER_SIDE * 5.0
    exp = (89.5 - 100) / 10.0 - (slip + T.cost_fraction("fx") * (100 + 89.5)) / 10.0
    assert r["status"] == "closed" and r["outcome"] == "STOP_INTRABAR" and abs(r["netto_r"] - round(exp, 3)) < 1e-9
    assert "cplus_stage2" not in r and r["d_swing"] is False


def test_levels_current_stop():
    st, _ = run(ROWS_SWING[:9])
    stop, net, who = XD.current_levels(st, "LONG", LINE, PRE + 9, 5.0)
    assert abs(stop - 109.5) < 1e-9 and net is None and who == "STOP"
    stop, _, _ = XD.current_levels(XD.new_state(), "SHORT", lambda j: 110.0, 5, 5.0)
    assert abs(stop - 110.5) < 1e-9


# ======================================================================== Zyklus-Integration
SIG = "2026-07-01T00:00:00+00:00"
BE = {"Str.3 Pro.1": "BE-0", "Str.3 D": "D"}


def _compat(rows, start="2026-07-01T00:00"):
    times = list(pd.date_range(start, periods=len(rows), freq="4h", tz="UTC"))
    return pd.DataFrame({"Time": times, "Open": [r[0] for r in rows], "High": [r[1] for r in rows],
                         "Low": [r[2] for r in rows], "Close": [r[3] for r in rows]})


def _result(psig="PSIG-D1"):
    decs = [VAR.VariantDecision("Str.3 Pro.1", VAR.PASS), VAR.VariantDecision(VAR.D_ID, VAR.PASS)]
    return {"symbol": "BTC-USD", "status": "ACCEPTED_PROVISIONAL", "parent_signal_id": psig, "direction": "LONG",
            "asset_class": "crypto", "atr": 5.0, "signal_close": 100.0, "baseline_stop": 90.0, "baseline_target": 130.0,
            "action_sig": "resistance:100.0:0.5", "signal_time": SIG, "signal_end_time": "2026-07-01T04:00:00+00:00",
            "safety_line": {"d0": -6, "p0": 90.0, "d1": -1, "p1": 90.0}, "variant_decisions": decs}


ROWS_CY = [(99, 100, 98, 100)] + ROWS_SWING


def _setup(tmp_path, name="a"):
    return (StateRegistry(str(tmp_path / f"s_{name}.json")), T.PaperTradeStore(str(tmp_path / f"t_{name}.json")))


def test_d_opens_same_entries_as_pro1_with_exit_mode_d(tmp_path):
    reg, store = _setup(tmp_path)
    opened = CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    assert len(opened) == 2
    by = {t.strategy_id: t for t in store.trades}
    p1, d = by["Str.3 Pro.1"], by["Str.3 D"]
    assert (p1.symbol, p1.direction, p1.stop_initial, p1.signal_time, p1.parent_signal_id) == \
           (d.symbol, d.direction, d.stop_initial, d.signal_time, d.parent_signal_id)
    assert p1.exit_mode == "" and d.exit_mode == "D" and d.break_even == "D" and d.safety_line["p0"] == 90.0
    assert d.cplus["SW"] is None and "stage3" in d.cplus
    reg2, store2 = _setup(tmp_path, "b")
    r = _result(); r["baseline_target"] = None
    assert CY.open_trades_for_accepted(r, BE, reg2, store2, now=1000) == []              # ohne Ziel-Gate wie Pro.1 nicht handelbar


def test_d_lifecycle_events_persistence_and_catch_up(tmp_path):
    reg, store = _setup(tmp_path)
    CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS_CY), store, reg, now=2000)
    d = next(t for t in store.trades if t.strategy_id == "Str.3 D")
    assert d.status == "closed" and d.result["outcome"] == "STOP_INTRABAR" and abs(d.result["exit_price"] - 109.5) < 1e-9
    assert d.result["d_swing"] is True and "BTC-USD" not in reg.get("Str.3 D").open_symbols
    assert [e["kind"] for e in d.cplus["events"]] == [XC.EV_TRAIL, XC.EV_EXIT]
    again = T.PaperTradeStore(str(tmp_path / "t_a.json"))
    assert next(t for t in again.trades if t.strategy_id == "Str.3 D").cplus == d.cplus
    for cut in range(3, len(ROWS_CY)):                                                   # Ausfall an jeder Stelle
        reg2, st2 = _setup(tmp_path, f"c{cut}")
        CY.open_trades_for_accepted(_result(), BE, reg2, st2, now=1000)
        CY.update_open_trades("BTC-USD", _compat(ROWS_CY[:cut]), st2, reg2, now=1500)
        st2 = T.PaperTradeStore(str(tmp_path / f"t_c{cut}.json"))
        reg2 = StateRegistry(str(tmp_path / f"s_c{cut}.json"))
        CY.update_open_trades("BTC-USD", _compat(ROWS_CY), st2, reg2, now=2000)
        x = next(t for t in st2.trades if t.strategy_id == "Str.3 D")
        assert (x.status, x.result.get("exit_price"), x.result.get("netto_r")) == (d.status, d.result.get("exit_price"), d.result.get("netto_r")), cut
        assert [e["id"] for e in x.cplus["events"]] == [e["id"] for e in d.cplus["events"]], cut


def test_d_does_not_change_pro1(tmp_path):
    reg, store = _setup(tmp_path)
    CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS_CY), store, reg, now=2000)
    p1 = next(t for t in store.trades if t.strategy_id == "Str.3 Pro.1")
    r = _result(); r["variant_decisions"] = r["variant_decisions"][:1]
    reg3, st3 = _setup(tmp_path, "solo")
    CY.open_trades_for_accepted(r, {"Str.3 Pro.1": "BE-0"}, reg3, st3, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS_CY), st3, reg3, now=2000)
    s = st3.trades[0]
    assert (p1.status, p1.result.get("outcome"), p1.result.get("netto_r")) == (s.status, s.result.get("outcome"), s.result.get("netto_r"))


def test_open_d_trade_keeps_current_stop_for_report(tmp_path):
    reg, store = _setup(tmp_path)
    CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS_CY[:10]), store, reg, now=2000)
    d = next(t for t in store.trades if t.strategy_id == "Str.3 D")
    assert d.status == "open" and abs(d.cplus["levels_next"]["threshold"] - 109.5) < 1e-9 and d.cplus["levels_next"]["source"] == "STOP"


# ======================================================================== Meldungen / Routing / Bericht
def _dtrade():
    t = T.PaperTrade(trade_id="d1", variant_evaluation_id="v", parent_signal_id="P1", strategy_id="Str.3 D", break_even="D",
                     symbol="X", asset_class="fx", direction="LONG", signal_time="2026-10-17T08:00:00+00:00", stop_initial=90.0,
                     target=130.0, exit_mode="D", signal_end_time="2026-10-17T12:00:00+00:00", booked_entry={"signal_close": 100.0},
                     atr=5.0, safety_line={"d0": -6, "p0": 90.0, "d1": -1, "p1": 90.0}, cplus=XD.new_state())
    return t


def test_open_message_for_d_has_no_target_and_names_nachgezogener_stop():
    from notify import trade_text as TT
    q = {"price": 101.0, "bar_time": "2026-10-17T12:01:00+00:00", "interval": "1m", "delay_s": 0}
    txt = TT.trade_opened_text(_dtrade(), quote=q, booked={"price": 100.0, "time": "2026-10-17T12:00:00+00:00", "partial": True})
    assert "Ausstieg nach D (nachgezogener Stop" in txt and "Ziel:" not in txt and "Abstand Kurs zu Ziel" not in txt
    assert "Aktueller Stop ≈ 89,5" in txt and "jede Berührung (auch ein Docht)" in txt


def test_event_texts_for_d():
    from notify import trade_text as TT
    t = _dtrade()
    tr = {"id": "TRAIL:x", "kind": XC.EV_TRAIL, "time": "2026-10-17T20:00:00+00:00", "level": 109.5, "swing_price": 112.0,
          "swing_time": "2026-10-17T12:00:00+00:00"}
    assert "Stop nachgezogen auf 109,5" in TT.cplus_event_text(t, tr)
    t.result = {"netto_r": 0.9, "net_return_pct": 1.1, "entry_open": 100.0, "duration_days": 2.0, "d_swing": True}
    ex = {"id": "EXIT:x", "kind": XC.EV_EXIT, "time": "2026-10-18T08:00:00+00:00", "outcome": "STOP_INTRABAR", "price": 109.5}
    txt = TT.cplus_event_text(t, ex)
    assert "Ausstieg (Stop berührt (Docht genügt))" in txt and "+0,90 R" in txt


def test_d_messages_go_to_the_pro6_group_with_titles(tmp_path):
    from notify.live import TelegramService
    from notify.transport import MockTransport
    env = {"TELEGRAM_BOT_TOKEN": "T", "STR3_PRO1_CHAT_ID": "-101", "STR3_PRO2_CHAT_ID": "-102", "STR3_PRO3_CHAT_ID": "-103",
           "STR3_PRO6_CHAT_ID": "-106", "STR3_COMPARISON_CHAT_ID": "-900", "STR3_SYSTEM_CHAT_ID": "-999"}
    tr = MockTransport()
    svc = TelegramService(["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"], env=env, transport=tr, queue_path=str(tmp_path / "q.json"))
    t = _dtrade()
    svc.cplus_event(t, {"id": "TRAIL:x", "kind": XC.EV_TRAIL, "time": "2026-10-17T20:00:00+00:00", "level": 109.5,
                        "swing_price": 112.0, "swing_time": "2026-10-17T12:00:00+00:00"})
    assert tr.chats_used() == {"-106"}
    assert "Str.3 D – Stop nachgezogen" in tr.texts_to("-106")[0] and "Paper-Trading - keine echte Order." in tr.texts_to("-106")[0]


def test_report_has_d_as_fourth_group_large(tmp_path):
    import time
    from engine.ledger import Ledger
    from notify import status_report as SR
    rt = str(tmp_path / "rt"); os.makedirs(rt)
    lg = Ledger(os.path.join(rt, "ledger.json"))
    store = T.PaperTradeStore(os.path.join(rt, "trades.json"))
    for i, sid in enumerate(["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]):
        t = T.PaperTrade(trade_id=f"t{i}", variant_evaluation_id="v", parent_signal_id="P", strategy_id=sid, break_even="BE-1",
                         symbol="X", asset_class="fx", direction="LONG", signal_time="2026-10-01T00:00:00+00:00", status="closed",
                         stop_initial=1.0, target=2.0, exit_mode={"Str.3 C+": "CPLUS", "Str.3 D": "D"}.get(sid, ""))
        t.result = {"status": "closed", "outcome": "STOP", "netto_r": 1.0 + i, "brutto_r": 1.0, "net_return_pct": 2.0 + i,
                    "gross_return_pct": 2.0, "closed_ts": time.time(), "duration_days": 1.0, "mfe_r": 0, "mae_r": 1,
                    "exit_time": "2026-10-02T00:00:00+00:00"}
        store.add(t)
    d = SR.collect(rt, None, check_process=False)
    assert [v["sid"] for v in d["variants"]] == ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]
    pdf = SR.build_pdf(d, str(tmp_path / "o" / "r.pdf"))
    assert os.path.getsize(pdf) > 5000
    cap = SR.caption(d)
    assert "D (Docht-Stop) +5,0 %" in cap and "Pro.1 Baseline +2,0 %" in cap


def test_live_settings_default_groups_include_d():
    from engine import live_settings
    assert "Str.3 D" in live_settings.DEFAULTS["prewarn"]["groups"]


# ======================================================================== Regression: D-Spalten der 80 Trades
ANALYSE = os.path.join(os.path.dirname(ROOT), "Analysen", "cplus_pro1")
DATA = os.path.join(ANALYSE, "daten_kopie")
CSV_PATH = os.path.join(ANALYSE, "einzeltrades_pro1.csv")


def _num(s):
    return None if s in ("", None) else float(str(s).replace(",", "."))


@pytest.mark.skipif(not (os.path.exists(CSV_PATH) and os.path.exists(os.path.join(DATA, "trades.json"))),
                    reason="Referenzdaten (Analysen/cplus_pro1) nicht vorhanden")
def test_regression_80_trades_d_matches_reference():
    from engine import aggregate_4h

    def safe(s):
        return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s)
    frames = {}

    def fin(sym):
        if sym not in frames:
            df = pd.read_csv(os.path.join(DATA, "data_cache", safe(sym) + "__1h.csv"))
            frames[sym] = aggregate_4h.final_only(aggregate_4h.aggregate(df)).reset_index(drop=True)
        return frames[sym]
    trades = [t for t in json.load(open(os.path.join(DATA, "trades.json"), encoding="utf-8")) if t["strategy_id"] == "Str.3 Pro.1"]
    led = json.load(open(os.path.join(DATA, "ledger.json"), encoding="utf-8"))
    cand = {c["parent_signal_id"]: c for c in led["candidates"]}
    ref = {}
    with open(CSV_PATH, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f, delimiter=";"):
            ref[(row["symbol"], row["signal_utc"])] = row
    n_checked = n_closed = n_swing = 0
    for t in trades:
        key = (t["symbol"], t["signal_time"])
        if key not in ref:
            continue
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
        line = XC.make_line_fn({"d0": i0 - bb_i, "p0": p0, "d1": i1 - bb_i, "p1": p1}, k)
        a = float(sn["atr"])
        r_t = t.get("result") or {}
        E = float(r_t["entry_open"]) if r_t.get("entry_open") is not None else float(t["entry_price"])
        risk = abs(E - stop0)
        st = XD.new_state()
        XD.advance(st, t["direction"], list(times), f4["Open"].values, f4["High"].values, f4["Low"].values,
                   f4["Close"].values, line, e, E, risk, a)
        res = XD.result_for_trade(st, t["direction"], t["asset_class"], a, E, stop0)
        n_checked += 1
        assert res["status"] == row["D_status"], key
        assert int(row["D_swing_genutzt"]) == int(st["stage3"]), key
        n_swing += int(st["stage3"])
        if row["D_status"] == "closed":
            n_closed += 1
            assert res["outcome"] == row["D_ausstieg"], key
            assert abs(res["netto_r"] - _num(row["D_netto_r"])) < 0.0011, key
            assert abs(res["net_return_pct"] - _num(row["D_netto_pct"])) < 0.0011, key
            assert abs(float(st["exit"]["price"]) - _num(row["D_exit_preis"])) < 1e-4 * abs(E), key
            assert pd.Timestamp(st["exit"]["time"]) == pd.Timestamp(row["D_exit_utc"]), key
    assert n_checked == 80 and n_closed > 30 and n_swing > 0
