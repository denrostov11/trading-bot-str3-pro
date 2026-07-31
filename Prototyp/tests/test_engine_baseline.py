# -*- coding: utf-8 -*-
"""Phase-B Increment S4/S5 - Datenqualitaet + Baseline-Kausalfixes.
QS-Tests: 10 (Stop falsche Seite), 11 (naechste Zone <2R, hier DIAGNOSTIC), 12 (kein rueckdatierter
Trade), 15 (fehlendes Volumen), 17 (Rollover sperrt Setup), 21/25 (Snapshot/parent_signal_id)."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import quality as Q
from engine import baseline as B


# ---------------- Datenqualitaet ----------------
def _df(vol, ac_high=100):
    n = len(vol)
    return pd.DataFrame({
        "Time": pd.date_range("2026-07-01", periods=n, freq="4h", tz="UTC"),
        "Open": [ac_high] * n, "High": [ac_high + 1] * n, "Low": [ac_high - 1] * n,
        "Close": [ac_high] * n, "Volume": vol,
    })

def test_fx_volume_not_usable():
    ok, reason = Q.validate_volume(_df([100] * 30), "fx")
    assert ok is False and reason == "FX_NO_CENTRAL_VOLUME"

def test_zero_volume_not_usable():
    ok, reason = Q.validate_volume(_df([0] * 30), "index")
    assert ok is False

def test_good_volume_usable():
    ok, reason = Q.validate_volume(_df([100 + i for i in range(30)], ), "crypto")
    assert ok is True and reason == "OK"

def test_volume_invalid_ratio():
    vol = [None] * 5 + [100] * 5   # 50% ungueltig
    ok, reason = Q.validate_volume(_df(vol), "crypto")
    assert ok is False and "INVALID_RATIO" in reason

def test_rollover_flagged_only_for_futures():
    # kleiner True-Range/Gap, dann ein grosser Sprung
    n = 40
    close = [100.0] * n
    openp = [100.0] * n
    high = [100.5] * n
    low = [99.5] * n
    # Ausreisser bei i=30: grosser Gap
    openp[30] = 130.0; high[30] = 131.0; low[30] = 129.0; close[30] = 130.0
    df = pd.DataFrame({"Time": pd.date_range("2026-06-01", periods=n, freq="4h", tz="UTC"),
                       "Open": openp, "High": high, "Low": low, "Close": close,
                       "Volume": [10] * n,
                       "session_date": pd.date_range("2026-06-01", periods=n, freq="4h").date})
    assert Q.detect_rollover(df, is_futures=True) != []
    assert Q.detect_rollover(df, is_futures=False) == []

def test_near_rollover():
    assert Q.near_rollover("2026-06-06", ["2026-06-05"], tol_days=2) is True
    assert Q.near_rollover("2026-06-20", ["2026-06-05"], tol_days=2) is False

def test_data_quality_detects_duplicates_and_monotonic():
    df = _df([10] * 5)
    df.loc[4, "Time"] = df.loc[3, "Time"]   # Duplikat + nicht monoton
    dq = Q.data_quality(df, "crypto", is_futures=False)
    assert dq["duplicate_count"] >= 1 and dq["status"] == "TIMESERIES_ISSUE"


# ---------------- Baseline-Kausalfixes ----------------
class FakeLine:
    """Duck-typed Linienobjekt fuer Tests (value_at linear)."""
    def __init__(self, i0, p0, i1, p1, kind, taps, angle=10.0, breaking_bar=-1):
        self.i0, self.p0, self.i1, self.p1 = i0, p0, i1, p1
        self.kind, self.taps, self.angle_deg = kind, list(taps), angle
        self.breaking_bar = breaking_bar
    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def _final_df(n, close=100.0):
    return pd.DataFrame({"Close": [close] * n})


# 12: kein rueckdatierter Trade - alter Bruch loest keinen Trigger aus (A3)
def test_no_backdated_trigger():
    assert B.is_fresh_trigger(breaking_bar=50, n=60) is False
    assert B.is_fresh_trigger(breaking_bar=59, n=60) is True

# 10: Stop auf falscher Seite -> REJECTED_STOP (B3)
def test_stop_wrong_side_rejected():
    n = 60; bb = n - 1
    # LONG, aber Safety liegt UEBER dem Einstieg -> Stop faelschlich > entry
    action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)
    safety_bad = FakeLine(0, 110, bb, 120, "support", [5, 25])   # projiziert oberhalb
    res = B.evaluate("BTC-USD", "crypto", "LONG", action, safety_bad, n, _final_df(n, 100.0),
                     atr_val=2.0, signal_time_iso="2026-07-20T16:00:00+00:00",
                     data_cutoff_iso="2026-07-20T20:00:00+00:00", pivot_prices=[80, 81, 120, 121],
                     data_quality_status="OK")
    assert res.status == B.REJECTED_STOP and res.rejection_reason == "WRONG_SIDE"

# 17: Rollover/Datenqualitaet sperrt Setup -> REJECTED_DATA_QUALITY (C4)
def test_data_quality_rejection():
    n = 60; bb = n - 1
    action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)
    safety = FakeLine(0, 85, bb, 80, "support", [5, 25])
    res = B.evaluate("CL=F", "commodity", "LONG", action, safety, n, _final_df(n, 100.0),
                     atr_val=2.0, signal_time_iso="2026-07-20T16:00:00+00:00",
                     data_cutoff_iso="2026-07-20T20:00:00+00:00", pivot_prices=[120, 121],
                     data_quality_status="OK", near_unexplained_rollover=True)
    assert res.status == B.REJECTED_DATA_QUALITY

# 21/25: Annahme erzeugt frozen Snapshot mit deterministischer parent_signal_id
def test_accepted_snapshot_and_parent_id_deterministic():
    n = 60; bb = n - 1
    action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)   # LONG-Bruch
    safety = FakeLine(0, 85, bb, 88, "support", [5, 25])   # unter dem Einstieg -> Stop unten
    args = dict(atr_val=2.0, signal_time_iso="2026-07-20T16:00:00+00:00",
                data_cutoff_iso="2026-07-20T20:00:00+00:00",
                pivot_prices=[130, 131, 132], data_quality_status="OK")
    res = B.evaluate("BTC-USD", "crypto", "LONG", action, safety, n, _final_df(n, 100.0), **args)
    assert res.status == B.ACCEPTED_PROVISIONAL
    snap = res.snapshot
    assert snap.parent_signal_id.startswith("PSIG-")
    # Snapshot ist unveraenderlich (frozen)
    import dataclasses, pytest
    with pytest.raises(dataclasses.FrozenInstanceError):
        snap.signal_close = 1.0
    # deterministisch: gleiche Eingaben -> gleiche ID
    res2 = B.evaluate("BTC-USD", "crypto", "LONG",
                      FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb),
                      FakeLine(0, 85, bb, 88, "support", [5, 25]), n, _final_df(n, 100.0), **args)
    assert res2.snapshot.parent_signal_id == snap.parent_signal_id

# 11 (DIAGNOSTIC): naechste Zone <2R wird berechnet + markiert, aber NICHT als Ablehnung aktiviert
def test_rr_gate_is_diagnostic_only():
    n = 60; bb = n - 1
    action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)
    safety = FakeLine(0, 85, bb, 88, "support", [5, 25])   # Stop ~ projiziert unter entry
    # naechste Zone knapp ueber entry -> rr < 2
    res = B.evaluate("BTC-USD", "crypto", "LONG", action, safety, n, _final_df(n, 100.0),
                     atr_val=2.0, signal_time_iso="2026-07-20T16:00:00+00:00",
                     data_cutoff_iso="2026-07-20T20:00:00+00:00",
                     pivot_prices=[104, 104.2], data_quality_status="OK")
    assert res.status == B.ACCEPTED_PROVISIONAL             # NICHT abgelehnt (Gate diagnostisch)
    assert res.diagnostics["would_reject_rr_DIAGNOSTIC"] is True

# B2: naechste Zone wird nicht uebersprungen
def test_nearest_zone_not_skipped():
    z, rr = B.nearest_zone_and_rr("LONG", entry=100.0, stop=98.0, zones=[102.8, 106.0])
    assert z == 102.8 and round(rr, 2) == 1.40   # nimmt die naechste (1.4R), nicht 3R
