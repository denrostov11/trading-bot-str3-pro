# -*- coding: utf-8 -*-
"""
Strategie 3 - Trendlinien-Erkennungs-Prototyp (Session 1)
Erkennt A+ Trendlinien nach den Tori-Trades-Kriterien auf 4h-Charts:
  - 3+ Taps (Wicks) vor Bruch (Safety Line: >=2 Taps, Gegenrichtung)
  - 6+ Kerzen Abstand zwischen Taps
  - < 45 Grad (normalisiert auf 3-Monats-Fenster)
  - > 3 Wochen Preisdaten von Start bis Bruch/heute
Ausgabe: PNG-Charts mit erkannten Linien + Konsolen-Report.
"""
import math
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from dataclasses import dataclass, field

# ------------------------- Konfiguration -------------------------
SYMBOLS = {"GC=F": "Gold", "CL=F": "Rohoel WTI", "PL=F": "Platin", "YM=F": "DOW Futures"}
LOOKBACK_DAYS = 240          # ~8 Monate 1h-Daten laden
WINDOW_BARS   = 540          # Analyse-Fenster: ~3-4 Monate in 4h-Kerzen (fuer Winkel-Norm: 390 = 3 Monate)
THREE_MONTH_BARS = 390
PIVOT_K       = 3            # Fractal-Lookback: Pivot = Extrem von k Kerzen links+rechts
MIN_TAPS      = 3            # Action-Line
MIN_TAPS_SAFETY = 2
MIN_SPACING   = 6            # Kerzen zwischen Taps
MIN_DURATION  = 6 * 5 * 3    # >3 Wochen: ~15 Handelstage x 6 Kerzen = 90 Bars
MAX_ANGLE_DEG = 45.0
TAP_TOL_ATR   = 0.25         # Tap zaehlt, wenn Wick die Linie bis auf 0.25*ATR beruehrt
BREACH_TOL_ATR= 0.15         # Linie "haelt", solange kein Schlusskurs > 0.15*ATR jenseits liegt

@dataclass
class Line:
    kind: str                # 'support' oder 'resistance'
    i0: int; p0: float       # Ankerpunkt 1 (Barindex, Preis)
    i1: int; p1: float       # Ankerpunkt 2
    taps: list = field(default_factory=list)      # Bar-Indizes der Taps
    angle_deg: float = 0.0
    duration: int = 0
    score: float = 0.0
    breaking_bar: int = -1   # Bar, dessen SCHLUSS die Linie bricht (-1 = intakt)

    def value_at(self, i):
        return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)

def fetch_4h(symbol):
    df = yf.download(symbol, period=f"{LOOKBACK_DAYS}d", interval="1h",
                     auto_adjust=False, progress=False, multi_level_index=False)
    if df.empty:
        return None
    df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    o = df.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                               "Close": "last", "Volume": "sum"}).dropna()
    return o.tail(WINDOW_BARS).reset_index(names="Time")

def atr(df, n=14):
    hl = df.High - df.Low
    hc = (df.High - df.Close.shift()).abs()
    lc = (df.Low - df.Close.shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1).rolling(n).mean().bfill()

def pivots(df, k=PIVOT_K):
    lows, highs = [], []
    L, H = df.Low.values, df.High.values
    for i in range(k, len(df) - k):
        if L[i] == L[i-k:i+k+1].min(): lows.append(i)
        if H[i] == H[i-k:i+k+1].max(): highs.append(i)
    return lows, highs

def norm_angle(slope_per_bar, price_ref):
    """Winkel normalisiert: 3 Monate (390 Bars) horizontal == Preisspanne von +/-... vertikal.
    Wir setzen: rise ueber 3 Monate relativ zu 25% des Referenzpreises == 45 Grad."""
    rise_3m = slope_per_bar * THREE_MONTH_BARS
    rel = rise_3m / (0.25 * price_ref)
    return math.degrees(math.atan(abs(rel)))

def find_lines(df, kind):
    """kind='support': Linien durch Pivot-Tiefs (Preis haelt sich OBERHALB).
       kind='resistance': durch Pivot-Hochs (Preis haelt sich UNTERHALB)."""
    a = atr(df)
    lows, highs = pivots(df)
    pts = lows if kind == "support" else highs
    price = df.Low.values if kind == "support" else df.High.values
    close = df.Close.values
    n = len(df)
    out = []
    for ai in range(len(pts)):
        for bi in range(ai + 1, len(pts)):
            i0, i1 = pts[ai], pts[bi]
            if i1 - i0 < MIN_SPACING: continue
            p0, p1 = price[i0], price[i1]
            ln = Line(kind, i0, float(p0), i1, float(p1))
            ref = float(np.median(close[max(0, i0):i1 + 1]))
            ln.angle_deg = norm_angle((p1 - p0) / (i1 - i0), ref)
            if ln.angle_deg > MAX_ANGLE_DEG: continue
            # Taps zaehlen + Guertigkeit (Linie muss bis zum Bruch halten)
            taps, breaking = [], -1
            for i in range(i0, n):
                lv = ln.value_at(i)
                tol_tap = TAP_TOL_ATR * a.iloc[i]
                tol_brk = BREACH_TOL_ATR * a.iloc[i]
                if kind == "support":
                    if close[i] < lv - tol_brk: breaking = i; break
                    if price[i] <= lv + tol_tap:
                        if not taps or i - taps[-1] >= MIN_SPACING: taps.append(i)
                        elif price[i] < price[taps[-1]] - 0.01: taps[-1] = i
                else:
                    if close[i] > lv + tol_brk: breaking = i; break
                    if price[i] >= lv - tol_tap:
                        if not taps or i - taps[-1] >= MIN_SPACING: taps.append(i)
                        elif price[i] > price[taps[-1]] + 0.01: taps[-1] = i
            ln.taps = taps
            ln.breaking_bar = breaking
            end = breaking if breaking > 0 else n - 1
            ln.duration = end - i0
            if len(taps) < MIN_TAPS_SAFETY: continue
            if ln.duration < MIN_DURATION: continue
            # Score: Taps zuerst, dann Dauer, flacher Winkel leicht belohnt
            ln.score = len(taps) * 100 + ln.duration * 0.1 - ln.angle_deg * 0.5
            out.append(ln)
    # Deduplizieren: aehnliche Linien (gleiche Taps) -> beste behalten
    out.sort(key=lambda l: -l.score)
    kept = []
    for ln in out:
        dup = False
        for k2 in kept:
            shared = len(set(ln.taps) & set(k2.taps))
            if shared >= max(2, min(len(ln.taps), len(k2.taps)) - 1): dup = True; break
        if not dup: kept.append(ln)
    return kept

def is_aplus(ln):
    return len(ln.taps) >= MIN_TAPS and ln.duration >= MIN_DURATION and ln.angle_deg < MAX_ANGLE_DEG

def plot(df, name, sym, action, safety):
    n = len(df)
    fig, ax = plt.subplots(figsize=(15, 8), facecolor="#0f1320")
    ax.set_facecolor("#0f1320")
    # Kerzen
    for i in range(n):
        o, h, l, c = df.Open[i], df.High[i], df.Low[i], df.Close[i]
        col = "#16c784" if c >= o else "#ea3943"
        ax.plot([i, i], [l, h], color=col, lw=0.7, zorder=2)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-9),
                               facecolor=col, edgecolor=col, zorder=3))
    def draw(ln, color, style, label):
        xs = [ln.i0, n - 1]
        ax.plot(xs, [ln.value_at(x) for x in xs], color=color, ls=style, lw=2.2, zorder=4, label=label)
        for t in ln.taps:
            ax.plot(t, ln.value_at(t), "o", ms=11, mfc="none", mec=color, mew=2, zorder=5)
        if ln.breaking_bar > 0:
            ax.axvline(ln.breaking_bar, color="#ffffff", lw=0.8, ls=":", alpha=0.6)
            ax.plot(ln.breaking_bar, df.Close[ln.breaking_bar], "v" if ln.kind == "support" else "^",
                    ms=12, color="#ffffff", zorder=6)
    if action:
        tag = "A+" if is_aplus(action) else f"{len(action.taps)} Taps"
        stat = f"BRUCH @ Kerze {action.breaking_bar}" if action.breaking_bar > 0 else "intakt"
        draw(action, "#3fd0e0", "-", f"Action-Line ({tag}, {action.angle_deg:.0f}°, {stat})")
    if safety:
        draw(safety, "#e0a526", "--", f"Safety Line ({len(safety.taps)} Taps, Gegenrichtung)")
    ax.set_xlim(-2, n + 1); ax.margins(y=0.06)
    ax.grid(color="#1e2438", lw=0.5)
    ax.tick_params(colors="#9aa3b5", labelsize=9)
    for s in ax.spines.values(): s.set_color("#1e2438")
    step = max(1, n // 8)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([str(df.Time[i])[:10] for i in range(0, n, step)], color="#9aa3b5")
    ax.set_title(f"{name} ({sym}) – 4h – automatische Trendlinien-Erkennung",
                 color="#e8ecf5", fontsize=15, fontweight="bold")
    if action or safety: ax.legend(facecolor="#191f33", labelcolor="#e8ecf5", edgecolor="#1e2438", fontsize=10)
    fig.tight_layout()
    fn = f"Erkennung_{name.replace(' ', '_')}.png"
    fig.savefig(fn, dpi=110, facecolor="#0f1320")
    plt.close(fig)
    return fn

def main():
    print("=" * 70)
    for sym, name in SYMBOLS.items():
        df = fetch_4h(sym)
        if df is None or len(df) < MIN_DURATION:
            print(f"{name}: keine/zu wenige Daten"); continue
        sup = find_lines(df, "support")
        res = find_lines(df, "resistance")
        # Action = beste Linie beliebiger Richtung; Safety = beste Gegenlinie
        all_lines = sorted(sup + res, key=lambda l: -l.score)
        action = next((l for l in all_lines if len(l.taps) >= MIN_TAPS), all_lines[0] if all_lines else None)
        safety = None
        if action:
            opp = res if action.kind == "support" else sup
            safety = next((l for l in opp if len(l.taps) >= MIN_TAPS_SAFETY), None)
        fn = plot(df, name, sym, action, safety)
        print(f"\n{name} ({sym}) – {len(df)} Kerzen, {str(df.Time[0])[:10]} bis {str(df.Time[len(df)-1])[:10]}")
        print(f"  Kandidaten: {len(sup)} Support-, {len(res)} Resistance-Linien")
        if action:
            ap = "A+ ERFUELLT" if is_aplus(action) else "kein A+ (zu wenige Taps)"
            brk = f", GEBROCHEN bei Kerze {action.breaking_bar}" if action.breaking_bar > 0 else ", intakt"
            print(f"  Action-Line: {action.kind}, {len(action.taps)} Taps, {action.angle_deg:.1f} Grad, "
                  f"{action.duration} Kerzen Dauer -> {ap}{brk}")
        else:
            print("  Keine gueltige Action-Line gefunden")
        if safety:
            print(f"  Safety Line: {safety.kind}, {len(safety.taps)} Taps (Gegenrichtung)")
        else:
            print("  Keine Safety Line gefunden")
        print(f"  Chart: {fn}")
    print("\n" + "=" * 70)

if __name__ == "__main__":
    main()
