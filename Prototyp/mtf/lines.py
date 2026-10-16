# -*- coding: utf-8 -*-
"""Linienerkennung je Zeitrahmen - nutzt die KANONISCHEN scan_100-Funktionen (pivots, find_lines, is_aplus,
pick_safety, atr) mit den je Zeitrahmen skalierten Parametern aus params.py. Kein Engine-Code wird veraendert.

Kontextlinien (Monat/Woche/Tag/1h; es gibt dort kein Signal):
  1. Kandidaten = intakte Linien (kein Schlusskurs-Bruch), Action-Kriterien A+ (>= 3 Taps, Dauer, Winkel < 45 Grad).
  2. Gewaehlt wird die dem aktuellen Schlusskurs naechste (Abstand in ATR).
  3. Rueckfall nach Tori: gibt es keine A+-Linie, genuegen 2 Beruehrungspunkte; dann gilt Punkt B = das JUENGSTE
     unberuehrte Hoch/Tief (groesstes i1), erst danach Naehe zum Kurs.
  4. Safety = pick_safety(...) (intakt, konvergent, Keil/Apex, Tap-Alter, richtige Seite).
  5. Bias (rein informativ) = Trendrichtung der Hauptlinie (Steigung): steigende Linie -> Aufwaertstrend, fallende ->
     Abwaertstrend (Unterstuetzung ODER Widerstand, solange sie intakt ist); nahezu waagerecht (< 3 Grad) -> seitwaerts, keine Aussage.
Gibt es keine gueltige Linie: Ergebnis ohne Linie - es wird NICHTS erfunden.
"""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from . import params as PR


@dataclass
class Ctx:
    tf: str
    df: pd.DataFrame = None            # Analysefenster (abgeschlossene Kerzen, index 0..n-1)
    atr: pd.Series = None
    action: object = None              # scan_100.Line
    safety: object = None
    kind: str = ""                     # "A+" | "2-Punkt (Tori)" | ""
    bias: str = ""                     # "up" | "down" | ""
    reason: str = ""                   # Begruendung, wenn keine Linie
    params: object = None
    extra: dict = field(default_factory=dict)


FLAT_ANGLE_DEG = 3.0


def line_bias(line):
    """'up' | 'down' | 'flat' aus der Steigung der Linie (normierter Winkel < 3 Grad = flach)."""
    if line.angle_deg < FLAT_ANGLE_DEG:
        return "flat"
    return "up" if (line.p1 - line.p0) / (line.i1 - line.i0) > 0 else "down"


def detect_context(df_closed, tf):
    """Kontextlinien fuer einen Zeitrahmen aus ABGESCHLOSSENEN Kerzen (df_closed mit Time/Open/High/Low/Close)."""
    P = PR.scaled(tf)
    ctx = Ctx(tf=tf, params=P)
    if df_closed is None or len(df_closed) < P.min_bars:
        ctx.reason = f"zu wenig Historie ({0 if df_closed is None else len(df_closed)} Kerzen, nötig {P.min_bars})"
        return ctx
    work = df_closed.tail(P.window).reset_index(drop=True)
    ctx.df = work
    s100 = PR._s100()
    with PR.scan_params(tf):
        a = s100.atr(work)
        ctx.atr = a
        piv = s100.pivots(work, k=P.k)
        sup = s100.find_lines(work, "support", a, piv)
        res = s100.find_lines(work, "resistance", a, piv)
        n = len(work)
        last = float(work["Close"].iloc[-1])
        atr_last = max(float(a.iloc[-1]), 1e-12)
        intact = [l for l in sup + res if l.breaking_bar < 0]
        # Seite pruefen: Unterstuetzung muss unter, Widerstand ueber dem Kurs liegen
        ok = []
        for l in intact:
            v = l.value_at(n - 1)
            if (l.kind == "support" and v <= last) or (l.kind == "resistance" and v >= last):
                ok.append(l)
        dist = lambda l: abs(l.value_at(n - 1) - last) / atr_last
        aplus = [l for l in ok if s100.is_aplus(l)]
        if aplus:
            ctx.action, ctx.kind = min(aplus, key=lambda l: (dist(l), -l.score)), "A+"
        elif ok:
            ctx.action, ctx.kind = max(ok, key=lambda l: (l.i1, -dist(l))), "2-Punkt (Tori)"
        if ctx.action is None:
            ctx.reason = "keine gültige Linie nach unseren Regeln"
            return ctx
        opp = res if ctx.action.kind == "support" else sup
        ctx.safety = s100.pick_safety(ctx.action, opp, work, a)
        ctx.bias = line_bias(ctx.action)
        ctx.extra["dist_atr"] = round(dist(ctx.action), 2)
    return ctx


# ------------------------------------------------------------------ Linien des Trades (4h, aus dem Snapshot)
def calibrate_shift(anchor_safety, stop0, k):
    """Index-Kalibrierung: baseline_stop = Safety(bb+4) -> damaliger Index der Bruchkerze. 0, wenn = k."""
    i0, p0, i1, p1 = anchor_safety[:4]
    if p1 == p0:
        return 0
    bb = i0 + (stop0 - p0) * (i1 - i0) / (p1 - p0) - 4
    return 0 if abs(bb - k) < 0.4 else int(round(k - bb))


def _locate(df, idx, price, col, tol=40):
    """Index der Kerze, deren Tief/Hoch dem Pivot-Preis entspricht (robust gegen spaeter aufgefuellte Historie)."""
    lo, hi = max(0, idx - tol), min(len(df) - 1, idx + tol)
    vals = df[col].values[lo:hi + 1]
    j = int(np.argmin(np.abs(vals - price)))
    return lo + j if abs(vals[j] - price) <= 1e-6 * max(abs(price), 1.0) else None


def walk_taps(line, df, atr):
    """Tap-/Bruch-Zaehlung exakt wie scan_100.find_lines (Kopie der Schleife, gleiche Konstanten)."""
    s100 = PR._s100()
    close = df["Close"].values
    price = df["Low"].values if line.kind == "support" else df["High"].values
    n = len(df)
    taps, breaking = [], -1
    for i in range(line.i0, n):
        lv = line.value_at(i)
        tol_tap = s100.TAP_TOL_ATR * atr.iloc[i]
        tol_brk = s100.BREACH_TOL_ATR * atr.iloc[i]
        if line.kind == "support":
            if close[i] < lv - tol_brk:
                breaking = i; break
            if price[i] <= lv + tol_tap:
                if not taps or i - taps[-1] >= s100.MIN_SPACING:
                    taps.append(i)
                elif price[i] < price[taps[-1]]:
                    taps[-1] = i
        else:
            if close[i] > lv + tol_brk:
                breaking = i; break
            if price[i] >= lv - tol_tap:
                if not taps or i - taps[-1] >= s100.MIN_SPACING:
                    taps.append(i)
                elif price[i] > price[taps[-1]]:
                    taps[-1] = i
    line.taps, line.breaking_bar = taps, breaking
    return line


def rebuild_trade_lines(df4h, snapshot, stop0, k):
    """Action-/Safety-Linie des Trades im aktuellen Index der 4h-Reihe (df4h bis zur Signalkerze k).
    Rueckgabe: (action, safety, info). info enthaelt shift, ob Pivots zu den Kerzen passen und Tap-Zahlen."""
    s100 = PR._s100()
    work = df4h.iloc[:k + 1].reset_index(drop=True)
    a = s100.atr(work)
    shift = calibrate_shift(snapshot["safety_anchor"], stop0, k)
    out, info = [], {"shift": shift, "atr_last": float(a.iloc[-1])}
    for name in ("action_anchor", "safety_anchor"):
        i0, p0, i1, p1, kind, ntaps, ang = snapshot[name]
        col = "Low" if kind == "support" else "High"
        # Geometrie wie im Snapshot (Anker-Indizes + Kalibrier-Shift -> Linie stimmt mit baseline_stop ueberein)
        j0, j1 = i0 + shift, i1 + shift
        info[name + "_matched"] = (0 <= j0 < len(work) and 0 <= j1 < len(work) and
                                   abs(work[col].iloc[j0] - p0) <= 1e-6 * max(abs(p0), 1.0) and
                                   abs(work[col].iloc[j1] - p1) <= 1e-6 * max(abs(p1), 1.0))
        ln = s100.Line(kind, int(j0), float(p0), int(j1), float(p1))
        ln.angle_deg = float(ang)
        walk_taps(ln, work, a)
        info[name + "_taps_snapshot"] = int(ntaps)
        info[name + "_taps_rebuilt"] = len(ln.taps)
        out.append(ln)
    return out[0], out[1], info


# ------------------------------------------------------------------ Linie -> Preis zu beliebiger Zeit
def _ns(series):
    """Zeiten als float-Nanosekunden (aufloesungsunabhaengig: pandas 3 mischt s/us/ns je Quelle)."""
    t = pd.to_datetime(pd.Series(series), utc=True).dt.tz_convert(None)
    return t.astype("datetime64[ns]").astype("int64").values.astype(float)


def line_values_at_times(line, df_line, times):
    """Preise der Linie (Index-Raum von df_line) zu den Zeitpunkten `times` (z. B. Kerzen eines niedrigeren Zeitrahmens).
    Index-Raum -> Zeit ueber lineare Interpolation der Kerzenzeiten; rechts davon mittlere Kerzendauer."""
    tt = _ns(df_line["Time"])
    n = len(tt)
    step = np.median(np.diff(tt)) if n > 1 else 1.0
    q = _ns(times)
    idx = np.interp(q, tt, np.arange(n))
    idx = np.where(q > tt[-1], (n - 1) + (q - tt[-1]) / step, idx)
    idx = np.where(q < tt[0], (q - tt[0]) / step, idx)
    return np.array([line.value_at(x) for x in idx])
