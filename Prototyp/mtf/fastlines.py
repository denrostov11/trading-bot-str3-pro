# -*- coding: utf-8 -*-
"""Schnelle, BEGRENZTE Variante von scan_100.find_lines (gleiche Semantik, gleiche Konstanten, gleiche Ergebnisse).

Warum: scan_100.find_lines prueft jedes Pivot-Paar mit einer Python-Schleife ueber alle Kerzen (O(P^2 * n)). Bei flachen oder
illiquiden Daten gibt es extrem viele (gleiche) Pivots -> Minuten statt Sekunden. Hier:
  * Die Kerzen-Schleife je Paar ist mit numpy vektorisiert (Bruch = erste Kerze mit Schluss jenseits der Linie, Tap-Kandidaten
    = Maske; nur die Kandidaten laufen durch die Abstandslogik). Ergebnis identisch zu scan_100 (Test vergleicht beide).
  * HARTE OBERGRENZEN: hoechstens MAX_PIVOTS (juengste) Pivots je Seite -> hoechstens ~MAX_PIVOTS^2/2 Paare; hoechstens MAX_CANDIDATES
    Linien (nach Score) gehen in die Duplikat-Bereinigung; zusaetzlich ein Zeitbudget (Deadline). Wird es ueberschritten, bricht die
    Suche mit MtfTimeout ab - der Aufrufer macht daraus "keine Linienaussage" (nichts wird erfunden, keine Teilergebnisse).
Die Obergrenzen liegen weit ueber dem Normalfall (Praxis: 30-80 Pivots je Seite); bei Normaldaten aendert sich nichts.

WICHTIG (Datenintegritaet): Alle Funktionen hier bekommen die zeitrahmen-skalierten Parameter (params.TFParams) ALS ARGUMENT und
lesen aus scan_100 nur Konstanten, die fuer alle Zeitrahmen gleich bleiben (Tap-/Bruch-Toleranz, max. Winkel, Min-Taps). Es werden
KEINE Modul-Konstanten von scan_100 veraendert - der parallel laufende Engine-Code (auch im selben Prozess/Thread-Pool) sieht
niemals andere Werte. (params.scan_params existiert weiter, wird aber nur noch in Tests als Referenz benutzt.)
"""
import math
import pandas as pd
import numpy as np

from . import params as PR
from .budget import MtfTimeout

MAX_PIVOTS = 110          # juengste Pivots je Seite
MAX_CANDIDATES = 800      # Linien (nach Score) fuer die Duplikat-Bereinigung


def _walk(kind, i0, p0, i1, p1, price, close, tol_tap, tol_brk, n, spacing):
    """Tap-/Bruchzaehlung einer Linie ab i0 - Ergebnis identisch zur Schleife in scan_100.find_lines."""
    idx = np.arange(i0, n)
    lv = p0 + (p1 - p0) * (idx - i0) / (i1 - i0)
    c, tb = close[i0:], tol_brk[i0:]
    if kind == "support":
        br = c < lv - tb
    else:
        br = c > lv + tb
    first = int(br.argmax()) if br.any() else -1
    breaking = i0 + first if first >= 0 else -1
    lim = first if first >= 0 else len(idx)
    pr, tt = price[i0:], tol_tap[i0:]
    if kind == "support":
        hit = pr[:lim] <= lv[:lim] + tt[:lim]
    else:
        hit = pr[:lim] >= lv[:lim] - tt[:lim]
    taps = []
    for j in np.flatnonzero(hit):
        i = i0 + int(j)
        if not taps or i - taps[-1] >= spacing:
            taps.append(i)
        elif (price[i] < price[taps[-1]]) if kind == "support" else (price[i] > price[taps[-1]]):
            taps[-1] = i
    return taps, breaking


def find_lines_fast(df, kind, a, piv, P, deadline=None, max_pivots=None, max_candidates=None):
    """Wie scan_100.find_lines(df, kind, a, piv), aber vektorisiert und begrenzt; P = params.scaled(tf) (kein Patchen von scan_100).
    Rueckgabe: (Linien, info) mit info = {pivots, pivots_used, pairs, truncated}."""
    s = PR._s100()
    max_pivots = MAX_PIVOTS if max_pivots is None else max_pivots
    max_candidates = MAX_CANDIDATES if max_candidates is None else max_candidates
    pts_all = piv[0] if kind == "support" else piv[1]
    pts = list(pts_all[-max_pivots:]) if len(pts_all) > max_pivots else list(pts_all)
    price = (df.Low if kind == "support" else df.High).values.astype(float)
    close = df.Close.values.astype(float)
    av = a.values.astype(float)
    tol_tap, tol_brk = s.TAP_TOL_ATR * av, s.BREACH_TOL_ATR * av
    n = len(df)
    out, pairs = [], 0
    for ai in range(len(pts)):
        if deadline is not None and deadline.expired():
            raise MtfTimeout("Linien-Suche: Zeitbudget überschritten")
        for bi in range(ai + 1, len(pts)):
            i0, i1 = pts[ai], pts[bi]
            if i1 - i0 < P.min_spacing:
                continue
            p0, p1 = float(price[i0]), float(price[i1])
            ref = float(np.median(close[max(0, i0):i1 + 1]))
            if ref <= 0:
                continue
            ln = s.Line(kind, i0, p0, i1, p1)
            ln.angle_deg = norm_angle((p1 - p0) / (i1 - i0), ref, P)
            if ln.angle_deg > s.MAX_ANGLE_DEG:
                continue
            pairs += 1
            taps, breaking = _walk(kind, i0, p0, i1, p1, price, close, tol_tap, tol_brk, n, P.min_spacing)
            ln.taps, ln.breaking_bar = taps, breaking
            end = breaking if breaking > 0 else n - 1
            ln.duration = end - i0
            if len(taps) < s.MIN_TAPS_SAFETY or ln.duration < P.min_duration:
                continue
            ln.score = len(taps) * 100 + ln.duration * 0.1 - ln.angle_deg * 0.5
            out.append(ln)
    out.sort(key=lambda l: -l.score)
    truncated = len(pts_all) > len(pts)
    if len(out) > max_candidates:
        out, truncated = out[:max_candidates], True
    kept, kept_sets = [], []
    for ln in out:
        st = set(ln.taps)
        if any(len(st & k2) >= max(2, min(len(st), len(k2)) - 1) for k2 in kept_sets):
            continue
        kept.append(ln)
        kept_sets.append(st)
    return kept, {"pivots": len(pts_all), "pivots_used": len(pts), "pairs": pairs, "truncated": truncated}


# ------------------------------------------------------------------ parametrisierte Kopien der scan_100-Hilfsfunktionen
def norm_angle(slope_per_bar, price_ref, P):
    """scan_100.norm_angle mit der zeitrahmen-skalierten Winkel-Normierung (P.angle_bars statt THREE_MONTH_BARS)."""
    return math.degrees(math.atan(abs(slope_per_bar * P.angle_bars / (0.25 * price_ref))))


def is_aplus(ln, P):
    """scan_100.is_aplus mit P.min_duration."""
    s = PR._s100()
    return len(ln.taps) >= s.MIN_TAPS and ln.duration >= P.min_duration and ln.angle_deg < s.MAX_ANGLE_DEG


def converges(action, safety, ref_i, max_apex):
    """scan_100.converges (Keil-Regel) mit P.max_apex."""
    sa = (action.p1 - action.p0) / (action.i1 - action.i0)
    ss = (safety.p1 - safety.p0) / (safety.i1 - safety.i0)
    gap = safety.value_at(ref_i) - action.value_at(ref_i)
    closing = (sa - ss) if gap > 0 else (ss - sa)
    if closing <= 0:
        return False
    return abs(gap) / closing <= max_apex


def pick_safety(action, opp_lines, df, a, P):
    """scan_100.pick_safety mit P.max_apex und P.safety_age_months (gleiche Auswahl: naechstgelegene intakte, konvergente
    Gegenlinie mit >= 2 Taps, aeltester Tap nicht aelter als das Safety-Tap-Alter, juengster Tap moeglichst frisch)."""
    s = PR._s100()
    n = len(df)
    ref_i = n - 1
    av = action.value_at(ref_i)
    times = pd.to_datetime(df["Time"]) if "Time" in getattr(df, "columns", []) else None
    tap_cutoff = (times.iloc[ref_i] - pd.DateOffset(months=P.safety_age_months)) if times is not None else None
    best, best_d = None, None
    for ln in opp_lines:
        if len(ln.taps) < s.MIN_TAPS_SAFETY:
            continue
        if tap_cutoff is not None and times.iloc[ln.taps[0]] < tap_cutoff:
            continue
        if ln.breaking_bar > 0:
            continue
        sv = ln.value_at(ref_i)
        if action.kind == "support" and sv <= av:
            continue
        if action.kind == "resistance" and sv >= av:
            continue
        if not converges(action, ln, ref_i, P.max_apex):
            continue
        d = abs(sv - av) / max(a.iloc[ref_i], 1e-9)
        recency = n - 1 - ln.taps[-1]
        key = d + recency * 0.02
        if best is None or key < best_d:
            best, best_d = ln, key
    return best
