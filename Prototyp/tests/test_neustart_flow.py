# -*- coding: utf-8 -*-
"""A3/A4/A5 End-zu-Ende ohne Netz: Zyklus -> Trades (Pro.1, C+) -> Telegram-Meldungen (Mock) -> Zustellmarken,
ruhige System-Gruppe, realistischer Einstieg, paralleler Abruf/Erkennung identisch zum sequentiellen Ablauf."""
import os, sys, json, threading, time
from concurrent.futures import ThreadPoolExecutor
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import run_paper, orchestrate, fastscan, livequote, entry_booking
from engine import exit_cplus as XC
from engine.tracker import PaperTradeStore
from notify.live import TelegramService
from notify.transport import MockTransport
from notify import trade_text as TT

CH = {"STR3_PRO1_CHAT_ID": "-101", "STR3_PRO2_CHAT_ID": "-102", "STR3_PRO3_CHAT_ID": "-103", "STR3_PRO6_CHAT_ID": "-106",
      "STR3_COMPARISON_CHAT_ID": "-900", "STR3_SYSTEM_CHAT_ID": "-999"}
ENV = {"TELEGRAM_BOT_TOKEN": "TESTTOKEN", **CH}
INST = dict(name="X", symbol="X-USD", asset_class="crypto", is_futures=False, anchor_hour=0, session_hours=None)
NOW = pd.Timestamp("2026-03-21 00:01:30", tz="UTC")


class FakeLine:
    def __init__(self, i0, p0, i1, p1, kind, taps, breaking_bar):
        self.i0, self.p0, self.i1, self.p1 = i0, p0, i1, p1
        self.kind, self.taps, self.angle_deg = kind, list(taps), 12.0
        self.breaking_bar = breaking_bar

    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def make_1h(n_hours, price=100.0):
    t0 = pd.Timestamp("2026-03-01", tz="UTC")
    rows = [{"Time": t0 + pd.Timedelta(hours=i), "Open": price, "High": price + 1, "Low": price - 1,
             "Close": price, "Volume": 100.0} for i in range(n_hours)]
    return pd.DataFrame(rows)


CALLS = {"n": 0}


def detect_stub(compat):
    CALLS["n"] += 1
    n = len(compat); bb = n - 1
    action = FakeLine(0, 90, bb, 100, "resistance", [0, 20, 40], breaking_bar=bb)       # LONG
    safety = FakeLine(0, 85, bb, 88, "support", [5, 25], breaking_bar=-1)
    return {"action": action, "safety": safety, "direction": "LONG", "atr_last": 2.0,
            "atr_series": pd.Series([2.0] * n), "pivots": ([], []), "pivot_prices": [300, 301], "n": n}


@pytest.fixture(autouse=True)
def stub_detector(monkeypatch):
    CALLS["n"] = 0
    monkeypatch.setattr(orchestrate, "default_detector", detect_stub)
    monkeypatch.setattr(fastscan, "_detect_job", detect_stub)


def quote_ok(sym):
    return {"price": 100.5, "bar_time": "2026-03-21T00:01:00+00:00", "interval": "1m", "delay_s": 5.0,
            "fetched_at": NOW.isoformat()}


def mk_svc(tmp_path, transport=None):
    tr = transport or MockTransport()
    svc = TelegramService(run_paper.ACTIVE_VARIANTS, env=ENV, transport=tr, queue_path=str(tmp_path / "q.json"))
    return svc, tr


def run(tmp_path, svc, hours=120 * 4, **kw):
    df = make_1h(hours)
    return run_paper.run_once(universe=[INST], base_dir=str(tmp_path / "rt"), now=NOW.to_pydatetime(),
                              telegram=True, svc=svc, downloader=lambda s, t: df, quote_fn=quote_ok,
                              doc_fn=lambda t: None, **kw)


# ------------------------------------------------------------------ Meldungen / ruhige System-Gruppe
def test_open_message_waiting_for_entry_and_quiet_system_group(tmp_path):
    svc, tr = mk_svc(tmp_path)
    mon = run(tmp_path, svc)
    assert mon["accepted"] == 1 and mon["opened"] >= 2
    store = PaperTradeStore(str(tmp_path / "rt" / "trades.json"))
    sids = {t.strategy_id for t in store.trades}
    assert "Str.3 Pro.1" in sids and "Str.3 C+" in sids and not (sids & {"Str.3 Pro.2", "Str.3 Pro.4", "Str.3 Pro.8"})
    # Meldungen nur in die Varianten-Gruppen (C+ -> Pro.2-Chat), NICHTS in die System-Gruppe
    assert tr.chats_used() <= {"-101", "-102", "-103", "-106"} and "-999" not in tr.chats_used()
    txt = tr.texts_to("-101")[0]
    ln = txt.splitlines()
    # KURZ: Variante/Symbol/Richtung, Einstieg (Zeit + Kurs), Stop, Ziel, PDF-Hinweis, Paper-Hinweis (alles andere steht in der PDF)
    assert ln[0] == "Pro.1 · X-USD · LONG" and ln[1] == "Einstieg: ab 21.03. 01:00 Uhr · Kurs folgt"
    assert ln[2].startswith("Stop: ") and ln[3].startswith("Ziel: ")
    assert ln[4] == "Details in der PDF" and ln[5] == "Paper-Trading - keine echte Order." and len(ln) == 6
    ctxt = tr.texts_to("-102")[0]
    assert ctxt.splitlines()[0] == "C+ · X-USD · LONG" and "Ausstieg nach C+" in ctxt and "Ziel:" not in ctxt and "Notfallnetz" not in ctxt
    for t in store.trades:
        assert t.notif.get("opened") and t.realistic["price"] == 100.5 and t.signal_end_time.startswith("2026-03-21T00:00")


def test_second_cycle_is_idempotent_no_duplicate_messages(tmp_path):
    svc, tr = mk_svc(tmp_path)
    run(tmp_path, svc)
    n = len(tr.sent)
    svc2, _ = mk_svc(tmp_path, tr)
    run(tmp_path, svc2)                                          # gleiche Daten: Wasserstand + Marken -> nichts neu
    assert len(tr.sent) == n


def test_booked_entry_when_next_candle_already_open(tmp_path):
    svc, tr = mk_svc(tmp_path)
    run(tmp_path, svc, hours=120 * 4 + 1)                        # 1h-Kerze 00:00 der Folgekerze liegt schon vor
    txt = tr.texts_to("-101")[0]
    assert "Einstieg: 21.03. 01:00 Uhr · Kurs 100" in txt and "Kurs folgt" not in txt and len(txt.splitlines()) == 6
    store = PaperTradeStore(str(tmp_path / "rt" / "trades.json"))
    assert all(t.booked_entry.get("price") == 100.0 for t in store.trades)


def test_telegram_failure_never_changes_trades(tmp_path):
    bad = MockTransport(fail_chats={"-101", "-102", "-103", "-106"})
    svc, _ = mk_svc(tmp_path, bad)
    mon = run(tmp_path, svc)
    store = PaperTradeStore(str(tmp_path / "rt" / "trades.json"))
    assert mon["errors"] == 0 and len(store.trades) >= 2
    assert all(t.status == "pending_fill" for t in store.trades)           # Zustand unveraendert
    assert len(svc.queue.pending()) >= 2                                   # Zustellung bleibt in der Queue


def test_no_cycle_or_heartbeat_message_even_with_activity_and_errors(tmp_path):
    svc, tr = mk_svc(tmp_path)
    run(tmp_path, svc)
    assert all(r["chat_id"] != "-999" for r in tr.sent)
    import inspect
    src = inspect.getsource(run_paper)
    assert "svc.system(" not in src
    from engine import run_loop
    assert "HEARTBEAT" not in inspect.getsource(run_loop) and "Heartbeat" not in inspect.getsource(run_loop)


def test_cplus_events_are_sent_once_and_exit_message_has_reason(tmp_path):
    svc, tr = mk_svc(tmp_path)
    run(tmp_path, svc)
    p = tmp_path / "rt" / "trades.json"
    store = PaperTradeStore(str(p))
    cp = next(t for t in store.trades if t.strategy_id == "Str.3 C+")
    # Kurs laeuft per 4h-Kerzen: Stufe 2 und dann Ausstieg unter der Schwelle
    t0 = pd.Timestamp("2026-03-21 00:00", tz="UTC")
    stop = cp.stop_initial
    risk = 100.0 - stop
    rows = [(100.0, 100 + 1.2 * risk, 99.5, 100 + 1.6 * risk),                 # Stufe 2 (Schluss >= +1,5R)
            (100 + 1.6 * risk, 100 + 1.7 * risk, 100 + 0.1 * risk, 100 + 0.2 * risk),   # Schluss < Schwelle? (Schwelle ~100,x)
            (100.0, 100.0, 90.0, 95.0)]
    base = make_1h(120 * 4)
    extra = []
    for k, (o, h, l, c) in enumerate(rows):
        for j in range(4):
            extra.append({"Time": t0 + pd.Timedelta(hours=4 * k + j), "Open": o if j == 0 else c, "High": h if j == 0 else c,
                          "Low": l if j == 0 else c, "Close": c, "Volume": 100.0})
    df2 = pd.concat([base, pd.DataFrame(extra)], ignore_index=True)
    now2 = t0 + pd.Timedelta(hours=12, seconds=90)
    svc2, _ = mk_svc(tmp_path, tr)
    run_paper.run_once(universe=[INST], base_dir=str(tmp_path / "rt"), now=now2.to_pydatetime(), telegram=True,
                       svc=svc2, downloader=lambda s, t: df2, quote_fn=quote_ok, doc_fn=lambda t: None)
    texts = tr.texts_to("-102")
    assert any("Stufe 2 erreicht" in x for x in texts)
    assert any("Ausstieg (" in x for x in texts)
    n = len(texts)
    run_paper.run_once(universe=[INST], base_dir=str(tmp_path / "rt"), now=now2.to_pydatetime(), telegram=True,
                       svc=mk_svc(tmp_path, tr)[0], downloader=lambda s, t: df2, quote_fn=quote_ok, doc_fn=lambda t: None)
    assert len(tr.texts_to("-102")) == n                                      # nichts doppelt


# ------------------------------------------------------------------ paralleler Ablauf == sequentieller Ablauf
class FakePool:
    def __init__(self):
        self.ex = ThreadPoolExecutor(2)

    def submit(self, compat):
        return self.ex.submit(detect_stub, compat)


def test_fast_path_equals_sequential_and_uses_precomputed(tmp_path):
    a = tmp_path / "a"; b = tmp_path / "b"; a.mkdir(); b.mkdir()
    df = make_1h(120 * 4)
    CALLS["n"] = 0
    m1 = run_paper.run_once(universe=[INST], base_dir=str(a), now=NOW.to_pydatetime(), downloader=lambda s, t: df, fast=False)
    seq_calls = CALLS["n"]
    CALLS["n"] = 0
    pool = FakePool()
    m2 = run_paper.run_once(universe=[INST], base_dir=str(b), now=NOW.to_pydatetime(), downloader=lambda s, t: df,
                            fast=True, pool=pool, throttle=fastscan.Throttle(min_interval=0))
    assert CALLS["n"] == seq_calls                                           # gleiche Zahl Erkennungen (im Pool gerechnet)
    for k in ("accepted", "opened", "closed", "no_trigger", "errors", "rejected"):
        assert m1[k] == m2[k], k
    t1 = PaperTradeStore(str(a / "trades.json")).trades
    t2 = PaperTradeStore(str(b / "trades.json")).trades
    assert [(t.trade_id, t.stop_initial, t.target, t.exit_mode) for t in t1] == \
           [(t.trade_id, t.stop_initial, t.target, t.exit_mode) for t in t2]
    assert json.load(open(a / "processed.json")) == json.load(open(b / "processed.json"))


def test_priority_symbols_are_processed_first_and_all_are_checked(tmp_path):
    insts = [dict(INST, symbol=f"S{i}-USD", name=f"S{i}") for i in range(5)]
    order = []

    def dl(sym, timeout):
        order.append(sym)
        return make_1h(120 * 4)
    run_paper.run_once(universe=insts, base_dir=str(tmp_path / "rt"), now=NOW.to_pydatetime(), downloader=dl, fast=False,
                       priority_symbols=["S3-USD", "S4-USD"])
    assert order[:2] == ["S3-USD", "S4-USD"] and sorted(order) == sorted(i["symbol"] for i in insts)


def test_track_mode_only_active_trade_symbols(tmp_path):
    svc, tr = mk_svc(tmp_path)
    run(tmp_path, svc)                                                        # eroeffnet Trades auf X-USD
    seen = []
    other = dict(INST, symbol="Y-USD", name="Y")

    def dl(sym, timeout):
        seen.append(sym)
        return make_1h(120 * 4)
    run_paper.run_once(universe=[INST, other], base_dir=str(tmp_path / "rt"), now=NOW.to_pydatetime(),
                       downloader=dl, mode="track")
    assert seen == ["X-USD"]


# ------------------------------------------------------------------ Abruf: vorsichtig
class Clk:
    def __init__(self): self.t = 0.0
    def __call__(self): return self.t
    def sleep(self, s): self.t += s


def test_throttle_spaces_requests_and_backs_off_on_rate_limit():
    c = Clk()
    th = fastscan.Throttle(min_interval=0.5, pause_after_failures=99, sleep_fn=c.sleep, clock=c)
    for _ in range(3):
        th.wait_turn()
    assert c.t >= 1.0 - 1e-9                                                  # 3 Starts im Abstand >= 0,5 s
    t_before = c.t
    th.failure(rate_limited=True, attempt=1)
    th.wait_turn()
    assert c.t - t_before >= 10.0 and th.backoffs == 1                        # Backoff nach Rate-Limit


def test_throttle_pauses_after_many_consecutive_failures():
    c = Clk()
    th = fastscan.Throttle(min_interval=0, pause_after_failures=3, pause_seconds=60, sleep_fn=c.sleep, clock=c)
    for _ in range(3):
        th.failure()
    assert th.pauses == 1
    t = c.t
    th.wait_turn()
    assert c.t - t >= 60


def test_fetch_one_retries_then_gives_up_without_raising():
    calls = {"n": 0}

    def dl(sym, timeout):
        calls["n"] += 1
        raise RuntimeError("Too Many Requests. Rate limited")
    c = Clk()
    th = fastscan.Throttle(min_interval=0, sleep_fn=c.sleep, clock=c)
    df, err = fastscan.fetch_one("A", dl, th, retries=2, sleep_fn=c.sleep)
    assert df is None and err == "RuntimeError" and calls["n"] == 3 and th.backoffs == 3


def test_fetch_many_isolates_failures_and_yields_all():
    def dl(sym, timeout):
        if sym == "BAD":
            raise ValueError("x")
        return make_1h(10)
    th = fastscan.Throttle(min_interval=0, pause_after_failures=99)
    res = {s: (df is not None) for s, df, e in
           fastscan.fetch_many(["A", "BAD", "B"], dl, th, workers=2, retries=0, sleep_fn=lambda s: None)}
    assert res == {"A": True, "BAD": False, "B": True}


def test_period_days_incremental_vs_full(tmp_path):
    from engine.cache import BarCache
    cache = BarCache(str(tmp_path / "c"))
    assert fastscan.period_days_for(cache, "X", NOW) == 240                 # leerer Cache: volle Historie wie bisher
    cache.merge("X", "1h", make_1h(600))
    d = fastscan.period_days_for(cache, "X", pd.Timestamp("2026-03-27", tz="UTC"))
    assert 7 <= d <= 14                                                      # nur die Luecke + Rand
    assert fastscan.period_days_for(cache, "X", pd.Timestamp("2027-01-01", tz="UTC")) == 240   # zu alt -> voll


# ------------------------------------------------------------------ Kurs / Einstieg
def test_livequote_delay_measurement_and_fallback():
    idx = pd.DatetimeIndex([pd.Timestamp("2026-03-21 00:00", tz="UTC"), pd.Timestamp("2026-03-21 00:01", tz="UTC")])
    df = pd.DataFrame({"Open": [1, 1], "High": [1, 1], "Low": [1, 1], "Close": [100.0, 101.0]}, index=idx)
    q = livequote.fetch_quote("X", downloader=lambda s, i, p: df, now=pd.Timestamp("2026-03-21 00:01:30", tz="UTC"))
    assert q["price"] == 101.0 and q["interval"] == "1m" and q["delay_s"] == 0.0           # Balken laeuft noch
    q = livequote.fetch_quote("X", downloader=lambda s, i, p: df, now=pd.Timestamp("2026-03-21 00:21:00", tz="UTC"))
    assert q["delay_s"] == 1140.0                                                          # 19 min seit Balkenende

    def only5(sym, interval, period):
        if interval == "1m":
            raise ValueError("kein 1m")
        return df
    assert livequote.fetch_quote("X", downloader=only5, now=NOW)["interval"] == "5m"

    def none(sym, interval, period):
        raise ValueError("x")
    assert livequote.fetch_quote("X", downloader=none, now=NOW) is None


def test_book_entry_partial_and_missing():
    df = make_1h(120 * 4 + 1)
    b = entry_booking.book_entry(None, "X", "2026-03-20T20:00:00+00:00", df1h=df, now=NOW)
    assert b["price"] == 100.0 and b["partial"] is True and b["time"].startswith("2026-03-21T00:00")
    assert entry_booking.book_entry(None, "X", "2026-03-20T20:00:00+00:00", df1h=make_1h(120 * 4), now=NOW) is None


# ------------------------------------------------------------------ Texte
def test_times_in_german_time_summer_and_winter():
    assert TT.fde("2026-10-24T22:00:00+00:00") == "25.10.2026 00:00 Uhr (MESZ)"
    assert TT.fde("2026-10-25T02:00:00+00:00") == "25.10.2026 03:00 Uhr (MEZ)"
    assert TT.fde("2026-11-02T12:00:00+00:00") == "02.11.2026 13:00 Uhr (MEZ)"


def test_distance_signs_in_price_and_r():
    assert TT.fdist(12.5, 25.0) == "+12,5 (+0,50 R)"
    assert TT.fdist(-30, 25.0) == "−30 (−1,20 R)"


def test_realistic_vs_theoretical_numbers():
    from engine.tracker import PaperTrade
    t = PaperTrade(trade_id="a", variant_evaluation_id="v", parent_signal_id="p", strategy_id="Str.3 Pro.1", break_even="BE-0",
                   symbol="X", asset_class="fx", direction="LONG", signal_time="t", status="closed", stop_initial=90.0)
    t.result = {"status": "closed", "entry_open": 100.0, "netto_r": 2.0, "net_return_pct": 5.0}
    t.realistic = {"price": 101.0}                                            # 1,0 teurer = 0,1 R schlechter
    x = TT.realistic_vs_theoretical(t)
    assert abs(x["adverse_r"] - 0.1) < 1e-9 and abs(x["r_real"] - 1.9) < 1e-9 and abs(x["pct_real"] - 4.0) < 1e-9
    t.direction = "SHORT"; t.stop_initial = 110.0
    x = TT.realistic_vs_theoretical(t)
    assert x["adverse_r"] < 0                                                 # Short: hoeherer Preis ist besser


# ------------------------------------------------------------------ Geplante Meldungen im Listener
def test_schedule_runner_sends_dst_and_report_once(tmp_path):
    from notify.report_listener import ScheduleRunner
    from datetime import datetime, timezone
    sent = MockTransport()
    built = []

    def build():
        built.append(1)
        return str(tmp_path / "r.pdf"), "Bericht-Text"
    r = ScheduleRunner(str(tmp_path / "s.json"), sent, build, "-999")
    U = timezone.utc
    assert r.tick(datetime(2026, 10, 24, 17, 59, tzinfo=U)) == []
    assert r.tick(datetime(2026, 10, 24, 18, 0, 20, tzinfo=U)) == ["dst:2026-10-25:eve"]
    assert r.tick(datetime(2026, 10, 24, 18, 1, tzinfo=U)) == []                    # nicht doppelt
    r2 = ScheduleRunner(str(tmp_path / "s.json"), sent, build, "-999")             # Neustart des Listeners
    assert r2.tick(datetime(2026, 10, 24, 19, 0, tzinfo=U)) == []
    assert r2.tick(datetime(2026, 10, 25, 7, 0, 5, tzinfo=U)) == ["dst:2026-10-25:day"]
    assert r2.tick(datetime(2026, 11, 1, 19, 0, 30, tzinfo=U)) == ["report14:2026-11-01"]
    assert built == [1] and sent.sent[-1]["kind"] == "document" and sent.sent[-1]["chat_id"] == "-999"
    assert len([x for x in sent.sent if x["kind"] == "text"]) == 2
    assert "Winterzeit" in sent.sent[0]["payload"] and "01, 05, 09, 13, 17, 21 Uhr" in sent.sent[0]["payload"]


def test_schedule_runner_retries_after_send_error(tmp_path):
    from notify.report_listener import ScheduleRunner
    from datetime import datetime, timezone
    tr = MockTransport(fail_chats={"-999"})
    r = ScheduleRunner(str(tmp_path / "s.json"), tr, lambda: ("x", "y"), "-999")
    U = timezone.utc
    assert r.tick(datetime(2026, 10, 25, 7, 0, 5, tzinfo=U)) == []
    tr.fail_chats.clear()
    assert r.tick(datetime(2026, 10, 25, 7, 1, 5, tzinfo=U)) == ["dst:2026-10-25:day"]


# ------------------------------------------------------------------ Regressionen aus der Selbstpruefung
def test_total_yahoo_block_aborts_cycle_fetching_quickly():
    """Bei Totalausfall/Sperre darf der Zyklus nicht Dutzende Minuten in Pausen haengen (max. 2 Pausen, dann Abbruch)."""
    c = Clk()
    th = fastscan.Throttle(min_interval=0, pause_after_failures=3, pause_seconds=60, sleep_fn=c.sleep, clock=c, max_pauses=2)

    def dl(sym, timeout):
        raise RuntimeError("blocked")
    res = {s: e for s, df, e in fastscan.fetch_many([f"S{i}" for i in range(94)], dl, th, workers=1, retries=2,
                                                    sleep_fn=lambda s: None)}
    assert th.aborted and th.pauses == 2
    assert sum(1 for e in res.values() if e == "ABORTED_YAHOO_BLOCK") > 80            # Rest entfaellt sofort
    assert c.t < 400                                                                   # statt ~47 min


def test_detect_pool_recovers_after_failure():
    t = {"now": 0.0}
    pool = fastscan.DetectPool(max_workers=1, retry_after_s=300, clock=lambda: t["now"])

    class Boom:
        def submit(self, *a):
            raise RuntimeError("broken pool")

        def shutdown(self, **kw):
            pass
    pool._ex = Boom()
    assert pool.submit(object()) is None and pool.broken and pool._ex is None
    assert pool._executor() is None                                                   # Wartezeit laeuft
    t["now"] = 301.0
    pool._executor_factory = None
    try:
        ex = pool._executor()                                                          # neuer Versuch (echter Pool, spawn)
        assert ex is not None and not pool.broken
    finally:
        pool.shutdown()


def test_outage_counts_total_fetch_failure_even_with_cache_fallback(tmp_path):
    from engine import outage
    sent = []
    m = outage.OutageMonitor(str(tmp_path / "o.json"), lambda k, t, p: sent.append(k))
    bad = {"instruments": 94, "no_data": 0, "fetch_failed": 94}
    m.cycle_result(mon=bad); m.cycle_result(mon=bad)
    assert sent == ["no_data"]


def test_process_watch_no_repeat_when_state_cannot_be_written_and_stop_file_means_no_alarm(tmp_path):
    from engine import outage
    clock = {"t": 10000.0}
    sent = []
    rt = tmp_path / "gibt_es_nicht"                                                   # Laufzeitordner fehlt -> Zustand nicht schreibbar
    w = outage.ProcessWatch(str(rt), lambda: False, lambda k, t, p: sent.append(k), clock=lambda: clock["t"], grace_seconds=0)
    for _ in range(20):
        clock["t"] += 200; w.poll()
    assert sent == ["process_missing"]                                                # nur EINMAL, trotz fehlgeschlagenem Speichern
    rt2 = tmp_path / "rt2"; rt2.mkdir(); (rt2 / "STOP").write_text("x")
    sent2 = []
    w2 = outage.ProcessWatch(str(rt2), lambda: False, lambda k, t, p: sent2.append(k), clock=lambda: clock["t"], grace_seconds=0)
    for _ in range(20):
        clock["t"] += 200; w2.poll()
    assert sent2 == []                                                                # bewusst gestoppt -> kein Alarm
