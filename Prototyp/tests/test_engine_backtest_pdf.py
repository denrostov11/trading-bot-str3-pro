# -*- coding: utf-8 -*-
"""Backtest-PDF (Etappe C2): mehrseitige Varianten-PDF (Gesamt+Equity+Monate) + Vergleichs-PDF
werden aus den erzeugten JSON/CSV gebaut. Prueft nur, dass valide, nicht-leere PDFs entstehen
und der reports-Dict fuer den Telegram-Versand korrekt gefuellt ist."""
import os, sys, json, csv
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import backtest_pdf as BP


def _rep(sid, n=40):
    return {"strategy_id": sid, "closed_trades": n, "hit_rate": 0.5, "total_r_netto": 3.2,
            "avg_r": 0.08, "expectancy_r": 0.08, "sum_positive_return_pct": 10.0,
            "sum_negative_return_pct": 4.0, "net_profit_pct": 6.0, "average_return_pct": 0.15,
            "profit_factor": 1.4, "max_drawdown_r": -2.1, "max_drawdown_pct": -1.5,
            "open_trades_unrealized": 0, "sample_flag": "OK"}


def test_build_all_creates_pdfs(tmp_path):
    uni = str(tmp_path / "Universum_Test")
    vdir = os.path.join(uni, "Pro.1_Baseline")
    os.makedirs(vdir)
    json.dump(_rep("Str.3 Pro.1"), open(os.path.join(vdir, "Pro.1_Baseline_GESAMT.json"), "w"))
    json.dump(_rep("Str.3 Pro.1", 5), open(os.path.join(vdir, "Monat_2025-01.json"), "w"))
    comp_dir = os.path.join(uni, "_GESAMT_Vergleich"); os.makedirs(comp_dir)
    json.dump({"variants": [_rep("Str.3 Pro.1")], "rankings": {"by_total_r": ["Str.3 Pro.1"]},
               "eligible_for_ranking": 1, "note": "Testnotiz."},
              open(os.path.join(comp_dir, "GESAMT_alle-Varianten.json"), "w"))
    csv_dir = os.path.join(uni, "_CSV_Audit"); os.makedirs(csv_dir)
    with open(os.path.join(csv_dir, "equity_curve.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["strategy_id", "closed_time", "netto_r", "cum_netto_r",
                                       "net_return_pct", "cum_net_pct"])
        w.writerow(["Str.3 Pro.1", "2025-01-05T00:00:00+00:00", "1.0", "1.0", "0.5", "0.5"])
        w.writerow(["Str.3 Pro.1", "2025-01-09T00:00:00+00:00", "-0.5", "0.5", "-0.3", "0.2"])

    reports = BP.build_all(uni, ["Str.3 Pro.1"], "2025-01-01", "2025-01-31", label="Test")
    vp = reports["variant_pdfs"]["Str.3 Pro.1"]
    assert os.path.exists(vp) and os.path.getsize(vp) > 1000
    assert os.path.exists(reports["comparison_pdf"]) and os.path.getsize(reports["comparison_pdf"]) > 1000
    assert reports["short_texts"]["Str.3 Pro.1"].startswith("STR.3 PRO.1")
