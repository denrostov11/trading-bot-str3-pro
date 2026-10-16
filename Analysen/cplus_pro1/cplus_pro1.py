# -*- coding: utf-8 -*-
"""Analyse: Haette sich Pro.1 im Zwei-Monats-Test mit dem Ausstieg "C+" verbessert oder verschlechtert?

NUR LESEN/RECHNEN. Arbeitet ausschliesslich auf der Kopie in daten_kopie/ (kopie_erstellen.py).
Der Einstieg jedes Pro.1-Trades bleibt identisch; nur der Ausstieg wird auf den 4h-Kerzen der Engine
(1h -> 4h, Anker 00:00 UTC, nur finale Kerzen) neu simuliert. Kosten/Prozent kommen aus
engine.tracker._result_block (identische Formeln wie im Test). R bezieht sich immer auf das
URSPRUENGLICHE Risiko |entry_open - baseline_stop|.

Varianten
  IST  tatsaechliches Testergebnis (zur Kontrolle zusaetzlich mit tracker.simulate_trade nachgerechnet)
  B    Schlusskurs-Ausstieg durch die Safety Line (Ausfuehrung Open der naechsten Kerze) + Notfallnetz 1 ATR
       jenseits der Linie (intrabar; Luecke -> Open). Kein Ziel, kein Nachziehen.
  C+   wie B, plus Stufe 2 (Kerze SCHLIESST >= +1,5R -> Gewinnschwelle Einstand+Kosten, Schlusskurs-basiert)
       und Stufe 3 (bestaetigtes Zwischentief/-hoch, Fraktal k=3, Ruecksetzer >= 1 ATR -> Schwelle = Swing -/+ 0,5 ATR).
       Stufe 3 erst nach Stufe 2, Schwelle nur in Gewinnrichtung, es gilt die guenstigere von Safety Line und
       Gewinnschwelle; unter der aktiven Schwelle liegt ein Notfallnetz 1 ATR dahinter (intrabar, Luecke -> Open).
  D    Intrabar-Stop 0,1 ATR jenseits der laufenden Safety Line, zusaetzlich am Swing (Stufe-3-Logik: Fraktal k=3,
       Ruecksetzer >= 1 ATR, Swing -/+ 0,5 ATR; OHNE Stufe-2-Voraussetzung) nachgezogen; jede Beruehrung loest aus
       (Luecke -> Open). Kein Ziel.
Parameter (1,5R / 0,5 ATR / 1 ATR / 0,1 ATR) sind vorab festgelegt und werden NICHT optimiert.
"""
import os, sys, json, csv
from datetime import datetime
import numpy as np
import pandas as pd

PROTO = r"C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp"
sys.path.insert(0, PROTO)
from engine import aggregate_4h                      # noqa: E402  (nur lesend genutzt)
from engine import tracker as T                      # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "daten_kopie")
STAGE2_R, SWING_BUF_ATR, NET_ATR, D_BUF_ATR, MIN_PULLBACK_ATR, K = 1.5, 0.5, 1.0, 0.1, 1.0, 3
VARS = ["IST", "B", "C+", "D"]


def safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in s)


_fin_cache = {}


def fin_bars(sym):
    if sym not in _fin_cache:
        df = pd.read_csv(os.path.join(DATA, "data_cache", safe(sym) + "__1h.csv"))
        _fin_cache[sym] = aggregate_4h.final_only(aggregate_4h.aggregate(df)).reset_index(drop=True)
    return _fin_cache[sym]


# ----------------------------------------------------------------- Simulation (in "LONG-Raum")
def _is_swing_low(Lw, i, e, k=K):
    """Fraktal: Tief[i] ist das niedrigste der k Kerzen davor und der k Kerzen danach; i >= Einstiegskerze."""
    if i < e or i - k < 0:
        return False
    return Lw[i] <= Lw[i - k:i].min() and Lw[i] <= Lw[i + 1:i + k + 1].min()


def simulate(variant, O, H, Lw, C, line, e, E, risk, a, cost_price):
    """Alle Arrays in LONG-Orientierung (Short vorab gespiegelt). line(i) = Safety-Linienwert (gespiegelt).
    Rueckgabe dict: status ('closed'/'open'), exit_idx, exit_price, outcome, stage2, stage3."""
    n = len(O)
    res = {"status": "open", "exit_idx": None, "exit_price": None, "outcome": "", "stage2": False, "stage3": False}
    P = None            # Gewinnschwelle (C+)
    SW = None           # Swing-Schwelle (D)
    top_since = H[e]    # hoechstes Hoch seit Einstieg
    for j in range(e, n):
        top_since = max(top_since, H[j])
        if variant in ("B", "C+"):
            thr, who = line(j), "LINE"
            if variant == "C+" and P is not None and P > thr:
                thr, who = P, "PROFIT"
            net = thr - NET_ATR * a
            if O[j] <= net:                                    # Luecke ueber das Netz -> realistisch zum Open
                res.update(status="closed", exit_idx=j, exit_price=O[j], outcome="NOTFALLNETZ"); return res
            if Lw[j] <= net:
                res.update(status="closed", exit_idx=j, exit_price=net, outcome="NOTFALLNETZ"); return res
            if C[j] < thr:                                     # Schlusskurs jenseits der Schwelle
                if j + 1 < n:
                    res.update(status="closed", exit_idx=j + 1, exit_price=O[j + 1],
                               outcome="SAFETY_CLOSE" if who == "LINE" else "GEWINNSCHWELLE_CLOSE")
                else:
                    res["outcome"] = "AUSSTIEG_SIGNAL_OFFEN"   # Ausfuehrung waere erst zur naechsten Kerze
                return res
            if variant == "C+":
                if C[j] - E >= STAGE2_R * risk:                # Stufe 2 (Schlusskurs-basiert)
                    res["stage2"] = True
                    P = max(P, E + cost_price) if P is not None else E + cost_price
                p = j - K                                       # Fraktal erst nach k Folgekerzen bestaetigt
                if res["stage2"] and p >= e and _is_swing_low(Lw, p, e):
                    if H[e:p + 1].max() - Lw[p] >= MIN_PULLBACK_ATR * a:
                        lvl = Lw[p] - SWING_BUF_ATR * a
                        if lvl > P:
                            P = lvl; res["stage3"] = True
        elif variant == "D":
            stop = line(j) - D_BUF_ATR * a
            if SW is not None:
                stop = max(stop, SW)
            if O[j] <= stop:
                res.update(status="closed", exit_idx=j, exit_price=O[j], outcome="STOP_INTRABAR"); return res
            if Lw[j] <= stop:
                res.update(status="closed", exit_idx=j, exit_price=stop, outcome="STOP_INTRABAR"); return res
            p = j - K
            if p >= e and _is_swing_low(Lw, p, e) and H[e:p + 1].max() - Lw[p] >= MIN_PULLBACK_ATR * a:
                lvl = Lw[p] - SWING_BUF_ATR * a
                if SW is None or lvl > SW:
                    SW = lvl; res["stage3"] = True
    return res


def to_real(x, short):
    return -x if short else x


def analyse_trade(t, cand):
    """Alle Varianten fuer EINEN Trade. t = Trade-dict (trades.json), cand = Ledger-Kandidat."""
    sym, direction = t["symbol"], t["direction"]
    short = direction == "SHORT"
    sn = cand["snapshot"]
    f = fin_bars(sym)
    times = pd.to_datetime(f["Time"], utc=True)
    k = int(times[times == pd.Timestamp(t["signal_time"])].index[0])
    e = k + 1                                                    # Einstiegskerze (wie cycle.update_open_trades)
    out = {"trade": t, "sym": sym, "direction": direction, "e": e, "n": len(f)}
    if e >= len(f):
        out["skip"] = "Einstiegskerze liegt noch nicht vor"
        return out
    i0, p0, i1, p1 = sn["safety_anchor"][:4]
    stop0 = float(t["stop_initial"])
    # Index-Kalibrierung: Aus baseline_stop = Linie(bb+4) folgt der damalige Index der Bruchkerze (bb_then).
    # Meist = k (d = 0). In den ersten Testtagen (Krypto-Cache wurde spaeter rueckwaerts aufgefuellt) lag er um
    # d Kerzen tiefer; dann wird die Linie um d verschoben, damit sie fuer alle Folgekerzen stimmt.
    bb_then = i0 + (stop0 - p0) * (i1 - i0) / (p1 - p0) - 4 if p1 != p0 else float(k)
    d = 0 if abs(bb_then - k) < 0.4 else int(round(k - bb_then))
    out["index_shift"] = d
    line_real = lambda i: p0 + (p1 - p0) * (i - d - i0) / (i1 - i0)
    out["stop_check"] = abs(line_real(k + 4) - stop0)           # Linie bei Bruch+4 muss baseline_stop ergeben
    a = float(sn["atr"])
    E_bar = float(f["Open"].iloc[e])
    r_t = t.get("result") or {}
    # Einstieg identisch zum Test: gespeicherter entry_open (geschlossene Trades) bzw. entry_price (offene Trades)
    E = float(r_t["entry_open"]) if r_t.get("entry_open") is not None else float(t["entry_price"])
    out["E_bar"] = E_bar
    risk = abs(E - stop0)
    out.update(a=a, E=E, risk=risk, stop0=stop0, asset=t["asset_class"])
    sg = -1.0 if short else 1.0
    O, H, Lw, C = (f["Open"].values * sg, f["High"].values * sg, f["Low"].values * sg, f["Close"].values * sg)
    if short:
        H, Lw = (-f["Low"].values), (-f["High"].values)          # Spiegelung: Hoch'=-Tief, Tief'=-Hoch
    line = lambda i: sg * line_real(i)
    fee = T.cost_fraction(t["asset_class"])
    cost_price = 2 * T.SLIP_ATR_PER_SIDE * a + fee * 2 * E
    last_close = float(f["Close"].iloc[-1])
    out["last_time"] = str(times.iloc[-1])
    out["res"] = {}
    for v in ("B", "C+", "D"):
        s = simulate(v, O, H, Lw, C, line, e, sg * E, risk, a, cost_price)
        r = {"status": s["status"], "stage2": s["stage2"], "stage3": s["stage3"], "outcome": s["outcome"]}
        if s["status"] == "closed":
            xp = sg * s["exit_price"]
            fill = E - T.SLIP_ATR_PER_SIDE * a if short else E + T.SLIP_ATR_PER_SIDE * a
            rb = T._result_block(direction, t["asset_class"], a, E, fill, risk, T.SLIP_ATR_PER_SIDE * a, stop0, stop0,
                                 0.0, xp, s["outcome"], False, 0.0, 0.0, False, s["exit_idx"] - e + 1)
            r.update(exit_idx=s["exit_idx"], exit_time=str(times.iloc[s["exit_idx"]]), exit_price=xp,
                     netto_r=rb["netto_r"], net_pct=rb["net_return_pct"], brutto_r=rb["brutto_r"],
                     bars=s["exit_idx"] - e + 1)
        out["res"][v] = r
    # unrealisiert (nur Anzeige, nicht gewertet): Mark-to-Market zum letzten Schlusskurs
    mm = T.mark_to_market(direction, t["asset_class"], a, E, stop0, 0.0, last_close, dur=len(f) - e)
    out["unreal_r"], out["unreal_pct"] = mm.get("netto_r"), mm.get("net_return_pct")

    # IST: gespeichert + Nachrechnung mit dem Engine-Tracker (BE-0, Ziel) auf den eigenen Kerzen
    bars = [{"High": float(f["High"].iloc[i]), "Low": float(f["Low"].iloc[i]),
             "Open": float(f["Open"].iloc[i]), "Close": float(f["Close"].iloc[i])} for i in range(e, len(f))]
    rs = T.simulate_trade(direction, t["asset_class"], a, E, stop0, float(t["target"]), bars, be_mode="BE-0")
    out["ist_resim"] = rs
    if t["status"] == "closed":
        r = t["result"]
        out["res"]["IST"] = {"status": "closed", "outcome": r["outcome"], "netto_r": r["netto_r"],
                             "net_pct": r["net_return_pct"], "exit_time": r.get("exit_time"), "exit_price": r["exit_price"],
                             "bars": r.get("duration_bars"), "stage2": False, "stage3": False}
    else:
        out["res"]["IST"] = {"status": "open", "outcome": "", "stage2": False, "stage3": False}
    return out


# ----------------------------------------------------------------- Kennzahlen
def stats(rows, var, subset=None):
    cl = [r for r in rows if r["res"][var]["status"] == "closed" and (subset is None or r["trade"]["trade_id"] in subset)]
    op = [r for r in rows if r["res"][var]["status"] == "open" and (subset is None or r["trade"]["trade_id"] in subset)]
    nr = [r["res"][var]["netto_r"] for r in cl]
    pc = [r["res"][var]["net_pct"] for r in cl]
    w = sum(1 for x in nr if x > 0)
    best = max(cl, key=lambda r: r["res"][var]["netto_r"]) if cl else None
    worst = min(cl, key=lambda r: r["res"][var]["netto_r"]) if cl else None
    return {
        "closed": len(cl), "open": len(op), "win": w, "loss": len(cl) - w,
        "hit": (w / len(cl) * 100) if cl else None, "sum_r": sum(nr), "sum_pct": sum(pc),
        "avg_r": (sum(nr) / len(cl)) if cl else None,
        "best": (best["sym"], best["res"][var]["netto_r"]) if best else None,
        "worst": (worst["sym"], worst["res"][var]["netto_r"]) if worst else None,
        "net_exits": sum(1 for r in cl if r["res"][var]["outcome"] == "NOTFALLNETZ"),
        "stage2": sum(1 for r in rows if r["res"][var].get("stage2") and (subset is None or r["trade"]["trade_id"] in subset)),
        "stage3": sum(1 for r in rows if r["res"][var].get("stage3") and (subset is None or r["trade"]["trade_id"] in subset)),
        "unreal_open_r": sum(r["unreal_r"] for r in op if r.get("unreal_r") is not None),
    }


def main():
    allt = json.load(open(os.path.join(DATA, "trades.json"), encoding="utf-8"))
    led = json.load(open(os.path.join(DATA, "ledger.json"), encoding="utf-8"))
    cand = {c["parent_signal_id"]: c for c in led["candidates"]}
    trades = [t for t in allt if t["strategy_id"] == "Str.3 Pro.1"]
    rows, skipped = [], []
    for t in trades:
        if t["status"] == "pending_fill":
            skipped.append((t["symbol"], t["signal_time"], "wartet auf Einstieg (pending_fill)")); continue
        r = analyse_trade(t, cand[t["parent_signal_id"]])
        if r.get("skip"):
            skipped.append((t["symbol"], t["signal_time"], r["skip"])); continue
        rows.append(r)

    # ---- Plausibilitaet
    chk = {}
    chk["n_trades"] = len(rows)
    chk["stop_check_max_rel"] = max(r["stop_check"] / r["risk"] for r in rows)
    chk["entry_vs_bar_mismatch"] = [(r["sym"], r["trade"]["signal_time"][:16]) for r in rows
                                    if abs(r["E_bar"] - r["E"]) > 1e-4 * abs(r["E"])]
    chk["index_shifted"] = [(r["sym"], r["trade"]["signal_time"][:16], r["index_shift"]) for r in rows if r["index_shift"]]
    mism = []
    for r in rows:
        t, rs = r["trade"], r["ist_resim"]
        if t["status"] == "closed":
            if rs.get("status") != "closed" or rs["outcome"] != t["result"]["outcome"] or abs(rs["netto_r"] - t["result"]["netto_r"]) > 0.01:
                mism.append((r["sym"], t["signal_time"], t["result"]["outcome"], t["result"]["netto_r"], rs.get("outcome"), rs.get("netto_r")))
        elif rs.get("status") == "closed":
            mism.append((r["sym"], t["signal_time"], "open", None, rs.get("outcome"), rs.get("netto_r")))
    chk["ist_resim_mismatch"] = mism
    ist = stats(rows, "IST")
    chk["ist"] = ist

    S = {v: stats(rows, v) for v in VARS}
    # fairer Vergleich: in ALLEN Varianten geschlossen
    fair_ids = {r["trade"]["trade_id"] for r in rows if all(r["res"][v]["status"] == "closed" for v in VARS)}
    F = {v: stats(rows, v, fair_ids) for v in VARS}

    fair3_ids = {r["trade"]["trade_id"] for r in rows if all(r["res"][v]["status"] == "closed" for v in ("IST", "C+", "D"))}
    F3 = {v: stats(rows, v, fair3_ids) for v in ("IST", "C+", "D")}
    pair_ids = {r["trade"]["trade_id"] for r in rows if r["res"]["IST"]["status"] == "closed" and r["res"]["C+"]["status"] == "closed"}
    PR = {v: stats(rows, v, pair_ids) for v in ("IST", "C+")}
    diffs = [r["res"]["C+"]["netto_r"] - r["res"]["IST"]["netto_r"] for r in rows if r["trade"]["trade_id"] in pair_ids]
    pairs = {"n": len(diffs), "better": sum(1 for x in diffs if x > 0.01), "worse": sum(1 for x in diffs if x < -0.01),
             "equal": sum(1 for x in diffs if abs(x) <= 0.01), "median": float(np.median(diffs)) if diffs else None}
    conc = {}
    for v in ("IST", "B", "C+", "D"):
        cl = sorted([float(r["res"][v]["netto_r"]) for r in rows if r["res"][v]["status"] == "closed"], reverse=True)
        conc[v] = {"sum": sum(cl), "top3": cl[:3], "ohne_top3": sum(cl[3:])}
    cls = {}
    for v in ("IST", "B", "C+", "D"):
        for r in rows:
            if r["res"][v]["status"] == "closed":
                cls.setdefault(v, {}).setdefault(r["asset"], [0, 0.0])
                cls[v][r["asset"]][0] += 1
                cls[v][r["asset"]][1] += float(r["res"][v]["netto_r"])

    # ---- Top-5 Unterschiede C+ vs IST (beide geschlossen)
    both = [r for r in rows if r["res"]["IST"]["status"] == "closed" and r["res"]["C+"]["status"] == "closed"]
    both.sort(key=lambda r: -abs(r["res"]["C+"]["netto_r"] - r["res"]["IST"]["netto_r"]))
    top5 = both[:5]

    return {"rows": rows, "skipped": skipped, "chk": chk, "S": S, "F": F, "fair_n": len(fair_ids), "top5": top5,
            "F3": F3, "fair3_n": len(fair3_ids), "PR": PR, "pairs": pairs, "conc": conc, "cls": cls,
            "last_time": rows[0]["last_time"] if rows else ""}


def fx(v, d=2, sign=False):
    if v is None:
        return "–"
    s = f"{v:+.{d}f}" if sign else f"{v:.{d}f}"
    return s.replace(".", ",").replace("-", "−")


def write_csv(rows, path):
    cols = ["symbol", "richtung", "klasse", "signal_utc", "einstieg_utc", "entry_open", "stop_baseline", "risiko", "atr"]
    for v in VARS:
        cols += [f"{v}_status", f"{v}_ausstieg", f"{v}_exit_utc", f"{v}_exit_preis", f"{v}_netto_r", f"{v}_netto_pct"]
    cols += ["C+_stufe2", "C+_stufe3", "D_swing_genutzt", "unrealisiert_netto_r_letzter_kurs"]
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols)
        for r in rows:
            t = r["trade"]
            line = [r["sym"], r["direction"], r["asset"], t["signal_time"], t.get("entry_time"), f"{r['E']:.6g}",
                    f"{r['stop0']:.6g}", f"{r['risk']:.6g}", f"{r['a']:.6g}"]
            for v in VARS:
                x = r["res"][v]
                line += [x["status"], x.get("outcome", ""), x.get("exit_time", ""),
                         "" if x.get("exit_price") is None else f"{x['exit_price']:.6g}",
                         "" if x.get("netto_r") is None else f"{x['netto_r']:.3f}".replace(".", ","),
                         "" if x.get("net_pct") is None else f"{x['net_pct']:.3f}".replace(".", ",")]
            line += [int(r["res"]["C+"]["stage2"]), int(r["res"]["C+"]["stage3"]), int(r["res"]["D"]["stage3"]),
                     "" if r.get("unreal_r") is None else f"{r['unreal_r']:.3f}".replace(".", ",")]
            w.writerow(line)


if __name__ == "__main__":
    R = main()
    S, F = R["S"], R["F"]
    for name, X in (("ALLE", S), (f"FAIR (n={R['fair_n']})", F)):
        print("==", name)
        for v in VARS:
            s = X[v]
            print(f"{v:4} gesch {s['closed']:3} offen {s['open']:3} G/V {s['win']}/{s['loss']} Treffer {fx(s['hit'],1)}% "
                  f"R {fx(s['sum_r'],2,True)} % {fx(s['sum_pct'],1,True)} avgR {fx(s['avg_r'],3,True)} netz {s['net_exits']} "
                  f"st2 {s['stage2']} st3 {s['stage3']} best {s['best']} worst {s['worst']} unreal {fx(s['unreal_open_r'],2,True)}")
    print(R["chk"]["n_trades"], R["chk"]["stop_check_max_rel"], R["chk"]["entry_vs_bar_mismatch"], R["chk"]["index_shifted"], R["chk"]["ist_resim_mismatch"])
    print(R["skipped"])
    write_csv(R["rows"], os.path.join(HERE, "einzeltrades_pro1.csv"))
