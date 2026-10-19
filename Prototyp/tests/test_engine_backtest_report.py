# -*- coding: utf-8 -*-
"""Backtest-Auswertung/Export (Etappe C): TEST_END-Bewertung offener Trades, Monatsaufteilung,
CSV-Audit-Set und beschriftete Ordnerstruktur."""
import os, sys, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import backtest_report as BRP
from engine.tracker import PaperTrade, PaperTradeStore
from engine.ledger import Ledger


def _closed_trade(sid, ts, netto=1.5, direction="LONG"):
    t = PaperTrade(trade_id=f"{sid}-{ts}", variant_evaluation_id="VE", parent_signal_id="P",
                   strategy_id=sid, break_even="BE-1", symbol="BTC-USD", asset_class="crypto",
                   direction=direction, signal_time="2025-06-01T00:00:00+00:00", status="closed")
    d = pd.Timestamp(ts, tz="UTC")
    t.result = {"status": "closed", "outcome": "TARGET", "netto_r": netto, "brutto_r": netto + 0.1,
                "net_return_pct": netto, "gross_return_pct": netto + 0.1, "mfe_r": 2.0, "mae_r": 0.3,
                "duration_days": 1.0, "ambiguous_intrabar": False,
                "closed_ts": float(d.timestamp()), "exit_time": d.isoformat()}
    return t


def test_month_utils():
    assert BRP.month_list("2025-01-01", "2025-03-31") == [(2025, 1), (2025, 2), (2025, 3)]
    trades = [_closed_trade("Str.3 Pro.1", "2025-06-15"), _closed_trade("Str.3 Pro.1", "2025-07-02")]
    assert len(BRP.trades_in_month(trades, 2025, 6)) == 1
    assert len(BRP.trades_in_month(trades, 2025, 7)) == 1


def test_test_end_close_marks_open_trade(tmp_path):
    store = PaperTradeStore(str(tmp_path / "t.json"))
    # ein OFFENER, bereits gefuellter Trade
    t = PaperTrade(trade_id="OPEN-1", variant_evaluation_id="VE", parent_signal_id="P",
                   strategy_id="Str.3 Pro.1", break_even="BE-0", symbol="BTC-USD",
                   asset_class="crypto", direction="LONG", signal_time="2026-06-20T00:00:00+00:00",
                   status="open")
    t.entry_time = "2026-06-20T04:00:00+00:00"; t.entry_price = 100.0
    t.stop_initial = 98.0; t.target = 110.0; t.atr = 2.0
    t.result = {"status": "open", "mfe_r": 1.0, "mae_r": 0.2, "be_moved": False,
                "stop_current": 98.0, "duration_bars": 5}
    store.add(t)
    compat = pd.DataFrame({"Time": pd.to_datetime(["2026-06-29", "2026-06-30"], utc=True),
                           "Open": [104, 105], "High": [106, 107], "Low": [103, 104],
                           "Close": [105, 106]})
    te, nf = BRP.test_end_close(store, {"BTC-USD": compat}, "2026-06-30T23:59:59+00:00")
    assert te == 1 and nf == 0
    r = store.trades[0].result
    assert store.trades[0].status == "closed" and r["outcome"] == "TEST_END"
    assert r["brutto_r"] > 0                                    # 105-Einstieg... LONG, exit 106 > entry 100
    assert r["netto_r"] < r["brutto_r"]                        # Kosten abgezogen


def test_build_universe_reports_structure(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    lg.record_candidate("P1", "BTC-USD", "LONG", "ACCEPTED_PROVISIONAL", "2025-06-01T00:00", "c")
    lg.record_variant_eval("P1", "Str.3 Pro.1", "v1", "PASS")
    store = PaperTradeStore(str(tmp_path / "t.json"))
    for ts in ["2025-06-10", "2025-07-10"]:
        store.add(_closed_trade("Str.3 Pro.1", ts))
    variants = [f"Str.3 Pro.{i}" for i in range(1, 9)]
    manifest = {"run_id": "R1", "window": ["2025-06-01", "2025-07-31"]}
    base = BRP.build_universe_reports(str(tmp_path / "out"), "Universum_94", lg, store, variants,
                                      "2025-06-01", "2025-07-31", manifest)
    # Variantenordner mit klaren Namen
    assert os.path.isdir(os.path.join(base, "Pro.1_Baseline"))
    assert os.path.isdir(os.path.join(base, "Pro.5_Kombi-EMA+RVOL+ATR"))
    # Gesamt + Monatsberichte (Juni + Juli)
    assert os.path.exists(os.path.join(base, "Pro.1_Baseline", "Pro.1_Baseline_GESAMT.json"))
    assert os.path.exists(os.path.join(base, "Pro.1_Baseline", "Monat_2025-06.json"))
    assert os.path.exists(os.path.join(base, "Pro.1_Baseline", "Monat_2025-07.json"))
    # Vergleich + CSV-Audit
    assert os.path.exists(os.path.join(base, "_GESAMT_Vergleich", "GESAMT_alle-Varianten.json"))
    for csv in ("trades.csv", "signals.csv", "summary_by_strategy.csv", "equity_curve.csv",
                "run_manifest.json"):
        assert os.path.exists(os.path.join(base, "_CSV_Audit", csv)), csv
    # Monatskennzahl stimmt: Juni hat genau 1 Trade
    juni = json.load(open(os.path.join(base, "Pro.1_Baseline", "Monat_2025-06.json"), encoding="utf-8"))
    assert juni["closed_trades"] == 1
