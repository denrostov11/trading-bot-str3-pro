# -*- coding: utf-8 -*-
"""Zeitplan der Gruppe "STR3 System" (A3b/A3c): Erinnerung an die Zeitumstellung und Bericht alle 2 Wochen.
Reine Funktionen (Uhr und Zustand werden uebergeben) - alle Termine werden aus der Zeitzone Europe/Berlin
berechnet, nie fest eincodiert.

- Zeitumstellung: Erinnerung am Vorabend 20:00 und am Tag selbst 08:00 (Berliner Zeit). Naechste Umstellungen
  (nur zur Kontrolle): So 25.10.2026 (auf Winterzeit), So 28.03.2027 (auf Sommerzeit).
- Bericht: alle 2 Wochen sonntags 20:00 (Berliner Zeit), erstmals 01.11.2026.
Verpasste Termine (PC war aus) werden innerhalb eines Zeitfensters nachgeholt, sonst uebersprungen.
"""
from datetime import datetime, timedelta, timezone, date, time as dtime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
UTC = timezone.utc
FIRST_REPORT_DATE = date(2026, 11, 1)
REPORT_EVERY_DAYS = 14
REPORT_HOUR = 20
REPORT_LATE_WINDOW = timedelta(days=3)


def _utc(dt):
    return dt.replace(tzinfo=UTC) if dt.tzinfo is None else dt.astimezone(UTC)


def next_transition(after_utc, horizon_days=800):
    """Naechste Zeitumstellung nach `after_utc`: -> (moment_utc, offset_vorher_h, offset_nachher_h) oder None."""
    t = _utc(after_utc).replace(minute=0, second=0, microsecond=0)
    prev = t.astimezone(TZ).utcoffset()
    for _ in range(horizon_days * 24):
        t += timedelta(hours=1)
        cur = t.astimezone(TZ).utcoffset()
        if cur != prev:
            return t, prev.total_seconds() / 3600, cur.total_seconds() / 3600
        prev = cur
    return None


def close_hours_local(offset_hours):
    """Schlusszeiten der 4h-Kerzen (00/04/08/12/16/20 UTC) in deutscher Zeit bei gegebenem UTC-Offset."""
    return [int((h + offset_hours) % 24) for h in (0, 4, 8, 12, 16, 20)]


def _fmt_hours(hs):
    return ", ".join(f"{h:02d}" for h in sorted(hs)) + " Uhr"


def dst_events(now_utc):
    """Erinnerungen fuer die NAECHSTE Umstellung (und ggf. gerade laufende): Liste von dicts
    {id, due_utc, valid_until_utc, text}. due = Zeitpunkt des Versands, valid_until = bis wann nachgeholt wird."""
    now = _utc(now_utc)
    tr = next_transition(now - timedelta(days=2))
    if tr is None:
        return []
    moment, off_before, off_after = tr
    local = moment.astimezone(TZ)
    day = local.date()
    to_winter = off_after < off_before
    hrs = close_hours_local(off_after)
    new_name = "Winterzeit (MEZ)" if to_winter else "Sommerzeit (MESZ)"
    body = (f"Zeitumstellung auf {new_name} am {day.strftime('%d.%m.%Y')}. Die 4h-Kerzen schließen danach "
            f"um {_fmt_hours(hrs)} deutscher Zeit (bisher {_fmt_hours(close_hours_local(off_before))}). "
            f"Der Bot rechnet intern in UTC und läuft unverändert weiter – es ist nichts zu tun.")
    eve = datetime.combine(day - timedelta(days=1), dtime(20, 0), tzinfo=TZ)
    morn = datetime.combine(day, dtime(8, 0), tzinfo=TZ)
    end_of_day = datetime.combine(day, dtime(20, 0), tzinfo=TZ)
    return [
        {"id": f"dst:{day.isoformat()}:eve", "due_utc": eve.astimezone(UTC), "valid_until_utc": morn.astimezone(UTC),
         "text": "Erinnerung (Vorabend): " + body, "title": "Zeitumstellung morgen"},
        {"id": f"dst:{day.isoformat()}:day", "due_utc": morn.astimezone(UTC), "valid_until_utc": end_of_day.astimezone(UTC),
         "text": "Erinnerung (heute): " + body, "title": "Zeitumstellung heute"},
    ]


def report_due_dates(now_utc):
    """Faellige/letzte Berichtstermine (UTC) um `now` herum: der juengste Termin <= now und der naechste."""
    now = _utc(now_utc)
    d0 = FIRST_REPORT_DATE
    due = lambda k: datetime.combine(d0 + timedelta(days=REPORT_EVERY_DAYS * k), dtime(REPORT_HOUR, 0), tzinfo=TZ).astimezone(UTC)
    if now < due(0):
        return None, due(0), 0
    k = 0
    while due(k + 1) <= now:
        k += 1
    return due(k), due(k + 1), k


def report_id(k):
    return f"report14:{(FIRST_REPORT_DATE + timedelta(days=REPORT_EVERY_DAYS * k)).isoformat()}"


def pending(now_utc, sent):
    """Alles, was JETZT gesendet werden soll: Liste von dicts {kind: 'text'|'report', id, text|None}.
    sent = dict id -> iso-Zeit (bereits erledigt)."""
    now = _utc(now_utc)
    out = []
    for ev in dst_events(now):
        if ev["id"] in sent:
            continue
        if ev["due_utc"] <= now < ev["valid_until_utc"]:
            out.append({"kind": "text", "id": ev["id"], "text": ev["text"], "title": ev["title"]})
    last, nxt, k = report_due_dates(now)
    if last is not None:
        rid = report_id(k)
        if rid not in sent and now - last < REPORT_LATE_WINDOW:
            out.append({"kind": "report", "id": rid, "late": (now - last) > timedelta(hours=2)})
    return out
