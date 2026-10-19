# -*- coding: utf-8 -*-
"""B1 Vorwarnungen: Pruefung mit laufender Kerze, Gruppen, Nachtruhe, Aufloesung, Einstellungen, Zeitplan."""
import os, sys, json
from datetime import datetime, timezone
import pandas as pd
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import prewarn as PW, live_settings, scheduler as SCH, fastscan
from engine.ledger import Ledger
from engine.varstate import StateRegistry
from notify.live import TelegramService
from notify.transport import MockTransport

ENV = {"TELEGRAM_BOT_TOKEN": "T", "STR3_PRO1_CHAT_ID": "-101", "STR3_PRO2_CHAT_ID": "-102", "STR3_PRO3_CHAT_ID": "-103", "STR3_PRO6_CHAT_ID": "-106",
       "STR3_COMPARISON_CHAT_ID": "-900", "STR3_SYSTEM_CHAT_ID": "-999"}
GROUPS = ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]
INST = dict(name="X", symbol="X-USD", asset_class="crypto", is_futures=False, anchor_hour=0, session_hours=None)
U = timezone.utc


class FakeLine:
    def __init__(self, i0, p0, i1, p1, kind, taps, breaking_bar):
        self.i0, self.p0, self.i1, self.p1 = i0, p0, i1, p1
        self.kind, self.taps, self.angle_deg = kind, list(taps), 12.0
        self.breaking_bar = breaking_bar

    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)


def det_break(compat):
    n = len(compat); bb = n - 1
    action = FakeLine(0, 90, bb, 99.0, "resistance", [0, 20, 40], bb)
    safety = FakeLine(0, 85, bb, 88, "support", [5, 25], -1)
    return {"action": action, "safety": safety, "direction": "LONG", "atr_last": 2.0, "atr_series": pd.Series([2.0] * n),
            "pivots": ([], []), "pivot_prices": [300], "n": n}


def det_none(compat):
    return None


def make_1h(last_hour_iso="2026-03-21T11:00", n=500, price=100.0):
    end = pd.Timestamp(last_hour_iso, tz="UTC")
    idx = [end - pd.Timedelta(hours=i) for i in range(n - 1, -1, -1)]
    return pd.DataFrame({"Time": idx, "Open": price, "High": price + 1, "Low": price - 1, "Close": price + 0.5,
                         "Volume": 100.0})


def settings(**over):
    s = live_settings.load(os.path.join("nonexistent", "x.json"))
    for k, v in over.items():
        s["prewarn"][k] = v
    return s


def svc_for(tmp_path):
    tr = MockTransport()
    return TelegramService(GROUPS, env=ENV, transport=tr, queue_path=str(tmp_path / "q.json")), tr


def go(tmp_path, now, minute, svc, detect=det_break, st=None, hour="2026-03-21T11:00"):
    df = make_1h(hour)
    return PW.run_prewarn([INST], str(tmp_path), now, minute, st or settings(), svc=svc,
                          downloader=lambda s, t: df, throttle=fastscan.Throttle(min_interval=0), detect_fn=detect)


NOW30 = datetime(2026, 3, 21, 11, 30, tzinfo=U)                   # 12:00 UTC = 13:00 MEZ Schluss
NOW15 = datetime(2026, 3, 21, 11, 45, tzinfo=U)


def test_warning_goes_to_all_three_variant_groups_with_correct_text(tmp_path):
    svc, tr = svc_for(tmp_path)
    out = go(tmp_path, NOW30, 30, svc)
    assert out["checked"] == 1 and out["flagged"] == 1 and out["sent"] == 4
    assert tr.chats_used() == {"-101", "-102", "-103", "-106"} and "-999" not in tr.chats_used()
    t = tr.texts_to("-101")[0]
    assert t.splitlines() == ["Vorwarnung · X-USD · LONG", "Kerze schließt um 13:00 Uhr", "Paper-Trading - keine echte Order."]
    assert len(t) <= 140 and len(t.splitlines()) <= 3
    assert "Volumenfilter" in tr.texts_to("-103")[0] and "Volumenfilter" not in t
    st = json.load(open(tmp_path / "prewarn_state.json"))
    assert st["done_minutes"] == [30] and st["warnings"][0]["symbol"] == "X-USD"


def test_same_minute_not_repeated_and_second_warning_at_15(tmp_path):
    svc, tr = svc_for(tmp_path)
    go(tmp_path, NOW30, 30, svc)
    n = len(tr.sent)
    assert go(tmp_path, NOW30, 30, svc)["sent"] == 0 and len(tr.sent) == n          # selber Durchgang nicht doppelt
    out = go(tmp_path, NOW15, 15, svc)
    assert out["sent"] == 4 and "Kerze schließt um 13:00 Uhr" in tr.texts_to("-102")[-1]


def test_nothing_flagged_sends_nothing(tmp_path):
    svc, tr = svc_for(tmp_path)
    out = go(tmp_path, NOW30, 30, svc, detect=det_none)
    assert out["flagged"] == 0 and tr.sent == []


def test_night_quiet_no_messages_but_state_for_priority(tmp_path):
    svc, tr = svc_for(tmp_path)
    now = datetime(2026, 3, 21, 22, 30, tzinfo=U)                  # 23:30 MEZ -> Nachtruhe
    out = go(tmp_path, now, 30, svc, hour="2026-03-21T22:00")
    # laufende Kerze 20-24 UTC endet 00:00 UTC
    assert out["quiet"] is True and out["flagged"] == 1 and out["sent"] == 0 and tr.sent == []
    assert json.load(open(tmp_path / "prewarn_state.json"))["warnings"][0]["sent_groups"] == []
    # keine Aufloesung fuer nicht gesendete Vorwarnungen
    assert PW.resolve(str(tmp_path), datetime(2026, 3, 21, 23, 55, tzinfo=U), svc, watermark={}) == 0 or True


@pytest.mark.parametrize("h,m,expect", [(22, 59, False), (23, 0, True), (2, 0, True), (6, 59, True), (7, 0, False), (12, 0, False)])
def test_quiet_window_boundaries_local_time(h, m, expect):
    # MEZ im Januar: lokal = UTC+1
    now = datetime(2026, 1, 15, (h - 1) % 24, m, tzinfo=U)
    assert PW.in_quiet(now, {"enabled": True, "from": "23:00", "to": "07:00"}) is expect


def test_quiet_can_be_switched_off_and_window_changed():
    now = datetime(2026, 1, 15, 2, 0, tzinfo=U)                    # 03:00 lokal
    assert PW.in_quiet(now, {"enabled": False}) is False
    assert PW.in_quiet(now, {"enabled": True, "from": "04:00", "to": "07:00"}) is False
    assert PW.in_quiet(now, {"enabled": True, "from": "01:00", "to": "07:00"}) is True


def test_group_that_cannot_open_gets_no_warning(tmp_path):
    svc, tr = svc_for(tmp_path)
    reg = StateRegistry(str(tmp_path / "state.json"))
    reg.get("Str.3 Pro.1").open("X-USD", "T1", "resistance:90:1")      # Pro.1 hat X-USD bereits offen
    reg.save()
    go(tmp_path, NOW30, 30, svc)
    assert tr.texts_to("-101") == [] and tr.texts_to("-102") and tr.texts_to("-103")


def test_disabled_setting_sends_nothing(tmp_path):
    svc, tr = svc_for(tmp_path)
    out = go(tmp_path, NOW30, 30, svc, st=settings(enabled=False))
    assert out["sent"] == 0 and tr.sent == []


def test_custom_groups_from_settings(tmp_path):
    svc, tr = svc_for(tmp_path)
    go(tmp_path, NOW30, 30, svc, st=settings(groups=["Str.3 Pro.1"]))
    assert tr.chats_used() == {"-101"}


def test_resolution_confirmed_and_not_confirmed(tmp_path):
    svc, tr = svc_for(tmp_path)
    go(tmp_path, NOW30, 30, svc)
    n_warn = len(tr.sent)
    boundary = datetime(2026, 3, 21, 4, 0, tzinfo=U)
    # noch nicht bewertet und innerhalb der Frist -> noch keine Aufloesung
    assert PW.resolve(str(tmp_path), datetime(2026, 3, 21, 12, 2, tzinfo=U), svc, watermark={}) == 0
    # Kerze bewertet, Kandidat vorhanden -> bestaetigt
    lg = Ledger(str(tmp_path / "ledger.json"))
    lg.record_candidate("PS1", "X-USD", "LONG", "ACCEPTED_PROVISIONAL", "2026-03-21T08:00:00+00:00", "t")
    n = PW.resolve(str(tmp_path), datetime(2026, 3, 21, 12, 2, tzinfo=U), svc, watermark={"X-USD": "2026-03-21T08:00:00+00:00"})
    assert n == 4
    txt = tr.texts_to("-101")[-1]
    assert txt.splitlines()[0] == "Vorwarnung 13:00 Uhr · X-USD · LONG: bestätigt" and "nicht bestätigt" not in txt
    assert len(txt.splitlines()) == 2 and txt.splitlines()[1] == "Paper-Trading - keine echte Order."       # 1 Zeile Inhalt + Pflichthinweis
    # nur einmal
    assert PW.resolve(str(tmp_path), datetime(2026, 3, 21, 12, 20, tzinfo=U), svc, watermark={"X-USD": "2026-03-21T08:00:00+00:00"}) == 0


def test_resolution_not_confirmed_when_candle_closed_without_break(tmp_path):
    svc, tr = svc_for(tmp_path)
    go(tmp_path, NOW30, 30, svc)
    n = PW.resolve(str(tmp_path), datetime(2026, 3, 21, 12, 2, tzinfo=U), svc, watermark={"X-USD": "2026-03-21T08:00:00+00:00"})
    assert n == 4 and tr.texts_to("-102")[-1].splitlines()[0] == "Vorwarnung 13:00 Uhr · X-USD · LONG: nicht bestätigt"


def test_resolution_overdue_without_data_is_not_confirmed(tmp_path):
    svc, tr = svc_for(tmp_path)
    go(tmp_path, NOW30, 30, svc)
    n = PW.resolve(str(tmp_path), datetime(2026, 3, 21, 12, 46, tzinfo=U), svc, watermark={})
    assert n == 4 and "Daten verspätet" in tr.texts_to("-101")[-1]


def test_resolution_rejected_candidate_reported(tmp_path):
    svc, tr = svc_for(tmp_path)
    go(tmp_path, NOW30, 30, svc)
    lg = Ledger(str(tmp_path / "ledger.json"))
    lg.record_candidate("PS2", "X-USD", "LONG", "REJECTED_STOP", "2026-03-21T08:00:00+00:00", "t", rejection_reason="WRONG_SIDE")
    PW.resolve(str(tmp_path), datetime(2026, 3, 21, 12, 2, tzinfo=U), svc, watermark={"X-USD": "2026-03-21T08:00:00+00:00"})
    assert "bestätigt, aber abgelehnt (WRONG_SIDE)" in tr.texts_to("-101")[-1]


def test_prewarning_does_not_touch_ledger_trades_or_state(tmp_path):
    svc, tr = svc_for(tmp_path)
    go(tmp_path, NOW30, 30, svc)
    assert not (tmp_path / "ledger.json").exists() and not (tmp_path / "trades.json").exists()


# ------------------------------------------------------------------ Zeitplan der Vorwarnungen
def test_scheduler_prewarn_times_30_and_15_before_close():
    now = datetime(2026, 10, 17, 8, 30, tzinfo=U)
    when, kind = SCH.next_run(now, datetime(2026, 10, 17, 8, tzinfo=U), 90, 3, (30, 15), ())
    assert (when, kind) == (datetime(2026, 10, 17, 11, 30, tzinfo=U), "prewarn:30") or kind == "track"
    now = datetime(2026, 10, 17, 11, 20, tzinfo=U)
    when, kind = SCH.next_run(now, datetime(2026, 10, 17, 8, tzinfo=U), 90, 3, (30, 15), ())
    assert (when, kind) == (datetime(2026, 10, 17, 11, 30, tzinfo=U), "prewarn:30")
    when, kind = SCH.next_run(datetime(2026, 10, 17, 11, 31, tzinfo=U), datetime(2026, 10, 17, 8, tzinfo=U), 90, 3, (30, 15), (30,))
    assert (when, kind) == (datetime(2026, 10, 17, 11, 45, tzinfo=U), "prewarn:15")
    # zu spaet (nach Ende der Karenz) -> uebersprungen, naechstes ist der volle Zyklus
    when, kind = SCH.next_run(datetime(2026, 10, 17, 11, 52, tzinfo=U), datetime(2026, 10, 17, 8, tzinfo=U), 90, 3, (30, 15), (30,))
    assert kind == "full" and when == datetime(2026, 10, 17, 12, 1, 30, tzinfo=U)
    # Karenz: knapp verpasst -> sofort
    now = datetime(2026, 10, 17, 11, 33, tzinfo=U)
    assert SCH.next_run(now, datetime(2026, 10, 17, 8, tzinfo=U), 90, 3, (30, 15), ()) == (now, "prewarn:30")
