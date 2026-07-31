# -*- coding: utf-8 -*-
"""Prozent-Spezifikation (§9) - Invarianten: kein Doppelabzug, Vorzeichen, sum_negative absolut,
R<->Prozent-Konsistenz, zeitgeordneter Drawdown."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import tracker as T
from engine import reporting as REP
from engine.ledger import Ledger


def bar(h, l, o=None, c=None):
    return {"High": h, "Low": l, "Open": o if o is not None else (h + l) / 2,
            "Close": c if c is not None else (h + l) / 2}


# Fix P1: keine doppelte Slippage. Brutto aus entry_open (ungeslippt), Kosten genau einmal.
def test_no_double_slippage():
    bars = [bar(104.5, 101)]                 # Ziel 104
    r = T.simulate_trade("LONG", "crypto", atr=2.0, entry_open=100.0, stop_initial=98.0,
                         target=104.0, bars=bars)
    # Brutto bezieht sich auf entry_open=100: (104-100)/2 = 2.0R ; %-brutto = 4.0%
    assert r["brutto_r"] == 2.0 and r["gross_return_pct"] == 4.0
    assert r["entry_open"] == 100.0 and r["entry_price"] == 100.1   # Fill nur informativ
    # net = gross - fees - slippage EINMAL; slippage_pct = (2*0.1)/100*100 = 0.2 %
    assert r["slippage_pct"] == 0.2
    assert round(r["gross_return_pct"] - r["fees_pct"] - r["slippage_pct"], 4) == r["net_return_pct"]


# Vorzeichen SHORT
def test_short_percent_sign():
    bars = [bar(100.1, 95.5)]                 # SHORT Ziel 96
    r = T.simulate_trade("SHORT", "fx", atr=2.0, entry_open=100.0, stop_initial=102.0,
                         target=96.0, bars=bars)
    assert r["gross_return_pct"] > 0 and r["net_return_pct"] > 0   # Gewinn positiv


# R und Prozent immer gleiches Vorzeichen (Konsistenz)
def test_sign_consistency_r_and_pct():
    for (o, s, tg, bars) in [
        (100, 98, 104, [bar(104.5, 101)]),          # Gewinn
        (100, 98, 110, [bar(100.5, 97.5)]),         # Verlust (Stop)
    ]:
        r = T.simulate_trade("LONG", "crypto", 2.0, o, s, tg, bars)
        assert (r["net_return_pct"] > 0) == (r["netto_r"] > 0)


# sum_negative_return_pct wird als positiver Betrag ausgewiesen; net = pos - neg
def test_sum_negative_absolute(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    trades = []
    T_ = __import__("engine.tracker", fromlist=["PaperTrade"]).PaperTrade
    def mk(net_pct, ts):
        t = T_(trade_id=f"x{ts}", variant_evaluation_id="VE", parent_signal_id="P",
               strategy_id="Str.3 Pro.1", break_even="BE-1", symbol="BTC-USD", asset_class="crypto",
               direction="LONG", signal_time="t", status="closed")
        t.result = {"status": "closed", "outcome": "TARGET" if net_pct > 0 else "STOP",
                    "netto_r": net_pct, "brutto_r": net_pct, "net_return_pct": net_pct,
                    "gross_return_pct": net_pct, "closed_ts": ts, "duration_days": 1,
                    "mfe_r": 1, "mae_r": 0.2, "ambiguous_intrabar": False}
        return t
    trades = [mk(2.0, 1), mk(-1.5, 2), mk(-0.5, 3)]
    rep = REP.variant_report(lg, trades, "Str.3 Pro.1")
    assert rep["sum_positive_return_pct"] == 2.0
    assert rep["sum_negative_return_pct"] == 2.0            # |-1.5-0.5| positiv
    assert rep["net_profit_pct"] == 0.0


# Fix P2: Drawdown aus zeitgeordneter Equity - unsortierte Eingabe muss korrekt sortiert werden
def test_drawdown_time_ordered(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    T_ = __import__("engine.tracker", fromlist=["PaperTrade"]).PaperTrade
    def mk(net, ts):
        t = T_(trade_id=f"x{ts}", variant_evaluation_id="VE", parent_signal_id="P",
               strategy_id="S", break_even="BE-1", symbol="B", asset_class="crypto",
               direction="LONG", signal_time="t", status="closed")
        t.result = {"status": "closed", "outcome": "TARGET" if net > 0 else "STOP",
                    "netto_r": net, "brutto_r": net, "net_return_pct": net, "gross_return_pct": net,
                    "closed_ts": ts, "duration_days": 1, "mfe_r": 1, "mae_r": 0.2,
                    "ambiguous_intrabar": False}
        return t
    # zeitliche Reihenfolge: +3, -2, -2, +1  -> Equity 3,1,-1,0 ; Drawdown ab Peak 3 -> -4
    # bewusst UNSORTIERT uebergeben:
    trades = [mk(1, 4), mk(-2, 2), mk(3, 1), mk(-2, 3)]
    rep = REP.variant_report(lg, trades, "S")
    assert rep["max_drawdown_r"] == -4.0
