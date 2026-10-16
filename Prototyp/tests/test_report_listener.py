# -*- coding: utf-8 -*-
"""Bericht-Abruf per Telegram: Ausloeser-Parsing, Chat-/Nutzerfilter, Rate-Limit, Offset-Persistenz,
Fehlerpfad und Zwischenstands-PDF (alles ohne Netz, MockTransport)."""
import os, sys, time
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notify import report_listener as RL
from notify.transport import MockTransport

SYS_CHAT = "-1001"
BOT = "Str3_trading_alerts_bot"


# ------------------------------------------------------------------ Ausloeser
@pytest.mark.parametrize("text", ["bericht", "Bericht", "BERICHT", "  bericht  ", "\tBericht\n", "bericht\u00a0",
                                  "/bericht", "/Bericht", f"/bericht@{BOT}", f"/BERICHT@{BOT.upper()}",
                                  "/bericht jetzt", "\u200bbericht"])
def test_trigger_accepted(text):
    assert RL.is_report_trigger(text, BOT)


@pytest.mark.parametrize("text", ["", None, "berichte", "mein bericht", "bericht bitte", "/berichte", "/status",
                                  "/bericht@anderer_bot", "wochenbericht", "bericht!", "/ bericht"])
def test_trigger_rejected(text):
    assert not RL.is_report_trigger(text, BOT)


def test_trigger_command_for_other_bot_ignored_even_without_known_name():
    assert not RL.is_report_trigger("/bericht@irgendwer", None)
    assert RL.is_report_trigger("/bericht", None)


# ------------------------------------------------------------------ Filter
def test_chat_and_user_filter():
    assert RL.chat_allowed("-1001", "-1001") and RL.chat_allowed(-1001, "-1001")
    assert not RL.chat_allowed("-2002", "-1001")
    assert not RL.chat_allowed(None, "-1001")
    assert not RL.chat_allowed("-1001", "")
    assert RL.user_allowed("42", ["42", "43"]) and not RL.user_allowed("44", ["42"])
    assert RL.user_allowed("44", [])           # leere Allowlist = nur Chat-Filter


def test_rate_check():
    assert RL.rate_check(0, 1000) == (True, 0)
    ok, wait = RL.rate_check(1000, 1030, 60)
    assert not ok and wait == 30
    assert RL.rate_check(1000, 1060, 60)[0]


# ------------------------------------------------------------------ Offset-Persistenz
def test_offset_persistence_atomic(tmp_path):
    p = str(tmp_path / "rt" / "state.json")
    st = RL.StateStore(p)
    assert st.offset == 0 and not st.initialized
    st.advance(100)
    st.advance(99)                                  # nie zurueck
    assert st.offset == 101
    st2 = RL.StateStore(p)                          # "Neustart"
    assert st2.offset == 101
    assert not os.path.exists(p + ".tmp")           # atomar: keine Temp-Reste
    st2.last_report_ts, st2.initialized = 123.0, True
    st2.save()
    st3 = RL.StateStore(p)
    assert st3.last_report_ts == 123.0 and st3.initialized


def test_corrupt_state_falls_back(tmp_path):
    p = tmp_path / "state.json"
    p.write_text("{kaputt", encoding="utf-8")
    assert RL.StateStore(str(p)).offset == 0


# ------------------------------------------------------------------ Listener-Ablauf
class Clock:
    def __init__(self, t=1_000_000.0): self.t = t
    def __call__(self): return self.t


def _upd(uid, text, chat=SYS_CHAT, user="42", is_bot=False):
    return {"update_id": uid, "message": {"text": text, "chat": {"id": int(chat)},
                                          "from": {"id": int(user), "is_bot": is_bot}}}


def _mk(tmp_path, builder=None, users=("42",), clock=None):
    mt = MockTransport()
    state = RL.StateStore(str(tmp_path / "state.json"))
    clock = clock or Clock()
    calls = []

    def build():
        calls.append(1)
        return "C:/x/report.pdf", "Kurztext"
    lis = RL.Listener(state, mt, builder or build, SYS_CHAT, users, BOT, clock=clock)
    return lis, mt, state, clock, calls


def test_report_flow_sends_announce_then_document(tmp_path):
    lis, mt, state, clock, calls = _mk(tmp_path)
    assert lis.handle_update(_upd(1, "Bericht")) == "sent"
    kinds = [(r["kind"], r["chat_id"]) for r in mt.sent]
    assert kinds == [("text", SYS_CHAT), ("document", SYS_CHAT)]
    assert mt.sent[0]["payload"] == "Erstelle Bericht …"
    assert mt.sent[1]["caption"] == "Kurztext" and len(calls) == 1
    assert state.offset == 2


def test_other_chat_and_other_user_ignored(tmp_path):
    lis, mt, state, clock, calls = _mk(tmp_path)
    assert lis.handle_update(_upd(5, "bericht", chat="-2002")) == "ignored"
    assert lis.handle_update(_upd(6, "bericht", user="99")) == "ignored"
    assert lis.handle_update(_upd(7, "bericht", is_bot=True)) == "ignored"
    assert lis.handle_update(_upd(8, "hallo")) == "not_trigger"
    assert lis.handle_update({"update_id": 9, "edited_message": {}}) == "ignored"
    assert mt.sent == [] and calls == []
    assert state.offset == 10                        # auch ignorierte Updates schieben den Offset


def test_rate_limit_one_report_per_minute(tmp_path):
    lis, mt, state, clock, calls = _mk(tmp_path)
    assert lis.handle_update(_upd(1, "bericht")) == "sent"
    clock.t += 20
    assert lis.handle_update(_upd(2, "/bericht")) == "rate_limited"
    assert len(calls) == 1
    assert "bitte warten" in mt.sent[-1]["payload"]
    clock.t += 45                                     # insgesamt 65 s
    assert lis.handle_update(_upd(3, f"/bericht@{BOT}")) == "sent"
    assert len(calls) == 2


def test_rate_limit_survives_restart(tmp_path):
    lis, mt, state, clock, calls = _mk(tmp_path)
    lis.handle_update(_upd(1, "bericht"))
    lis2, mt2, state2, _, calls2 = _mk(tmp_path, clock=clock)    # gleicher Zustand auf Platte
    assert lis2.handle_update(_upd(2, "bericht")) == "rate_limited" and calls2 == []


def test_error_is_reported_without_secrets_or_paths(tmp_path):
    def boom():
        raise RuntimeError("Datei C:\\geheim\\pfad\\x fehlt, token 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghi")
    lis, mt, state, clock, _ = _mk(tmp_path, builder=boom)
    assert lis.handle_update(_upd(1, "bericht")) == "error"
    last = mt.sent[-1]["payload"]
    assert "RuntimeError" in last and "geheim" not in last and "123456789" not in last and "C:\\" not in last


def test_telegram_send_failure_does_not_crash(tmp_path):
    lis, mt, state, clock, calls = _mk(tmp_path)
    mt.fail_chats.add(SYS_CHAT)
    assert lis.process_updates([_upd(1, "bericht")]) == ["error"]       # kein Absturz
    assert state.offset == 2


def test_process_updates_in_order_and_offset(tmp_path):
    lis, mt, state, clock, calls = _mk(tmp_path)
    res = lis.process_updates([_upd(12, "hallo"), _upd(10, "x"), _upd(11, "bericht")])
    assert res == ["not_trigger", "sent", "not_trigger"]
    assert state.offset == 13


# ------------------------------------------------------------------ Zwischenstands-PDF (read-only)
def test_status_report_build(tmp_path):
    from engine.ledger import Ledger
    from engine.tracker import PaperTradeStore, PaperTrade
    from notify import status_report as SR
    rt = str(tmp_path / "rt"); os.makedirs(rt)
    lg = Ledger(os.path.join(rt, "ledger.json"))
    lg.record_candidate("P1", "BTC-USD", "LONG", "ACCEPTED_PROVISIONAL", "t", "t")
    lg.record_variant_eval("P1", "Str.3 Pro.1", "v1", "PASS")
    lg.record_variant_eval("P1", "Str.3 Pro.2", "v1", "NOT_EVALUABLE", rejection_reason="Daily-Daten fehlen")
    store = PaperTradeStore(os.path.join(rt, "trades.json"))

    def mk(tid, status, net_r, outcome="TARGET"):
        t = PaperTrade(trade_id=tid, variant_evaluation_id="VE", parent_signal_id="P1", strategy_id="Str.3 Pro.1",
                       break_even="BE-0", symbol="BTC-USD", asset_class="crypto", direction="LONG",
                       signal_time="2026-10-01T00:00:00+00:00", status=status, stop_initial=90.0, target=120.0)
        if status == "closed":
            t.result = {"status": "closed", "outcome": outcome, "netto_r": net_r, "brutto_r": net_r,
                        "net_return_pct": net_r, "gross_return_pct": net_r, "closed_ts": time.time(),
                        "duration_days": 1.0, "mfe_r": 1, "mae_r": 0.2, "exit_time": "2026-10-02T00:00:00+00:00"}
        else:
            t.entry_time = "2026-10-01T04:00:00+00:00"; t.result = {"status": "open", "mfe_r": 0.5, "mae_r": 0.1}
        return t
    store.add(mk("a", "closed", 2.0)); store.add(mk("b", "closed", -1.1, "STOP")); store.add(mk("c", "open", 0))
    d = SR.collect(rt, None, check_process=False)
    assert d["totals"]["closed"] == 2 and d["totals"]["open"] == 1
    p1 = d["variants"][0]
    assert p1["closed"] == 2 and abs(p1["rep"]["total_r_netto"] - 0.9) < 1e-9     # offene Trades zaehlen nicht
    assert "NOT_EVALUABLE" in d["variants"][1]["note"]
    pdf = SR.build_pdf(d, str(tmp_path / "out" / "r.pdf"))
    assert os.path.getsize(pdf) > 5000
    cap = SR.caption(d)
    assert "nicht gewertet" in cap and len(cap) <= 1024 and "Paper-Trading" in cap


# ------------------------------------------------------------------ Gesamt-% je Gruppe
def test_total_pct_helpers_sign_color_and_format():
    from notify import status_report as SR
    assert SR.pct_color(5.0) == SR.GREEN and SR.pct_color(-0.1) == SR.RED
    assert SR.pct_color(None) == SR.GREY and SR.pct_color(0.0) == "black"
    assert SR.fpct(81.94) == "+81,9 %" and SR.fpct(-3.26) == "−3,3 %" and SR.fpct(None) == "–"


def _seed(tmp_path, rows):
    """rows: Liste (strategy_id, status, net_pct, netto_r)"""
    from engine.ledger import Ledger
    from engine.tracker import PaperTradeStore, PaperTrade
    rt = str(tmp_path / "rt2"); os.makedirs(rt)
    lg = Ledger(os.path.join(rt, "ledger.json"))
    for sid, n_eval, reason in [("Str.3 Pro.1", 1, ""), ("Str.3 Pro.2", 1, "Daily-Daten fehlen"),
                                ("Str.3 Pro.5", 1, "COMBINED_NOT_EVALUABLE")]:
        lg.record_candidate("P", "BTC-USD", "LONG", "ACCEPTED_PROVISIONAL", "t", "t")
        lg.record_variant_eval("P", sid, "v1", "PASS" if not reason else "NOT_EVALUABLE", rejection_reason=reason)
    lg.record_variant_eval("P", "Str.3 Pro.8", "v1", "NOT_CONFIGURED", rejection_reason="PRO8_NOT_CONFIGURED")
    store = PaperTradeStore(os.path.join(rt, "trades.json"))
    for i, (sid, status, pct, r) in enumerate(rows):
        t = PaperTrade(trade_id=f"t{i}", variant_evaluation_id="VE", parent_signal_id="P", strategy_id=sid,
                       break_even="BE-1", symbol="X", asset_class="fx", direction="LONG", signal_time="2026-10-01T00:00:00+00:00",
                       status=status, stop_initial=1.0, target=2.0)
        t.result = {"status": "closed", "outcome": "STOP", "netto_r": r, "brutto_r": r, "net_return_pct": pct,
                    "gross_return_pct": pct, "closed_ts": time.time() + i, "duration_days": 1.0, "mfe_r": 0, "mae_r": 1,
                    "exit_time": "2026-10-02T00:00:00+00:00"} if status == "closed" else {"status": "open"}
        store.add(t)
    return rt


def test_total_pct_negative_group_and_groups_without_trades(tmp_path):
    from notify import status_report as SR
    rt = _seed(tmp_path, [("Str.3 Pro.1", "closed", -1.5, -1.1), ("Str.3 Pro.1", "closed", 0.5, 0.4),
                          ("Str.3 Pro.1", "open", 9.0, 0)])
    d = SR.collect(rt, None, check_process=False)
    v = {x["sid"]: x for x in d["variants"]}
    assert abs(SR.total_pct(v["Str.3 Pro.1"]) - (-1.0)) < 1e-9          # Summe aller geschlossenen, offener zaehlt nicht
    assert SR.pct_color(SR.total_pct(v["Str.3 Pro.1"])) == SR.RED
    assert SR.total_pct(v["Str.3 Pro.2"]) is None
    assert SR.no_trade_reason(v["Str.3 Pro.2"]) == "Tagesdaten fehlen"
    assert SR.no_trade_reason(v["Str.3 Pro.5"]) == "Tagesdaten/Volumen fehlen"
    assert SR.no_trade_reason(v["Str.3 Pro.8"]) == "nicht konfiguriert"
    assert os.path.getsize(SR.build_pdf(d, str(tmp_path / "o" / "r.pdf"))) > 5000
    cap = SR.caption(d)
    assert "Pro.1 −1,0 %" in cap and "Pro.2 +" not in cap and "Pro.2 −" not in cap    # nur handelnde Varianten
    assert len(cap) <= 1024


def test_caption_total_pct_line_positive(tmp_path):
    from notify import status_report as SR
    rt = _seed(tmp_path, [("Str.3 Pro.1", "closed", 81.9, 4.0)])
    cap = SR.caption(SR.collect(rt, None, check_process=False))
    assert "Gesamt-% (alle abgeschlossenen Trades" in cap and "Pro.1 +81,9 %" in cap
