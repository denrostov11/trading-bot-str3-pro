# -*- coding: utf-8 -*-
"""Linienerkennung je Zeitrahmen - nutzt die KANONISCHEN scan_100-Funktionen (pivots, is_aplus, pick_safety, atr) mit den je
Zeitrahmen skalierten Parametern aus params.py; die Paar-Suche (find_lines) laeuft ueber die schnelle, BEGRENZTE Variante
fastlines.find_lines_fast (identische Ergebnisse, harte Obergrenzen, Zeitbudget). Kein Engine-Code wird veraendert.

Kontextlinien (Monat/Woche/Tag/1h; es gibt dort kein Signal):
  1. Kandidaten = intakte Linien (kein Schlusskurs-Bruch), Action-Kriterien A+ (>= 3 Taps, Dauer, Winkel < 45 Grad).
  2. Gewaehlt wird die dem aktuellen Schlusskurs naechste (Abstand in ATR).
  3. Rueckfall nach Tori: gibt es keine A+-Linie, genuegen 2 Beruehrungspunkte; dann gilt Punkt B = das JUENGSTE
     unberuehrte Hoch/Tief (groesstes i1), erst danach Naehe zum Kurs.
  4. Safety = pick_safety(...) (intakt, konvergent, Keil/Apex, Tap-Alter, richtige Seite).
  5. Bias (rein informativ): siehe topdown.py - Struktur der letzten Swings, Lage des Kurses zu den Linien, Bruch einer Linie.
     detect_context liefert dafuer die Eingaben in ctx.extra["bias_in"].
Gibt es keine gueltige Linie (oder keine Daten / Zeitbudget ueberschritten): Ergebnis ohne Linie - es wird NICHTS erfunden.
"""
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

from . import params as PR
from .budget import MtfTimeout
from .fastlines import find_lines_fast, is_aplus as _is_aplus_p, pick_safety as _pick_safety_p


@dataclass
class Ctx:
    tf: str
    df: pd.DataFrame = None            # Analysefenster (abgeschlossene Kerzen, index 0..n-1)
    atr: pd.Series = None
    action: object = None              # scan_100.Line
    safety: object = None
    kind: str = ""                     # "A+" | "2-Punkt (Tori)" | ""
    bias: str = ""                     # "up" | "down" | "flat" | "" - Steigung der Hauptlinie (nur Anzeige / alte Regel)
    reason: str = ""                   # Begruendung, wenn keine Linie
    params: object = None
    no_data: bool = False              # True: keine Kerzen -> "keine Daten"
    timeout: bool = False              # True: Zeitbudget der Linien-Suche ueberschritten
    safety_note: str = ""              # Begruendung, wenn Action-Line da, aber keine Safety Line
    extra: dict = field(default_factory=dict)


FLAT_ANGLE_DEG = 3.0
N_SWINGS = 3                                         # letzte N Swing-Hochs bzw. -Tiefs fuer die Struktur
BREAK_RECENT = {"M": 6, "W": 8, "D": 10, "4h": 10, "1h": 12}      # "juenger Bruch" = Bruch in den letzten N Kerzen
SWING_TOL_ATR = 0.1                                  # Swing-Preise innerhalb 0,1 ATR gelten als gleich


def line_bias(line):
    """'up' | 'down' | 'flat' aus der Steigung der Linie (normierter Winkel < 3 Grad = flach)."""
    if line.angle_deg < FLAT_ANGLE_DEG:
        return "flat"
    return "up" if (line.p1 - line.p0) / (line.i1 - line.i0) > 0 else "down"


def _bias_inputs(work, tf, piv, sup, res, ok, action, last, atr_last, P):
    """Eingaben der Top-down-Bewertung: Swing-Preise, naechste intakte Unterstuetzung/Widerstand, juengster Linienbruch.
    Rueckgabe: (Linienobjekte fuer die Darstellung, reine Zahlen-/Text-Eingaben fuer topdown.assess)."""
    n = len(work)
    lows = [float(work["Low"].iloc[i]) for i in piv[0][-N_SWINGS:]]
    highs = [float(work["High"].iloc[i]) for i in piv[1][-N_SWINGS:]]
    ref = n - 1

    def near(kind):
        c = [l for l in ok if l.kind == kind and (_is_aplus_p(l, P) or l is action)]
        return min(c, key=lambda l: (abs(l.value_at(ref) - last), -l.score)) if c else None
    # juengster Bruch einer A+-Linie, die jenseits der Linie geblieben ist (kein gescheiterter Ausbruch)
    brk, brk_line = None, None
    for l in sup + res:
        if l.breaking_bar > 0 and _is_aplus_p(l, P) and l.breaking_bar >= n - BREAK_RECENT[tf]:
            v = l.value_at(ref)
            beyond = last > v if l.kind == "resistance" else last < v
            if beyond and (brk is None or (l.breaking_bar, len(l.taps)) > (brk["bar"], brk["taps"])):
                brk = {"kind": l.kind, "bar": int(l.breaking_bar), "bars_ago": int(n - 1 - l.breaking_bar), "taps": len(l.taps)}
                brk_line = l
    ns, nr = near("support"), near("resistance")
    bias_lines = {"support": ns, "resistance": nr, "break": brk_line}
    return bias_lines, {"highs": highs, "lows": lows, "tol": SWING_TOL_ATR * atr_last, "atr": atr_last, "last": last,
            "support": None if ns is None else {"bias": line_bias(ns), "taps": len(ns.taps), "kind": ns.kind},
            "resistance": None if nr is None else {"bias": line_bias(nr), "taps": len(nr.taps), "kind": nr.kind},
            "break": brk}


def detect_context(df_closed, tf, deadline=None):
    """Kontextlinien fuer einen Zeitrahmen aus ABGESCHLOSSENEN Kerzen (df_closed mit Time/Open/High/Low/Close).
    deadline: optionales budget.Deadline fuer die Linien-Suche; bei Ueberschreitung -> Ctx ohne Linien (timeout=True)."""
    P = PR.scaled(tf)
    ctx = Ctx(tf=tf, params=P)
    nb = 0 if df_closed is None else len(df_closed)
    if nb == 0:
        ctx.no_data, ctx.reason = True, "keine Daten"
        return ctx
    if nb < P.min_bars:
        ctx.df = df_closed.tail(P.window).reset_index(drop=True)
        ctx.reason = f"zu wenig Historie ({nb} Kerzen, nötig {P.min_bars})"
        return ctx
    work = df_closed.tail(P.window).reset_index(drop=True)
    ctx.df = work
    s100 = PR._s100()
    try:
        a = s100.atr(work)
        ctx.atr = a
        piv = s100.pivots(work, k=P.k)
        sup, i1 = find_lines_fast(work, "support", a, piv, P, deadline=deadline)
        res, i2 = find_lines_fast(work, "resistance", a, piv, P, deadline=deadline)
        ctx.extra["search"] = {"pivots": (i1["pivots"], i2["pivots"]), "pairs": i1["pairs"] + i2["pairs"],
                               "truncated": bool(i1["truncated"] or i2["truncated"])}
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
        aplus = [l for l in ok if _is_aplus_p(l, P)]
        if aplus:
            ctx.action, ctx.kind = min(aplus, key=lambda l: (dist(l), -l.score)), "A+"
        elif ok:
            ctx.action, ctx.kind = max(ok, key=lambda l: (l.i1, -dist(l))), "2-Punkt (Tori)"
        ctx.extra["bias_lines"], ctx.extra["bias_in"] = _bias_inputs(work, tf, piv, sup, res, ok, ctx.action, last, atr_last, P)
        if ctx.action is None:
            ctx.reason = "keine gültige Linie nach unseren Regeln"
            return ctx
        opp = res if ctx.action.kind == "support" else sup
        ctx.safety = _pick_safety_p(ctx.action, opp, work, a, P)
        if ctx.safety is None:
            ctx.safety_note = "keine gültige Safety Line nach unseren Regeln"
        ctx.bias = line_bias(ctx.action)
        ctx.extra["dist_atr"] = round(dist(ctx.action), 2)
    except MtfTimeout:
        ctx.action = ctx.safety = None
        ctx.timeout = True
        ctx.reason = "Zeitbudget der Linien-Suche überschritten – keine Linienaussage"
        ctx.extra.pop("bias_in", None)
        ctx.extra.pop("bias_lines", None)
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
