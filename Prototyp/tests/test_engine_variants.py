# -*- coding: utf-8 -*-
"""Phase-B Increment S6/S7 - Ledger, Varianten-Engine, variantengetrennte Zustaende, Features.
QS-Tests: D1 (abgelehnte Setups protokolliert), 15 (Volumen deaktiviert nur Volumenfilter),
21/24 (gemeinsamer Snapshot/parent_signal_id, eigene IDs), 11-Trennung (Praez. 2), 22 (config_hash)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import features as F
from engine import variants as V
from engine.ledger import Ledger, make_variant_eval_id
from engine.varstate import StateRegistry


class Snap:
    def __init__(self, direction, psig="PSIG-abc"):
        self.direction = direction
        self.parent_signal_id = psig


# ---------------- Features ----------------
def test_ema_and_rvol():
    assert F.ema([1, 2, 3, 4, 5], 3) is not None
    assert F.ema([1, 2], 3) is None
    r = F.rvol([10] * 20 + [20], window=20)
    assert round(r, 2) == 2.0

def test_percentile_and_breakout_and_r2():
    p = F.percentile_rank(list(range(100)) + [50], window=100)
    assert 40 <= p <= 60
    bm = F.breakout_metrics(o=100, h=105, l=100, c=104, atr_val=2.0)
    assert bm["close_pos"] == 0.8 and bm["range_atr"] == 2.5
    assert F.linreg_r2([1, 2, 3, 4, 5]) == 1.0    # perfekte Gerade


# ---------------- Varianten ----------------
def test_pro2_ema200_direction():
    up = {"daily_close": 110, "daily_ema200": 100, "daily_bars": 300}
    assert V.pro2(Snap("LONG"), up).status == V.PASS
    assert V.pro2(Snap("SHORT"), up).status == V.FAIL
    assert V.pro2(Snap("LONG"), {"daily_close": 1, "daily_ema200": 2, "daily_bars": 100}).status == V.NOT_EVALUABLE

def test_pro3_rvol_and_volume_gate():
    assert V.pro3(Snap("LONG"), {"volume_usable": True, "rvol20": 1.3}).status == V.PASS
    assert V.pro3(Snap("LONG"), {"volume_usable": True, "rvol20": 1.0}).status == V.FAIL
    # 15: fehlendes Volumen deaktiviert NUR den Volumenfilter (NOT_EVALUABLE, kein FAIL)
    assert V.pro3(Snap("LONG"), {"volume_usable": False}).status == V.NOT_EVALUABLE

def test_pro4_atr_regime():
    assert V.pro4(Snap("LONG"), {"atr_percentile": 50}).status == V.PASS
    assert V.pro4(Snap("LONG"), {"atr_percentile": 95}).status == V.FAIL

def test_pro5_combined_not_evaluable_without_volume():
    assert V.pro5(Snap("LONG"), {"volume_usable": False}).status == V.NOT_EVALUABLE

def test_pro6_breakout_quality():
    good = {"body_ratio": 0.6, "close_pos": 0.8, "range_atr": 1.5}
    assert V.pro6(Snap("LONG"), good).status == V.PASS
    bad = {"body_ratio": 0.6, "close_pos": 0.4, "range_atr": 1.5}   # Close nicht im oberen 25%
    assert V.pro6(Snap("LONG"), bad).status == V.FAIL

def test_pro7_diagnostic_and_pro8_not_configured():
    d7 = V.pro7(Snap("LONG"), {"adx": 22, "choppiness": 55, "r2": 0.4})
    assert d7.status == V.DIAGNOSTIC and d7.accepted is True
    assert V.pro8(Snap("LONG"), {}).status == V.NOT_CONFIGURED

def test_evaluate_variants_shared_parent():
    snap = Snap("LONG", "PSIG-xyz")
    feats = {"volume_usable": True, "rvol20": 1.4, "atr_percentile": 40,
             "daily_close": 110, "daily_ema200": 100, "daily_bars": 300,
             "body_ratio": 0.6, "close_pos": 0.8, "range_atr": 1.2}
    decs = V.evaluate_variants(snap, feats, ["Str.3 Pro.1", "Str.3 Pro.2", "Str.3 Pro.3"])
    assert [d.strategy_id for d in decs] == ["Str.3 Pro.1", "Str.3 Pro.2", "Str.3 Pro.3"]
    assert all(d.status in (V.PASS, V.DIAGNOSTIC) for d in decs)


# ---------------- Ledger (D1) ----------------
def test_ledger_records_rejected_and_recovers(tmp_path):
    p = str(tmp_path / "ledger.json")
    lg = Ledger(p)
    lg.record_candidate("PSIG-1", "GC=F", "LONG", "REJECTED_STOP", "2026-07-20T16:00", "2026-07-20T20:00",
                        rejection_reason="WRONG_SIDE")
    lg.record_candidate("PSIG-2", "CL=F", "LONG", "ACCEPTED_PROVISIONAL", "2026-07-20T16:00", "2026-07-20T20:00")
    lg.record_variant_eval("PSIG-2", "Str.3 Pro.3", "v1", "NOT_EVALUABLE", rejection_reason="VOLUME_NOT_AVAILABLE")
    # Neustart -> alles da (auch der abgelehnte Kandidat)
    lg2 = Ledger(p)
    assert len(lg2.candidates) == 2
    cand, evals = lg2.by_parent("PSIG-2")
    assert cand["status"] == "ACCEPTED_PROVISIONAL" and len(evals) == 1

def test_variant_eval_ids_distinct_same_parent(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))
    a = lg.record_variant_eval("PSIG-9", "Str.3 Pro.2", "v1", "PASS")
    b = lg.record_variant_eval("PSIG-9", "Str.3 Pro.3", "v1", "FAIL")
    assert a != b                      # verschiedene Varianten -> verschiedene IDs
    assert a == make_variant_eval_id("PSIG-9", "Str.3 Pro.2")   # deterministisch


# ---------------- Variantengetrennte Zustaende (Praez. 2) ----------------
def test_variant_states_are_independent(tmp_path):
    reg = StateRegistry(str(tmp_path / "state.json"))
    p2 = reg.get("Str.3 Pro.2")
    p3 = reg.get("Str.3 Pro.3")
    sig = "support:100.0:0.5"
    ok, _ = p2.can_open("GC=F", sig, now=1000)
    assert ok
    p2.open("GC=F", "T1", sig)
    # Pro.2 hat jetzt Gold offen -> in Pro.2 kein zweiter Gold-Trade
    ok2, reason = p2.can_open("GC=F", "support:101:0.4", now=1001)
    assert ok2 is False and reason == "INSTRUMENT_BUSY"
    # Pro.3 darf denselben Gold-Trade parallel eroeffnen
    ok3, _ = p3.can_open("GC=F", sig, now=1001)
    assert ok3 is True

def test_line_reuse_and_cooldown_per_variant(tmp_path):
    reg = StateRegistry(str(tmp_path / "s.json"))
    p2 = reg.get("Str.3 Pro.2")
    sig = "support:100.0:0.5"
    p2.open("GC=F", "T1", sig)
    p2.close("GC=F", now=2000)
    # Cooldown aktiv
    ok, reason = p2.can_open("GC=F", "resistance:200:0.1", now=2000 + 10)
    assert ok is False and reason == "COOLDOWN"
    # nach Cooldown, aber gleiche Linie -> gesperrt
    ok2, reason2 = p2.can_open("GC=F", sig, now=2000 + 25 * 3600)
    assert ok2 is False and reason2 == "LINE_ALREADY_TRADED"
    # nach Cooldown, neue Linie -> erlaubt
    ok3, _ = p2.can_open("GC=F", "resistance:250:0.2", now=2000 + 25 * 3600)
    assert ok3 is True
