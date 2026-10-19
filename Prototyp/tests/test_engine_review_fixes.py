# -*- coding: utf-8 -*-
"""Regressionstests fuer die im Codex-Review (Oktober 2026) gefundenen und behobenen Fehler.

Jeder Test haette mit dem Stand vor der Behebung fehlgeschlagen:
  1 Daily-Filter am Kerzen-ENDE statt am Kerzenbeginn (Pro.2/Pro.5, Backtest)
  2 erste Kerze des Testfensters wird bewertet
  3 gescheitertes Symbol haelt das Universum offen (kein Teil-Bericht, Wiederholung)
  4 Checkpoints werden atomar geschrieben
  5 eingefrorene Rohdaten werden atomar geschrieben
  6 Checkpoints sind an die Lauf-Konfiguration gebunden
  7 Monatsberichte zaehlen nur die Signale des Monats
  8 TEST_END-Bewertungen werden getrennt ausgewiesen
"""
import os, sys, json
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import backtest_loop as BL, backtest_run as BR, backtest_data as BD
from engine import backtest_report as BRP, backtest_pdf as BPDF, orchestrate, aggregate_4h
from engine.instruments import classify
from engine.ledger import Ledger
from engine.tracker import PaperTradeStore
from engine.varstate import StateRegistry

SID = "Str.3 Pro.1"


# ---------------- Testdaten (wie in test_engine_backtest_loop) ----------------
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
    return {"start": "2025-01-01", "end": "2025-01-11", "variants": [SID],
            "be_map": {SID: "BE-0"}, "code_version": "bt-test", "config_hash": "CTEST",
            "out_root": out_root, "frozen_dir": frozen_dir}


U2 = {"name": "Universum_Test", "symbols": [["Alpha", "AAA-USD"], ["Beta", "BBB-USD"]]}


def _dirs(tmp_path):
    base = str(tmp_path / "rt"); os.makedirs(base)
    return base, str(tmp_path / "frozen"), str(tmp_path / "out")


def _run_universe(u, cfg, base, frozen, out):
    return BL.process_universe(u, cfg, base, frozen, out, dl_1h=_dl_1h, dl_1d=_dl_1d,
                               detect_fn=_detect_every)


def _write_cfg(base, cfg):
    p = os.path.join(base, "backtest_config.json")
    with open(p, "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    return p


# ---------------- 1 + 2: Fensterbeginn und Daily-Zeitpunkt ----------------
def test_decision_times_are_candle_ends():
    fin = aggregate_4h.final_only(aggregate_4h.aggregate(_dl_1h("X"), anchor_hour=0,
                                                         session_hours=None)).reset_index(drop=True)
    opens = pd.to_datetime(fin["Time"], utc=True)
    ends = orchestrate._decision_times(fin, opens)
    assert len(ends) == len(opens)
    assert ((ends - opens) == pd.Timedelta(hours=4)).all()


def test_daily_candle_closed_within_4h_candle_is_visible():
    d = _dl_1d("X")
    day = pd.Timestamp("2024-08-10", tz="UTC")
    # 4h-Kerze 20:00-24:00 am 10.08. -> entschieden um 00:00 am 11.08.: Tageskerze vom 10.08. ist bekannt
    seen_at_close = BD.daily_asof(d, day + pd.Timedelta(hours=24))
    assert pd.to_datetime(seen_at_close["Time"], utc=True).max() == day
    # alter Fehler: am Kerzenbeginn (20:00) bewertet -> nur bis 09.08., einen Tag zu alt
    seen_at_open = BD.daily_asof(d, day + pd.Timedelta(hours=20))
    assert pd.to_datetime(seen_at_open["Time"], utc=True).max() == day - pd.Timedelta(days=1)


def test_first_window_candle_is_evaluated_with_daily_at_candle_end(tmp_path, monkeypatch):
    seen = []
    real = BD.daily_asof

    def recording(daily_df, ts):
        seen.append(pd.Timestamp(ts))
        return real(daily_df, ts)

    monkeypatch.setattr(BD, "daily_asof", recording)
    lg = Ledger(str(tmp_path / "l.json"))
    store = PaperTradeStore(str(tmp_path / "t.json"))
    state = StateRegistry(str(tmp_path / "s.json"))
    c = classify("AAA-USD")
    BR.run_symbol("Alpha", "AAA-USD", c["asset_class"], c["is_futures"], [SID], _dl_1h("AAA-USD"),
                  _dl_1d("AAA-USD"), "2025-01-01", "2025-01-11", lg, store, state, {SID: "BE-0"},
                  0, None, {"code_version": "t", "config_hash": "C"}, None, _detect_every)
    start = pd.Timestamp("2025-01-01", tz="UTC")
    # Fix 2: die Kerze, die genau zum Fensterbeginn oeffnet, wird bewertet
    assert start in {pd.Timestamp(x["signal_time"]) for x in lg.candidates}
    # Fix 1: Daily-Schnitt am ENDE dieser ersten Kerze, nicht an ihrem Beginn
    assert seen and min(seen) == start + pd.Timedelta(hours=4)


# ---------------- 3: gescheitertes Symbol ----------------
def test_failed_symbol_keeps_universe_open_and_is_retried(tmp_path, monkeypatch):
    base, frozen, out = _dirs(tmp_path)
    cfg = _cfg(out, frozen)
    real = BL._process_symbol

    def flaky(inst, *a, **k):
        if inst["symbol"] == "BBB-USD":
            raise RuntimeError("simulierter Absturz")
        return real(inst, *a, **k)

    monkeypatch.setattr(BL, "_process_symbol", flaky)
    assert _run_universe(U2, cfg, base, frozen, out) is False
    assert json.load(open(os.path.join(base, "run_Universum_Test", "done.json"))) == ["AAA-USD"]
    assert not os.path.exists(os.path.join(out, "Universum_Test", "_GESAMT_Vergleich"))  # kein Teil-Bericht

    calls = []

    def tracking(inst, *a, **k):
        calls.append(inst["symbol"])
        return real(inst, *a, **k)

    monkeypatch.setattr(BL, "_process_symbol", tracking)
    assert _run_universe(U2, cfg, base, frozen, out) is True
    assert calls == ["BBB-USD"]                       # nur das gescheiterte Symbol wird nachgeholt
    assert os.path.exists(os.path.join(out, "Universum_Test", "_GESAMT_Vergleich",
                                       "GESAMT_alle-Varianten.json"))


def test_run_does_not_mark_incomplete_universe_done(tmp_path, monkeypatch):
    base, frozen, out = _dirs(tmp_path)
    monkeypatch.setattr(BL, "BASE", base)
    cfg = dict(_cfg(out, frozen), queue=[{"name": "Universum_Test", "symbols": [["Alpha", "AAA-USD"]]}])
    attempts = []

    def always_fail(inst, *a, **k):
        attempts.append(inst["symbol"])
        raise RuntimeError("dauerhaft kaputt")

    monkeypatch.setattr(BL, "_process_symbol", always_fail)
    BL.run(_write_cfg(base, cfg))
    assert attempts == ["AAA-USD", "AAA-USD"]        # genau ein zweiter Versuch, keine Endlosschleife
    assert not os.path.exists(os.path.join(base, "universes_done.json"))


# ---------------- 4 + 5: atomares Schreiben ----------------
def test_atomic_json_keeps_old_checkpoint_when_write_fails(tmp_path):
    p = str(tmp_path / "done.json")
    BL._atomic_json(p, ["AAA-USD"])
    with pytest.raises(TypeError):
        BL._atomic_json(p, ["BBB-USD", object()])    # bricht mitten im Schreiben ab
    assert json.load(open(p)) == ["AAA-USD"]          # alter Checkpoint unversehrt


def test_interrupted_freeze_leaves_no_truncated_file(tmp_path, monkeypatch):
    fz = str(tmp_path / "frozen")
    final = os.path.join(fz, BD.safe_name("AAA-USD") + "_1h.csv")
    real = pd.DataFrame.to_csv

    def broken(self, path, *a, **k):
        with open(path, "w") as f:
            f.write("Time,Open\n2024-12-01T00:00:00+00:00,100\n")   # halb geschrieben
        raise OSError("Strom weg")

    monkeypatch.setattr(pd.DataFrame, "to_csv", broken)
    with pytest.raises(OSError):
        BD.fetch_and_freeze("AAA-USD", fz, dl_1h=_dl_1h, dl_1d=_dl_1d)
    assert not os.path.exists(final)                  # nichts, was spaeter als vollstaendig gaelte

    monkeypatch.setattr(pd.DataFrame, "to_csv", real)
    got = BD.fetch_and_freeze("AAA-USD", fz, dl_1h=_dl_1h, dl_1d=_dl_1d)
    assert os.path.exists(final) and len(got["1h"]) == len(_dl_1h("AAA-USD"))


# ---------------- 6: Checkpoints an die Konfiguration binden ----------------
def test_changed_config_refuses_to_reuse_checkpoints(tmp_path):
    base, frozen, out = _dirs(tmp_path)
    cfg = _cfg(out, frozen)
    assert _run_universe(U2, cfg, base, frozen, out) is True
    changed = dict(cfg, end="2025-01-10", config_hash="CTEST2")
    with pytest.raises(BL.RunIdentityMismatch):
        _run_universe(U2, changed, base, frozen, out)


def test_legacy_checkpoints_without_identity_are_not_reused(tmp_path):
    base, frozen, out = _dirs(tmp_path)
    run_dir = os.path.join(base, "run_Universum_Test"); os.makedirs(run_dir)
    with open(os.path.join(run_dir, "done.json"), "w") as f:
        json.dump(["AAA-USD"], f)
    with pytest.raises(BL.RunIdentityMismatch):
        _run_universe(U2, _cfg(out, frozen), base, frozen, out)


def test_run_aborts_instead_of_skipping_when_config_changed(tmp_path, monkeypatch, capsys):
    base, frozen, out = _dirs(tmp_path)
    monkeypatch.setattr(BL, "BASE", base)
    monkeypatch.setattr(BL, "_process_symbol", lambda inst, *a, **k: {"status": "OK"})
    cfg = dict(_cfg(out, frozen), queue=[{"name": "Universum_Test", "symbols": [["Alpha", "AAA-USD"]]}])
    BL.run(_write_cfg(base, cfg))
    ud_path = os.path.join(base, "universes_done.json")
    assert json.load(open(ud_path)) == ["Universum_Test"]
    capsys.readouterr()                                     # Ausgabe des ersten Laufs verwerfen

    def must_not_run(*a, **k):
        raise AssertionError("alte Checkpoints duerfen mit neuer Konfiguration nicht weiterlaufen")

    monkeypatch.setattr(BL, "_process_symbol", must_not_run)
    BL.run(_write_cfg(base, dict(cfg, end="2025-01-10", config_hash="CTEST2")))
    log = capsys.readouterr().out
    # alter Fehler: das Universum galt trotz geaenderter Konfiguration still als "fertig"
    assert "Alle Universen der Warteschlange fertig" not in log
    assert "ABBRUCH Universum_Test" in log and "abweichend" in log
    assert json.load(open(ud_path)) == ["Universum_Test"]   # nichts als fertig umgebucht


# ---------------- 7: Monatsberichte ----------------
def test_monthly_reports_count_only_that_months_signals(tmp_path):
    lg = Ledger(str(tmp_path / "l.json"))

    def cand(cid, t):
        return {"candidate_id": cid, "parent_signal_id": "P" + cid, "signal_time": t,
                "status": "ACCEPTED_PROVISIONAL", "symbol": "AAA-USD"}

    def ev(cid, status):
        return {"candidate_id": cid, "parent_signal_id": "P" + cid, "strategy_id": SID, "status": status}

    lg.candidates = [cand("a", "2025-01-05T04:00:00+00:00"), cand("b", "2025-01-20T08:00:00+00:00"),
                     cand("c", "2025-02-03T12:00:00+00:00")]
    lg.variant_evals = [ev("a", "PASS"), ev("b", "FAIL"), ev("c", "PASS")]
    views = BRP.ledgers_by_month(lg, [(2025, 1), (2025, 2), (2025, 3)])
    assert views[(2025, 1)].counts_by_status(SID) == {"PASS": 1, "FAIL": 1}
    assert views[(2025, 2)].counts_by_status(SID) == {"PASS": 1}
    assert views[(2025, 3)].counts_by_status(SID) == {}
    assert lg.counts_by_status(SID) == {"PASS": 2, "FAIL": 1}      # Original unveraendert
    with pytest.raises(TypeError):
        views[(2025, 1)]._save()                                   # Sicht ist nur lesend


# ---------------- 8: TEST_END getrennt ausweisen ----------------
def test_test_end_valuations_are_reported_separately(tmp_path):
    base, frozen, out = _dirs(tmp_path)
    cfg = _cfg(out, frozen)
    assert _run_universe(U2, cfg, base, frozen, out) is True     # Dauer-Signal -> offen bis Testende
    uni = os.path.join(out, "Universum_Test")
    rep = json.load(open(os.path.join(uni, "Pro.1_Baseline", "Pro.1_Baseline_GESAMT.json"), encoding="utf-8"))
    ab = rep["abschluss_aufschluesselung"]
    assert ab["test_end_bewertungen"]["n"] >= 1
    assert ab["test_end_bewertungen"]["n"] + ab["regulaere_ausstiege"]["n"] == rep["closed_trades"]
    comp = json.load(open(os.path.join(uni, "_GESAMT_Vergleich", "GESAMT_alle-Varianten.json"), encoding="utf-8"))
    assert comp["test_end_hinweis"]
    assert all("abschluss_aufschluesselung" in v for v in comp["variants"])
    # PDF-Erzeugung verkraftet den neuen TEST_END-Hinweis
    BPDF.build_all(uni, cfg["variants"], cfg["start"], cfg["end"])
    assert any(f.lower().endswith(".pdf") for _, _, fs in os.walk(uni) for f in fs)


# ---------------- 9: voruebergehend fehlende Daten (Yahoo-Sperre am 09.08.2026) ----------------
def test_no_data_is_retried_on_later_days_before_quarantine(tmp_path, monkeypatch):
    base, frozen, out = _dirs(tmp_path)
    cfg = _cfg(out, frozen)
    real = BL._process_symbol

    def bbb_without_data(inst, *a, **k):
        if inst["symbol"] == "BBB-USD":
            return {"symbol": "BBB-USD", "status": "NO_DATA_QUARANTINE"}
        return real(inst, *a, **k)

    monkeypatch.setattr(BL, "_process_symbol", bbb_without_data)
    run_dir = os.path.join(base, "run_Universum_Test")
    # zweimal am selben Tag (zaehlt einmal), dann an zwei weiteren Tagen -> erst am 3. Tag aufgegeben
    for day, complete in (("2026-08-09", False), ("2026-08-09", False),
                          ("2026-08-10", False), ("2026-08-11", True)):
        monkeypatch.setattr(BL, "_today", lambda d=day: d)
        assert _run_universe(U2, cfg, base, frozen, out) is complete
        assert ("BBB-USD" in json.load(open(os.path.join(run_dir, "done.json")))) is complete
    assert json.load(open(os.path.join(run_dir, BL.NO_DATA_FILE)))["BBB-USD"]["days"] == \
        ["2026-08-09", "2026-08-10", "2026-08-11"]


def test_no_data_streak_pauses_run_instead_of_burning_through_symbols(tmp_path, monkeypatch):
    base, frozen, out = _dirs(tmp_path)
    syms = [[f"S{i}", f"S{i:02d}-USD"] for i in range(25)]
    calls = []

    def blocked(inst, *a, **k):
        calls.append(inst["symbol"])
        return {"symbol": inst["symbol"], "status": "NO_DATA_QUARANTINE"}

    monkeypatch.setattr(BL, "_process_symbol", blocked)
    u = {"name": "Universum_Test", "symbols": syms}
    res = _run_universe(u, _cfg(out, frozen), base, frozen, out)
    assert res is BL.PAUSED and not res                     # pausiert - und gilt nie als "fertig"
    assert len(calls) == BL.NO_DATA_BREAKER                 # Pause nach 10 statt alle 25 zu verbrennen
    dp = os.path.join(base, "run_Universum_Test", "done.json")
    assert not os.path.exists(dp) or json.load(open(dp)) == []   # kein Symbol endgueltig aufgegeben


def test_multi_day_outage_still_trips_breaker_on_third_day(tmp_path, monkeypatch):
    # Codex-Zweitpruefung: zaehlten endgueltige Quarantaenen nicht zur Serie, rauschte eine
    # 3-taegige Sperre am 3. Tag wieder durch alle Symbole (Ursprungsfehler, nur verzoegert).
    base, frozen, out = _dirs(tmp_path)
    syms = [[f"S{i}", f"S{i:02d}-USD"] for i in range(25)]
    calls = []

    def blocked(inst, *a, **k):
        calls.append(inst["symbol"])
        return {"symbol": inst["symbol"], "status": "NO_DATA_QUARANTINE"}

    monkeypatch.setattr(BL, "_process_symbol", blocked)
    u = {"name": "Universum_Test", "symbols": syms}
    for day in ("2026-08-09", "2026-08-10", "2026-08-11"):
        monkeypatch.setattr(BL, "_today", lambda d=day: d)
        calls.clear()
        res = _run_universe(u, _cfg(out, frozen), base, frozen, out)
        assert res is BL.PAUSED and len(calls) == BL.NO_DATA_BREAKER
    done = json.load(open(os.path.join(base, "run_Universum_Test", "done.json")))
    # Schaden pro gestoertem Tag begrenzt: hoechstens Breaker-1 Symbole, nicht 25
    assert len(done) == BL.NO_DATA_BREAKER - 1


def test_run_does_not_retry_immediately_when_paused(tmp_path, monkeypatch):
    # Codex-Zweitpruefung: eine Pause darf keinen sofortigen zweiten Versuch ausloesen
    # (der wuerde die gesperrte Datenquelle mit weiteren Anfragen belasten).
    base, frozen, out = _dirs(tmp_path)
    monkeypatch.setattr(BL, "BASE", base)
    syms = [[f"S{i}", f"S{i:02d}-USD"] for i in range(25)]
    calls = []

    def blocked(inst, *a, **k):
        calls.append(inst["symbol"])
        return {"symbol": inst["symbol"], "status": "NO_DATA_QUARANTINE"}

    monkeypatch.setattr(BL, "_process_symbol", blocked)
    BL.run(_write_cfg(base, dict(_cfg(out, frozen), queue=[{"name": "Universum_Test", "symbols": syms}])))
    assert len(calls) == BL.NO_DATA_BREAKER                 # 10 Anfragen, nicht 20
    assert not os.path.exists(os.path.join(base, "universes_done.json"))
