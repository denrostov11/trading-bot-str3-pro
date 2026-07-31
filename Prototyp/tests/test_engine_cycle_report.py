# -*- coding: utf-8 -*-
"""Phase-B Increment S9 - Vorwaerts-Zyklus (Trade-Lebenszyklus) + Berichte + Instrumente."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import cycle as CY
from engine import reporting as REP
from engine import instruments as INS
from engine.varstate import StateRegistry
from engine.ledger import Ledger
from engine import variants as VAR
from engine import tracker as T


# ---------------- Instrumente ----------------
def test_classify():
    assert INS.classify("BTC-USD")["asset_class"] == "crypto"
    assert INS.classify("BTC-USD")["session_exact"] is True
    assert INS.classify("EURUSD=X")["asset_class"] == "fx"
    assert INS.classify("^GDAXI")["asset_class"] == "index"
    assert INS.classify("GC=F")["is_futures"] is True
    assert INS.classify("AAPL")["asset_class"] == "stock"


# ---------------- Trade-Lebenszyklus ----------------
def _compat(times, ohlc):
    return pd.DataFrame({"Time": pd.to_datetime(times, utc=True),
                         "Open": [o for o, *_ in ohlc], "High": [h for _, h, *_ in ohlc],
                         "Low": [l for _, _, l, _ in ohlc], "Close": [c for *_, c in ohlc]})


def _accepted_result(symbol="BTC-USD", psig="PSIG-1", stop=98.0, target=106.0):
    d1 = VAR.VariantDecision("Str.3 Pro.1", VAR.PASS)
    d3 = VAR.VariantDecision("Str.3 Pro.3", VAR.PASS)
    return {"symbol": symbol, "status": "ACCEPTED_PROVISIONAL", "parent_signal_id": psig,
            "direction": "LONG", "asset_class": "crypto", "atr": 2.0,
            "signal_close": 100.0, "baseline_stop": stop, "baseline_target": target,
            "action_sig": "resistance:100.0:0.5", "signal_time": "2026-07-01T00:00:00+00:00",
            "variant_decisions": [d1, d3]}


def test_lifecycle_open_fill_track_close(tmp_path):
    reg = StateRegistry(str(tmp_path / "state.json"))
    store = T.PaperTradeStore(str(tmp_path / "trades.json"))
    res = _accepted_result()
    # Zyklus 1: Signal bei 00:00 -> zwei Trades (Pro.1, Pro.3) pending_fill
    opened = CY.open_trades_for_accepted(res, {"Str.3 Pro.1": "BE-0", "Str.3 Pro.3": "BE-1"},
                                         reg, store, now=1000)
    assert len(opened) == 2
    assert all(t.status == "pending_fill" for t in store.trades)
    # Zwei Varianten -> gleicher Ursprung, verschiedene Trades (getrennt)
    assert store.trades[0].parent_signal_id == store.trades[1].parent_signal_id
    assert store.trades[0].strategy_id != store.trades[1].strategy_id

    # Zyklus 2: naechste Kerzen erscheinen; Kurs laeuft ins Ziel 106
    compat = _compat(
        ["2026-07-01T00:00", "2026-07-01T04:00", "2026-07-01T08:00"],
        [(100, 101, 99, 100), (100.2, 103, 100, 102), (102, 107, 101, 106.5)])
    closed = CY.update_open_trades("BTC-USD", compat, store, reg, now=2000)
    assert closed == 2
    assert all(t.status == "closed" and t.result["outcome"] == "TARGET" for t in store.trades)


def test_variant_separation_same_instrument(tmp_path):
    reg = StateRegistry(str(tmp_path / "s.json"))
    store = T.PaperTradeStore(str(tmp_path / "t.json"))
    CY.open_trades_for_accepted(_accepted_result(), {"Str.3 Pro.1": "BE-0", "Str.3 Pro.3": "BE-1"},
                                reg, store, now=1000)
    # Pro.1 hat BTC offen; ein zweites akzeptiertes Signal auf gleicher Linie -> Pro.1 blockiert,
    # aber nur innerhalb Pro.1 (Pro.3 hat ja seinen eigenen Trade)
    reopened = CY.open_trades_for_accepted(_accepted_result(psig="PSIG-1"),
                                           {"Str.3 Pro.1": "BE-0", "Str.3 Pro.3": "BE-1"},
                                           reg, store, now=1001)
    assert reopened == []          # gleiche Linie/Instrument -> keine Doppelung je Variante


# ---------------- Berichte ----------------
def _closed_trade(sid, direction, netto, brutto, outcome, ac="crypto", dur=1.0,
                  net_pct=None, gross_pct=None, ts=0.0):
    t = T.PaperTrade(trade_id=f"{sid}-{netto}-{ts}", variant_evaluation_id="VE", parent_signal_id="P",
                     strategy_id=sid, break_even="BE-1", symbol="BTC-USD", asset_class=ac,
                     direction=direction, signal_time="2026-07-01T00:00", status="closed")
    t.result = {"status": "closed", "outcome": outcome, "netto_r": netto, "brutto_r": brutto,
                "net_return_pct": net_pct if net_pct is not None else netto * 1.0,
                "gross_return_pct": gross_pct if gross_pct is not None else brutto * 1.0,
                "mfe_r": abs(brutto) + 0.5, "mae_r": 0.3, "duration_days": dur,
                "ambiguous_intrabar": False, "closed_ts": ts}
    return t


def test_variant_report_metrics(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    lg.record_variant_eval("P", "Str.3 Pro.1", "v1", "PASS")
    trades = [_closed_trade("Str.3 Pro.1", "LONG", 2.0, 2.1, "TARGET", net_pct=1.4, ts=1),
              _closed_trade("Str.3 Pro.1", "LONG", -1.05, -1.0, "STOP", net_pct=-0.9, ts=2),
              _closed_trade("Str.3 Pro.1", "SHORT", 1.5, 1.6, "TARGET", net_pct=1.1, ts=3)]
    rep = REP.variant_report(lg, trades, "Str.3 Pro.1")
    assert rep["closed_trades"] == 3 and rep["winners"] == 2 and rep["losers"] == 1
    assert rep["hit_rate"] == round(2 / 3, 4)
    assert rep["profit_factor"] is not None
    assert rep["sample_flag"] == "UNZUREICHENDE_STICHPROBE"   # <30
    # Prozent: Summe positiv = 1.4+1.1=2.5; Summe negativ (absolut)=0.9; netto=1.6
    assert rep["sum_positive_return_pct"] == 2.5
    assert rep["sum_negative_return_pct"] == 0.9
    assert rep["net_profit_pct"] == 1.6


def test_comparison_no_auto_winner(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    trades = [_closed_trade("Str.3 Pro.1", "LONG", 2.0, 2.1, "TARGET", net_pct=1.4, ts=1),
              _closed_trade("Str.3 Pro.2", "LONG", -1.0, -1.0, "STOP", net_pct=-0.9, ts=1)]
    comp = REP.comparison(lg, trades, ["Str.3 Pro.1", "Str.3 Pro.2"])
    assert comp["eligible_for_ranking"] == 0        # beide <30 Trades -> nicht ranking-faehig
    assert "Keine automatische Gewinnerbehauptung" in comp["note"]
