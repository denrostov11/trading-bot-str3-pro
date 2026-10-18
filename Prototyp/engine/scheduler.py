# -*- coding: utf-8 -*-
"""Zyklus-Zeitplan (A5): ein vollstaendiger Zyklus 1-2 Minuten nach JEDEM 4h-Schluss (00/04/08/12/16/20 UTC),
dazwischen stuendlich die Trade-Verfolgung. Reine Funktionen (Uhr injizierbar) - testbar ohne Warten.

Das Aufholen nach einem Ausfall bleibt erhalten: War seit dem letzten vollen Zyklus ein 4h-Schluss, laeuft
sofort ein voller Zyklus (Kerzen-fuer-Kerze-Replay in orchestrate.analyze_instrument_history).
"""
from datetime import datetime, timedelta, timezone

FULL = "full"
TRACK = "track"
PREWARN = "prewarn"            # Kind "prewarn:<Minuten vor Schluss>"
PREWARN_GRACE_MIN = 5          # so lange nach dem Soll-Zeitpunkt wird eine Vorwarnung noch nachgeholt
DEFAULT_CLOSE_DELAY_S = 90
TRACK_MINUTE = 5
# Nachpruefungen nach dem 4h-Schluss (Sekunden nach dem Schluss): Yahoo liefert die letzte 1h-Kerze bei manchen
# Instrumenten (Futures/Aktien ~15 min Verzoegerung) erst spaeter. Billig: bei bereits bewerteten Kerzen entfaellt die
# Erkennung, es werden nur kurze Kursausschnitte nachgeladen.
RETRY_OFFSETS_S = (360, 960)


def _utc(dt):
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def floor4h(dt):
    dt = _utc(dt)
    return dt.replace(hour=dt.hour - dt.hour % 4, minute=0, second=0, microsecond=0)


def next_run(now, last_full_boundary=None, close_delay_s=DEFAULT_CLOSE_DELAY_S, passes=1,
             prewarn_minutes=(), prewarn_done=()):
    """-> (zeitpunkt_utc, art). last_full_boundary = 4h-Schluss (UTC), fuer den zuletzt ein voller Zyklus lief.
    - Ist ein 4h-Schluss verstrichen, fuer den noch kein voller Zyklus lief und die Verzoegerung abgelaufen
      ist -> sofort ("full").
    - passes = Anzahl voller Durchgaenge fuer den letzten 4h-Schluss (Nachpruefungen bei +6/+16 min).
    - Sonst der naechste Zeitpunkt aus: 4h-Schluss + Verzoegerung (full) bzw. volle Stunde + 5 min (track)."""
    now = _utc(now)
    lfb = _utc(last_full_boundary) if last_full_boundary is not None else None
    b = floor4h(now)
    pw = []                                                                 # Vorwarnungen (B1) vor dem naechsten Schluss
    for m in sorted({int(x) for x in prewarn_minutes}, reverse=True):
        if m in set(prewarn_done):
            continue
        t = b + timedelta(hours=4) - timedelta(minutes=m)
        if now < t:
            pw.append((t, f"{PREWARN}:{m}"))
        elif now < t + timedelta(minutes=PREWARN_GRACE_MIN):
            return now, f"{PREWARN}:{m}"                                    # knapp verpasst -> sofort
    due_full = b + timedelta(seconds=close_delay_s)
    if (lfb is None or lfb < b) and now >= due_full:
        return now, FULL
    cands = list(pw)
    if lfb is not None and lfb == b and 1 <= passes <= len(RETRY_OFFSETS_S):
        r = b + timedelta(seconds=RETRY_OFFSETS_S[passes - 1])
        if now >= r:
            if now - r < timedelta(minutes=30):
                return now, FULL                                        # Nachpruefung knapp verpasst -> sofort
        else:
            cands.append((r, FULL))
    if lfb is None or lfb < b:
        cands.append((due_full, FULL))                                  # Schluss steht dicht bevor/gerade war
    cands.append((b + timedelta(hours=4, seconds=close_delay_s), FULL))
    h = now.replace(minute=TRACK_MINUTE, second=0, microsecond=0)
    if h <= now:
        h += timedelta(hours=1)
    while h.hour % 4 == 0 and h.minute == TRACK_MINUTE:                 # Schlussstunde deckt der volle Zyklus ab
        h += timedelta(hours=1)
    cands.append((h, TRACK))
    return min(cands, key=lambda x: x[0])
