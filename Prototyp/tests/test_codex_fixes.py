# -*- coding: utf-8 -*-
"""Regressionstests zu den Codex-Funden (16.10.2026). Jeder Test scheitert am Stand VOR dem Fix."""
import os, sys, json, types, importlib.util
from datetime import datetime, timedelta, timezone
import numpy as np
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import exit_cplus as XC
from engine import cycle as CY
from engine import tracker as T
from engine import variants as VAR
from engine import entry_booking, outage, prewarn as PW, fastscan, live_settings, notifier as NOTI, trade_doc
from engine.varstate import StateRegistry
from notify import trade_text as TT
from notify.live import TelegramService
from notify.transport import MockTransport

U = timezone.utc
LINE = lambda j: 90.0
PRE = 3
NL = chr(10)


# ======================================================================== C+ : wartendes Ausstiegssignal
def mk(rows, pre=PRE, shift=0):
    a = [(130, 130, 130, 130)] * (pre + shift) + list(rows)
    A = np.array(a, dtype=float)
    t = list(pd.date_range("2026-10-01", periods=len(A), freq="4h", tz="UTC"))
    return t, A[:, 0], A[:, 1], A[:, 2], A[:, 3], pre + shift


ROWS_SIGNAL = [(100, 105, 95, 100), (100, 102, 88, 89)]                  # letzte Kerze: Schluss 89 < Linie 90 -> Signal
ROWS_NEXT = [(87, 90, 85, 88)]


def test_pending_exit_resolved_by_timestamp_after_cache_backfill():
    t, O, H, L, C, e = mk(ROWS_SIGNAL)
    st = XC.new_state()
    XC.advance(st, "LONG", t, O, H, L, C, LINE, e, 100.0, 10.0, 5.0, 1.0)
    assert st["pending"]["time"] == t[-1].isoformat() and st["exit"] is None
    # Cache-Auffuellung: ZWEI aeltere Kerzen kommen davor - alle Indizes verschieben sich, KEINE neue Kerze
    t2, O2, H2, L2, C2, e2 = mk(ROWS_SIGNAL, shift=2)
    t2 = list(pd.date_range(t[0] - pd.Timedelta(hours=8), periods=len(O2), freq="4h", tz="UTC"))
    ev = XC.advance(st, "LONG", t2, O2, H2, L2, C2, LINE, e2, 100.0, 10.0, 5.0, 1.0)
    assert st["exit"] is None and ev == []                              # vor dem Fix: Ausstieg zum Open einer ALTEN Kerze
    t3, O3, H3, L3, C3, e3 = mk(ROWS_SIGNAL + ROWS_NEXT, shift=2)
    t3 = list(pd.date_range(t[0] - pd.Timedelta(hours=8), periods=len(O3), freq="4h", tz="UTC"))
    XC.advance(st, "LONG", t3, O3, H3, L3, C3, LINE, e3, 100.0, 10.0, 5.0, 1.0)
    assert st["exit"]["price"] == 87.0 and st["exit"]["time"] == t3[-1].isoformat()


def test_execute_pending_uses_only_the_open_and_equals_later_processing():
    t, O, H, L, C, e = mk(ROWS_SIGNAL)
    st = XC.new_state()
    XC.advance(st, "LONG", t, O, H, L, C, LINE, e, 100.0, 10.0, 5.0, 1.0)
    next_time = t[-1] + pd.Timedelta(hours=4)
    ev = XC.execute_pending(st, 87.0, next_time)
    assert st["exit"]["price"] == 87.0 and st["pending"] is None and [x["kind"] for x in ev] == [XC.EV_EXIT]
    t2, O2, H2, L2, C2, e2 = mk(ROWS_SIGNAL + ROWS_NEXT)
    again = XC.advance(st, "LONG", t2, O2, H2, L2, C2, LINE, e2, 100.0, 10.0, 5.0, 1.0)
    assert again == [] and st["exit"]["price"] == 87.0
    ref = XC.new_state()
    XC.advance(ref, "LONG", t2, O2, H2, L2, C2, LINE, e2, 100.0, 10.0, 5.0, 1.0)
    assert ref["exit"]["price"] == st["exit"]["price"] and ref["exit"]["bars"] == st["exit"]["bars"]
    assert [x["id"] for x in ref["events"]] == [x["id"] for x in st["events"]]


def test_execute_pending_without_pending_does_nothing():
    st = XC.new_state()
    assert XC.execute_pending(st, 1.0, "2026-10-01T00:00:00+00:00") == [] and st["exit"] is None


SIG = "2026-07-01T00:00:00+00:00"
BE = {"Str.3 Pro.1": "BE-0", "Str.3 C+": "C+"}


def _compat(rows, start="2026-07-01T00:00"):
    times = list(pd.date_range(start, periods=len(rows), freq="4h", tz="UTC"))
    return pd.DataFrame({"Time": times, "Open": [r[0] for r in rows], "High": [r[1] for r in rows],
                         "Low": [r[2] for r in rows], "Close": [r[3] for r in rows]})


def _result():
    decs = [VAR.VariantDecision(VAR.CPLUS_ID, VAR.PASS)]
    return {"symbol": "BTC-USD", "status": "ACCEPTED_PROVISIONAL", "parent_signal_id": "PSIG-C9", "direction": "LONG",
            "asset_class": "crypto", "atr": 5.0, "signal_close": 100.0, "baseline_stop": 90.0, "baseline_target": 130.0,
            "action_sig": "resistance:100.0:0.5", "signal_time": SIG, "signal_end_time": "2026-07-01T04:00:00+00:00",
            "safety_line": {"d0": -6, "p0": 90.0, "d1": -1, "p1": 90.0}, "variant_decisions": decs}


ROWS_CY = [(99, 100, 98, 100), (100, 105, 95, 100), (100, 102, 88, 89)]     # Signalkerze, Einstieg, Schluss unter Linie


def _setup(tmp_path):
    reg = StateRegistry(str(tmp_path / "s.json"))
    store = T.PaperTradeStore(str(tmp_path / "t.json"))
    CY.open_trades_for_accepted(_result(), BE, reg, store, now=1000)
    return reg, store


def test_cycle_executes_pending_exit_at_known_next_open(tmp_path):
    reg, store = _setup(tmp_path)
    nxt = {"price": 87.0, "time": "2026-07-01T12:00:00+00:00", "running": True, "opened_at_start": True}
    n = CY.update_open_trades("BTC-USD", _compat(ROWS_CY), store, reg, now=2000, next_open_fn=lambda s, a: nxt)
    cp = store.trades[0]
    assert n == 1 and cp.status == "closed" and cp.result["exit_price"] == 87.0 and cp.result["outcome"] == XC.OUT_LINE
    assert "BTC-USD" not in reg.get("Str.3 C+").open_symbols                 # Cooldown startet JETZT, nicht 4 h spaeter
    rows = ROWS_CY + [(87, 90, 85, 88)]
    CY.update_open_trades("BTC-USD", _compat(rows), store, reg, now=3000, next_open_fn=lambda s, a: nxt)
    assert store.trades[0].result["exit_price"] == 87.0 and len(store.trades[0].cplus["events"]) == 1


@pytest.mark.parametrize("nb", [None, {"price": 87.0, "time": "x", "running": False, "opened_at_start": True},
                                {"price": 87.0, "time": "x", "running": True, "opened_at_start": False}])
def test_cycle_does_not_execute_when_open_unreliable(tmp_path, nb):
    reg, store = _setup(tmp_path)
    CY.update_open_trades("BTC-USD", _compat(ROWS_CY), store, reg, now=2000, next_open_fn=lambda s, a: nb)
    assert store.trades[0].status == "open" and store.trades[0].cplus["pending"]


def test_book_entry_flags_running_and_full_block():
    def mk1h_(last):
        end = pd.Timestamp(last, tz="UTC")
        idx = [end - pd.Timedelta(hours=i) for i in range(299, -1, -1)]
        return pd.DataFrame({"Time": idx, "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0})
    now = pd.Timestamp("2026-03-21 00:01:30", tz="UTC")
    b = entry_booking.book_entry(None, "X", "2026-03-20T20:00:00+00:00", df1h=mk1h_("2026-03-21T00:00"), now=now)
    assert b["running"] is True and b["opened_at_start"] is True
    d = mk1h_("2026-03-21T01:00")
    d = d[d["Time"] != pd.Timestamp("2026-03-21T00:00", tz="UTC")]
    b = entry_booking.book_entry(None, "X", "2026-03-20T20:00:00+00:00", df1h=d, now=pd.Timestamp("2026-03-21 01:30", tz="UTC"))
    assert b["opened_at_start"] is False


# ======================================================================== Abruf: kein Rueckgriff auf Cache
class FakeLine:
    def __init__(self, i0, p0, i1, p1, kind, taps, bb):
        self.i0, self.p0, self.i1, self.p1, self.kind = i0, p0, i1, p1, kind
        self.taps, self.angle_deg, self.breaking_bar = list(taps), 12.0, bb

    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def make_1h(n):
    t0 = pd.Timestamp("2026-03-01", tz="UTC")
    return pd.DataFrame([{"Time": t0 + pd.Timedelta(hours=i), "Open": 100.0, "High": 101.0, "Low": 99.0, "Close": 100.0,
                          "Volume": 100.0} for i in range(n)])


def test_failed_fetch_skips_symbol_instead_of_using_stale_cache(tmp_path):
    from engine import run_paper
    from engine.cache import BarCache
    rt = tmp_path / "rt"
    cache = BarCache(str(rt / "data_cache"))
    df = make_1h(120 * 4)
    df.loc[df.index[-1], "Close"] = 55.0                             # unfertige letzte Stunde aus einem Zwischenabruf
    cache.merge("X-USD", "1h", df)
    inst = dict(name="X", symbol="X-USD", asset_class="crypto", is_futures=False, anchor_hour=0, session_hours=None)

    def boom(s, t):
        raise RuntimeError("yahoo down")
    mon = run_paper.run_once(universe=[inst], base_dir=str(rt), now=datetime(2026, 3, 21, 0, 1, 30, tzinfo=U), fast=True,
                             downloader=boom, throttle=fastscan.Throttle(min_interval=0, sleep_fn=lambda s: None))
    assert mon["fetch_failed"] == 1 and mon["no_trigger"] == 0 and mon["accepted"] == 0
    assert not os.path.exists(rt / "processed.json") or "X-USD" not in json.load(open(rt / "processed.json"))


def test_prewarn_never_writes_the_cache(tmp_path):
    from engine.cache import BarCache
    cache = BarCache(str(tmp_path / "data_cache"))
    cache.merge("X-USD", "1h", make_1h(300))
    path = cache._path("X-USD", "1h")
    snap = open(path, "rb").read()
    new = make_1h(310)
    new.loc[new.index[-1], "Close"] = 12.34                          # laufende, unfertige Stunde
    merged = PW.merge_in_memory(cache, "X-USD", new)
    assert len(merged) == 310 and merged["Close"].iloc[-1] == 12.34
    assert open(path, "rb").read() == snap


# ======================================================================== Ausfall-Meldungen
def test_all_instruments_erroring_is_not_a_success_and_never_recovers(tmp_path):
    sent = []
    m = outage.OutageMonitor(str(tmp_path / "o.json"), lambda k, t, p: sent.append(k))
    bad = {"instruments": 94, "no_data": 0, "fetch_failed": 0, "errors": 94}
    for _ in range(3):
        m.cycle_result(mon=bad)
    assert sent == ["errors"]
    m.cycle_result(mon={"instruments": 0})                           # leere Verfolgungsrunde: keine Erholung
    m.cycle_result(mon={"instruments": 2, "no_data": 0, "fetch_failed": 2, "errors": 0})
    assert sent == ["errors"]
    m.cycle_result(mon={"instruments": 94, "no_data": 3, "errors": 0})
    assert sent == ["errors", "recovered"]


def test_empty_tracking_rounds_keep_liveness_but_do_not_count_as_data_proof(tmp_path):
    t = {"v": 0.0}
    m = outage.OutageMonitor(str(tmp_path / "o.json"), lambda *a: None, clock=lambda: t["v"])
    t["v"] = 6000.0
    m.cycle_result(mon={"instruments": 0})
    assert m.last_success == 6000.0 and m.fail_streak == 0


def test_outage_sender_is_direct_without_queue(tmp_path, monkeypatch):
    from engine import run_loop
    import notify.live as live
    import notify.transport as tp
    sent = []

    class FakeTr:
        def __init__(self, token):
            pass

        def send_text(self, chat, text):
            sent.append((chat, text))
    monkeypatch.setattr(tp, "RealTelegramTransport", FakeTr)
    monkeypatch.setattr(live, "read_env", lambda path=None: {"TELEGRAM_BOT_TOKEN": "T", "STR3_SYSTEM_CHAT_ID": "-999"})

    def no_queue(*a, **k):
        raise AssertionError("TelegramService/Queue darf im Watchdog-Pfad nicht benutzt werden")
    monkeypatch.setattr(run_loop, "TelegramService", no_queue)
    run_loop._outage_sender(str(tmp_path))("errors", "Bot-Ausfall", "p1")
    assert sent == [("-999", "STR3 System – Bot-Status" + NL + "Bot-Ausfall")]


# ======================================================================== Vorwarnungen: nichts geht verloren
ENV = {"TELEGRAM_BOT_TOKEN": "T", "STR3_PRO1_CHAT_ID": "-101", "STR3_PRO2_CHAT_ID": "-102", "STR3_PRO3_CHAT_ID": "-103", "STR3_PRO6_CHAT_ID": "-106",
       "STR3_COMPARISON_CHAT_ID": "-900", "STR3_SYSTEM_CHAT_ID": "-999"}
GROUPS = ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]
INST = dict(name="X", symbol="X-USD", asset_class="crypto", is_futures=False, anchor_hour=0, session_hours=None)


def det_break(compat):
    n = len(compat)
    bb = n - 1
    return {"action": FakeLine(0, 90, bb, 99.0, "resistance", [0, 20, 40], bb), "safety": FakeLine(0, 85, bb, 88, "support", [5, 25], -1),
            "direction": "LONG", "atr_last": 2.0, "atr_series": pd.Series([2.0] * n), "pivots": ([], []), "pivot_prices": [300], "n": n}


def mk1h(last_iso, n=500):
    end = pd.Timestamp(last_iso, tz="UTC")
    return pd.DataFrame({"Time": [end - pd.Timedelta(hours=i) for i in range(n - 1, -1, -1)], "Open": 100.0, "High": 101.0,
                         "Low": 99.0, "Close": 100.5, "Volume": 100.0})


def pw_go(tmp_path, now, minute, svc, hour):
    s = live_settings.load(os.path.join("none", "x.json"))
    return PW.run_prewarn([INST], str(tmp_path), now, minute, s, svc=svc, downloader=lambda a, b: mk1h(hour),
                          throttle=fastscan.Throttle(min_interval=0), detect_fn=det_break)


def svc_for(tmp_path, transport=None, env=None):
    tr = transport or MockTransport()
    return TelegramService(GROUPS, env=env or ENV, transport=tr, queue_path=str(tmp_path / "q.json")), tr


def test_unresolved_warning_survives_the_next_boundary_and_is_resolved_by_deadline(tmp_path):
    svc, tr = svc_for(tmp_path)
    pw_go(tmp_path, datetime(2026, 3, 21, 11, 30, tzinfo=U), 30, svc, "2026-03-21T11:00")
    pw_go(tmp_path, datetime(2026, 3, 21, 15, 30, tzinfo=U), 30, svc, "2026-03-21T15:00")     # ueberschreibt frueher den Zustand
    st = json.load(open(tmp_path / "prewarn_state.json"))
    assert any(w["boundary"].startswith("2026-03-21T12:00") and not w["done"] for w in st["warnings"])
    n = PW.resolve(str(tmp_path), datetime(2026, 3, 21, 16, 1, tzinfo=U), svc, watermark={})
    assert n >= 4 and any("Daten verspätet" in x for x in tr.texts_to("-101"))


def test_resolution_retried_when_telegram_disabled_or_failing(tmp_path):
    svc, tr = svc_for(tmp_path)
    pw_go(tmp_path, datetime(2026, 3, 21, 11, 30, tzinfo=U), 30, svc, "2026-03-21T11:00")
    wm = {"X-USD": "2026-03-21T08:00:00+00:00"}
    later = datetime(2026, 3, 21, 12, 5, tzinfo=U)
    disabled = types.SimpleNamespace(enabled=False)
    assert PW.resolve(str(tmp_path), later, disabled, watermark=wm) == 0           # Telegram aus -> NICHT als erledigt markiert
    assert not json.load(open(tmp_path / "prewarn_state.json"))["warnings"][0]["done"]

    class Flaky:
        enabled = True

        def __init__(self, real):
            self.real, self.fail = real, {"Str.3 C+"}

        def send(self, m, period=""):
            if m.strategy_id in self.fail:
                raise RuntimeError("queue down")
            return self.real.send(m, period=period)
    fl = Flaky(svc)
    n1 = PW.resolve(str(tmp_path), later, fl, watermark=wm)
    assert n1 == 3 and not json.load(open(tmp_path / "prewarn_state.json"))["warnings"][0]["done"]
    fl.fail = set()
    n2 = PW.resolve(str(tmp_path), later + timedelta(minutes=1), fl, watermark=wm)
    assert n2 == 1 and json.load(open(tmp_path / "prewarn_state.json"))["warnings"][0]["done"]
    assert len(tr.texts_to("-102")) == 2                                            # Warnung + Aufloesung


def test_warning_not_counted_as_sent_when_routing_failed(tmp_path):
    env = dict(ENV)
    env.pop("STR3_PRO3_CHAT_ID")                                                    # Pro.3-Chat fehlt -> WARNING statt Zustellung
    svc, tr = svc_for(tmp_path, env=env)
    out = pw_go(tmp_path, datetime(2026, 3, 21, 11, 30, tzinfo=U), 30, svc, "2026-03-21T11:00")
    st = json.load(open(tmp_path / "prewarn_state.json"))
    assert set(st["warnings"][0]["sent_groups"]) == {"Str.3 Pro.1", "Str.3 C+", "Str.3 D"} and out["sent"] == 3


# ======================================================================== Meldungstexte / Anhaenge
def _trade(direction="LONG", mode=""):
    return T.PaperTrade(trade_id="a", variant_evaluation_id="v", parent_signal_id="P1", strategy_id="Str.3 Pro.1", break_even="BE-0",
                        symbol="X", asset_class="fx", direction=direction, signal_time="2026-10-17T08:00:00+00:00",
                        stop_initial=90.0 if direction == "LONG" else 110.0, target=120.0 if direction == "LONG" else 80.0,
                        exit_mode=mode, signal_end_time="2026-10-17T12:00:00+00:00", booked_entry={"signal_close": 100.0})


@pytest.mark.parametrize("direction,cur,expect", [("LONG", 105.0, "ungünstig"), ("LONG", 95.0, "günstig"),
                                                  ("SHORT", 95.0, "ungünstig"), ("SHORT", 105.0, "günstig")])
def test_late_entry_deviation_is_labelled_correctly(direction, cur, expect):
    q = {"price": cur, "bar_time": "2026-10-17T12:01:00+00:00", "interval": "1m", "delay_s": 0}
    txt = TT.trade_details_text(_trade(direction), quote=q, booked={"price": 100.0, "time": "2026-10-17T12:00:00+00:00", "partial": True})
    line = [x for x in txt.splitlines() if "weicht bereits" in x][0]
    assert f"({expect} für einen späteren Einstieg)" in line
    if expect == "günstig":
        assert "ungünstig" not in line


def test_attachments_are_separate_per_exit_mode(tmp_path):
    calls = []

    class Svc:
        enabled = True

        def trade_opened(self, *a, **k):
            pass

        def trade_attachment(self, t, p):
            calls.append((t.exit_mode, p))

        def cplus_event(self, *a):
            pass

        def trade_closed(self, *a):
            pass
    store = T.PaperTradeStore(str(tmp_path / "t.json"))
    t1 = _trade()
    t2 = _trade(mode="CPLUS")
    t2.trade_id = "b"
    t2.strategy_id = "Str.3 C+"
    store.add(t1)
    store.add(t2)
    n = NOTI.TradeNotifier(Svc(), store, doc_fn=lambda t: f"doc_{t.exit_mode or 'BASE'}.pdf", quote_fn=lambda s: None,
                           book_fn=lambda *a: None)
    n.notify_all()
    assert sorted(calls) == [("", "doc_BASE.pdf"), ("CPLUS", "doc_CPLUS.pdf")]


def test_trade_doc_pdf_name_and_png_target_depend_on_exit_mode():
    import inspect
    src = inspect.getsource(trade_doc)
    assert "t.exit_mode or 'BASE'" in src and 't.exit_mode in ("CPLUS", "D")' in src


# ======================================================================== Umstellung / Wartebot
def _load(name, fname):
    p = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), fname)
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


UM = _load("umstellung_cf", "umstellung_17-10.py")
WA = _load("warte_cf", "warte_und_umstellen.py")
import test_umstellung as TU


def test_process_query_excludes_itself_and_filters_by_process_name():
    w = UM._where("run_loop.py|neustart")
    assert "$_.ProcessId -ne $PID" in w and "$_.Name -like 'python*'" in w
    assert "wscript*" in UM._where("TradingBot_Neustart.vbs")
    from notify import status_report as SR
    import inspect
    assert "$_.ProcessId -ne $PID" in inspect.getsource(SR._process_alive)


def test_real_process_query_does_not_find_itself():
    if os.name != "nt":
        pytest.skip("nur Windows")
    assert UM.default_alive("run_loop.py|gibt_es_garantiert_nicht") is False       # vor dem Fix: True (matcht die eigene Abfrage)


def test_logs_redact_tokens_and_chat_ids():
    t = UM.redact("POST https://api.telegram.org/bot1234567890:AAHtestTokenTokenTokenTokenToken/sendMessage chat -9876543210 ok")
    assert "AAHtest" not in t and "1234567890:" not in t and "9876543210" not in t and "api.telegram.org" in t
    cfg = types.SimpleNamespace(now=lambda: datetime(2026, 10, 17, 12, 0), dry=True, log_lines=[], log_path="x")
    UM.log(cfg, "Fehler 1234567890:AAHtestTokenTokenTokenTokenToken")
    assert "AAHtest" not in cfg.log_lines[0]


def test_idle_requires_recent_cycle_end_not_only_low_cpu():
    ns = types.SimpleNamespace
    assert UM.old_run_is_sleeping(ns(cycle_age=lambda: 4000, proc_idle=lambda p: True)) is False   # Zyklus koennte laufen
    assert UM.old_run_is_sleeping(ns(cycle_age=lambda: 900, proc_idle=lambda p: True)) is True
    assert UM.old_run_is_sleeping(ns(cycle_age=lambda: 900, proc_idle=lambda p: False)) is False
    assert UM.old_run_is_sleeping(ns(cycle_age=lambda: None, proc_idle=lambda p: True)) is False
    assert UM.old_run_is_sleeping(ns(cycle_age=lambda: 5, proc_idle=lambda p: True)) is False       # gerade erst beendet


def _tree(tmp_path):
    return TU.tree.__wrapped__(tmp_path) if hasattr(TU.tree, "__wrapped__") else TU.tree.__pytest_wrapped__.obj(tmp_path)


def test_test_runner_exception_triggers_rollback(tmp_path):
    root = _tree(tmp_path)
    sim = TU.Sim(root, TU.AFTER)

    def boom(d):
        raise TimeoutError("pytest haengt")
    cfg = sim.cfg()
    cfg.run_tests = boom
    assert UM.run(cfg, dry=False) == 3
    p = os.path.join(str(root), "Prototyp")
    assert open(os.path.join(p, "engine", "run_loop.py")).read() == "ALT run_loop"
    assert open(os.path.join(p, "notify", "live.py")).read() == "ALT live"
    assert sim.cmds == [] and len(sim.sent) == 1


def test_copy_error_midway_rolls_back_partial_state(tmp_path, monkeypatch):
    root = _tree(tmp_path)
    sim = TU.Sim(root, TU.AFTER)
    cfg = sim.cfg()
    real = UM.shutil.copyfile
    n = {"i": 0}

    def flaky(src, dst):
        n["i"] += 1
        if n["i"] == 3:
            raise OSError("Platte voll")
        return real(src, dst)
    monkeypatch.setattr(UM.shutil, "copyfile", flaky)
    assert UM.run(cfg, dry=False) == 3
    p = os.path.join(str(root), "Prototyp")
    assert open(os.path.join(p, "engine", "run_loop.py")).read() == "ALT run_loop"
    assert open(os.path.join(p, "notify", "live.py")).read() == "ALT live"


def test_failure_after_new_run_started_unwinds_everything(tmp_path):
    root = _tree(tmp_path)
    sim = TU.Sim(root, TU.AFTER)
    cfg = sim.cfg()
    cfg.new_run_wait_s = 20
    orig_cmd = sim.cmd

    def cmd(argv):
        rc = orig_cmd(argv)
        if os.path.basename(argv[-1]) == "NEUSTART-LAUF starten.bat":
            os.remove(os.path.join(str(root), "Prototyp", "paper_runtime_neustart", "last_cycle_monitor.json"))   # erster Zyklus kommt nie
        return rc
    cfg.run_cmd = cmd
    assert UM.run(cfg, dry=False) == 3
    p = os.path.join(str(root), "Prototyp")
    assert open(os.path.join(p, "engine", "run_loop.py")).read() == "ALT run_loop"                    # Code zurueck
    assert not os.path.exists(os.path.join(p, "paper_runtime_neustart"))                              # umbenannt, damit Neuversuch geht
    assert any(d.startswith("paper_runtime_neustart_abgebrochen_") for d in os.listdir(p))
    assert "TradingBot_Neustart.vbs" in sim.killed and "run_loop.py|neustart" in sim.killed            # Watchdog + Lauf gestoppt
    assert sim.cmds.count("Bericht-Listener starten.bat") == 2                                          # Listener mit altem Code neu
    st = os.path.join(str(root), "Startup")
    assert os.path.exists(os.path.join(st, "TradingBot_2Monate.vbs")) and not os.path.exists(os.path.join(st, "TradingBot_Neustart.vbs"))
    assert len(sim.sent) == 1 and sim.sent[0].startswith("Umstellung NICHT erfolgt")


def test_autostart_failure_restores_old_entry(tmp_path):
    root = _tree(tmp_path)
    sim = TU.Sim(root, TU.AFTER)
    cfg = sim.cfg()
    st = os.path.join(str(root), "Startup")
    os.makedirs(os.path.join(st, "TradingBot_Neustart.vbs"))                      # Ziel ist ein Ordner -> Kopieren scheitert
    assert UM.run(cfg, dry=False) == 3
    assert os.path.exists(os.path.join(st, "TradingBot_2Monate.vbs"))
    p = os.path.join(str(root), "Prototyp")
    assert open(os.path.join(p, "engine", "run_loop.py")).read() == "ALT run_loop"
    assert len(sim.sent) == 1


def test_wartebot_sends_fallback_when_go_crashes_unhandled(tmp_path):
    s = TU.WSim(tmp_path, TU.D(10, 0), go_rc=99)
    assert WA.run(s.hooks(tmp_path)) == WA.RC_FAIL and s.sent == [WA.FAIL_TEXT]
    sub = tmp_path / "x"
    sub.mkdir()
    s = TU.WSim(sub, TU.D(10, 0), go_rc=3)
    assert WA.run(s.hooks(sub)) == WA.RC_FAIL and s.sent == []                       # behandelter Fehler: keine zweite Meldung


# ======================================================================== Runde 2 (Variante D + Fixes)
def test_d_trail_event_only_when_effective_stop_tightens():
    from engine import exit_d as XD
    # flache Linie 90 -> Linien-Stop 89,5. Bestaetigtes Tief 90 -> Swing-Stop 87,5 ist WEIT lockerer: kein "Stop nachgezogen"
    rows = [(100, 110, 99, 108), (108, 112, 96, 100), (100, 108, 92, 105), (105, 109, 90, 106),
            (106, 112, 100, 110), (110, 114, 101, 112), (112, 116, 102, 114), (114, 118, 103, 116)]
    t = list(pd.date_range("2026-10-01", periods=len(rows) + 3, freq="4h", tz="UTC"))
    a = np.array([(130, 130, 130, 130)] * 3 + rows, dtype=float)
    st = XD.new_state()
    ev = XD.advance(st, "LONG", t, a[:, 0], a[:, 1], a[:, 2], a[:, 3], lambda j: 90.0, 3, 100.0, 10.0, 5.0)
    assert st["exit"] is None
    assert st["SW"] is not None and st["SW"] < 89.5                       # Swing-Komponente gesetzt, aber unwirksam
    assert [e for e in ev if e["kind"] == XC.EV_TRAIL] == []              # ... daher keine (irrefuehrende) Meldung
    assert XD.current_levels(st, "LONG", lambda j: 90.0, 11, 5.0)[0] == 89.5   # gemeldeter/wirksamer Stop = tatsaechlicher Stop


def test_trailing_texts_are_short_and_show_new_level_for_d_and_cplus():
    for mode, key in (("D", "Neuer Stop: 90,5"), ("CPLUS", "Neue Schwelle: 90,5")):
        t = _trade("SHORT", mode)
        t.strategy_id = "Str.3 D" if mode == "D" else "Str.3 C+"
        ev = {"id": "TRAIL:x", "kind": XC.EV_TRAIL, "time": "2026-10-17T20:00:00+00:00", "level": 90.5, "swing_price": 90.0,
              "swing_time": "2026-10-17T12:00:00+00:00"}
        for d in ("SHORT", "LONG"):
            t.direction = d
            assert TT.cplus_event_text(t, ev) == key and len(TT.cplus_event_text(t, ev).splitlines()) == 1      # 1 Zeile, Kernzahl
            assert "nachgezogen" in TT.cplus_event_title(t, ev) and t.direction in TT.cplus_event_title(t, ev)


def test_cutover_first_cycle_with_only_fetch_failures_is_rejected(tmp_path):
    root = _tree(tmp_path)
    sim = TU.Sim(root, TU.AFTER)
    cfg = sim.cfg()
    cfg.new_run_wait_s = 30
    orig = sim.cmd

    def cmd(argv):
        rc = orig(argv)
        if os.path.basename(argv[-1]) == "NEUSTART-LAUF starten.bat":
            json.dump({"instruments": 94, "no_data": 0, "fetch_failed": 94, "errors": 0},
                      open(os.path.join(str(root), "Prototyp", "paper_runtime_neustart", "last_cycle_monitor.json"), "w"))
        return rc
    cfg.run_cmd = cmd
    assert UM.run(cfg, dry=False) == 3
    assert not os.path.exists(os.path.join(str(root), "Startup", "TradingBot_Neustart.vbs"))
    assert len(sim.sent) == 1 and sim.sent[0].startswith("Umstellung NICHT erfolgt")


def test_outage_message_is_kept_in_outbox_and_retried(tmp_path, monkeypatch):
    from engine import run_loop
    import notify.live as live
    import notify.transport as tp
    sent = []
    state = {"ok": False}

    class FakeTr:
        def __init__(self, token):
            pass

        def send_text(self, chat, text):
            if not state["ok"]:
                raise RuntimeError("offline")
            sent.append(text)
    monkeypatch.setattr(tp, "RealTelegramTransport", FakeTr)
    monkeypatch.setattr(live, "read_env", lambda path=None: {"TELEGRAM_BOT_TOKEN": "T", "STR3_SYSTEM_CHAT_ID": "-999"})
    monkeypatch.setattr(run_loop.time, "sleep", lambda s: None)
    send = run_loop._outage_sender(str(tmp_path))
    send("errors", "Ausfall", "p1")
    send("recovered", "laeuft wieder", "p2")
    assert sent == [] and len(json.load(open(tmp_path / "outage_outbox.json"))) == 2          # nichts verloren
    assert send.flush() == 0
    state["ok"] = True
    assert send.flush() == 2
    assert [x.split(chr(10))[1] for x in sent] == ["Ausfall", "laeuft wieder"]                  # Reihenfolge erhalten
    assert json.load(open(tmp_path / "outage_outbox.json")) == []
