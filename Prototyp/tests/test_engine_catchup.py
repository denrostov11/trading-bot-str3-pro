# -*- coding: utf-8 -*-
"""Luecken-Aufholen (PC war zwischen Zyklen aus): analyze_instrument_history spielt jede seit dem
Wasserstand NEU abgeschlossene 4h-Kerze der Reihe nach als eigenes 'letzte-Kerze'-Fenster durch
(kein Look-ahead). run_cycle verarbeitet die Ergebnis-LISTE und schliesst einen Trade, der komplett
in der Aus-Zeit auf- und zuging, im selben Zyklus ab."""
import os, sys
import pandas as pd
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import orchestrate as O
from engine import cycle as CY
from engine import variants as VAR
from engine import tracker as T
from engine.ledger import Ledger
from engine.varstate import StateRegistry

NOW = pd.Timestamp("2026-07-24", tz="UTC")


class FakeLine:
    def __init__(self, i0, p0, i1, p1, kind, taps, breaking_bar):
        self.i0, self.p0, self.i1, self.p1 = i0, p0, i1, p1
        self.kind, self.taps, self.angle_deg = kind, list(taps), 12.0
        self.breaking_bar = breaking_bar
    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def make_1h(n_hours, price=100.0):
    t0 = pd.Timestamp("2026-03-01", tz="UTC")
    rows = [{"Time": t0 + pd.Timedelta(hours=i), "Open": price, "High": price + 1,
             "Low": price - 1, "Close": price, "Volume": 100 + i} for i in range(n_hours)]
    return pd.DataFrame(rows)


def _mem_ledger():
    lg = Ledger.__new__(Ledger)
    lg.path = ":mem:"; lg.candidates = []; lg.variant_evals = []; lg._save = lambda: None
    return lg


def _detect_always(compat):
    """Feuert auf JEDER Kerze (letzte Kerze = Bruchkerze) -> ACCEPTED_PROVISIONAL."""
    n = len(compat); bb = n - 1
    action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)   # LONG
    safety = FakeLine(0, 85, bb, 88, "support", [5, 25], breaking_bar=-1)
    return {"action": action, "safety": safety, "direction": "LONG", "atr_last": 2.0,
            "atr_series": pd.Series([2.0] * n), "pivots": ([], []),
            "pivot_prices": [300, 301], "n": n}


def _hist(ledger, since_time):
    return O.analyze_instrument_history(
        "X", "X-USD", "crypto", False, ["Str.3 Pro.1"], ledger, since_time=since_time,
        downloader=lambda s, t: make_1h(120 * 4), detect_fn=_detect_always, now=NOW)


# --------- Erststart: nur die aktuelle Kerze, KEIN History-Backfill ----------
def test_first_start_only_last_candle():
    lg = _mem_ledger()
    results, full_compat, newest = _hist(lg, since_time=None)
    assert full_compat is not None
    assert len(results) == 1                                   # nur die letzte Kerze
    assert results[0]["status"] == "ACCEPTED_PROVISIONAL"
    assert newest == pd.Timestamp(full_compat["Time"].iloc[-1]).isoformat()


# --------- Luecke: alle seit dem Wasserstand verpassten Kerzen werden nachgeholt ----------
def test_gap_replays_all_missed_candles():
    lg = _mem_ledger()
    _, full_compat, _ = _hist(lg, since_time=None)             # Wasserstand ermitteln
    n = len(full_compat)
    since = full_compat["Time"].iloc[n - 4]                    # 3 Kerzen "verpasst"
    lg2 = _mem_ledger()
    results, _, newest = _hist(lg2, since_time=since)
    assert len(results) == 3                                   # genau die 3 verpassten Kerzen
    assert all(r["status"] == "ACCEPTED_PROVISIONAL" for r in results)
    times = [r["signal_time"] for r in results]
    assert times == sorted(times) and len(set(times)) == 3     # chronologisch + verschieden
    assert newest == pd.Timestamp(full_compat["Time"].iloc[-1]).isoformat()


# --------- Kein neuer Kerzenschluss -> nichts erneut bewerten (aber weiter tracken) ----------
def test_no_new_candle_no_reprocess():
    lg = _mem_ledger()
    _, full_compat, newest = _hist(lg, since_time=None)
    results, full_compat2, newest2 = _hist(_mem_ledger(), since_time=newest)
    assert results == []                                       # keine neue Kerze
    assert full_compat2 is not None                            # trotzdem Kerzen fuers Tracking
    assert newest2 == newest


# --------- NO_DATA -> Fehlerstatus, Wasserstand nicht vorruecken ----------
def test_no_data_returns_error_and_keeps_watermark():
    def dl_none(sym, timeout):
        raise ValueError("leer")
    results, full_compat, newest = O.analyze_instrument_history(
        "X", "X-USD", "crypto", False, ["Str.3 Pro.1"], _mem_ledger(),
        since_time="2026-07-20T00:00:00+00:00", downloader=dl_none,
        detect_fn=_detect_always, now=NOW)
    assert full_compat is None
    assert results[0]["status"] == "NO_DATA"
    assert newest == "2026-07-20T00:00:00+00:00"               # Wasserstand unveraendert


# --------- Integration: Trade, der komplett in der Aus-Zeit auf- und zuging, schliesst im Zyklus ----------
def _compat(times, ohlc):
    return pd.DataFrame({"Time": pd.to_datetime(times, utc=True),
                         "Open": [o for o, *_ in ohlc], "High": [h for _, h, *_ in ohlc],
                         "Low": [l for _, _, l, _ in ohlc], "Close": [c for *_, c in ohlc]})


def _accepted(sig_time, psig):
    d1 = VAR.VariantDecision("Str.3 Pro.1", VAR.PASS)
    return {"symbol": "BTC-USD", "status": "ACCEPTED_PROVISIONAL", "parent_signal_id": psig,
            "direction": "LONG", "asset_class": "crypto", "atr": 2.0, "signal_close": 100.0,
            "baseline_stop": 98.0, "baseline_target": 106.0, "action_sig": f"resistance:100:{psig}",
            "signal_time": sig_time, "variant_decisions": [d1]}


def test_run_cycle_gap_trade_opens_and_closes_same_cycle(tmp_path):
    reg = StateRegistry(str(tmp_path / "state.json"))
    store = T.PaperTradeStore(str(tmp_path / "trades.json"))
    # Volle Kerzen: Signal bei 00:00 (in der Aus-Zeit), Ziel 106 wird bei 08:00 getroffen
    compat = _compat(
        ["2026-07-01T00:00", "2026-07-01T04:00", "2026-07-01T08:00"],
        [(100, 101, 99, 100), (100.2, 103, 100, 102), (102, 107, 101, 106.5)])
    # results_by_symbol als LISTE (mehrere nachgeholte Kerzen; hier eine akzeptierte)
    results = {"BTC-USD": [_accepted("2026-07-01T00:00:00+00:00", "PSIG-GAP")]}
    summary = CY.run_cycle({"BTC-USD": compat}, results, {"Str.3 Pro.1": "BE-0"},
                           reg, store, now=2000)
    assert summary["opened"] == 1
    assert summary["closed"] == 1                              # dank zweitem Track-Durchgang
    t = store.trades[0]
    assert t.status == "closed" and t.result["outcome"] == "TARGET"
