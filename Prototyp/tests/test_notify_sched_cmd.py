# -*- coding: utf-8 -*-
"""Increment-3-Tests: Terminierung/DST, Einmal-Versand, rollierend-30 != Kalendermonat,
autorisierte Befehle (Allowlist, keine Codeausfuehrung), Dispatcher Router->Queue.
Spec-Telegram-Tests: 6,9,10,20,21,22,23,24,30."""
import os, sys
from datetime import datetime, timezone
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notify import messages as M
from notify import scheduling as S
from notify import commands as C
from notify.config import load_and_validate
from notify.queue import PersistentQueue
from notify.dispatcher import Dispatcher
from notify.transport import MockTransport

TZ = "Europe/Berlin"
ENV = {"TELEGRAM_BOT_TOKEN": "1234567890:AAHtokentokentokentokentokentokenXYZ",
       "TELEGRAM_AUTHORIZED_USER_IDS": "42",
       "STR3_PRO2_CHAT_ID": "-1002", "STR3_PRO3_CHAT_ID": "-1003",
       "STR3_COMPARISON_CHAT_ID": "-1009", "STR3_SYSTEM_CHAT_ID": "-1010"}
ACTIVE = ["Str.3 Pro.2", "Str.3 Pro.3"]


def cfg():
    c, _ = load_and_validate(ENV, ACTIVE); return c


# --- 22: Zeitraum in Europe/Berlin bestimmt, als UTC gespeichert ---
def test_weekly_period_utc_boundaries():
    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)   # Sommerzeit (+2)
    s_utc, e_utc, sd, ed = S.last_full_calendar_days(now, 7, TZ)
    # Ende = heute 00:00 Berlin = 2026-07-20 00:00 +02:00 = 2026-07-19 22:00 UTC
    assert e_utc == datetime(2026, 7, 19, 22, 0, tzinfo=timezone.utc)
    assert s_utc == datetime(2026, 7, 12, 22, 0, tzinfo=timezone.utc)
    assert str(sd) == "2026-07-13" and str(ed) == "2026-07-19"   # 7 volle Tage inkl.


# --- 23: Sommerzeitwechsel -> keine doppelten/fehlenden Berichte (Periode eindeutig) ---
def test_dst_change_period_unique():
    # DST-Ende in DE: 2026-10-25. Zwei Laeufe an aufeinanderfolgenden Tagen -> verschiedene Perioden.
    n1 = datetime(2026, 10, 25, 10, 0, tzinfo=timezone.utc)
    n2 = datetime(2026, 10, 26, 10, 0, tzinfo=timezone.utc)
    k1 = S.make_report_key("Str.3 Pro.2", M.WEEKLY_REPORT, *S.period_for(M.WEEKLY_REPORT, n1, TZ)[2:], "v1")
    k2 = S.make_report_key("Str.3 Pro.2", M.WEEKLY_REPORT, *S.period_for(M.WEEKLY_REPORT, n2, TZ)[2:], "v1")
    assert k1 != k2


# --- 9: Einmal-Versand je (scope, type, period, version) ---
def test_report_once_only(tmp_path):
    reg = S.ReportRegistry(str(tmp_path / "reports.json"))
    now = datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)
    _, _, sd, ed = S.period_for(M.WEEKLY_REPORT, now, TZ)
    key = S.make_report_key("Str.3 Pro.2", M.WEEKLY_REPORT, sd, ed, "v1")
    assert not reg.already_sent(key)
    reg.record(key, delivery_status="SENT", file_hash="abc")
    reg2 = S.ReportRegistry(str(tmp_path / "reports.json"))   # Neustart
    assert reg2.already_sent(key)


# --- 21: rollierend-30 wird NICHT als Kalendermonat bezeichnet ---
def test_rolling_label_not_calendar_month():
    lbl = S.period_label(M.ROLLING_30D_REPORT, "2026-06-20", "2026-07-19")
    assert "Kalendermonat" not in lbl and "30" in lbl
    cal = S.period_label(M.CALENDAR_MONTH_REPORT, "2026-06-01", "2026-06-30")
    assert "Kalendermonat" in cal


# --- 10: Befehle nicht autorisierter Nutzer werden ignoriert ---
def test_unauthorized_user_ignored():
    res = C.handle(user_id="999", chat_id="-1002", text="/status",
                   authorized_user_ids={"42"}, handlers={"/status": lambda: "x"})
    assert res.status == "IGNORED_UNAUTHORIZED" and res.text == ""


# --- 24: unbekannter Befehl loest keine Codeausfuehrung aus ---
def test_unknown_command_no_execution():
    called = {"n": 0}
    def boom(): called["n"] += 1; return "should not run"
    res = C.handle("42", "-1002", "/rm_rf oder beliebiger text", {"42"}, {"/status": boom})
    assert res.status == "UNKNOWN_COMMAND" and called["n"] == 0

def test_known_command_runs_handler():
    res = C.handle("42", "-1002", "/status", {"42"}, {"/status": lambda: "alles ok"})
    assert res.status == "OK" and res.text == "alles ok"


# --- 20/30: gleiche parent_signal_id -> verschiedene Varianten an ihre eigene Gruppe ---
def test_same_parent_signal_routes_to_own_groups(tmp_path):
    q = PersistentQueue(str(tmp_path / "q.json"))
    disp = Dispatcher(cfg(), q)
    for sid, chat in (("Str.3 Pro.2", "-1002"), ("Str.3 Pro.3", "-1003")):
        m = M.Message(sid, "v1", M.TRADE_OPENED, symbol="GC=F", signal_id="SIG-1",
                      parent_signal_id="PSIG-1", body="x")
        assert disp.dispatch(m) is not None
    t = MockTransport(); q.process(t)
    assert set(t.chats_used()) == {"-1002", "-1003"}   # jede Variante an ihre Gruppe


# --- Fehlende Varianten-Chat-ID: Dispatcher warnt, keine Fehlleitung ---
def test_dispatch_missing_chat_warns_no_misroute(tmp_path):
    q = PersistentQueue(str(tmp_path / "q.json"))
    disp = Dispatcher(cfg(), q)
    m = M.Message("Str.3 Pro.4", "v1", M.TRADE_OPENED, symbol="X", signal_id="S", body="x")  # Pro.4 nicht konfiguriert
    assert disp.dispatch(m) == "WARNING"
    t = MockTransport(); q.process(t)
    # nur die Systemwarnung ging an die Systemgruppe, KEINE Variantengruppe
    assert t.chats_used() <= {"-1010"}
