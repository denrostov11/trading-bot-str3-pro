# -*- coding: utf-8 -*-
"""
Strategie 3 - WATCHLIST: nur Setups, bei denen der Einstieg NOCH BEVORSTEHT.
Kriterien:
  - Action-Line intakt (kein Bruch) und A+ (3+ Taps, Dauer, Winkel)
  - Kurs nahe an der Action-Line (Naehe in ATR) -> Bruch koennte bald ausloesen
  - Safety Line (Gegenrichtung, >=2 Taps) vorhanden und moeglichst nah -> enger Stop
Ausgabe: Charts nur der Kandidaten in Trading_Bot\\Watchlist + _Watchlist.txt
"""
import os, sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from scan_100 import (INSTRUMENTS, fetch_4h, atr, pivots, find_lines, is_aplus,
                      pick_safety, MIN_TAPS)

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Watchlist")
os.makedirs(OUT, exist_ok=True)

MAX_PROX_ATR   = 5.0   # Kurs max. 5 ATR von der Action-Line entfernt
MAX_SAFETY_ATR = 10.0  # Safety max. 10 ATR entfernt (sonst Stop zu gross)

def plot(df, name, sym, action, safety, a, prox, sdist, direction):
    n = len(df)
    fig, ax = plt.subplots(figsize=(13, 6.8), facecolor="#0f1320")
    ax.set_facecolor("#0f1320")
    for i in range(n):
        o, h, l, c = df.Open[i], df.High[i], df.Low[i], df.Close[i]
        col = "#16c784" if c >= o else "#ea3943"
        ax.plot([i, i], [l, h], color=col, lw=0.6, zorder=2)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-9),
                               facecolor=col, edgecolor=col, zorder=3))
    def draw(ln, color, style, label):
        xs = [ln.i0, n - 1]
        ax.plot(xs, [ln.value_at(x) for x in xs], color=color, ls=style, lw=2.2, zorder=4, label=label)
        for t in ln.taps:
            ax.plot(t, ln.value_at(t), "o", ms=10, mfc="none", mec=color, mew=1.8, zorder=5)
    draw(action, "#3fd0e0", "-",
         f"Action-Line A+ ({len(action.taps)} Taps, {action.angle_deg:.0f} Grad) - Kurs {prox:.1f} ATR entfernt")
    if safety:
        draw(safety, "#e0a526", "--", f"Safety Line ({len(safety.taps)} Taps, {sdist:.1f} ATR) -> Stop-Basis")
    # Trigger-Hinweis rechts
    lv = action.value_at(n - 1)
    ax.annotate(f"TRIGGER: 4h-Schluss {'UNTER' if direction == 'SHORT' else 'UEBER'} {lv:.4g}\n-> {direction}-Einstieg",
                xy=(n - 1, lv), xytext=(n * 0.72, lv),
                color="#ffffff", fontsize=10, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color="#ffffff", lw=1.2),
                bbox=dict(boxstyle="round,pad=0.4", fc="#B22222" if direction == "SHORT" else "#2E7D32", ec="none"))
    ax.set_xlim(-2, n + 1); ax.margins(y=0.06)
    ax.grid(color="#1e2438", lw=0.5)
    ax.tick_params(colors="#9aa3b5", labelsize=8)
    for s in ax.spines.values(): s.set_color("#1e2438")
    step = max(1, n // 7)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([str(df.Time[i])[:10] for i in range(0, n, step)], color="#9aa3b5")
    ax.set_title(f"{name} ({sym}) - 4h - WATCHLIST: Einstieg steht noch aus ({direction} bei Bruch)",
                 color="#e8ecf5", fontsize=13, fontweight="bold")
    ax.legend(facecolor="#191f33", labelcolor="#e8ecf5", edgecolor="#1e2438", fontsize=9)
    fig.tight_layout()
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    fn = os.path.join(OUT, f"{safe}.png")
    fig.savefig(fn, dpi=95, facecolor="#0f1320")
    plt.close(fig)
    return fn

def main():
    rows = []
    for idx, (name, cands) in enumerate(INSTRUMENTS, 1):
        if not cands: continue
        sym, df = fetch_4h(cands)
        if df is None: continue
        a = atr(df); piv = pivots(df)
        sup = find_lines(df, "support", a, piv)
        res = find_lines(df, "resistance", a, piv)
        n = len(df)
        # Nur INTAKTE A+-Linien betrachten
        candidates = [l for l in (sup + res) if l.breaking_bar < 0 and is_aplus(l)]
        best = None
        for action in sorted(candidates, key=lambda l: -l.score):
            close = float(df.Close[n - 1]); lv = action.value_at(n - 1)
            atr_now = max(float(a.iloc[n - 1]), 1e-9)
            prox = (close - lv) / atr_now if action.kind == "support" else (lv - close) / atr_now
            if prox < 0 or prox > MAX_PROX_ATR: continue   # schon drueber/zu weit weg
            safety = pick_safety(action, res if action.kind == "support" else sup, df, a)
            sdist = (abs(safety.value_at(n-1) - lv) / atr_now) if safety else 99
            if safety is None or sdist > MAX_SAFETY_ATR: continue
            direction = "SHORT" if action.kind == "support" else "LONG"
            score = (len(action.taps) * 10 - action.angle_deg * 0.3
                     + (MAX_PROX_ATR - prox) * 8 + (MAX_SAFETY_ATR - sdist) * 2)
            best = (score, action, safety, prox, sdist, direction)
            break  # beste intakte Linie reicht
        if best:
            score, action, safety, prox, sdist, direction = best
            plot(df, name, sym, action, safety, a, prox, sdist, direction)
            rows.append({"name": name, "sym": sym, "score": round(score, 1), "dir": direction,
                         "taps": len(action.taps), "angle": round(action.angle_deg),
                         "prox": round(prox, 1), "sdist": round(sdist, 1)})
            print(f"[{idx:3}] {name}: WATCH {direction} | {len(action.taps)} Taps | Kurs {prox:.1f} ATR | Safety {sdist:.1f} ATR | Score {score:.0f}")
        else:
            print(f"[{idx:3}] {name}: kein wartendes Setup")

    rows.sort(key=lambda r: -r["score"])
    lines = ["STRATEGIE-3-WATCHLIST - Einstieg steht noch aus (beste zuerst)", "=" * 84,
             f"{'#':>3} {'Score':>6} {'Richtung':8} {'Instrument':26} {'Taps':>4} {'Winkel':>6} {'Kurs->Linie':>11} {'Safety':>7}",
             "-" * 84]
    for i, r in enumerate(rows, 1):
        lines.append(f"{i:3} {r['score']:6.1f} {r['dir']:8} {r['name']:26} {r['taps']:4} {r['angle']:5}° {r['prox']:9.1f} ATR {r['sdist']:5.1f} ATR")
    txt = "\n".join(lines)
    with open(os.path.join(OUT, "_Watchlist.txt"), "w", encoding="utf-8") as f:
        f.write(txt)
    print("\n" + txt)
    print(f"\nFertig. {len(rows)} wartende Setups. Charts in: {OUT}")

if __name__ == "__main__":
    main()
