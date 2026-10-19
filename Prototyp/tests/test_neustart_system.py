# -*- coding: utf-8 -*-
"""A3/A5: Zeitplan der Zyklen, Ausfall-Meldungen, Zeitumstellung, 2-Wochen-Bericht, Einstellungen."""
import os, sys, json
from datetime import datetime, timedelta, timezone, date
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import scheduler as SCH
from engine import outage as OUT
from engine import live_settings
from notify import system_schedule as SS

U = timezone.utc


def dt(*a):
    return datetime(*a, tzinfo=U)


# ------------------------------------------------------------------ Zeitplan (A5)
def test_full_cycle_90s_after_each_4h_close():
    for h in (0, 4, 8, 12, 16, 20):
        b = dt(2026, 10, 17, h)
        when, kind = SCH.next_run(b - timedelta(minutes=10), b - timedelta(hours=4), 90, passes=1)
        # vor dem Schluss: naechstes Ereignis ist der Schluss + 90 s oder (vorher) eine Track-Runde; nach Schluss+90s voll
        w2, k2 = SCH.next_run(b + timedelta(seconds=91), b - timedelta(hours=4), 90)
        assert k2 == SCH.FULL and w2 == b + timedelta(seconds=91)
    when, kind = SCH.next_run(dt(2026, 10, 17, 11, 59), dt(2026, 10, 17, 8), 90, passes=3)
    assert (when, kind) == (dt(2026, 10, 17, 12, 1, 30), SCH.FULL)


def test_hourly_tracking_between_closes_and_no_track_at_close_hour():
    t = dt(2026, 10, 17, 9, 10)
    when, kind = SCH.next_run(t, dt(2026, 10, 17, 8), 90, passes=3)
    assert (when, kind) == (dt(2026, 10, 17, 10, 5), SCH.TRACK)
    # 11:10 -> naechstes ist der 4h-Schluss 12:00 + 90 s (kein Track um 12:05)
    when, kind = SCH.next_run(dt(2026, 10, 17, 11, 10), dt(2026, 10, 17, 8), 90, passes=3)
    assert kind == SCH.FULL and when == dt(2026, 10, 17, 12, 1, 30)


def test_retry_passes_after_close():
    b = dt(2026, 10, 17, 12)
    when, kind = SCH.next_run(b + timedelta(minutes=3), b, 90, passes=1)
    assert kind == SCH.FULL and when == b + timedelta(minutes=6)
    when, kind = SCH.next_run(b + timedelta(minutes=7), b, 90, passes=2)
    assert kind == SCH.FULL and when == b + timedelta(minutes=16)
    when, kind = SCH.next_run(b + timedelta(minutes=17), b, 90, passes=3)
    assert kind == SCH.TRACK                                                  # keine weitere Nachpruefung


def test_catch_up_after_outage_runs_immediately():
    now = dt(2026, 10, 17, 15, 20)                                           # PC war seit 08:30 aus
    when, kind = SCH.next_run(now, dt(2026, 10, 17, 8), 90, passes=1)
    assert kind == SCH.FULL and when == now


def test_old_missed_retry_is_skipped():
    now = dt(2026, 10, 17, 14, 0)                                            # Nachpruefung von 12:06 laengst vorbei
    when, kind = SCH.next_run(now, dt(2026, 10, 17, 12), 90, passes=1)
    assert kind == SCH.TRACK


def test_first_start_without_state_runs_full_after_delay():
    now = dt(2026, 10, 17, 12, 30)
    assert SCH.next_run(now, None, 90) == (now, SCH.FULL)


# ------------------------------------------------------------------ Ausfall-Meldungen (A3a)
class Rec:
    def __init__(self):
        self.msgs = []

    def __call__(self, kind, text, period):
        self.msgs.append((kind, text, period))


def mk(tmp_path, t0=1000.0):
    clock = {"t": t0}
    rec = Rec()
    m = OUT.OutageMonitor(str(tmp_path / "o.json"), rec, clock=lambda: clock["t"])
    return m, rec, clock


GOOD = {"instruments": 94, "no_data": 0}
NODATA = {"instruments": 94, "no_data": 94}


def test_three_failed_cycles_one_message_then_recovery(tmp_path):
    m, rec, clock = mk(tmp_path)
    m.cycle_result(exception=True); m.cycle_result(exception=True)
    assert rec.msgs == []
    m.cycle_result(exception=True)
    assert [k for k, *_ in rec.msgs] == ["errors"]
    for _ in range(5):                                                       # weitere Fehler -> KEINE Wiederholung
        m.cycle_result(exception=True)
    assert len(rec.msgs) == 1
    m.cycle_result(mon=GOOD)
    assert [k for k, *_ in rec.msgs] == ["errors", "recovered"]
    m.cycle_result(mon=GOOD)
    assert len(rec.msgs) == 2                                                # Erholung nur einmal


def test_no_data_for_all_instruments_twice(tmp_path):
    m, rec, _ = mk(tmp_path)
    m.cycle_result(mon=NODATA)
    assert rec.msgs == []
    m.cycle_result(mon=NODATA)
    assert [k for k, *_ in rec.msgs] == ["no_data"]


def test_partial_no_data_is_not_an_outage(tmp_path):
    m, rec, _ = mk(tmp_path)
    for _ in range(5):
        m.cycle_result(mon={"instruments": 94, "no_data": 20})
    assert rec.msgs == []


def test_stall_over_two_hours(tmp_path):
    m, rec, clock = mk(tmp_path)
    for i in range(1, 300):                                                  # Watchdog tickt alle 30 s
        clock["t"] += 30
        m.tick()
    assert [k for k, *_ in rec.msgs] == ["stall"] and (clock["t"] - 1000) > 7200
    assert len(rec.msgs) == 1


def test_standby_gap_does_not_trigger_stall(tmp_path):
    m, rec, clock = mk(tmp_path)
    clock["t"] += 30; m.tick()
    clock["t"] += 6 * 3600; m.tick()                                         # PC war 6 h im Standby
    clock["t"] += 30; m.tick()
    assert rec.msgs == []


def test_state_persists_across_restart_and_recovers(tmp_path):
    m, rec, clock = mk(tmp_path)
    for _ in range(3):
        m.cycle_result(exception=True)
    rec2 = Rec()
    m2 = OUT.OutageMonitor(str(tmp_path / "o.json"), rec2, clock=lambda: clock["t"] + 50)
    m2.cycle_result(exception=True)
    assert rec2.msgs == []                                                   # Ausfall schon gemeldet
    m2.cycle_result(mon=GOOD)
    assert [k for k, *_ in rec2.msgs] == ["recovered"]


def test_send_failure_never_raises(tmp_path):
    def boom(*a):
        raise RuntimeError("telegram down")
    m = OUT.OutageMonitor(str(tmp_path / "o.json"), boom)
    for _ in range(3):
        m.cycle_result(exception=True)
    m.cycle_result(mon=GOOD)


def test_process_watch_reports_once_and_respects_grace(tmp_path):
    rt = tmp_path
    clock = {"t": 10000.0}
    rec = Rec()
    alive = {"v": False}
    w = OUT.ProcessWatch(str(rt), lambda: alive["v"], rec, clock=lambda: clock["t"], grace_seconds=600)
    # Karenzzeit: kurz nach Start keine Meldung
    for _ in range(5):
        clock["t"] += 100; w.poll()
    assert rec.msgs == []
    # danach: 3 Pruefungen im Abstand >= 180 s ohne Prozess -> genau EINE Meldung
    for _ in range(12):
        clock["t"] += 200; w.poll()
    assert [k for k, *_ in rec.msgs] == ["process_missing"]
    # laeuft der Prozess wieder, meldet der Lauf selbst "laeuft wieder" (Zustand active bleibt bis dahin)
    st = json.load(open(rt / "outage_state.json"))
    assert "process_missing" in st["active"]


def test_process_watch_ignores_fresh_monitor(tmp_path):
    clock = {"t": 1_800_000_000.0}
    end = datetime.fromtimestamp(clock["t"] - 60, U).isoformat()
    (tmp_path / "last_cycle_monitor.json").write_text(json.dumps({"end": end}))
    rec = Rec()
    w = OUT.ProcessWatch(str(tmp_path), lambda: False, rec, clock=lambda: clock["t"], grace_seconds=0)
    for _ in range(6):
        clock["t"] += 200; w.poll()
    assert rec.msgs == []


# ------------------------------------------------------------------ Zeitumstellung / Bericht (A3b/c)
def test_next_transitions_from_europe_berlin():
    m, a, b = SS.next_transition(dt(2026, 10, 16))
    assert m == dt(2026, 10, 25, 1) and (a, b) == (2.0, 1.0)
    m, a, b = SS.next_transition(dt(2026, 10, 26))
    assert m == dt(2027, 3, 28, 1) and (a, b) == (1.0, 2.0)


def test_close_hours_winter_and_summer():
    assert SS.close_hours_local(1) == [1, 5, 9, 13, 17, 21]
    assert SS.close_hours_local(2) == [2, 6, 10, 14, 18, 22]


def test_dst_reminders_times_and_text():
    evs = SS.dst_events(dt(2026, 10, 16))
    eve, day = evs
    assert eve["due_utc"] == dt(2026, 10, 24, 18)        # Sa 24.10. 20:00 MESZ
    assert day["due_utc"] == dt(2026, 10, 25, 7)         # So 25.10. 08:00 MEZ (nach Umstellung um 03:00 -> 02:00)
    assert "01, 05, 09, 13, 17, 21 Uhr" in eve["text"] and "UTC" in eve["text"]
    # Fruehjahr 2027: Vorabend 27.03. 20:00 MEZ, Tag 28.03. 08:00 MESZ
    evs = SS.dst_events(dt(2027, 3, 1))
    assert evs[0]["due_utc"] == dt(2027, 3, 27, 19) and evs[1]["due_utc"] == dt(2027, 3, 28, 6)
    assert "02, 06, 10, 14, 18, 22 Uhr" in evs[0]["text"]


def test_pending_sends_each_reminder_once_in_window():
    sent = {}
    assert SS.pending(dt(2026, 10, 24, 17, 59), sent) == []
    p = SS.pending(dt(2026, 10, 24, 18, 0, 5), sent)
    assert [x["id"] for x in p] == ["dst:2026-10-25:eve"]
    sent["dst:2026-10-25:eve"] = "x"
    assert SS.pending(dt(2026, 10, 24, 23, 0), sent) == []
    # PC war aus, geht am Morgen des Umstelltags an: Vorabend-Erinnerung verfallen, Tages-Erinnerung noch gueltig
    p = SS.pending(dt(2026, 10, 25, 9, 0), {})
    assert [x["id"] for x in p] == ["dst:2026-10-25:day"]
    assert SS.pending(dt(2026, 10, 25, 19, 0), {}) == []        # nach 20:00 des Tages nicht mehr nachholen


def test_biweekly_report_first_on_1_nov_2026_and_every_14_days():
    assert SS.pending(dt(2026, 11, 1, 18, 59), {}) == []
    p = SS.pending(dt(2026, 11, 1, 19, 0, 10), {})              # 20:00 MEZ = 19:00 UTC
    assert p == [{"kind": "report", "id": "report14:2026-11-01", "late": False}]
    assert SS.pending(dt(2026, 11, 8, 19, 5), {}) == []          # eine Woche spaeter: kein Bericht
    p = SS.pending(dt(2026, 11, 15, 19, 0, 10), {"report14:2026-11-01": "x"})
    assert [x["id"] for x in p] == ["report14:2026-11-15"]
    # 28.03.2028-Sommerzeit: sonntags 20:00 bleibt 20:00 lokale Zeit
    due, _, k = SS.report_due_dates(dt(2027, 4, 5))
    assert due.astimezone(SS.TZ).hour == 20 and due.astimezone(SS.TZ).weekday() == 6


def test_missed_report_is_caught_up_within_3_days_marked_late():
    p = SS.pending(dt(2026, 11, 2, 10), {})
    assert p and p[0]["late"] is True
    assert SS.pending(dt(2026, 11, 5, 10), {}) == []


# ------------------------------------------------------------------ Einstellungen (B1/B2)
def test_settings_defaults_and_rereading(tmp_path):
    p = str(tmp_path / "live_settings.json")
    s = live_settings.load(p)
    assert s["trade_pdf"]["enabled"] is True and s["prewarn"]["minutes_before"] == [30, 15]
    json.dump({"trade_pdf": {"enabled": False}, "prewarn": {"minutes_before": [20, 10], "night_quiet": {"from": "22:00"}}},
              open(p, "w"))
    s = live_settings.load(p)
    assert s["trade_pdf"]["enabled"] is False and s["trade_pdf"]["timeout_s"] == 90
    assert s["prewarn"]["minutes_before"] == [20, 10] and s["prewarn"]["night_quiet"]["from"] == "22:00"
    assert s["prewarn"]["night_quiet"]["to"] == "07:00"
    open(p, "w").write("{kaputt")
    assert live_settings.load(p)["trade_pdf"]["enabled"] is True            # kaputte Datei -> Standard
    json.dump({"trade_pdf": {"enabled": "ja", "timeout_s": "x"}}, open(p, "w"))
    assert live_settings.load(p)["trade_pdf"]["enabled"] is True
