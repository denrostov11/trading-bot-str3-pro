# -*- coding: utf-8 -*-
"""Berichtszeitraeume & -terminierung (deterministisch, DST-sicher, Einmal-Versand).

Regeln (Spec):
- Wochenbericht = letzte 7 VOLLE Kalendertage. Rollierend-30 = letzte 30 VOLLE Kalendertage
  (NIE als Kalendermonat bezeichnen). Optionaler echter Kalendermonatsbericht getrennt.
- Zeitraeume in REPORT_TIMEZONE (z. B. Europe/Berlin) bestimmen, als eindeutige UTC-Zeitpunkte speichern.
- Ein Bericht darf fuer (report_type, period, strategy_version) NICHT doppelt gesendet werden.
- Sommerzeitwechsel darf nicht zu doppelten/fehlenden Berichten fuehren -> Eindeutigkeit ueber die
  Kalender-Periode (Datumsgrenzen), nicht ueber UTC-Offsets.
"""
import json, os, hashlib
from datetime import datetime, timedelta, time, timezone
from zoneinfo import ZoneInfo

from .messages import WEEKLY_REPORT, ROLLING_30D_REPORT, CALENDAR_MONTH_REPORT


def last_full_calendar_days(now_utc, n, tzname):
    """(period_start_utc, period_end_utc, start_date_local, end_date_local_inklusiv).
    Deckt die n vollen Kalendertage VOR dem heutigen (lokalen) Tag ab."""
    tz = ZoneInfo(tzname)
    local_now = now_utc.astimezone(tz)
    end_local = datetime.combine(local_now.date(), time(0, 0), tzinfo=tz)   # heute 00:00 lokal (exklusiv)
    start_local = end_local - timedelta(days=n)
    return (start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc),
            start_local.date(), (end_local - timedelta(days=1)).date())


def last_full_calendar_month(now_utc, tzname):
    tz = ZoneInfo(tzname)
    local_now = now_utc.astimezone(tz)
    first_this = datetime.combine(local_now.date().replace(day=1), time(0, 0), tzinfo=tz)
    end_local = first_this
    prev_last = (first_this - timedelta(days=1)).date()
    start_local = datetime.combine(prev_last.replace(day=1), time(0, 0), tzinfo=tz)
    return (start_local.astimezone(timezone.utc), end_local.astimezone(timezone.utc),
            start_local.date(), prev_last)


def period_for(report_type, now_utc, tzname):
    if report_type == WEEKLY_REPORT:
        return last_full_calendar_days(now_utc, 7, tzname)
    if report_type == ROLLING_30D_REPORT:
        return last_full_calendar_days(now_utc, 30, tzname)
    if report_type == CALENDAR_MONTH_REPORT:
        return last_full_calendar_month(now_utc, tzname)
    raise ValueError(f"Kein Berichtszeitraum fuer {report_type}")


def period_label(report_type, start_date, end_date):
    """Menschlesbares Label. Rollierend-30 wird NIE als Kalendermonat bezeichnet."""
    if report_type == WEEKLY_REPORT:
        return f"Woche (letzte 7 volle Kalendertage: {start_date} bis {end_date})"
    if report_type == ROLLING_30D_REPORT:
        return f"Rollierende 30 Tage (letzte 30 volle Kalendertage: {start_date} bis {end_date})"
    if report_type == CALENDAR_MONTH_REPORT:
        return f"Kalendermonat ({start_date} bis {end_date})"
    return report_type


def make_report_key(scope, report_type, start_date, end_date, strategy_version):
    raw = f"{scope}|{report_type}|{start_date}|{end_date}|{strategy_version}"
    return "R" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:15]


class ReportRegistry:
    """Verhindert Doppelversand je (scope, report_type, period, strategy_version) und haelt
    Zustellnachweise (report_id, file_hash, generated_at, sent_at, delivery_status)."""
    def __init__(self, path):
        self.path = path
        self.records = {}     # report_key -> dict
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.records = json.load(f)

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.records, f, indent=1)
        os.replace(tmp, self.path)

    def already_sent(self, report_key):
        rec = self.records.get(report_key)
        return bool(rec and rec.get("delivery_status") == "SENT")

    def record(self, report_key, **fields):
        rec = self.records.get(report_key, {"report_id": report_key})
        rec.update(fields)
        self.records[report_key] = rec
        self._save()
        return rec
