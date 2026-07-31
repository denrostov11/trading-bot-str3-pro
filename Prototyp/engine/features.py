# -*- coding: utf-8 -*-
"""Indikator-/Feature-Berechnung fuer die Varianten-Filter (reine Funktionen, testbar).

Diese Funktionen berechnen NUR Zusatz-Features auf bereits erkannten Snapshots/Kerzen. Sie
veraendern NIE die Trendlinie, Safety-Line, Pivots oder S/R-Zone des gemeinsamen Snapshots.
"""
import math


def ema(values, period):
    """Exponentieller gleitender Durchschnitt; gibt letzten Wert (oder None bei zu wenig Daten)."""
    vals = [float(v) for v in values if v is not None]
    if len(vals) < period:
        return None
    k = 2.0 / (period + 1)
    e = sum(vals[:period]) / period          # Seed = SMA der ersten period Werte
    for v in vals[period:]:
        e = v * k + e * (1 - k)
    return e


def rvol(volumes, window=20):
    """Relatives Volumen der letzten Kerze ggü. Median der vorherigen `window` Kerzen."""
    v = [float(x) for x in volumes if x is not None]
    if len(v) < window + 1:
        return None
    last = v[-1]
    ref = sorted(v[-window - 1:-1])
    med = ref[len(ref) // 2] if len(ref) % 2 else (ref[len(ref) // 2 - 1] + ref[len(ref) // 2]) / 2
    if med <= 0:
        return None
    return last / med


def percentile_rank(series, value=None, window=100):
    """Perzentil-Rang (0..100) des letzten (oder gegebenen) Werts innerhalb der letzten `window`."""
    s = [float(x) for x in series if x is not None]
    if len(s) < 5:
        return None
    ref = s[-window:]
    val = s[-1] if value is None else float(value)
    below = sum(1 for x in ref if x < val)
    return 100.0 * below / len(ref)


def breakout_metrics(o, h, l, c, atr_val):
    """Kennzahlen der Bruchkerze: Body/Range, Position des Close, Range in ATR."""
    rng = h - l
    if rng <= 0:
        return {"body_ratio": 0.0, "close_pos": 0.5, "range_atr": 0.0}
    body_ratio = abs(c - o) / rng
    close_pos = (c - l) / rng            # 1.0 = Schluss am Hoch, 0.0 = am Tief
    range_atr = rng / atr_val if atr_val else 0.0
    return {"body_ratio": round(body_ratio, 4), "close_pos": round(close_pos, 4),
            "range_atr": round(range_atr, 4)}


def linreg_r2(closes):
    """R^2 einer linearen Regression ueber die Schlusskurse (Trendqualitaet, Pro.7 diagnostisch)."""
    y = [float(v) for v in closes if v is not None]
    n = len(y)
    if n < 3:
        return None
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(y) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    syy = sum((v - my) ** 2 for v in y)
    sxy = sum((xs[i] - mx) * (y[i] - my) for i in range(n))
    if sxx <= 0 or syy <= 0:
        return 0.0
    r = sxy / math.sqrt(sxx * syy)
    return round(r * r, 4)


def _tr(highs, lows, closes):
    tr = [highs[0] - lows[0]]
    for i in range(1, len(highs)):
        tr.append(max(highs[i] - lows[i], abs(highs[i] - closes[i - 1]), abs(lows[i] - closes[i - 1])))
    return tr


def adx(highs, lows, closes, period=14):
    """ADX(14) - Trendstaerke (Pro.7 diagnostisch)."""
    n = len(highs)
    if n < 2 * period + 1:
        return None
    plus_dm, minus_dm = [], []
    for i in range(1, n):
        up = highs[i] - highs[i - 1]
        dn = lows[i - 1] - lows[i]
        plus_dm.append(up if (up > dn and up > 0) else 0.0)
        minus_dm.append(dn if (dn > up and dn > 0) else 0.0)
    tr = _tr(highs, lows, closes)[1:]

    def smooth(x):
        s = sum(x[:period])
        out = [s]
        for v in x[period:]:
            s = s - s / period + v
            out.append(s)
        return out
    atr_s = smooth(tr)
    pdm_s = smooth(plus_dm)
    mdm_s = smooth(minus_dm)
    dx = []
    for i in range(len(atr_s)):
        if atr_s[i] == 0:
            dx.append(0.0); continue
        pdi = 100 * pdm_s[i] / atr_s[i]
        mdi = 100 * mdm_s[i] / atr_s[i]
        dx.append(100 * abs(pdi - mdi) / (pdi + mdi) if (pdi + mdi) else 0.0)
    if len(dx) < period:
        return round(sum(dx) / len(dx), 2) if dx else None
    return round(sum(dx[-period:]) / period, 2)


def choppiness(highs, lows, closes, period=14):
    """Choppiness Index(14) - Seitwaerts vs. Trend (Pro.7 diagnostisch)."""
    if len(highs) < period + 1:
        return None
    tr = _tr(highs, lows, closes)[-period:]
    atr_sum = sum(tr)
    hi = max(highs[-period:])
    lo = min(lows[-period:])
    rng = hi - lo
    if rng <= 0 or atr_sum <= 0:
        return None
    return round(100 * math.log10(atr_sum / rng) / math.log10(period), 2)
