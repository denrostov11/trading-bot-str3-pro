# -*- coding: utf-8 -*-
"""Trade-PDF (Top-down: Monat -> Woche -> Tag -> 4h -> 1h) - 3 Seiten, Vektor.

make_trade_pdf(...) ist so geschnitten, dass es nach dem 17.10.2026 ohne Umbau aus dem Live-Lauf aufgerufen werden
kann (Eingaben: Trade-dict, Snapshot-dict, 1h- und Tagesdaten). outcome ist optional (live: None); ohne outcome gibt
es keinen Verlauf nach dem Signal und keine C+-Muster-Auswertung. JETZT NICHT in den Live-Lauf eingehaengt.
"""
import os
import textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from . import data as D, lines as L, params as PR, topdown as TD, cplus_overlay as CO
from .render import COL, draw_chart, legend_handles

PW, PH = 8.27, 11.69
LEFT, WIDTH = 0.075, 0.83
EXTRA_RIGHT = {"M": 14, "W": 16, "D": 18, "4h": 26, "1h": 24}     # Platz fuer Beschriftungen rechts (in Kerzen)
MUSTER = "MUSTER – fiktiver Trade aus Paper-Test"


def fde(ts, with_time=True):
    t = pd.Timestamp(ts)
    return t.strftime("%d.%m.%Y %H:%M UTC") if with_time else t.strftime("%d.%m.%Y")


def fnum(x, d=2, sign=False):
    s = (f"{x:+.{d}f}" if sign else f"{x:.{d}f}").replace(".", ",").replace("-", "−")
    return s


def fprice(x):
    return f"{float(x):.6g}".replace(".", ",")


# ------------------------------------------------------------------ Analyse
def analyse(trade, snapshot, h1, daily, fee_fraction):
    """Alles, was die Charts brauchen. Nutzt zum Signalzeitpunkt nur Daten bis cutoff; Daten danach nur fuer die
    optionale Muster-Auswertung (post)."""
    sig_start = pd.Timestamp(trade["signal_time"])
    sig_start = sig_start.tz_localize("UTC") if sig_start.tzinfo is None else sig_start.tz_convert("UTC")
    cutoff = sig_start + pd.Timedelta(hours=4)
    tfs = D.build_timeframes(h1, daily, cutoff)
    f4 = tfs["4h"]["closed"]
    assert pd.Timestamp(f4["Time"].iloc[-1]) == sig_start, "Signalkerze nicht letzte abgeschlossene 4h-Kerze"
    k = len(f4) - 1
    action, safety, info = L.rebuild_trade_lines(f4, snapshot, float(trade["stop_initial"]), k)
    ctxs = {tf: L.detect_context(tfs[tf]["closed"], tf) for tf in ("M", "W", "D", "1h")}
    direction = trade["direction"]
    td = TD.evaluate(direction, ctxs, signal_taps=len(action.taps))

    res = trade.get("result") or {}
    E = float(res["entry_open"]) if res.get("entry_open") is not None else float(trade["entry_price"])
    stop0, target = float(trade["stop_initial"]), float(trade["target"])
    a = float(snapshot["atr"])
    risk = abs(E - stop0)
    cost_price = 2 * 0.05 * a + fee_fraction * 2 * E
    A = {"trade": trade, "snapshot": snapshot, "cutoff": cutoff, "sig_start": sig_start, "tfs": tfs, "f4": f4, "k": k,
         "action": action, "safety": safety, "info": info, "ctxs": ctxs, "td": td, "E": E, "stop0": stop0,
         "target": target, "a": a, "risk": risk, "cost_price": cost_price, "direction": direction,
         "h1": h1, "post": None, "cplus": None, "ist": None}
    return A


def add_outcome(A, ist, h1_full_end=None):
    """Muster-Auswertung nach dem Signal: IST-Ausgang und C+-Stufenpunkte (aus den vollen Daten)."""
    f4_full = D.four_hour(A["h1"], A["h1"]["End"].max())
    f4_full = D.closed_until(f4_full, A["h1"]["End"].max())
    k, e = A["k"], A["k"] + 1
    times = pd.to_datetime(f4_full["Time"], utc=True)
    assert times.iloc[k] == A["sig_start"], "4h-Index der Signalkerze passt nicht (Daten veraendert?)"
    O, H, Lw, C = (f4_full[c].values.astype(float) for c in ("Open", "High", "Low", "Close"))
    tr = CO.trace(A["direction"], O, H, Lw, C, A["safety"].value_at, e, A["E"], A["risk"], A["a"], A["cost_price"])
    ist_idx = None
    if ist and ist.get("exit_time"):
        m = times[times == pd.Timestamp(ist["exit_time"])]
        ist_idx = int(m.index[0]) if len(m) else None
    ends = [x for x in (tr["exit"]["idx"] if tr["exit"] else None, ist_idx) if x is not None]
    last = min(len(f4_full) - 1, (max(ends) if ends else k + 60) + 4, k + 150)
    A.update(cplus=tr, ist=dict(ist or {}, idx=ist_idx), f4_full=f4_full, post=f4_full.iloc[k + 1:last + 1].reset_index(drop=True))
    A["cplus_r"] = A["cplus_pct"] = None
    if tr["exit"]:
        from engine import tracker as T                      # nur die Ergebnisformeln (read-only)
        short = A["direction"] == "SHORT"
        slip = T.SLIP_ATR_PER_SIDE * A["a"]
        fill = A["E"] - slip if short else A["E"] + slip
        rb = T._result_block(A["direction"], A["trade"]["asset_class"], A["a"], A["E"], fill, A["risk"], slip, A["stop0"], A["stop0"],
                             0.0, tr["exit"]["price"], tr["exit"]["outcome"], False, 0.0, 0.0, False, 1)
        A["cplus_r"], A["cplus_pct"] = rb["netto_r"], rb["net_return_pct"]
        A["cplus_exit_time"] = str(pd.Timestamp(f4_full["Time"].iloc[tr["exit"]["idx"]]))
    return A


# ------------------------------------------------------------------ Chart-Spezifikationen
def _closed_view(ctx, closed, n_max=None):
    d = ctx.df if ctx.df is not None else closed.tail(PR.scaled(ctx.tf).window).reset_index(drop=True)
    if n_max and len(d) > n_max:
        d = d.tail(n_max).reset_index(drop=True)
    return d


def _own_lines(ctx, offset, label_prefix):
    out = []
    if ctx.action is not None:
        t = "Action" if True else ""
        out.append({"line": ctx.action, "role": "action", "x_offset": offset,
                    "label": f"{label_prefix}-Action-Line ({ctx.kind}, {len(ctx.action.taps)} Taps)"})
    if ctx.safety is not None:
        out.append({"line": ctx.safety, "role": "safety", "x_offset": offset,
                    "label": f"{label_prefix}-Safety-Line ({len(ctx.safety.taps)} Taps)"})
    return out


def _overlays(ctx_high, label_prefix, df_line=None, action=None, safety=None):
    out = []
    dfl = df_line if df_line is not None else ctx_high.df
    a = action if action is not None else ctx_high.action
    s = safety if safety is not None else ctx_high.safety
    if a is not None:
        out.append({"line": a, "df_line": dfl, "role": "action", "label": f"{label_prefix}-Action-Line"})
    if s is not None:
        out.append({"line": s, "df_line": dfl, "role": "safety", "label": f"{label_prefix}-Safety-Line"})
    return out


def build_specs(A):
    ctx, tfs, td = A["ctxs"], A["tfs"], A["td"]
    specs = {}
    for tf, prefix, above, above_prefix in (("M", "Monats", None, None), ("W", "Wochen", "M", "Monats"), ("D", "Tages", "W", "Wochen")):
        c = ctx[tf]
        view = _closed_view(c, tfs[tf]["closed"])
        specs[tf] = {"tf": tf, "closed": view, "partial": tfs[tf]["partial"], "lines": _own_lines(c, 0, prefix),
                     "overlays": _overlays(ctx[above], above_prefix) if above else [], "hlines": [], "extra_right": EXTRA_RIGHT[tf],
                     "empty_text": "keine gültige Linie nach unseren Regeln" if c.action is None else None}
    # ---- 4h
    f4, k = A["f4"], A["k"]
    act, saf = A["action"], A["safety"]
    start = max(0, min(act.i0, saf.i0) - 8, k - 330)
    view = f4.iloc[start:k + 1].reset_index(drop=True)
    long = A["direction"] == "LONG"
    hl = [{"y": A["E"], "label": f"Einstieg {fprice(A['E'])}", "color": COL["entry"], "x_from": k - start + 1},
          {"y": A["stop0"], "label": f"Stop {fprice(A['stop0'])}", "color": COL["stop"], "x_from": k - start + 1, "style": "--"},
          {"y": A["target"], "label": f"Ziel {fprice(A['target'])}", "color": COL["target"], "x_from": k - start + 1, "style": "--"}]
    s4 = {"tf": "4h", "closed": view, "partial": None, "post": None,
          "lines": [{"line": act, "role": "action", "x_offset": start,
                     "label": f"4h-Action-Line ({len(act.taps)} Taps) – gebrochen"},
                    {"line": saf, "role": "safety", "x_offset": start, "label": f"4h-Safety-Line ({len(saf.taps)} Taps)"}],
          "overlays": _overlays(ctx["D"], "Tages"), "hlines": hl, "extra_right": EXTRA_RIGHT["4h"], "break_x": k - start,
          "break_dir": "up" if long else "down", "markers": [], "steps": []}
    s4["lines"][0]["x_end"] = k - start
    s4["lines"][1]["x_end"] = k - start + (len(A["post"]) if A["post"] is not None else 6)
    if A["post"] is not None and len(A["post"]):
        cp, ist = A["cplus"], A["ist"]
        s4["post"] = A["post"]
        s4["post_from"] = k - start
        s4["post_label"] = "nach dem Signal (Auswertung)"
        # +1,5R-Marke
        s4["hlines"].append({"y": cp["stage2_level"], "label": "+1,5R (Stufe 2)", "color": COL["cplus"],
                             "x_from": k - start + 1, "style": ":"})
        # Gewinnschwelle als Stufenlinie
        if cp["profit_steps"]:
            xs = [st["from"] - start for st in cp["profit_steps"]]
            ys = [st["level"] for st in cp["profit_steps"]]
            end_x = (cp["exit"]["idx"] if cp["exit"] else k + len(A["post"])) - start
            xs.append(end_x); ys.append(ys[-1])
            s4["steps"].append({"xs": xs, "ys": ys})
        for si, sw in enumerate(cp["swings"], 1):
            s4["markers"].append({"x": sw["pivot_idx"] - start, "y": sw["pivot_price"], "text": f"S{si}", "color": COL["cplus"],
                                  "marker": "^" if long else "v"})
        if cp["exit"]:
            s4["markers"].append({"x": cp["exit"]["idx"] - start, "y": cp["exit"]["price"],
                                  "text": f"C+ Ausstieg {fnum(A['cplus_r'], 2, True)} R" if A.get("cplus_r") is not None else "C+ Ausstieg",
                                  "color": COL["cplus"], "marker": "o"})
        if ist and ist.get("idx") is not None:
            s4["markers"].append({"x": ist["idx"] - start, "y": ist["exit_price"],
                                  "text": f"IST Ausstieg {fnum(ist['netto_r'], 2, True)} R", "color": COL["entry"], "marker": "o", "off": (4, -12)})
    specs["4h"] = s4
    # ---- 1h
    c1 = ctx["1h"]
    h = A["h1"]
    h1c = tfs["1h"]["closed"]
    n1 = 240
    base = c1.df if c1.df is not None else h1c.tail(PR.scaled("1h").window).reset_index(drop=True)
    view1 = base.tail(n1).reset_index(drop=True)
    off1 = len(base) - len(view1)
    t0 = pd.Timestamp(f4["Time"].iloc[-1])
    in_break = view1[(view1["Time"] >= t0) & (view1["Time"] < t0 + pd.Timedelta(hours=4))].index.tolist()
    hl1 = [{"y": A["E"], "label": f"Einstieg {fprice(A['E'])}", "color": COL["entry"], "x_from": len(view1) - 1},
           {"y": A["stop0"], "label": f"Stop {fprice(A['stop0'])}", "color": COL["stop"], "x_from": len(view1) - 1, "style": "--"},
           {"y": A["target"], "label": f"Ziel {fprice(A['target'])}", "color": COL["target"], "x_from": len(view1) - 1, "style": "--"}]
    f4w = f4.iloc[:k + 1].reset_index(drop=True)
    specs["1h"] = {"tf": "1h", "closed": view1, "partial": None, "lines": _own_lines(c1, off1, "1h"),
                   "overlays": _overlays(None, "4h", df_line=f4w, action=act, safety=saf), "hlines": hl1,
                   "extra_right": EXTRA_RIGHT["1h"], "break_span": (in_break[0], in_break[-1]) if in_break else None,
                   "empty_text": "keine gültige 1h-Linie nach unseren Regeln" if c1.action is None else None}
    return specs


# ------------------------------------------------------------------ Seiten
def _wrap(text, width, indent=0):
    sub = " " * indent
    return "\n".join(textwrap.fill(p, width=width, subsequent_indent=sub) if p.strip() else "" for p in text.split("\n"))


def _header(fig, A, page, total, label, topdown_line=None):
    fig.add_artist(Rectangle((0, 1 - 0.32 / PH), 1, 0.32 / PH, transform=fig.transFigure, fc="#d97706", ec="none"))
    fig.text(0.04, 1 - 0.16 / PH, label, color="white", fontsize=9.5, fontweight="bold", va="center")
    fig.text(0.96, 1 - 0.16 / PH, f"Seite {page}/{total}", color="white", fontsize=8.5, va="center", ha="right")
    t = A["trade"]
    title = f"{t['symbol']} · {t['direction']} · Signal {fde(A['cutoff'])} · Str.3 Pro.1"
    fig.text(0.04, 1 - 0.55 / PH, title, fontsize=11.5, fontweight="bold", color=COL["text"], va="center")
    if topdown_line:
        fig.text(0.04, 1 - 0.85 / PH, topdown_line, fontsize=8.8, color="#0f766e", fontweight="bold", va="center")


def _footer(fig):
    fig.text(0.04, 0.12 / PH, "Prototyp-Muster · Paper-Trading – keine echte Order · keine Anlageberatung · "
             "Linien aus abgeschlossenen Kerzen, Zeiten in UTC", fontsize=6.8, color=COL["grey"], va="center")


def _legend(fig, items, y_in):
    h = legend_handles(items)
    fig.legend(handles=h, loc="center", bbox_to_anchor=(0.5, 1 - y_in / PH), ncol=3,
               fontsize=6.3, frameon=True, framealpha=1, edgecolor="#d1d5db", columnspacing=1.4, handlelength=2.2)


def _block(fig, top_in, height_in, title, note, spec, color_note="#f9fafb"):
    """Titel, Kurznotiz und Chart. top_in = Abstand der Blockoberkante von oben (Zoll)."""
    fig.text(0.04, 1 - (top_in + 0.12) / PH, title, fontsize=10, fontweight="bold", color="#1f2d4d", va="center")
    fig.text(0.04, 1 - (top_in + 0.30) / PH, _wrap(note, 128), fontsize=7.4, color=COL["text"], va="top",
             bbox=dict(boxstyle="round,pad=0.35", fc=color_note, ec="#d1d5db", lw=0.6), linespacing=1.25)
    ax_top, ax_h = top_in + 0.82, height_in - 0.82 - 0.32
    ax = fig.add_axes([LEFT, 1 - (ax_top + ax_h) / PH, WIDTH, ax_h / PH])
    draw_chart(ax, spec)
    return ax


def make_trade_pdf(out_path, A, description, label=MUSTER):
    """Erzeugt die 3-seitige Trade-PDF. description = Text der Kurzbeschreibung (S.3)."""
    td = A["td"]
    specs = A["specs"] = build_specs(A)
    items = td["items"]
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    long = A["direction"] == "LONG"
    with PdfPages(out_path, metadata={"Title": f"Top-down-Muster {A['trade']['symbol']}", "Author": "", "Subject": "Muster, Paper-Trading"}) as pdf:
        # ---- Seite 1: Monat + Woche
        fig = plt.figure(figsize=(PW, PH), facecolor="white")
        _header(fig, A, 1, 3, label, TD.headline(td))
        _legend(fig, ["action", "safety", "ov_action", "ov_safety", "tap", "partial"], 1.22)
        _block(fig, 1.55, 4.9, "1 · Monat – das große Bild: Trend und Hauptlinien", items["M"]["text"], specs["M"])
        _block(fig, 6.5, 4.9, "2 · Woche – baut auf dem Monat auf", items["W"]["text"], specs["W"])
        _footer(fig); pdf.savefig(fig); plt.close(fig)
        # ---- Seite 2: Tag + 4h
        fig = plt.figure(figsize=(PW, PH), facecolor="white")
        _header(fig, A, 2, 3, label)
        leg = ["action", "safety", "ov_action", "ov_safety", "tap", "break", "entry", "stop", "target"]
        if A["post"] is not None:
            leg += ["stage2", "cplus", "swing", "post"]
        _legend(fig, leg, 1.08)
        _block(fig, 1.50, 4.85, "3 · Tag – baut auf der Woche auf", items["D"]["text"], specs["D"])
        note4 = (f"{items['4h']['text']} Einstieg {fprice(A['E'])} · Stop {fprice(A['stop0'])} (1R = {fprice(A['risk'])}) · "
                 f"Ziel {fprice(A['target'])} · ATR {fprice(A['a'])}.")
        _block(fig, 6.4, 5.0, "4 · 4h – Handels-Zeitrahmen: hier liegt das Signal", note4, specs["4h"])
        _footer(fig); pdf.savefig(fig); plt.close(fig)
        # ---- Seite 3: 1h + Kurzbeschreibung
        fig = plt.figure(figsize=(PW, PH), facecolor="white")
        _header(fig, A, 3, 3, label)
        _legend(fig, ["action", "safety", "ov_action", "ov_safety", "tap", "break", "entry", "stop", "target"], 0.98)
        _block(fig, 1.40, 4.9, "5 · 1h – Verfeinerung des Einstiegs", items["1h"]["text"] + " Gelb unterlegt: die 4h-Signalkerze.", specs["1h"])
        fig.text(0.04, 1 - 6.55 / PH, "Kurzbeschreibung des Trades", fontsize=10.5, fontweight="bold", color="#1f2d4d", va="center")
        fig.text(0.045, 1 - 6.78 / PH, _wrap(description, 108, indent=20), fontsize=7.9, family="DejaVu Sans Mono", va="top", linespacing=1.38,
                 bbox=dict(boxstyle="round,pad=0.6", fc="#f9fafb", ec="#d1d5db", lw=0.6))
        _footer(fig); pdf.savefig(fig); plt.close(fig)
    return out_path
