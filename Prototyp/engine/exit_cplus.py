# -*- coding: utf-8 -*-
"""C+-Ausstieg (Variante "Str.3 C+"): Schlusskurs-Ausstieg an der mitwandernden Safety Line mit
Notfallnetz, Gewinnschwelle ab +1,5R und Nachziehen an bestaetigten Zwischentiefs/-hochs.
Kein festes Ziel.

Referenzimplementierung: Analysen/cplus_pro1/cplus_pro1.py (Variante "C+"). Regressionstest:
tests/test_exit_cplus.py (80 Trades aus einzeltrades_pro1.csv muessen dieselben Ergebnisse liefern).

Regeln (alle Werte vorab festgelegt, NICHT optimiert):
- Grundausstieg: schliesst eine 4h-Kerze jenseits der Schwelle (Safety Line am Kerzenende, bzw.
  Gewinnschwelle, falls guenstiger), steigt der Bot zum OPEN der naechsten Kerze aus. Docht allein loest nicht aus.
- Notfallnetz: 1 ATR jenseits der aktiven Schwelle, intrabar. Ausfuehrung am Netzpreis; bei Luecke ueber das
  Netz hinaus zum Open der Kerze.
- Stufe 1: unter +1,5R passiert nichts.
- Stufe 2: schliesst eine Kerze >= +1,5R (Einstand + 1,5 x Risiko), gilt die Gewinnschwelle Einstand + Kosten.
- Stufe 3 (erst nach Stufe 2): bestaetigtes Zwischentief (Fraktal k=3, Ruecksetzer >= 1 ATR unter dem
  hoechsten Hoch seit Einstieg; Short gespiegelt) -> Schwelle = Swing - 0,5 ATR.
- Die Schwelle bewegt sich nur in Gewinnrichtung; es gilt der guenstigere Wert aus Safety Line und Schwelle.

Persistenz/Aufholen: der Zustand (Stufe, Schwelle, letzte verarbeitete Kerze, Ereignisse) liegt als reines
dict am Trade. `advance` verarbeitet die Kerzen strikt der Reihe nach und liest je Kerze j nur Daten mit
Index <= j (kein Look-ahead). Ein Aufholen nach Ausfall liefert exakt dasselbe Ergebnis wie ein Durchlauf.
"""
import numpy as np
import pandas as pd

STAGE2_R = 1.5
SWING_BUF_ATR = 0.5
NET_ATR = 1.0
MIN_PULLBACK_ATR = 1.0
K = 3

OUT_NET = "NOTFALLNETZ"
OUT_LINE = "SAFETY_CLOSE"
OUT_PROFIT = "GEWINNSCHWELLE_CLOSE"
EXIT_REASON_DE = {
    OUT_NET: "Notfallnetz",
    OUT_LINE: "Schlusskurs jenseits der Safety Line",
    OUT_PROFIT: "Schlusskurs jenseits der Gewinnschwelle",
}

EV_STAGE2 = "STAGE2"
EV_TRAIL = "TRAIL"
EV_EXIT = "EXIT"


def new_state():
    """Leerer, JSON-serialisierbarer Zustand."""
    return {"last_time": None, "stage2": False, "stage3": False, "P": None,
            "pending": None, "exit": None, "events": [], "mfe": 0.0, "mae": 0.0}


def make_line_fn(safety_line, signal_idx):
    """Safety-Linie als Funktion des Kerzenindex j im AKTUELLEN Frame. safety_line = {d0,p0,d1,p1} mit
    d = Kerzenversatz relativ zur Signalkerze (negativ = davor); signal_idx = Index der Signalkerze im Frame."""
    d0, p0 = float(safety_line["d0"]), float(safety_line["p0"])
    d1, p1 = float(safety_line["d1"]), float(safety_line["p1"])
    k = int(signal_idx)

    def line(j):
        return p0 + (p1 - p0) * ((j - k) - d0) / (d1 - d0)
    return line


def _is_swing_low(Lw, i, e, k=K):
    """Fraktal: Tief[i] ist das niedrigste der k Kerzen davor und der k Kerzen danach; i >= Einstiegskerze."""
    if i < e or i - k < 0:
        return False
    return Lw[i] <= Lw[i - k:i].min() and Lw[i] <= Lw[i + 1:i + k + 1].min()


def _add_event(state, ev):
    if not any(x["id"] == ev["id"] for x in state["events"]):
        state["events"].append(ev)
        return True
    return False


def advance(state, direction, times, O, H, L, C, line_real, e, E, risk, atr, cost_price):
    """Verarbeitet alle noch nicht verarbeiteten Kerzen (Index > last_time) der Reihe nach.
    Arrays in ECHTEN Preisen (numpy), `times` = Liste der Kerzenbeginne (UTC), line_real(j) = Safety-Linie (echt),
    e = Index der Einstiegskerze, E = Einstiegskurs (entry_open), risk = |E - Stop|, cost_price = Kosten in Preis.
    Mutiert `state` und gibt die NEUEN Ereignisse zurueck. Abgeschlossener Zustand bleibt unveraendert."""
    if state.get("exit"):
        return []
    short = direction == "SHORT"
    sg = -1.0 if short else 1.0
    n = len(O)
    O = np.asarray(O, float); H = np.asarray(H, float); L = np.asarray(L, float); C = np.asarray(C, float)
    # LONG-Raum (Short gespiegelt: Hoch' = -Tief, Tief' = -Hoch)
    o, c = O * sg, C * sg
    h, lw = (-L, -H) if short else (H, L)
    line = lambda i: sg * line_real(i)
    Ea = sg * E
    ts = [pd.Timestamp(t) for t in times]

    # Startindex
    start = e
    rebuild = False
    if state.get("last_time"):
        lt = pd.Timestamp(state["last_time"])
        idx = [i for i, t in enumerate(ts) if t == lt]
        if idx and idx[0] >= e - 1:
            start = idx[0] + 1
        else:
            rebuild = True
    pend_idx = None
    if state.get("pending") is not None and not rebuild:
        # wartendes Ausstiegssignal ueber den ZEITSTEMPEL der Signalkerze aufloesen (nie ueber einen gespeicherten Index:
        # eine Cache-Auffuellung kann den Frame verschieben)
        pt = state["pending"].get("time")
        hit = [i for i, t in enumerate(ts) if pt is not None and t == pd.Timestamp(pt)]
        if hit:
            pend_idx = hit[0]
        else:
            rebuild = True
    if rebuild:                                 # Frame passt nicht mehr -> sauberer Neuaufbau aus der Einstiegskerze
        keep = state["events"]
        state.update(new_state()); state["events"] = keep
        start = e
    new_events = []
    P = state["P"]

    def ev(kind, j, level_long=None, extra=None):
        d = {"id": f"{kind}:{ts[j].isoformat()}" + (f":{round(sg * level_long, 8)}" if level_long is not None else ""),
             "kind": kind, "time": ts[j].isoformat()}
        if level_long is not None:
            d["level"] = sg * level_long
        if extra:
            d.update(extra)
        if _add_event(state, d):
            new_events.append(d)

    def close(j_exit, price_long, outcome, j_signal=None):
        state["exit"] = {"idx": int(j_exit), "time": ts[j_exit].isoformat(), "price": sg * price_long,
                         "outcome": outcome, "bars": int(j_exit - e + 1)}
        state["pending"] = None
        ev(EV_EXIT, j_exit, None, {"outcome": outcome, "price": sg * price_long})

    # Ausstieg-Signal der Vorkerze wartet auf das Open der naechsten Kerze
    if state.get("pending") is not None and pend_idx is not None:
        pj = pend_idx
        if pj + 1 < n:
            close(pj + 1, o[pj + 1], state["pending"]["outcome"])
            state["last_time"] = ts[pj + 1].isoformat()
            return new_events
        return new_events

    for j in range(start, n):
        # MFE/MAE in R (informativ)
        state["mfe"] = max(state["mfe"], (h[j] - Ea) / risk)
        state["mae"] = max(state["mae"], (Ea - lw[j]) / risk)
        thr, who = line(j), "LINE"
        if P is not None and P > thr:
            thr, who = P, "PROFIT"
        net = thr - NET_ATR * atr
        if o[j] <= net:                                        # Luecke ueber das Netz -> zum Open
            close(j, o[j], OUT_NET); state["last_time"] = ts[j].isoformat(); break
        if lw[j] <= net:                                       # Netz intrabar -> zum Netzpreis
            close(j, net, OUT_NET); state["last_time"] = ts[j].isoformat(); break
        if c[j] < thr:                                         # Schlusskurs jenseits der Schwelle
            outcome = OUT_LINE if who == "LINE" else OUT_PROFIT
            if j + 1 < n:
                close(j + 1, o[j + 1], outcome)
                state["last_time"] = ts[j + 1].isoformat()
            else:
                state["pending"] = {"idx": int(j), "time": ts[j].isoformat(), "outcome": outcome, "bars": int(j - e + 2)}
                state["last_time"] = ts[j].isoformat()
            break
        # Stufe 2 (Schlusskurs-basiert)
        if c[j] - Ea >= STAGE2_R * risk:
            lvl = Ea + cost_price
            if P is None:
                P = lvl
                state["stage2"] = True
                ev(EV_STAGE2, j, P)
            else:
                if not state["stage2"]:
                    state["stage2"] = True
                if lvl > P:                                     # Referenz: P = max(P, E+Kosten)
                    P = lvl
        # Stufe 3: Fraktal erst nach k Folgekerzen bestaetigt
        p = j - K
        if state["stage2"] and p >= e and _is_swing_low(lw, p, e):
            if h[e:p + 1].max() - lw[p] >= MIN_PULLBACK_ATR * atr:
                lvl = lw[p] - SWING_BUF_ATR * atr
                if lvl > P:
                    P = lvl; state["stage3"] = True
                    ev(EV_TRAIL, j, P, {"swing_time": ts[p].isoformat(), "swing_price": sg * lw[p]})
        state["P"] = P
        state["last_time"] = ts[j].isoformat()
    state["P"] = P
    return new_events


def execute_pending(state, open_price, open_time):
    """Fuehrt ein wartendes Ausstiegssignal zum bereits bekannten OPEN der naechsten (gerade eroeffneten, noch laufenden)
    Kerze aus. Es fliessen NUR Open-Kurs und -Zeit ein - High/Low/Close der laufenden Kerze bleiben unberuehrt (kein
    Look-ahead). Gleiches Ergebnis (Preis, Zeit, Ereignis-ID) wie die spaetere Verarbeitung ueber die abgeschlossene Kerze.
    -> Liste der neuen Ereignisse (leer, wenn nichts wartet)."""
    pend = state.get("pending")
    if not pend or state.get("exit"):
        return []
    t = pd.Timestamp(open_time)
    state["exit"] = {"idx": int(pend["idx"]) + 1, "time": t.isoformat(), "price": float(open_price),
                     "outcome": pend["outcome"], "bars": int(pend.get("bars", 1))}
    state["pending"] = None
    ev = {"id": f"{EV_EXIT}:{t.isoformat()}", "kind": EV_EXIT, "time": t.isoformat(), "outcome": pend["outcome"],
          "price": float(open_price)}
    return [ev] if _add_event(state, ev) else []


def current_levels(state, direction, line_real, j, atr):
    """Aktive Schwelle (Schlusskurs-Ausstieg) und Notfallnetz fuer Kerze j in ECHTEN Preisen.
    Gibt (schwelle, netz, quelle) mit quelle 'LINE'/'PROFIT'."""
    short = direction == "SHORT"
    sg = -1.0 if short else 1.0
    thr, who = sg * line_real(j), "LINE"
    P = state.get("P")
    if P is not None and P > thr:
        thr, who = P, "PROFIT"
    net = thr - NET_ATR * atr
    return sg * thr, sg * net, who


def result_for_trade(state, direction, asset_class, atr, E, stop_initial):
    """Baut das Ergebnis-dict (gleiche Kosten-/R-Formeln wie tracker.simulate_trade ueber _result_block).
    Geschlossen -> dict mit status 'closed'; sonst {'status': 'open', ...}."""
    from . import tracker as T
    ex = state.get("exit")
    risk = abs(E - stop_initial)
    if risk <= 0:
        return {"error": "ZERO_RISK"}
    slip = T.SLIP_ATR_PER_SIDE * atr
    fill = E - slip if direction == "SHORT" else E + slip
    if not ex:
        return {"status": "open", "mfe_r": round(state.get("mfe", 0.0), 3), "mae_r": round(state.get("mae", 0.0), 3),
                "be_moved": False, "stop_current": None, "duration_bars": 0,
                "cplus_stage2": bool(state.get("stage2")), "cplus_stage3": bool(state.get("stage3")),
                "cplus_pending_exit": state.get("pending")}
    r = T._result_block(direction, asset_class, atr, E, fill, risk, slip, stop_initial,
                        stop_initial, 0.0, ex["price"], ex["outcome"], False,
                        state.get("mfe", 0.0), state.get("mae", 0.0), False, ex["bars"])
    r["cplus_stage2"] = bool(state.get("stage2"))
    r["cplus_stage3"] = bool(state.get("stage3"))
    return r


def cost_price_for(direction, asset_class, atr, E):
    """Kosten in Preiseinheiten (Slippage 2 Seiten + Gebuehren 2 Seiten) - Basis der Gewinnschwelle."""
    from . import tracker as T
    return 2 * T.SLIP_ATR_PER_SIDE * atr + T.cost_fraction(asset_class) * 2 * E
