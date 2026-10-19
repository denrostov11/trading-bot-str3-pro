# -*- coding: utf-8 -*-
"""Trade-PDF (Top-down: Monat -> Woche -> Tag -> 4h -> 1h) - 3 Seiten, Vektor, je Zeitrahmen ein eigener Chart.

  S.1 Monat + Woche | S.2 Tag + 4h | S.3 1h + Kurzbeschreibung des Trades

Oeffentliche API (Signaturen stabil; neue Parameter sind optional und nur per Schluesselwort):
  analyse(trade, snapshot, h1, daily, fee_fraction, *, c_plus=None, live_info=None, muster=False, max_seconds=None) -> A
  make_trade_pdf(out_path, A, description, label=None, max_seconds=None) -> out_path
  (Text: telegram_text.description(A) fuer S.3, telegram_text.telegram_draft(A) fuer die Nachricht unter der PDF)

Live-faehig: outcome ist optional (kein Verlauf nach dem Signal, keine C+-Auswertung); c_plus = Angaben "kein Ziel, Ausstieg nach
C+" + +1,5R-Marke; live_info = aktueller Kurs/Abstaende vom Aufrufer. Zeitlimit: analyse + make_trade_pdf zusammen <= 60 s
(budget.TOTAL_SECONDS, Umgebungsvariable MTF_MAX_SECONDS), sonst budget.MtfTimeout -> Aufrufer faellt auf das PNG zurueck.
Fehlende Daten in einem Zeitrahmen ergeben "keine Daten" im Chart; die PDF entsteht trotzdem.
"""
import os
import time
import textwrap
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from . import data as D, lines as L, params as PR, topdown as TD, cplus_overlay as CO
from .budget import Deadline, MtfTimeout, TOTAL_SECONDS, PER_TF_SECONDS
from .render import COL, draw_chart, draw_empty, legend_handles

PW, PH = 8.27, 11.69
LEFT, WIDTH = 0.075, 0.83
EXTRA_RIGHT = {"M": 14, "W": 16, "D": 18, "4h": 26, "1h": 24}     # Platz fuer Beschriftungen rechts (in Kerzen)
MUSTER = "MUSTER – fiktiver Trade aus Paper-Test"
LIVE_LABEL = "Strategie 3 Pro · Paper-Trading – keine echte Order"


# ------------------------------------------------------------------ Formatierung
def fde(ts, with_time=True):
    t = pd.Timestamp(ts)
    return t.strftime("%d.%m.%Y %H:%M UTC") if with_time else t.strftime("%d.%m.%Y")


def _last_sunday(year, month):
    d = pd.Timestamp(year=year, month=month, day=31, tz="UTC")           # Maerz und Oktober haben 31 Tage
    return d - pd.Timedelta(days=(d.weekday() + 1) % 7)


def fde_de(ts, with_time=True):
    """Deutsche Zeit (MEZ/MESZ nach EU-Regel: letzter Sonntag im Maerz 01:00 UTC bis letzter Sonntag im Oktober 01:00 UTC)."""
    t = pd.Timestamp(ts)
    t = t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")
    start, end = _last_sunday(t.year, 3) + pd.Timedelta(hours=1), _last_sunday(t.year, 10) + pd.Timedelta(hours=1)
    dst = start <= t < end
    loc = t + pd.Timedelta(hours=2 if dst else 1)
    if not with_time:
        return loc.strftime("%d.%m.%Y")
    return loc.strftime("%d.%m.%Y %H:%M") + (" MESZ" if dst else " MEZ")


def fnum(x, d=2, sign=False):
    s = (f"{x:+.{d}f}" if sign else f"{x:.{d}f}").replace(".", ",").replace("-", "−")
    return s


def fprice(x):
    return f"{float(x):.6g}".replace(".", ",")


def _num(v):
    """float oder None (0, NaN, '' und Unsinn -> None)."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return x if x == x and x != 0.0 else None


# ------------------------------------------------------------------ Analyse
def _norm_cplus(c_plus):
    """c_plus: None/False = aus | True oder dict (auch leer = Standardwerte) = an -> None oder dict(stage2_r, swing_buf_atr, net_atr)."""
    if c_plus is None or c_plus is False:
        return None
    d = {"stage2_r": CO.STAGE2_R, "swing_buf_atr": CO.SWING_BUF, "net_atr": CO.NET_ATR}
    if isinstance(c_plus, dict):
        for k in d:
            if c_plus.get(k) is not None:
                d[k] = float(c_plus[k])
    return d


def _ctx_fallback(tf, msg):
    c = L.Ctx(tf=tf, params=PR.scaled(tf))
    c.reason = msg
    return c


def analyse(trade, snapshot, h1, daily, fee_fraction, *, c_plus=None, live_info=None, muster=False, max_seconds=None):
    """Alles, was die Charts brauchen. Nutzt zum Signalzeitpunkt nur Daten bis cutoff; Daten danach nur fuer die
    optionale Muster-Auswertung (add_outcome). Ohne Ausgangsdaten und ohne C+-Auswertung lauffaehig (Live-Modus).
    trade: dict (symbol, direction, signal_time, stop_initial, entry_price, [target], [entry_time], [atr], ...).
    snapshot: dict mit action_anchor/safety_anchor/atr (None -> keine Trade-Linien, Hinweis in A['warnings']).
    h1, daily: DataFrames (Time, Open, High, Low, Close[, Volume, End]); None/leer erlaubt (-> "keine Daten").
    max_seconds: Gesamtlimit fuer analyse + make_trade_pdf (Standard 60 s). Ueberschreitung -> MtfTimeout."""
    dl = Deadline(TOTAL_SECONDS if max_seconds is None else max_seconds, "Trade-PDF")
    warnings = []
    h1 = D.prepare(h1, pd.Timedelta(hours=1))
    daily = D.prepare(daily, pd.Timedelta(days=1))
    sig_start = pd.Timestamp(trade["signal_time"])
    sig_start = sig_start.tz_localize("UTC") if sig_start.tzinfo is None else sig_start.tz_convert("UTC")
    cutoff = sig_start + pd.Timedelta(hours=4)
    tfs = D.build_timeframes(h1, daily, cutoff)
    dl.check("Daten")
    f4 = tfs["4h"]["closed"]
    f4_ok = len(f4) > 0 and pd.Timestamp(f4["Time"].iloc[-1]) == sig_start
    k = len(f4) - 1
    action = safety = None
    info = {}
    if not f4_ok:
        warnings.append("4h: Signalkerze nicht in den Daten – keine Trade-Linien" if len(f4) else "4h: keine Daten")
    elif snapshot is None or not snapshot.get("action_anchor") or not snapshot.get("safety_anchor"):
        warnings.append("4h: kein Snapshot mit Linien-Ankern – keine Trade-Linien")
    else:
        try:
            action, safety, info = L.rebuild_trade_lines(f4, snapshot, float(trade["stop_initial"]), k)
        except Exception as e:                               # defekter Snapshot: PDF trotzdem erzeugen
            warnings.append(f"4h: Trade-Linien nicht rekonstruierbar ({type(e).__name__})")
    ctxs = {}
    for tf in ("M", "W", "D", "1h"):
        dl.check(f"Linien {tf}")
        try:
            ctxs[tf] = L.detect_context(tfs[tf]["closed"], tf, deadline=dl.child(PER_TF_SECONDS))
        except MtfTimeout:
            raise
        except Exception as e:
            ctxs[tf] = _ctx_fallback(tf, f"Analyse nicht möglich ({type(e).__name__})")
            warnings.append(f"{tf}: Linien-Suche fehlgeschlagen ({type(e).__name__})")
        c = ctxs[tf]
        if c.no_data:
            warnings.append(f"{tf}: keine Daten")
        elif c.timeout:
            warnings.append(f"{tf}: Zeitbudget der Linien-Suche überschritten")
    direction = trade["direction"]
    td = TD.evaluate(direction, ctxs, signal_taps=len(action.taps) if action is not None else 0)

    res = trade.get("result") or {}
    sig_close = float(f4["Close"].iloc[-1]) if f4_ok else None
    booked = _num(trade.get("entry_price"))
    E = _num(res.get("entry_open")) or booked or sig_close          # Muster: rohe Eroeffnung (R wie Engine), live: gebuchter Kurs
    if E is None:
        raise ValueError("kein Einstiegskurs ermittelbar (weder entry_price noch Signalkerze)")
    stop0 = float(trade["stop_initial"])
    cp = _norm_cplus(c_plus)
    target = None if cp else _num(trade.get("target"))
    a = _num((snapshot or {}).get("atr")) or _num(trade.get("atr"))
    if a is None:
        a = float(PR._s100().atr(f4).iloc[-1]) if len(f4) > 14 else abs(E - stop0) / 3.0
        warnings.append("ATR nicht übergeben – aus den 4h-Kerzen berechnet")
    risk = abs(E - stop0)
    cost_price = 2 * 0.05 * a + fee_fraction * 2 * E
    entry_time = None
    if str(trade.get("entry_time") or "").strip():
        try:
            entry_time = pd.Timestamp(trade["entry_time"])
            entry_time = entry_time.tz_localize("UTC") if entry_time.tzinfo is None else entry_time.tz_convert("UTC")
        except Exception:
            entry_time = None
    A = {"trade": trade, "snapshot": snapshot, "cutoff": cutoff, "sig_start": sig_start, "tfs": tfs, "f4": f4, "k": k, "f4_ok": f4_ok,
         "action": action, "safety": safety, "info": info, "ctxs": ctxs, "td": td, "E": E, "stop0": stop0,
         "target": target, "a": a, "risk": risk, "cost_price": cost_price, "direction": direction,
         "h1": h1, "post": None, "cplus": None, "ist": None,
         "booked_price": booked, "entry_booked": booked is not None, "entry_time": entry_time or cutoff,
         "c_plus": cp, "live_info": _norm_live(live_info, E, stop0, target, risk, direction), "muster": bool(muster),
         "warnings": warnings, "max_seconds": dl.seconds, "elapsed": dl.elapsed()}
    if cp:
        sg = -1.0 if direction == "SHORT" else 1.0
        A["stage2_price"] = E + sg * cp["stage2_r"] * risk
    return A


def _norm_live(li, E, stop0, target, risk, direction):
    """live_info (optional, vom Aufrufer): price (aktueller Kurs), time, r_now, dist_stop, dist_target, stop_current, pnl_pct.
    Fehlende Abstaende werden aus price berechnet. None, wenn kein Kurs."""
    if not li or _num(li.get("price")) is None:
        return None
    price = float(li["price"])
    sg = -1.0 if direction == "SHORT" else 1.0
    out = {"price": price, "time": li.get("time")}
    stop_now = _num(li.get("stop_current")) or stop0
    out["stop_current"] = stop_now
    out["r_now"] = float(li["r_now"]) if li.get("r_now") is not None else (sg * (price - E) / risk if risk else None)
    out["dist_stop"] = float(li["dist_stop"]) if li.get("dist_stop") is not None else abs(price - stop_now)
    out["dist_stop_r"] = out["dist_stop"] / risk if risk else None
    if li.get("dist_target") is not None:
        out["dist_target"] = float(li["dist_target"])
    elif target is not None:
        out["dist_target"] = abs(target - price)
    else:
        out["dist_target"] = None
    out["pnl_pct"] = float(li["pnl_pct"]) if li.get("pnl_pct") is not None else (sg * (price - E) / E * 100 if E else None)
    for k in ("sent_at", "interval", "delay_s"):          # Angaben zum Versandzeitpunkt (Beschreibung S.3)
        if li.get(k) is not None:
            out[k] = li[k]
    return out


def add_outcome(A, ist, h1_full_end=None):
    """Muster-Auswertung nach dem Signal: IST-Ausgang und C+-Stufenpunkte (aus den vollen Daten). Nur fuer Nachrechnungen."""
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
        out.append({"line": ctx.action, "role": "action", "x_offset": offset,
                    "label": f"{label_prefix}-Action-Line ({ctx.kind}, {len(ctx.action.taps)} Taps)"})
    if ctx.safety is not None:
        out.append({"line": ctx.safety, "role": "safety", "x_offset": offset,
                    "label": f"{label_prefix}-Safety-Line ({len(ctx.safety.taps)} Taps)"})
    for side, name in (("support", "Unterstützung"), ("resistance", "Widerstand")):      # weitere Hauptlinie der Lage-Bewertung
        bl = (ctx.extra.get("bias_lines") or {}).get(side)
        if bl is not None and bl is not ctx.action:
            out.append({"line": bl, "role": "bias", "x_offset": offset, "lw": 1.0, "ls": (0, (1, 2)), "ms": 5,
                        "label": f"{label_prefix}-{name} ({len(bl.taps)} Taps, Lage)"})
    bk = (ctx.extra.get("bias_lines") or {}).get("break")
    if bk is not None:                                                                   # gebrochene Linie (Bruch-Bewertung)
        out.append({"line": bk, "role": "bias", "x_offset": offset, "lw": 1.0, "ls": (0, (5, 2, 1, 2)), "ms": 5,
                    "x_end": bk.breaking_bar - offset + 2,
                    "label": f"{label_prefix}-{'Widerstand' if bk.kind == 'resistance' else 'Unterstützung'} gebrochen ({len(bk.taps)} Taps)"})
    return out


def _overlays(ctx_high, label_prefix, df_line=None, action=None, safety=None):
    out = []
    dfl = df_line if df_line is not None else (ctx_high.df if ctx_high is not None else None)
    a = action if action is not None else (ctx_high.action if ctx_high is not None else None)
    s = safety if safety is not None else (ctx_high.safety if ctx_high is not None else None)
    if dfl is None or not len(dfl):
        return out
    if a is not None:
        out.append({"line": a, "df_line": dfl, "role": "action", "label": f"{label_prefix}-Action-Line"})
    if s is not None:
        out.append({"line": s, "df_line": dfl, "role": "safety", "label": f"{label_prefix}-Safety-Line"})
    return out


def _empty_text(c):
    """Text mitten im Chart, wenn es keine Linie gibt (nichts erfinden)."""
    if c.action is not None:
        return None
    if c.no_data:
        return "keine Daten"
    return c.reason or "keine gültige Linie nach unseren Regeln"


def _notes(c):
    return [c.safety_note] if (c.action is not None and c.safety is None and c.safety_note) else []


def _trade_hlines(A, x_from, with_stage2=True, far_soft=False):
    """Einstieg/Stop/Ziel/+1,5R-Linien. far_soft=True (1h-Chart): Ziel und +1,5R duerfen ausserhalb des Kerzenbereichs liegen
    (Pfeil am Rand), damit sie die Kerzen nicht zusammendruecken."""
    hl = [{"y": A["E"], "label": f"Einstieg {fprice(A['E'])}", "color": COL["entry"], "x_from": x_from},
          {"y": A["stop0"], "label": f"Stop {fprice(A['stop0'])}", "color": COL["stop"], "x_from": x_from, "style": "--"}]
    if A["target"] is not None:
        hl.append({"y": A["target"], "label": f"Ziel {fprice(A['target'])}", "color": COL["target"], "x_from": x_from, "style": "--",
                   "extend": not far_soft})
    if A.get("c_plus") and with_stage2:
        hl.append({"y": A["stage2_price"], "label": f"+{fnum(A['c_plus']['stage2_r'], 1)}R (C+ Stufe 2)",
                   "color": COL["cplus"], "x_from": x_from, "style": ":", "extend": not far_soft})
    return hl


def build_specs(A):
    ctx, tfs = A["ctxs"], A["tfs"]
    specs = {}
    for tf, prefix, above, above_prefix in (("M", "Monats", None, None), ("W", "Wochen", "M", "Monats"), ("D", "Tages", "W", "Wochen")):
        c = ctx[tf]
        view = _closed_view(c, tfs[tf]["closed"])
        specs[tf] = {"tf": tf, "closed": view, "partial": tfs[tf]["partial"] if len(view) else None, "lines": _own_lines(c, 0, prefix),
                     "overlays": _overlays(ctx[above], above_prefix) if above else [], "hlines": [], "extra_right": EXTRA_RIGHT[tf],
                     "empty_text": _empty_text(c), "notes": _notes(c)}
    # ---- 4h
    f4, k = A["f4"], A["k"]
    act, saf = A["action"], A["safety"]
    long = A["direction"] == "LONG"
    if len(f4):
        start = max(0, k - 330)
        if act is not None and saf is not None:
            start = max(0, min(act.i0, saf.i0) - 8, k - 330)
        view = f4.iloc[start:k + 1].reset_index(drop=True)
    else:
        start, view = 0, f4
    s4 = {"tf": "4h", "closed": view, "partial": None, "post": None, "lines": [], "overlays": _overlays(ctx["D"], "Tages"),
          "hlines": _trade_hlines(A, k - start + 1) if A["f4_ok"] else [], "extra_right": EXTRA_RIGHT["4h"],
          "markers": [], "steps": [], "notes": []}
    if A["f4_ok"]:
        s4["break_x"], s4["break_dir"] = k - start, "up" if long else "down"
    if act is not None and saf is not None:
        s4["lines"] = [{"line": act, "role": "action", "x_offset": start, "x_end": k - start,
                        "label": f"4h-Action-Line ({len(act.taps)} Taps) – gebrochen"},
                       {"line": saf, "role": "safety", "x_offset": start,
                        "x_end": k - start + (len(A["post"]) if A["post"] is not None else 6),
                        "label": f"4h-Safety-Line ({len(saf.taps)} Taps)"}]
    elif len(view):
        s4["empty_text"] = "Signalkerze/Linien nicht verfügbar – keine Trade-Linien" if not A["f4_ok"] else "Trade-Linien nicht rekonstruierbar"
    else:
        s4["empty_text"] = "keine Daten"
    if A.get("c_plus"):
        s4["notes"].append("kein festes Ziel – Ausstieg nach C+")
    elif (A.get("trade") or {}).get("exit_mode") == "D":
        s4["notes"].append("kein festes Ziel – Ausstieg nach D")
    if A["post"] is not None and len(A["post"]):
        cp, ist = A["cplus"], A["ist"]
        s4["post"] = A["post"]
        s4["post_from"] = k - start
        s4["post_label"] = "nach dem Signal (Auswertung)"
        if not A.get("c_plus"):
            s4["hlines"].append({"y": cp["stage2_level"], "label": "+1,5R (Stufe 2)", "color": COL["cplus"],
                                 "x_from": k - start + 1, "style": ":"})
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
    h1c = tfs["1h"]["closed"]
    base = c1.df if c1.df is not None else h1c.tail(PR.scaled("1h").window).reset_index(drop=True)
    view1 = base.tail(240).reset_index(drop=True)
    off1 = len(base) - len(view1)
    in_break = []
    if A["f4_ok"] and len(view1):
        t0 = pd.Timestamp(f4["Time"].iloc[-1])
        in_break = view1[(view1["Time"] >= t0) & (view1["Time"] < t0 + pd.Timedelta(hours=4))].index.tolist()
    hl1 = _trade_hlines(A, max(len(view1) - 1, 0), far_soft=True) if A["f4_ok"] else []
    li = A.get("live_info")
    if li:
        hl1.append({"y": li["price"], "label": f"aktuell {fprice(li['price'])}", "color": COL["grey"], "x_from": 0, "style": "-.",
                    "extend": False})
    f4w = f4.iloc[:k + 1].reset_index(drop=True) if len(f4) else f4
    specs["1h"] = {"tf": "1h", "closed": view1, "partial": None, "lines": _own_lines(c1, off1, "1h"),
                   "overlays": _overlays(None, "4h", df_line=f4w, action=act, safety=saf), "hlines": hl1,
                   "extra_right": EXTRA_RIGHT["1h"], "break_span": (in_break[0], in_break[-1]) if in_break else None,
                   "empty_text": ("keine gültige 1h-Linie nach unseren Regeln" if c1.reason == "keine gültige Linie nach unseren Regeln"
                                  else _empty_text(c1)), "notes": _notes(c1)}
    return specs


# ------------------------------------------------------------------ Seiten
def _wrap(text, width, indent=0):
    sub = " " * indent
    return "\n".join(textwrap.fill(p, width=width, subsequent_indent=sub) if p.strip() else "" for p in text.split("\n"))


def _title(A):
    t = A["trade"]
    return f"{t['symbol']} · {A['direction']} · {t.get('strategy_id', 'Str.3 Pro.1')} · Signal-Schluss {fde_de(A['cutoff'])}"


def _header(fig, A, page, total, label, topdown_line=None):
    fig.add_artist(Rectangle((0, 1 - 0.32 / PH), 1, 0.32 / PH, transform=fig.transFigure, fc="#d97706", ec="none"))
    fig.text(0.04, 1 - 0.16 / PH, label, color="white", fontsize=9.5, fontweight="bold", va="center")
    fig.text(0.96, 1 - 0.16 / PH, f"Seite {page}/{total}", color="white", fontsize=8.5, va="center", ha="right")
    fig.text(0.04, 1 - 0.55 / PH, _title(A), fontsize=11.5, fontweight="bold", color=COL["text"], va="center")
    if topdown_line:
        fig.text(0.04, 1 - 0.85 / PH, topdown_line, fontsize=8.8, color="#0f766e", fontweight="bold", va="center")


def _footer(fig, A):
    kind = "Prototyp-Muster · " if A.get("muster") else ""
    fig.text(0.04, 0.12 / PH, f"{kind}Paper-Trading – keine echte Order · keine Anlageberatung · "
             "Linien aus abgeschlossenen Kerzen · Chart-Zeiten in UTC, Kopfzeile/Text in deutscher Zeit", fontsize=6.6,
             color=COL["grey"], va="center")


def _legend(fig, items, y_in):
    h = legend_handles(items)
    fig.legend(handles=h, loc="center", bbox_to_anchor=(0.5, 1 - y_in / PH), ncol=3,
               fontsize=6.3, frameon=True, framealpha=1, edgecolor="#d1d5db", columnspacing=1.4, handlelength=2.2)


def _block(fig, top_in, height_in, title, note, spec, A=None, color_note="#f9fafb"):
    """Titel, Kurznotiz und Chart. top_in = Abstand der Blockoberkante von oben (Zoll). Ein Fehler im Chart zerstoert
    die PDF nicht: dann steht "Chart nicht darstellbar" im Rahmen."""
    fig.text(0.04, 1 - (top_in + 0.12) / PH, title, fontsize=10, fontweight="bold", color="#1f2d4d", va="center")
    fig.text(0.04, 1 - (top_in + 0.30) / PH, _wrap(note, 128), fontsize=7.4, color=COL["text"], va="top",
             bbox=dict(boxstyle="round,pad=0.35", fc=color_note, ec="#d1d5db", lw=0.6), linespacing=1.25)
    ax_top, ax_h = top_in + 0.82, height_in - 0.82 - 0.32
    ax = fig.add_axes([LEFT, 1 - (ax_top + ax_h) / PH, WIDTH, ax_h / PH])
    try:
        draw_chart(ax, spec)
    except MtfTimeout:
        raise
    except Exception as e:
        ax.clear()
        draw_empty(ax, "Chart nicht darstellbar", spec.get("tf", ""))
        if A is not None:
            A.setdefault("warnings", []).append(f"{spec.get('tf')}: Chart nicht darstellbar ({type(e).__name__})")
    return ax


def make_trade_pdf(out_path, A, description, label=None, max_seconds=None):
    """Erzeugt die 3-seitige Trade-PDF. description = Text der Kurzbeschreibung (S.3, z. B. telegram_text.description(A)).
    Zeitlimit: Gesamtbudget (analyse + dies) <= max_seconds (Standard: das von analyse uebernommene Limit, 60 s); sonst
    budget.MtfTimeout und KEINE (Teil-)Datei am Zielpfad. Geschrieben wird erst in <out_path>.part, dann atomar umbenannt."""
    total = float(max_seconds if max_seconds is not None else A.get("max_seconds", TOTAL_SECONDS))
    dl = Deadline(max(0.0, total - float(A.get("elapsed", 0.0))), "Trade-PDF")
    dl.check("vor Beginn")
    label = label or (MUSTER if A.get("muster") else LIVE_LABEL)
    td = A["td"]
    specs = A["specs"] = build_specs(A)
    items = td["items"]
    out_dir = os.path.dirname(out_path) or "."
    os.makedirs(out_dir, exist_ok=True)
    long = A["direction"] == "LONG"
    tmp = out_path + ".part"
    sym = A["trade"]["symbol"]
    try:
        with PdfPages(tmp, metadata={"Title": f"Top-down-Analyse {sym}", "Author": "", "Subject": "Paper-Trading"}) as pdf:
            # ---- Seite 1: Monat + Woche
            fig = plt.figure(figsize=(PW, PH), facecolor="white")
            try:
                _header(fig, A, 1, 3, label, TD.headline(td))
                _legend(fig, ["action", "safety", "ov_action", "ov_safety", "bias", "tap", "partial"], 1.22)
                _block(fig, 1.55, 4.9, "1 · Monat – das große Bild: Trend und Hauptlinien", items["M"]["text"], specs["M"], A)
                dl.check("Seite 1")
                _block(fig, 6.5, 4.9, "2 · Woche – baut auf dem Monat auf", items["W"]["text"], specs["W"], A)
                _footer(fig, A); pdf.savefig(fig)
            finally:
                plt.close(fig)
            dl.check("Seite 1")
            # ---- Seite 2: Tag + 4h
            fig = plt.figure(figsize=(PW, PH), facecolor="white")
            try:
                _header(fig, A, 2, 3, label)
                leg = ["action", "safety", "ov_action", "ov_safety", "bias", "tap", "break", "entry", "stop"]
                if A["target"] is not None:
                    leg.append("target")
                if A.get("c_plus") or A["post"] is not None:
                    leg.append("stage2")
                if A["post"] is not None:
                    leg += ["cplus", "swing", "post"]
                _legend(fig, leg, 1.08)
                _block(fig, 1.50, 4.85, "3 · Tag – baut auf der Woche auf", items["D"]["text"], specs["D"], A)
                dl.check("Seite 2")
                note4 = f"{items['4h']['text']} {_levels_text(A)}."
                _block(fig, 6.4, 5.0, "4 · 4h – Handels-Zeitrahmen: hier liegt das Signal", note4, specs["4h"], A)
                _footer(fig, A); pdf.savefig(fig)
            finally:
                plt.close(fig)
            dl.check("Seite 2")
            # ---- Seite 3: 1h + Kurzbeschreibung
            fig = plt.figure(figsize=(PW, PH), facecolor="white")
            try:
                _header(fig, A, 3, 3, label)
                leg3 = ["action", "safety", "ov_action", "ov_safety", "bias", "tap", "break", "entry", "stop"]
                if A["target"] is not None:
                    leg3.append("target")
                if A.get("c_plus"):
                    leg3.append("stage2")
                _legend(fig, leg3, 0.98)
                _block(fig, 1.40, 4.9, "5 · 1h – Verfeinerung des Einstiegs", items["1h"]["text"] + " Gelb unterlegt: die 4h-Signalkerze.", specs["1h"], A)
                fig.text(0.04, 1 - 6.55 / PH, "Kurzbeschreibung des Trades", fontsize=10.5, fontweight="bold", color="#1f2d4d", va="center")
                fig.text(0.045, 1 - 6.78 / PH, _wrap(description, 108, indent=20), fontsize=7.9, family="DejaVu Sans Mono", va="top",
                         linespacing=1.38, bbox=dict(boxstyle="round,pad=0.6", fc="#f9fafb", ec="#d1d5db", lw=0.6))
                _footer(fig, A); pdf.savefig(fig)
            finally:
                plt.close(fig)
        dl.check("Seite 3")
        os.replace(tmp, out_path)
    except BaseException:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)                          # nur die eigene Teildatei
        except OSError:
            pass
        raise
    A["elapsed"] = float(A.get("elapsed", 0.0)) + dl.elapsed()
    return out_path


def _levels_text(A):
    """Einstieg/Stop/1R/Ziel/ATR als ein Satz (Kurznotiz 4h-Chart)."""
    if A["target"] is not None:
        goal = f"Ziel {fprice(A['target'])}"
    elif A.get("c_plus"):
        goal = f"kein festes Ziel – Ausstieg nach C+ (+{fnum(A['c_plus']['stage2_r'], 1)} R bei {fprice(A['stage2_price'])})"
    elif (A.get("trade") or {}).get("exit_mode") == "D":
        goal = "kein festes Ziel – Ausstieg nach D (nachgezogener Stop)"
    else:
        goal = "kein Ziel angegeben"
    return (f"Einstieg {fprice(A['E'])} · Stop {fprice(A['stop0'])} (1R = {fprice(A['risk'])}) · {goal} · ATR {fprice(A['a'])}")
