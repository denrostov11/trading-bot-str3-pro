# -*- coding: utf-8 -*-
"""FIKTIVER Beispiel-Bericht (47 Tage, 23 Trades) - Charts folgen EXAKT den
Strategie-3-Kriterien: Action-Line 3+ Wick-Taps / >=6 Kerzen Abstand / <45 Grad,
Safety Line gegenlaeufig intakt mit >=2 Taps, Stop = Safety-Projektion 4. Kerze."""
import os, time, random
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from alert_bot import build_report, tg_document, val_fmt, TRADES_DIR, PROTO

random.seed(47); np.random.seed(47)
NOW = time.time(); DAY = 86400

INSTR = [("Gold GC", 4120), ("WTI Rohoel CL", 84.5), ("Erdgas NG", 3.05), ("Silber SI", 52.3),
         ("Platin PL", 1655), ("EUR/USD", 1.089), ("USD/JPY", 161.2), ("GBP/JPY", 204.6),
         ("Kaffee KC", 341.0), ("Mais ZC", 452.0), ("Zucker SB", 19.4), ("Baumwolle CT", 71.2),
         ("Bitcoin BTC", 64200), ("Ethereum ETH", 3350), ("Solana SOL", 148.5), ("Cardano ADA", 0.462),
         ("Nvidia NVDA", 128.4), ("Apple AAPL", 226.1), ("Microsoft MSFT", 442.0), ("DAX Futures", 18650),
         ("RTY Russell2000", 2148), ("Sojabohnen ZS", 1042), ("EUR/CAD", 1.612)]
# 96 Trades ueber 177 Tage, 52 Gewinner (etwas mehr als die Haelfte positiv)
N_TRADES, N_WINS, N_DAYS = 96, 52, 177
OUTCOMES = ["W"] * N_WINS + ["L"] * (N_TRADES - N_WINS)
random.shuffle(OUTCOMES)

TAPS_A = [10, 38, 66, 94, 122]   # 5 Action-Taps, 28 Kerzen Abstand (>=6 erfuellt)
TAPS_S = [24, 80, 118]           # 3 Safety-Taps, Gegenrichtung
N_PRE = 130

def synth_composite(t, idx):
    """Konstruiert den Chart UM die Trendlinien herum:
    Keil aus Action- und Safety-Line, Wicks beruehren die Linien an den Taps."""
    entry = t["entry"]; short = t["direction"] == "SHORT"
    rr = t["rr"]; win = t["outcome"] == "ZIEL"
    n_post = max(14, int(t["days"] * 6)); n = N_PRE + n_post + 1
    x = np.arange(n)
    # --- Keil-Geometrie (Steigung ~2.5 % ueber 130 Kerzen -> flach, <45 Grad) ---
    rise = entry * 0.025
    off_b = entry * 0.003                      # Bruch-Abstand der letzten Kerze zur Linie
    gap0, gap1 = entry * 0.050, entry * 0.013  # Keil laeuft zusammen; Stop-Distanz bleibt < 2 %
    gap = gap0 + (gap1 - gap0) * np.clip(x, 0, N_PRE) / N_PRE
    if short:   # Action = steigende Support-Linie, Safety = fallende Resistance darueber
        act = (entry + off_b) - rise * (N_PRE - x) / N_PRE
        saf = act + gap
        lo_line, hi_line = act, saf
    else:       # Action = fallende Resistance-Linie, Safety = steigende Support darunter
        act = (entry - off_b) + rise * (N_PRE - x) / N_PRE
        saf = act - gap
        lo_line, hi_line = saf, act
    # --- Kurs pendelt IM Keil; osc=0 beruehrt untere, osc=1 obere Linie ---
    osc = 0.5 + 0.38 * np.sin(2 * np.pi * x / 47 + 1.3) + np.random.normal(0, 0.05, n)
    osc = np.clip(osc, 0.12, 0.88)
    a_taps_osc = 0.06 if short else 0.94       # Action-Taps: Koerper nahe der Action-Line
    s_taps_osc = 0.94 if short else 0.06
    for i in TAPS_A: osc[i] = a_taps_osc
    for i in TAPS_S: osc[i] = s_taps_osc
    close = lo_line + osc * (hi_line - lo_line)
    # --- Bruch & Nachher-Verlauf: Stop = Safety-Projektion an Kerze N_PRE+4 ---
    sgn = -1 if short else 1
    stop = float(saf[min(n - 1, N_PRE + 4)])
    risk = abs(entry - stop)
    target = entry + sgn * rr * risk
    exitp = target if win else stop
    close[N_PRE] = entry                        # Bruchkerze schliesst jenseits der Action-Line
    for i in range(N_PRE + 1, n):
        w = (i - N_PRE) / n_post
        close[i] = entry + (exitp - entry) * w + np.random.normal(0, risk * 0.10)
    close[-1] = exitp
    m = risk * 0.06
    close[N_PRE + 1:n - 1] = np.clip(close[N_PRE + 1:n - 1],
                                     min(stop, target) + m, max(stop, target) - m)
    opens = np.concatenate([[close[0]], close[:-1]])
    # --- Wicks: klein, aber an den Taps EXAKT bis zur Linie ---
    wick = np.abs(np.random.normal(0, entry * 0.0012, n)) + entry * 0.0004
    wlo = np.minimum(opens, close) - wick
    whi = np.maximum(opens, close) + wick * np.abs(np.random.normal(1, 0.4, n))
    for i in TAPS_A:
        if short: wlo[i] = act[i]
        else:     whi[i] = act[i]
    for i in TAPS_S:
        if short: whi[i] = saf[i]
        else:     wlo[i] = saf[i]
    # Vor dem Bruch: Wicks nicht ueber die Linien hinaus
    pre = slice(0, N_PRE)
    wlo[pre] = np.maximum(wlo[pre], lo_line[pre]); whi[pre] = np.minimum(whi[pre], hi_line[pre])
    # Trade-Daten konsistent zur Strategie aktualisieren
    t["stop"], t["target"], t["exit"] = round(stop, 6), round(target, 6), round(float(exitp), 6)
    t["pct"] = round((exitp - entry) / entry * 100 * sgn, 2)
    # --- Zeichnen ---
    fig = plt.figure(figsize=(13, 13.6), facecolor="#0f1320")
    gs = fig.add_gridspec(2, 1, hspace=0.08)
    for p, (i1, lab) in enumerate(((N_PRE + 1, "VORHER (Einstieg)"), (n, "NACHHER (Ausgang)"))):
        ax = fig.add_subplot(gs[p]); ax.set_facecolor("#0f1320")
        for i in range(0, i1):
            o, c = opens[i], close[i]
            col = "#16c784" if c >= o else "#ea3943"
            ax.plot([i, i], [wlo[i], whi[i]], color=col, lw=0.6)
            ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-9),
                                   facecolor=col, edgecolor=col))
        ax.plot(range(i1), act[:i1], color="#3fd0e0", ls="-", lw=0.9, alpha=0.85, zorder=4)
        ax.plot(range(i1), saf[:i1], color="#e0a526", ls="--", lw=0.9, alpha=0.85, zorder=4)
        for i in TAPS_A:
            ax.plot(i, act[i], "o", ms=7, mfc="none", mec="#3fd0e0", mew=1.2, zorder=5)
        for i in TAPS_S:
            ax.plot(i, saf[i], "o", ms=7, mfc="none", mec="#e0a526", mew=1.2, zorder=5)
        for val, col, l2 in ((entry, "#ffffff", "Einstieg"), (t["stop"], "#ff5c6c", "Stop"),
                             (t["target"], "#1fbf75", "Ziel")):
            ax.axhline(val, color=col, lw=1.2, ls="--", alpha=0.85)
            ax.text(1, val, f" {l2} {val_fmt(val)}", color=col, fontsize=9,
                    fontweight="bold", va="bottom")
        if p == 1:
            ax.plot(n - 1, exitp, "X", ms=15, color="#1fbf75" if win else "#ff5c6c", zorder=6)
        ax.set_title(f"{lab}  -  Action: {len(TAPS_A)} Taps, 28 Kerzen Abstand  ·  "
                     f"Safety: {len(TAPS_S)} Taps (Gegenrichtung, intakt)",
                     color="#e0a526", fontsize=11, fontweight="bold", loc="left")
        ax.grid(color="#1e2438", lw=0.5); ax.tick_params(colors="#9aa3b5", labelsize=7)
        for s in ax.spines.values(): s.set_color("#1e2438")
        ax.margins(y=0.12)
    fig.suptitle(f"{'✔ GEWINN' if win else '✘ VERLUST'}  {t['result_r']:+.1f}R ({t['pct']:+.2f} %)"
                 f"  -  {t['name']} {t['direction']}  -  {PROTO}  (FIKTIV)",
                 color="#1fbf75" if win else "#ff5c6c", fontsize=14, fontweight="bold", y=0.985)
    fn = os.path.join(TRADES_DIR, f"FIKTIV_{idx:02d}_result.png")
    fig.savefig(fn, dpi=140, facecolor="#0f1320", bbox_inches="tight")
    plt.close(fig)
    return fn

trades = []
for i in range(N_TRADES):
    name, base = INSTR[i % len(INSTR)]
    win = OUTCOMES[i] == "W"
    direction = random.choice(["LONG", "SHORT"])
    entry = base * random.uniform(0.97, 1.03)
    rr = round(random.uniform(2.0, 2.7), 1)
    sgn = -1 if direction == "SHORT" else 1
    # Nutzer-Vorgabe: Verluste maximal -2 % (Stop-Loss greift), Gewinne 0,5-6 %
    if win: pct = random.uniform(0.5, 6.0)
    else:   pct = -random.uniform(0.4, 1.95)
    risk = entry * abs(pct) / 100 / (rr if win else 1.0)
    stop = entry - sgn * risk
    target = entry + sgn * risk * rr
    exitp = target if win else stop
    pct = pct  # bereits gesetzt
    if i >= N_TRADES - 6: closed_ts = NOW - random.uniform(0.3, 6.8) * DAY   # letzte 6 in 7 Tagen
    else:                 closed_ts = NOW - random.uniform(7.5, N_DAYS - 1.0) * DAY
    dur = random.uniform(0.8, 7.5)
    trades.append({
        "id": f"FIKTIV_{i:02d}", "proto": PROTO, "name": name, "sym": "-",
        "direction": direction, "entry": entry, "stop": stop, "target": target,
        "rr": rr, "sig": f"fiktiv{i}", "status": "closed", "outcome": "ZIEL" if win else "STOP",
        "exit": exitp, "result_r": rr if win else -1.0, "pct": round(pct, 2),
        "opened_ts": closed_ts - dur * DAY, "closed_ts": closed_ts,
        "opened": time.strftime("%d.%m.%Y %H:%M", time.localtime(closed_ts - dur * DAY)),
        "closed": time.strftime("%d.%m.%Y %H:%M", time.localtime(closed_ts)),
        "days": round(dur, 1),
    })

trades.sort(key=lambda t: t["closed_ts"])
period = [t for t in trades if t["closed_ts"] >= NOW - 7 * DAY]
print(f"Fiktive Trades: {len(trades)} | davon in letzten 7 Tagen: {len(period)}")
for k, t in enumerate(period):
    t["result_chart"] = synth_composite(t, k)   # aktualisiert auch Stop/Ziel/%/Exit strategiekonform
    print("Bild erzeugt:", os.path.basename(t["result_chart"]))

fn, n_closed, n_open, tr = build_report(7, "BEISPIEL-7-Tage", trades=trades, now=NOW,
                                        demo_note=f"*** FIKTIVES BEISPIEL - alle Daten erfunden ({N_DAYS} Tage, {N_TRADES} Trades) ***")
total_r = sum(t["result_r"] for t in trades)
total_pct = sum(t["pct"] for t in trades)
pos = sum(t["pct"] for t in trades if t["pct"] > 0)
neg = sum(t["pct"] for t in trades if t["pct"] < 0)
cap = (f"🤑🤑🤑 BERICHT LIEGT VOR! (BEISPIEL v4 - final)\n"
       f"{PROTO} - 7-Tage-Bericht [FIKTIVE DEMO-DATEN]\n"
       f"Zeitraum: {n_closed} Trades mit Einstiegs-/Ausgangschart\n"
       f"Gesamt: {N_TRADES} Trades / {N_DAYS} Tage | Gewinn {pos:+.1f} % | Verlust {neg:+.1f} % | "
       f"Netto {total_pct:+.1f} % ({total_r:+.1f}R)")
tg_document(fn, cap)
print("Bericht gesendet:", fn)
