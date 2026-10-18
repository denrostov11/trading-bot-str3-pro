# -*- coding: utf-8 -*-
"""Gebuchter (theoretischer) Einstieg = Open der ersten 4h-Kerze NACH der Signalkerze.

Der Wert ist schon unmittelbar nach dem 4h-Schluss bekannt (Open der gerade beginnenden Kerze, erste
1h-Kerze der neuen 4h-Kerze). Er ist identisch mit dem Wert, den der Tracker spaeter aus der dann
abgeschlossenen Folgekerze nimmt - hier wird nur frueher gebucht (fuer die Meldung). Die 4h-Aggregation
bleibt unveraendert (gleicher Anker/Session); es wird dieselbe Funktion benutzt.
"""
import pandas as pd

from . import aggregate_4h


def _utc(ts):
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def book_entry(cache, symbol, signal_time_iso, anchor_hour=0, session_hours=None, now=None, df1h=None):
    """-> {"price", "time", "partial"} oder None ('wartet auf Einstieg': Folgekerze noch nicht eroeffnet,
    z. B. Markt geschlossen)."""
    d = df1h if df1h is not None else (cache.load(symbol, "1h") if cache is not None else None)
    if d is None or len(d) == 0:
        return None
    agg = aggregate_4h.aggregate(d, anchor_hour=anchor_hour, session_hours=session_hours, data_cutoff=now)
    if agg.empty:
        return None
    sig = pd.Timestamp(signal_time_iso)
    sig = sig.tz_localize("UTC") if sig.tzinfo is None else sig.tz_convert("UTC")
    after = agg[pd.to_datetime(agg["Time"], utc=True) > sig]
    if after.empty:
        return None
    row = after.iloc[0]
    start = _utc(row["Time"])
    end = _utc(row["end_utc"])
    g = d[(pd.to_datetime(d["Time"], utc=True) >= start) & (pd.to_datetime(d["Time"], utc=True) < end)]
    first_bar = _utc(g["Time"].min()) if len(g) else None
    nowt = _utc(now) if now is not None else _utc(pd.Timestamp.now(tz="UTC"))
    return {"price": float(row["Open"]), "time": start.isoformat(), "partial": not bool(row["is_final"]),
            # running = Kerze laeuft gerade (Ende noch nicht erreicht); opened_at_start = die erste 1h-Kerze liegt auf dem
            # Kerzenbeginn (voller Block, kein verkuerzter Sessionblock) -> der Open ist fuer einen Ausstieg verlaesslich
            "running": bool(end > nowt), "opened_at_start": bool(first_bar is not None and first_bar == start)}
