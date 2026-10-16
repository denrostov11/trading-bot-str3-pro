# -*- coding: utf-8 -*-
"""Vektor-Charts (matplotlib): Kerzen als PolyCollection/LineCollection -> kleine, zoombare PDFs.

Ein Chart wird ueber ein spec-dict beschrieben (siehe draw_chart). Gleiches Farbschema in allen Charts:
Action Line = Teal (durchgezogen), Safety Line = Amber (durchgezogen), Linien des naechsthoeheren Zeitrahmens =
gleiche Farben DUENN GESTRICHELT mit Beschriftung, Einstieg = Navy, Stop = Rot, Ziel = Gruen, C+ = Violett.
Unfertige Kerzen (laufende Periode zum Signalzeitpunkt) sind hell/transparent mit gestricheltem Rand.
"""
import textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection, PolyCollection
from matplotlib.lines import Line2D

from .lines import line_values_at_times

matplotlib.rcParams["pdf.fonttype"] = 42             # TrueType-Schrift (kleine Datei, Text bleibt auswaehlbar)
matplotlib.rcParams["font.family"] = "DejaVu Sans"

COL = {"up": "#1a9e5c", "down": "#c0392b", "action": "#0f766e", "safety": "#d97706", "entry": "#1f2d4d",
       "stop": "#c0392b", "target": "#16a34a", "cplus": "#6d3fc0", "grey": "#6b7280", "grid": "#e5e7eb",
       "post": "#f3f4f6", "brk": "#fde68a", "text": "#111827"}
TF_FMT = {"M": "%m/%Y", "W": "%d.%m.%y", "D": "%d.%m.%y", "4h": "%d.%m. %Hh", "1h": "%d.%m. %Hh"}


def draw_candles(ax, df, xs, alpha=1.0, dashed_edge=False, zorder=3):
    o, h, l, c = (df[k].values.astype(float) for k in ("Open", "High", "Low", "Close"))
    up = c >= o
    wicks = [[(x, lo), (x, hi)] for x, lo, hi in zip(xs, l, h)]
    cols = [COL["up"] if u else COL["down"] for u in up]
    ax.add_collection(LineCollection(wicks, colors=cols, linewidths=0.6, alpha=alpha, zorder=zorder))
    w = 0.34
    polys = []
    for x, oo, cc in zip(xs, o, c):
        lo, hi = min(oo, cc), max(oo, cc)
        polys.append([(x - w, lo), (x + w, lo), (x + w, hi), (x - w, hi)])
    ax.add_collection(PolyCollection(polys, facecolors=cols, edgecolors=cols, linewidths=0.4, alpha=alpha,
                                     linestyles="--" if dashed_edge else "-", zorder=zorder))


def _spread_labels(items, y_lo, y_hi, min_gap_frac=0.055):
    """Beschriftungen vertikal entzerren: items = [(y, text, color, bold)] -> [(y_label, ...)]."""
    gap = (y_hi - y_lo) * min_gap_frac
    items = sorted(items, key=lambda t: t[0])
    out, last = [], -1e18
    for y, text, color, bold in items:
        yy = min(max(y, y_lo + gap * 0.5), y_hi - gap * 0.5)
        yy = max(yy, last + gap)
        out.append((yy, y, text, color, bold))
        last = yy
    return out


def draw_chart(ax, spec):
    """spec:
      tf, closed (DataFrame, sichtbar), partial (dict|None), post (DataFrame|None),
      lines  [{line, role('action'|'safety'), label, x_offset}]   - Linien im eigenen Zeitrahmen (Index-Raum + x_offset)
      overlays [{line, df_line, role, label}]                      - Linien des hoeheren Zeitrahmens (Zeit-Mapping)
      hlines [{y, label, color, x_from, style}]                    - Einstieg/Stop/Ziel/C+-Level
      steps  [{from_x, level}]                                     - C+-Gewinnschwelle (Stufenlinie)
      markers [{x, y, text, color, marker}]                        - Ausstiege etc.
      break_x (int|None), break_span (x0,x1)|None, post_from (int|None), post_label (str)
      empty_text (str)  - Text mitten im Chart, wenn keine Linie.
    """
    closed = spec["closed"].reset_index(drop=True)
    n = len(closed)
    xs = np.arange(n)
    parts = [closed]
    if spec.get("partial"):
        p = pd.DataFrame([spec["partial"]])
        parts.append(p)
    post = spec.get("post")
    if post is not None and len(post):
        parts.append(post.reset_index(drop=True))
    allb = pd.concat([x[["Time", "Open", "High", "Low", "Close"]] for x in parts], ignore_index=True)
    m = len(allb)
    draw_candles(ax, closed, xs)
    if spec.get("partial"):
        draw_candles(ax, pd.DataFrame([spec["partial"]]), [n], alpha=0.35, dashed_edge=True)
    if post is not None and len(post):
        draw_candles(ax, post, np.arange(n + (1 if spec.get("partial") else 0), m), alpha=0.6)
        px = spec.get("post_from", n)
        ax.axvspan(px + 0.5, m + spec.get("extra_right", 0), color=COL["post"], zorder=0)
        ax.axvline(px + 0.5, color=COL["grey"], lw=0.8, ls=":", zorder=1)
        ax.text(px + 0.8, 0.012, spec.get("post_label", "nach dem Signal"), transform=ax.get_xaxis_transform(),
                fontsize=6.4, color=COL["grey"], va="bottom")
    lo_v, hi_v = float(allb["Low"].min()), float(allb["High"].max())
    for h in spec.get("hlines", []):
        lo_v, hi_v = min(lo_v, h["y"]), max(hi_v, h["y"])
    pad = (hi_v - lo_v) * 0.06 or abs(hi_v) * 0.01 or 1.0
    y_lo, y_hi = lo_v - pad, hi_v + pad
    extra = spec.get("extra_right", 0)
    ax.set_xlim(-1.2, m + extra)
    ax.set_ylim(y_lo, y_hi)

    if spec.get("break_span"):
        a, b = spec["break_span"]
        ax.axvspan(a - 0.5, b + 0.5, color=COL["brk"], alpha=0.55, zorder=0)
    elif spec.get("break_x") is not None:
        ax.axvspan(spec["break_x"] - 0.5, spec["break_x"] + 0.5, color=COL["brk"], alpha=0.55, zorder=0)

    labels = []
    # eigene Linien (durchgezogen) + Taps
    for L in spec.get("lines", []):
        ln, off, role = L["line"], L.get("x_offset", 0), L["role"]
        col = COL[role]
        x0 = max(ln.i0 - off, 0)
        xe = L.get("x_end", m - 1)
        xx = np.arange(x0, xe + 1)
        yy = np.array([ln.value_at(x + off) for x in xx])
        ax.plot(xx, yy, color=col, lw=1.5, zorder=4, solid_capstyle="round")
        for t in ln.taps:
            if 0 <= t - off < n:
                ax.plot(t - off, ln.value_at(t), "o", ms=6.5, mfc="none", mec=col, mew=1.2, zorder=5)
        labels.append((float(yy[-1]), L["label"], col, True))
    # Linien des hoeheren Zeitrahmens (duenn gestrichelt)
    times = allb["Time"]
    for O in spec.get("overlays", []):
        vals = line_values_at_times(O["line"], O["df_line"], times)
        col = COL[O["role"]]
        ax.plot(np.arange(m), vals, color=col, lw=0.9, ls=(0, (4, 3)), zorder=3.5, alpha=0.95)
        labels.append((float(vals[-1]), O["label"], col, False))
    # horizontale Levels
    for h in spec.get("hlines", []):
        x0 = h.get("x_from", 0)
        ax.plot([x0, m + 0.3], [h["y"], h["y"]], color=h["color"], lw=1.1, ls=h.get("style", "-"), zorder=3.2)
        labels.append((float(h["y"]), h["label"], h["color"], True))
    for s in spec.get("steps", []):
        ax.step(s["xs"], s["ys"], where="post", color=COL["cplus"], lw=1.3, zorder=4.2)
    for mk in spec.get("markers", []):
        ax.plot(mk["x"], mk["y"], mk.get("marker", "v"), ms=7, color=mk["color"], zorder=6, mec="white", mew=0.5)
        ax.annotate(mk["text"], (mk["x"], mk["y"]), xytext=mk.get("off", (4, 7)), textcoords="offset points", fontsize=6.6,
                    color=mk["color"], zorder=6)
    if spec.get("break_x") is not None:
        bx = spec["break_x"]
        ax.plot(bx, float(allb["Close"].iloc[bx]), "v" if spec.get("break_dir") == "down" else "^", ms=8, color=COL["text"],
                zorder=6, mec="white", mew=0.6)
    # Beschriftungen rechts (entzerrt)
    if labels:
        for yy, y0, text, color, bold in _spread_labels(labels, y_lo, y_hi):
            txt = textwrap.fill(text + (" ↑" if y0 > y_hi else " ↓" if y0 < y_lo else ""), width=21)
            ax.text(m + 0.6, yy, txt, fontsize=6.0, color=color, va="center", linespacing=1.05,
                    fontweight="bold" if bold else "normal", clip_on=False, zorder=7)
    if spec.get("empty_text"):
        ax.text(0.5, 0.93, spec["empty_text"], transform=ax.transAxes, ha="center", va="top", fontsize=9, color=COL["grey"],
                bbox=dict(boxstyle="round,pad=0.4", fc="white", ec=COL["grey"], lw=0.8))
    # Achsen
    k = 7
    pos = np.unique(np.linspace(0, m - 1, k).round().astype(int))
    ax.set_xticks(pos)
    ax.set_xticklabels([pd.Timestamp(allb["Time"].iloc[i]).strftime(TF_FMT[spec["tf"]]) for i in pos], fontsize=6.8)
    ax.tick_params(axis="y", labelsize=6.8, length=2)
    ax.tick_params(axis="x", length=2)
    ax.grid(color=COL["grid"], lw=0.5, zorder=0)
    for s in ax.spines.values():
        s.set_color("#d1d5db")
    ax.yaxis.tick_left()
    return {"n": n, "m": m, "y": (y_lo, y_hi)}


def legend_handles(items):
    """items: Schluessel -> Line2D; fuer die Seitenlegende."""
    H = {
        "action": Line2D([0], [0], color=COL["action"], lw=1.6, label="Action Line (Bruchlinie)"),
        "safety": Line2D([0], [0], color=COL["safety"], lw=1.6, label="Safety Line (Stop-Linie)"),
        "ov_action": Line2D([0], [0], color=COL["action"], lw=1.0, ls=(0, (4, 3)), label="Action Line des höheren Zeitrahmens"),
        "ov_safety": Line2D([0], [0], color=COL["safety"], lw=1.0, ls=(0, (4, 3)), label="Safety Line des höheren Zeitrahmens"),
        "tap": Line2D([0], [0], marker="o", mfc="none", mec=COL["grey"], ls="", ms=6, label="Berührungspunkt (Tap)"),
        "break": Line2D([0], [0], marker="s", color=COL["brk"], ls="", ms=8, label="Bruchkerze"),
        "partial": Line2D([0], [0], marker="s", color="#c7d2cc", ls="", ms=8, label="unfertige Kerze (laufende Periode)"),
        "entry": Line2D([0], [0], color=COL["entry"], lw=1.2, label="Einstieg"),
        "stop": Line2D([0], [0], color=COL["stop"], lw=1.2, ls="--", label="Stop"),
        "target": Line2D([0], [0], color=COL["target"], lw=1.2, ls="--", label="Ziel"),
        "cplus": Line2D([0], [0], color=COL["cplus"], lw=1.3, label="C+-Gewinnschwelle (Muster)"),
        "stage2": Line2D([0], [0], color=COL["cplus"], lw=1.0, ls=":", label="+1,5R (Stufe 2)"),
        "post": Line2D([0], [0], marker="s", color=COL["post"], mec="#d1d5db", ls="", ms=8, label="Verlauf nach dem Signal (nur Auswertung)"),
        "swing": Line2D([0], [0], marker="^", color=COL["cplus"], ls="", ms=6, label="bestätigtes Zwischentief/-hoch (Swing, S1, S2 …)"),
    }
    return [H[i] for i in items]
