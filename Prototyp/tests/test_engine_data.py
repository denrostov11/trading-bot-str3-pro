# -*- coding: utf-8 -*-
"""Phase-B Increment S1/S2 - Datenzugriffsschicht.
Deckt QS-Tests: 2 (unvollstaendige 4h-Kerze nicht final), 13 (Dedup), 14 (Cache nicht kuerzen),
16 (Downloadfehler stoppt nicht alles) + Retry/Backoff + Aggregations-Korrektheit."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import dataaccess as DA
from engine.cache import BarCache
from engine import aggregate_4h as AGG


def hours(start_iso, n, price0=100.0):
    """n aufeinanderfolgende 1h-Bars ab start_iso (UTC)."""
    t0 = pd.Timestamp(start_iso, tz="UTC")
    rows = []
    for i in range(n):
        p = price0 + i
        rows.append({"Time": t0 + pd.Timedelta(hours=i),
                     "Open": p, "High": p + 0.5, "Low": p - 0.5, "Close": p + 0.2, "Volume": 10})
    return pd.DataFrame(rows)


# ---------- dataaccess: Retry/Backoff ----------
def test_retry_then_success():
    calls = {"n": 0}
    def flaky(sym, timeout):
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("temp")
        return hours("2026-07-01T00:00", 4)
    log = []
    df = DA.fetch("GC=F", downloader=flaky, retries=3, backoff_seconds=1,
                  sleep_fn=lambda s: None, log=log)
    assert df is not None and calls["n"] == 3

def test_permanent_failure_returns_none():
    def always(sym, timeout): raise TimeoutError("nope")
    log = []
    df = DA.fetch("X", downloader=always, retries=2, sleep_fn=lambda s: None, log=log)
    assert df is None
    assert any("dauerhaft" in m for m in log)

def test_batch_isolates_failures():
    def dl(sym, timeout):
        if sym == "BAD":
            raise ValueError("boom")
        return hours("2026-07-01T00:00", 4)
    res, log = DA.fetch_batch(["A", "BAD", "B"], downloader=dl, sleep_fn=lambda s: None, retries=0)
    assert res["A"] is not None and res["B"] is not None and res["BAD"] is None


# ---------- cache: additiv, dedup, nie kuerzen ----------
def test_cache_roundtrip(tmp_path):
    c = BarCache(str(tmp_path))
    c.merge("GC=F", "1h", hours("2026-07-01T00:00", 5))
    got = c.load("GC=F", "1h")
    assert len(got) == 5 and got["Time"].is_monotonic_increasing

def test_cache_merge_dedup_and_grow(tmp_path):
    c = BarCache(str(tmp_path))
    c.merge("GC=F", "1h", hours("2026-07-01T00:00", 10))
    # neuer Download ueberlappt (letzte 3) + 2 neue spaetere Bars
    c.merge("GC=F", "1h", hours("2026-07-01T07:00", 5))   # 07..11 -> 07,08,09 overlap, 10,11 neu
    got = c.load("GC=F", "1h")
    assert len(got) == 12                    # 10 + 2 neue, Duplikate entfernt
    assert got["Time"].is_unique

def test_cache_never_shrinks_on_shorter_download(tmp_path):
    c = BarCache(str(tmp_path))
    c.merge("GC=F", "1h", hours("2026-07-01T00:00", 20))
    # kuerzerer Download (nur 3 Bars) darf Historie NICHT loeschen
    c.merge("GC=F", "1h", hours("2026-07-01T00:00", 3))
    assert len(c.load("GC=F", "1h")) == 20


# ---------- aggregate_4h: Vollstaendigkeit / is_final ----------
def test_aggregate_full_blocks_crypto():
    df = hours("2026-07-01T00:00", 24)       # 24 volle Stunden -> 6 volle 4h-Bloecke
    out = AGG.aggregate(df, **AGG.CRYPTO_24_7)
    assert len(out) == 6
    assert all(out["source_1h_bar_count"] == 4)
    assert all(out["completeness_ratio"] == 1.0)
    # data_cutoff default = letzter Bar (23:00) + 1h = 24:00 -> alle 6 abgeschlossen
    assert out["is_final"].all()

def test_aggregate_incomplete_last_block_not_final():
    df = hours("2026-07-01T00:00", 22)       # 5 volle Bloecke + 1 Block mit nur 2 Stunden
    out = AGG.aggregate(df, **AGG.CRYPTO_24_7)
    last = out.iloc[-1]
    assert last["source_1h_bar_count"] == 2
    assert last["completeness_ratio"] == 0.5
    assert last["is_final"] == False          # A1-Fix: unvollstaendige Kerze nicht final
    assert AGG.final_only(out).shape[0] == 5   # nur die 5 vollen Bloecke

def test_aggregate_ohlc_correct():
    df = hours("2026-07-01T00:00", 4, price0=100.0)   # Preise 100,101,102,103
    out = AGG.aggregate(df, **AGG.CRYPTO_24_7).iloc[0]
    assert out["Open"] == 100.0                       # erster Open
    assert out["Close"] == 103.2                      # letzter Close (103 + 0.2)
    assert out["High"] == 103.5 and out["Low"] == 99.5
    assert out["Volume"] == 40.0

def test_aggregate_anchor_offset():
    # Anker um 1 Uhr: Bloecke beginnen 01,05,09,... -> erster Bar 00:00 faellt in Block ab 21:00 Vortag
    df = hours("2026-07-01T00:00", 8)
    out = AGG.aggregate(df, anchor_hour=1, session_hours=None)
    starts = [pd.Timestamp(s).strftime("%H:%M") for s in out["start_utc"]]
    assert "01:00" in starts and "05:00" in starts
