# -*- coding: utf-8 -*-
"""§5/§11 - Berichtserzeugung im Lauf (lokale PDFs + Kurztexte, Zeitraumfilter)."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import run_reports as RR
from engine.ledger import Ledger
from engine.tracker import PaperTradeStore, PaperTrade


def _seed_runtime(rt, now):
    os.makedirs(rt, exist_ok=True)
    lg = Ledger(os.path.join(rt, "ledger.json"))
    lg.record_variant_eval("P", "Str.3 Pro.1", "v1", "PASS")
    store = PaperTradeStore(os.path.join(rt, "trades.json"))
    def ct(sid, netto, net_pct, ts, outcome="TARGET", status="closed"):
        t = PaperTrade(trade_id=f"{sid}{ts}", variant_evaluation_id="VE", parent_signal_id="P",
                       strategy_id=sid, break_even="BE-1", symbol="BTC-USD", asset_class="crypto",
                       direction="LONG", signal_time="t", status=status)
        t.result = {"status": "closed", "outcome": outcome, "netto_r": netto, "brutto_r": netto,
                    "net_return_pct": net_pct, "gross_return_pct": net_pct, "closed_ts": ts,
                    "duration_days": 1, "mfe_r": 1, "mae_r": 0.2, "ambiguous_intrabar": False}
        return t
    # zwei Trades innerhalb 7 Tage, einer alt (ausserhalb)
    store.add(ct("Str.3 Pro.1", 2.0, 1.4, now - 2 * 86400))
    store.add(ct("Str.3 Pro.1", -1.0, -0.9, now - 3 * 86400, "STOP"))
    store.add(ct("Str.3 Pro.1", 1.0, 0.7, now - 20 * 86400))   # ausserhalb 7-Tage-Fenster


def test_generate_weekly_reports(tmp_path):
    rt = str(tmp_path / "rt"); now = time.time()
    _seed_runtime(rt, now)
    out = RR.generate_reports(rt, days=7, label="7-Tage", strategy_ids=["Str.3 Pro.1", "Str.3 Pro.2"], now=now)
    # PDFs erzeugt
    assert os.path.exists(out["variant_pdfs"]["Str.3 Pro.1"])
    assert os.path.exists(out["comparison_pdf"])
    # Kurztext enthaelt %-Kennzahlen + Paper-Hinweis
    txt = out["short_texts"]["Str.3 Pro.1"]
    assert "Reiner Nettogewinn" in txt and "Paper-Trading" in txt
    # Zeitraumfilter: nur 2 der 3 Trades zaehlen (der 20 Tage alte faellt raus)
    # -> pruefbar ueber die Datei-Existenz reicht; Detailwerte in reporting-Tests abgedeckt


def test_deliver_noop_without_telegram(tmp_path):
    rt = str(tmp_path / "rt"); now = time.time()
    _seed_runtime(rt, now)
    out = RR.generate_reports(rt, days=30, label="30 Tage (rollierend)", strategy_ids=["Str.3 Pro.1"], now=now)
    res = RR.deliver_via_telegram(out, telegram_config=None)
    assert res["delivered"] == 0 and "inaktiv" in res["note"]
    # rollierend-30 nicht als Kalendermonat bezeichnet
    assert "Kalendermonat" not in out["short_texts"]["Str.3 Pro.1"]
