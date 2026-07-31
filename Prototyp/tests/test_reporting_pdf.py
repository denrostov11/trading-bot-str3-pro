# -*- coding: utf-8 -*-
"""§9/§5 - Reporting: Kurztext + PDF (reine %-Auswertung, kein Kapitalkonto)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import reporting as REP, reporting_pdf as RP
from engine.ledger import Ledger
from engine import tracker as T


def _ct(sid, netto, net_pct, ts, outcome="TARGET"):
    t = T.PaperTrade(trade_id=f"{sid}{ts}", variant_evaluation_id="VE", parent_signal_id="P",
                     strategy_id=sid, break_even="BE-1", symbol="BTC-USD", asset_class="crypto",
                     direction="LONG", signal_time="t", status="closed")
    t.result = {"status": "closed", "outcome": outcome, "netto_r": netto, "brutto_r": netto,
                "net_return_pct": net_pct, "gross_return_pct": net_pct, "closed_ts": ts,
                "duration_days": 1, "mfe_r": 1, "mae_r": 0.2, "ambiguous_intrabar": False}
    return t


def test_short_text_percent_only(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    trades = [_ct("Str.3 Pro.1", 2.0, 1.4, 1), _ct("Str.3 Pro.1", -1.0, -0.9, 2, "STOP")]
    rep = REP.variant_report(lg, trades, "Str.3 Pro.1")
    txt = short_text = RP.short_text(rep, "7-Tage")
    assert "Reiner Nettogewinn" in txt and "%" in txt
    assert "kein Kapitalkonto" in txt
    assert "Paper-Trading – keine echte Order." in txt
    # keine Portfoliorendite/Kapitalzeile in reiner %-Auswertung
    assert "Portfolio" not in txt


def test_build_variant_and_comparison_pdf(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    trades = [_ct("Str.3 Pro.1", 2.0, 1.4, 1), _ct("Str.3 Pro.1", -1.0, -0.9, 2, "STOP"),
              _ct("Str.3 Pro.2", 1.5, 1.1, 1)]
    rep = REP.variant_report(lg, trades, "Str.3 Pro.1")
    p1 = RP.build_variant_pdf(rep, str(tmp_path / "pro1.pdf"), "7-Tage")
    assert os.path.exists(p1) and os.path.getsize(p1) > 500
    comp = REP.comparison(lg, trades, ["Str.3 Pro.1", "Str.3 Pro.2"])
    p2 = RP.build_comparison_pdf(comp, str(tmp_path / "cmp.pdf"))
    assert os.path.exists(p2) and os.path.getsize(p2) > 500
