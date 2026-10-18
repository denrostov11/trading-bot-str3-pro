# -*- coding: utf-8 -*-
"""A1/A2 Live-Integration: Variante "Str.3 C+" im Trade-Zyklus (gleiche Einstiege wie Pro.1, C+-Ausstieg,
persistenter Zustand, Aufholen nach Ausfall ohne Look-ahead)."""
import os, sys, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import cycle as CY
from engine import tracker as T
from engine import variants as VAR
from engine import exit_cplus as XC
from engine.varstate import StateRegistry

BE = {"Str.3 Pro.1": "BE-0", "Str.3 C+": "C+"}
SIG = "2026-07-01T00:00:00+00:00"


def _compat(rows, start="2026-07-01T00:00"):
    times = list(pd.date_range(start, periods=len(rows), freq="4h", tz="UTC"))
    return pd.DataFrame({"Time": times, "Open": [r[0] for r in rows], "High": [r[1] for r in rows],
                         "Low": [r[2] for r in rows], "Close": [r[3] for r in rows]})


def _result(psig="PSIG-C1", stop=90.0, target=130.0):
    decs = [VAR.VariantDecision("Str.3 Pro.1", VAR.PASS), VAR.VariantDecision(VAR.CPLUS_ID, VAR.PASS)]
    return {"symbol": "BTC-USD", "status": "ACCEPTED_PROVISIONAL", "parent_signal_id": psig,
            "direction": "LONG", "asset_class": "crypto", "atr": 5.0, "signal_close": 100.0,
            "baseline_stop": stop, "baseline_target": target, "action_sig": "resistance:100.0:0.5",
            "signal_time": SIG, "signal_end_time": "2026-07-01T04:00:00+00:00",
            "safety_line": {"d0": -6, "p0": 90.0, "d1": -1, "p1": 90.0},       # flache Linie bei 90
            "variant_decisions": decs}


# Signalkerze (Index 0), danach Einstiegskerze (Open 100). Verlauf wie ROWS_STAGE3 des Einheitentests.
ROWS = [(99, 100, 98, 100),                       # 0 Signalkerze
        (100, 110, 99, 108), (108, 120, 107, 116), (116, 135, 125, 130), (130, 131, 123, 128),
        (128, 129, 121, 126), (126, 127, 112, 124), (124, 128, 118, 126), (126, 129, 120, 127),
        (127, 130, 122, 128), (128, 128, 105, 108), (107, 110, 100, 103)]


def _setup(tmp_path, name="a"):
    reg = StateRegistry(str(tmp_path / f"state_{name}.json"))
    store = T.PaperTradeStore(str(tmp_path / f"trades_{name}.json"))
    return reg, store


def test_cplus_opens_same_entries_as_pro1_with_cplus_fields(tmp_path):
    reg, store = _setup(tmp_path)
    opened = CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    assert len(opened) == 2
    by = {t.strategy_id: t for t in store.trades}
    p1, cp = by["Str.3 Pro.1"], by["Str.3 C+"]
    assert (p1.symbol, p1.direction, p1.stop_initial, p1.signal_time, p1.parent_signal_id) == \
           (cp.symbol, cp.direction, cp.stop_initial, cp.signal_time, cp.parent_signal_id)
    assert p1.exit_mode == "" and cp.exit_mode == "CPLUS" and cp.safety_line["p0"] == 90.0
    assert cp.break_even == "C+" and cp.signal_end_time.startswith("2026-07-01T04:00")


def test_cplus_without_target_not_opened_like_pro1(tmp_path):
    reg, store = _setup(tmp_path)
    assert CY.open_trades_for_accepted(_result(target=None), BE, reg, store, now=1000) == []


def test_cplus_full_lifecycle_and_events(tmp_path):
    reg, store = _setup(tmp_path)
    CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS), store, reg, now=2000)
    cp = next(t for t in store.trades if t.strategy_id == "Str.3 C+")
    assert cp.status == "closed" and cp.result["outcome"] == XC.OUT_PROFIT
    assert cp.result["exit_price"] == 107 and cp.result["cplus_stage2"] and cp.result["cplus_stage3"]
    assert [e["kind"] for e in cp.cplus["events"]] == [XC.EV_STAGE2, XC.EV_TRAIL, XC.EV_EXIT]
    assert all(e.get("sent") is not True for e in cp.cplus["events"])           # Zustellmarke noch offen
    # Persistenz: neu laden liefert denselben Zustand
    again = T.PaperTradeStore(str(tmp_path / "trades_a.json"))
    cp2 = next(t for t in again.trades if t.strategy_id == "Str.3 C+")
    assert cp2.cplus == cp.cplus and cp2.exit_mode == "CPLUS"
    # State-Registry: C+ ist wieder frei (Cooldown gesetzt), Pro.1-Zustand unabhaengig
    assert "BTC-USD" not in reg.get("Str.3 C+").open_symbols


def test_catch_up_after_outage_equals_continuous(tmp_path):
    # Durchlauf in einem Rutsch
    reg1, st1 = _setup(tmp_path, "full")
    CY.open_trades_for_accepted(_result(), BE, reg1, st1, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS), st1, reg1, now=2000)
    full = next(t for t in st1.trades if t.strategy_id == "Str.3 C+")
    # Jeder Ausfall-Schnitt: bis Kerze `cut` hourly, dann Neustart (neu laden) und alles Verpasste auf einmal
    for cut in range(3, len(ROWS)):
        reg, st = _setup(tmp_path, f"cut{cut}")
        CY.open_trades_for_accepted(_result(), BE, reg, st, now=1000)
        CY.update_open_trades("BTC-USD", _compat(ROWS[:cut]), st, reg, now=1500)
        st = T.PaperTradeStore(str(tmp_path / f"trades_cut{cut}.json"))         # Prozess-Neustart
        reg = StateRegistry(str(tmp_path / f"state_cut{cut}.json"))
        CY.update_open_trades("BTC-USD", _compat(ROWS), st, reg, now=2000)
        cp = next(t for t in st.trades if t.strategy_id == "Str.3 C+")
        assert cp.status == full.status, cut
        assert cp.result.get("exit_price") == full.result.get("exit_price"), cut
        assert cp.result.get("netto_r") == full.result.get("netto_r"), cut
        assert [e["id"] for e in cp.cplus["events"]] == [e["id"] for e in full.cplus["events"]], cut


def test_open_trade_keeps_levels_for_next_candle(tmp_path):
    reg, store = _setup(tmp_path)
    CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS[:3]), store, reg, now=2000)       # Stufe 2 erreicht
    cp = next(t for t in store.trades if t.strategy_id == "Str.3 C+")
    assert cp.status == "open" and cp.cplus["stage2"] and cp.cplus["levels_next"]["source"] == "PROFIT"
    assert cp.cplus["levels_next"]["threshold"] > 100.0                           # Einstand + Kosten
    assert cp.cplus["levels_next"]["net"] == cp.cplus["levels_next"]["threshold"] - 5.0


def test_pending_fill_until_entry_candle_exists(tmp_path):
    reg, store = _setup(tmp_path)
    CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS[:1]), store, reg, now=1500)       # nur Signalkerze
    assert all(t.status == "pending_fill" for t in store.trades)


def test_pro1_unchanged_by_cplus_presence(tmp_path):
    reg, store = _setup(tmp_path)
    CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS), store, reg, now=2000)
    p1 = next(t for t in store.trades if t.strategy_id == "Str.3 Pro.1")
    # Referenz: derselbe Trade ohne C+ im Spiel
    reg2, store2 = _setup(tmp_path, "solo")
    CY.open_trades_for_accepted(_result(), {"Str.3 Pro.1": "BE-0"}, reg2, store2, now=1000)
    # (nur Pro.1 akzeptiert)
    r = _result(); r["variant_decisions"] = r["variant_decisions"][:1]
    reg3, store3 = _setup(tmp_path, "solo2")
    CY.open_trades_for_accepted(r, {"Str.3 Pro.1": "BE-0"}, reg3, store3, now=1000)
    CY.update_open_trades("BTC-USD", _compat(ROWS), store3, reg3, now=2000)
    s = store3.trades[0]
    assert (p1.status, p1.result.get("outcome"), p1.result.get("netto_r")) == \
           (s.status, s.result.get("outcome"), s.result.get("netto_r"))
