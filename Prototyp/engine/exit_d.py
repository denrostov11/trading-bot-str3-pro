# -*- coding: utf-8 -*-
"""Variante "Str.3 D": Docht-Stop an der mitwandernden Safety Line, am bestaetigten Zwischentief nachgezogen.

Referenz: Analysen/cplus_pro1/cplus_pro1.py, Variante "D" (Regressionstest: tests/test_exit_d.py gegen die D-Spalten
der 80 Trades in einzeltrades_pro1.csv). Gleiche Einstiege wie Pro.1; nur der Ausstieg unterscheidet sich.

Regeln (vorab festgelegt, NICHT optimiert):
- Intrabar-Stop = Safety Line (Wert am Index der Kerze) - 0,1 ATR (Short gespiegelt). JEDE Beruehrung loest aus,
  auch ein Docht. Ausfuehrung zum Stop-Preis; liegt das Open der Kerze schon jenseits des Stops (Luecke), zum Open.
- Nachziehen: bestaetigtes Zwischentief (Fraktal k=3, Ruecksetzer >= 1 ATR unter dem hoechsten Hoch seit Einstieg;
  Short gespiegelt) -> Stop = Swing - 0,5 ATR. OHNE Stufe-2-Voraussetzung (anders als C+).
- Der SWING-Stop bewegt sich nur in Gewinnrichtung; es gilt der hoehere von Linien-Stop und Swing-Stop. Kein Ziel.
  BEWUSST wie in der Referenz: der Linien-Stop folgt der Safety Line je Kerze (auch eine fallende Linie wuerde ihn
  lockern; ein zusaetzliches Festhalten des Stops wuerde Ergebnisse der 80 Referenz-Trades veraendern).
- Kosten, Slippage und R-Basis wie tracker.simulate_trade (ueber tracker._result_block).

Persistenz/Aufholen: wie exit_cplus - der Zustand ist ein reines dict am Trade; `advance` verarbeitet die Kerzen strikt der
Reihe nach und liest je Kerze j nur Daten mit Index <= j (kein Look-ahead); Aufholen == durchgehender Lauf.
"""
import numpy as np
import pandas as pd

from .exit_cplus import (make_line_fn, _is_swing_low, _add_event, K, SWING_BUF_ATR, MIN_PULLBACK_ATR,
                         EV_TRAIL, EV_EXIT, cost_price_for)

D_BUF_ATR = 0.1
OUT_STOP = "STOP_INTRABAR"
EXIT_REASON_DE = {OUT_STOP: "Stop berührt (Docht genügt)"}


def new_state():
    return {"last_time": None, "stage2": False, "stage3": False, "SW": None, "exit": None, "pending": None,
            "events": [], "mfe": 0.0, "mae": 0.0}


def advance(state, direction, times, O, H, L, C, line_real, e, E, risk, atr, cost_price=None):
    """Verarbeitet alle noch nicht verarbeiteten Kerzen der Reihe nach (Signatur wie exit_cplus.advance; cost_price
    wird nicht gebraucht). Mutiert `state`, gibt die NEUEN Ereignisse zurueck."""
    if state.get("exit"):
        return []
    sg = -1.0 if direction == "SHORT" else 1.0
    n = len(O)
    O = np.asarray(O, float); H = np.asarray(H, float); L = np.asarray(L, float); C = np.asarray(C, float)
    o = O * sg
    h, lw = (-L, -H) if sg < 0 else (H, L)                     # LONG-Raum (Short gespiegelt)
    line = lambda i: sg * line_real(i)
    Ea = sg * E
    ts = [pd.Timestamp(t) for t in times]

    start = e
    if state.get("last_time"):
        lt = pd.Timestamp(state["last_time"])
        idx = [i for i, t in enumerate(ts) if t == lt]
        if idx and idx[0] >= e - 1:
            start = idx[0] + 1
        else:                                                   # Frame passt nicht mehr -> sauberer Neuaufbau
            keep = state["events"]
            state.clear(); state.update(new_state()); state["events"] = keep
            start = e
    new_events = []
    SW = state.get("SW")

    def ev(kind, j, level_long=None, extra=None):
        d = {"id": f"{kind}:{ts[j].isoformat()}" + (f":{round(sg * level_long, 8)}" if level_long is not None else ""),
             "kind": kind, "time": ts[j].isoformat()}
        if level_long is not None:
            d["level"] = sg * level_long
        if extra:
            d.update(extra)
        if _add_event(state, d):
            new_events.append(d)

    for j in range(start, n):
        state["mfe"] = max(state["mfe"], (h[j] - Ea) / risk)
        state["mae"] = max(state["mae"], (Ea - lw[j]) / risk)
        stop = line(j) - D_BUF_ATR * atr
        if SW is not None:
            stop = max(stop, SW)
        if o[j] <= stop:                                        # Luecke jenseits des Stops -> zum Open
            px = o[j]
        elif lw[j] <= stop:                                     # Beruehrung (Docht genuegt) -> zum Stop-Preis
            px = stop
        else:
            px = None
        if px is not None:
            state["exit"] = {"idx": int(j), "time": ts[j].isoformat(), "price": sg * px, "outcome": OUT_STOP,
                             "bars": int(j - e + 1)}
            ev(EV_EXIT, j, None, {"outcome": OUT_STOP, "price": sg * px})
            state["last_time"] = ts[j].isoformat()
            break
        p = j - K                                               # Fraktal erst nach k Folgekerzen bestaetigt
        if p >= e and _is_swing_low(lw, p, e) and h[e:p + 1].max() - lw[p] >= MIN_PULLBACK_ATR * atr:
            lvl = lw[p] - SWING_BUF_ATR * atr
            if SW is None or lvl > SW:
                # nur melden, wenn der WIRKSAME Stop fuer die naechste Kerze dadurch strammer wird
                eff_next = max(line(j + 1) - D_BUF_ATR * atr, SW if SW is not None else -np.inf)
                SW = lvl
                state["stage3"] = True
                if lvl > eff_next:
                    ev(EV_TRAIL, j, lvl, {"swing_time": ts[p].isoformat(), "swing_price": sg * lw[p]})
        state["SW"] = SW
        state["last_time"] = ts[j].isoformat()
    state["SW"] = SW
    return new_events


def current_levels(state, direction, line_real, j, atr):
    """Aktiver Stop fuer Kerze j in ECHTEN Preisen -> (stop, None, 'STOP')."""
    sg = -1.0 if direction == "SHORT" else 1.0
    stop = sg * line_real(j) - D_BUF_ATR * atr
    if state.get("SW") is not None:
        stop = max(stop, state["SW"])
    return sg * stop, None, "STOP"


def execute_pending(state, open_price, open_time):
    return []                                                   # D hat kein wartendes Signal (Stop wird intrabar ausgefuehrt)


def result_for_trade(state, direction, asset_class, atr, E, stop_initial):
    from . import exit_cplus as XC
    r = XC.result_for_trade(state, direction, asset_class, atr, E, stop_initial)
    r["d_swing"] = bool(state.get("stage3"))
    r.pop("cplus_stage2", None); r.pop("cplus_stage3", None); r.pop("cplus_pending_exit", None)
    return r
