# -*- coding: utf-8 -*-
"""Checkpoint-fester Backtest-Runner (Etappe E): Universum abrechnen -> Merge -> Berichte;
done.json-Checkpoint; Resume ueberspringt fertige Symbole (ohne sie neu zu rechnen)."""
import os, sys, json
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import backtest_loop as BL


class FakeLine:
    def __init__(self, i0, p0, i1, p1, kind, taps, breaking_bar):
        self.i0, self.p0, self.i1, self.p1 = i0, p0, i1, p1
        self.kind, self.taps, self.angle_deg = kind, list(taps), 12.0
        self.breaking_bar = breaking_bar
    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def _dl_1h(sym):
    t0 = pd.Timestamp("2024-12-01", tz="UTC")
    return pd.DataFrame([{"Time": t0 + pd.Timedelta(hours=i), "Open": 100.0, "High": 100.5,
                          "Low": 99.5, "Close": 100.0, "Volume": 100} for i in range(24 * 42)])


def _dl_1d(sym):
    t0 = pd.Timestamp("2024-06-01", tz="UTC")
    return pd.DataFrame([{"Time": t0 + pd.Timedelta(days=i), "Open": 100, "High": 100,
                          "Low": 100, "Close": 100, "Volume": 1000} for i in range(260)])


def _detect_every(compat):
    n = len(compat); bb = n - 1
    return {"action": FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb),
            "safety": FakeLine(0, 97, bb, 98, "support", [5, 25], breaking_bar=-1),
            "direction": "LONG", "atr_last": 2.0, "atr_series": pd.Series([2.0] * n),
            "pivots": ([], []), "pivot_prices": [106.0, 106.5], "n": n}


def _cfg(out_root, frozen_dir):
    return {"start": "2025-01-01", "end": "2025-01-11", "variants": ["Str.3 Pro.1"],
            "be_map": {"Str.3 Pro.1": "BE-0"}, "code_version": "bt-test", "config_hash": "CTEST",
            "out_root": out_root, "frozen_dir": frozen_dir}


def test_runner_universe_reports_and_checkpoint(tmp_path):
    base = str(tmp_path / "rt"); os.makedirs(base)
    frozen = str(tmp_path / "frozen")
    out = str(tmp_path / "out")
    cfg = _cfg(out, frozen)
    u = {"name": "Universum_Test", "symbols": [["Alpha", "AAA-USD"], ["Beta", "BBB-USD"]]}

    BL.process_universe(u, cfg, base, frozen, out, dl_1h=_dl_1h, dl_1d=_dl_1d, detect_fn=_detect_every)

    # Berichte/Ordnerstruktur
    uni = os.path.join(out, "Universum_Test")
    assert os.path.isdir(os.path.join(uni, "Pro.1_Baseline"))
    assert os.path.exists(os.path.join(uni, "Pro.1_Baseline", "Monat_2025-01.json"))
    assert os.path.exists(os.path.join(uni, "_CSV_Audit", "trades.csv"))
    # Checkpoint: beide Symbole als fertig markiert
    done = json.load(open(os.path.join(base, "run_Universum_Test", "done.json")))
    assert set(done) == {"AAA-USD", "BBB-USD"}
    # es wurden real Trades erzeugt (Dauer-Signal -> je Symbol 1 offener, am TEST_END bewertet)
    trades = json.load(open(os.path.join(base, "run_Universum_Test", "trades_merged.json")))
    assert len(trades) >= 2


def test_runner_resume_skips_done(tmp_path):
    base = str(tmp_path / "rt"); os.makedirs(base)
    frozen = str(tmp_path / "frozen"); out = str(tmp_path / "out")
    cfg = _cfg(out, frozen)
    u = {"name": "Universum_Test", "symbols": [["Alpha", "AAA-USD"], ["Beta", "BBB-USD"]]}
    BL.process_universe(u, cfg, base, frozen, out, dl_1h=_dl_1h, dl_1d=_dl_1d, detect_fn=_detect_every)

    # zweiter Durchlauf: alle fertig -> Detektor/Downloader duerfen NICHT mehr aufgerufen werden
    def boom(*a, **k):
        raise AssertionError("fertiges Symbol wurde erneut gerechnet")
    BL.process_universe(u, cfg, base, frozen, out, dl_1h=boom, dl_1d=boom, detect_fn=boom)
    # Bericht existiert weiterhin
    assert os.path.exists(os.path.join(out, "Universum_Test", "_GESAMT_Vergleich",
                                        "GESAMT_alle-Varianten.json"))
