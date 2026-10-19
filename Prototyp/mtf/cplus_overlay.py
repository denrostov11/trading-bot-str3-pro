# -*- coding: utf-8 -*-
"""C+-Stufenpunkte fuer die Muster-Darstellung (Nachrechnung, nicht live): +1,5R-Marke, Gewinnschwelle (Einstand+Kosten),
Swing-Schwellen, Notfallnetz und Ausstieg. Gleiche Logik wie Analysen/cplus_pro1/cplus_pro1.simulate (Variante C+):
Schlusskurs-Regel, Netz 1 ATR, Stufe 2 bei Schlusskurs >= +1,5R, Stufe 3 nach bestaetigtem Fraktal (k=3,
Ruecksetzer >= 1 ATR) mit Swing -/+ 0,5 ATR, nur in Gewinnrichtung, es gilt die guenstigere von Linie und Schwelle.
"""
import numpy as np

STAGE2_R, SWING_BUF, NET_ATR, MIN_PULLBACK, K = 1.5, 0.5, 1.0, 1.0, 3


def trace(direction, O, H, L, C, line_real, e, E, risk, a, cost_price):
    """O,H,L,C: echte Preise (numpy). line_real(i): Safety-Linie (echt). Rueckgabe dict mit Ereignissen (echte Preise)."""
    short = direction == "SHORT"
    sg = -1.0 if short else 1.0
    o, c = O * sg, C * sg
    h, l = (-L, -H) if short else (H, L)
    line = lambda i: sg * line_real(i)
    n = len(o)
    P = None
    out = {"stage2_idx": None, "stage2_level": E + sg * STAGE2_R * risk, "profit_steps": [], "swings": [],
           "exit": None, "net_hit": False}
    for j in range(e, n):
        thr, who = line(j), "LINE"
        if P is not None and P > thr:
            thr, who = P, "PROFIT"
        net = sg * 0 + thr - NET_ATR * a
        if o[j] <= net:
            out["exit"] = {"idx": j, "price": sg * o[j], "outcome": "NOTFALLNETZ"}; return out
        if l[j] <= net:
            out["exit"] = {"idx": j, "price": sg * net, "outcome": "NOTFALLNETZ"}; return out
        if c[j] < thr:
            if j + 1 < n:
                out["exit"] = {"idx": j + 1, "price": sg * o[j + 1],
                               "outcome": "SAFETY_CLOSE" if who == "LINE" else "GEWINNSCHWELLE_CLOSE"}
            else:
                out["exit"] = None
            return out
        if c[j] - sg * E >= STAGE2_R * risk and out["stage2_idx"] is None:
            out["stage2_idx"] = j
        if c[j] - sg * E >= STAGE2_R * risk:
            lvl = sg * E + cost_price
            if P is None or lvl > P:
                P = lvl if P is None else max(P, lvl)
                out["profit_steps"].append({"from": j + 1, "level": sg * P, "kind": "Einstand+Kosten"})
        p = j - K
        if out["stage2_idx"] is not None and p >= e and p - K >= 0 and \
                l[p] <= l[p - K:p].min() and l[p] <= l[p + 1:p + K + 1].min() and \
                h[e:p + 1].max() - l[p] >= MIN_PULLBACK * a:
            lvl = l[p] - SWING_BUF * a
            if lvl > P:
                P = lvl
                out["profit_steps"].append({"from": j + 1, "level": sg * P, "kind": "Swing"})
                out["swings"].append({"pivot_idx": p, "pivot_price": sg * l[p], "confirm_idx": j})
    return out
