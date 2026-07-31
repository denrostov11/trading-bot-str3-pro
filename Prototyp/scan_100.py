# -*- coding: utf-8 -*-
"""
Strategie 3 - Scan ueber 100 Handelsinstrumente.
Verbesserung vs. v1: Safety Line = NAECHSTGELEGENE Gegenlinie (min. Abstand
zur Action-Line am aktuellen Rand), nicht die hoechstbewertete.
Ausgabe: 1 PNG pro Instrument in Trading_Bot\\Scan_100 + _Ranking.txt
"""
import os, math, sys, io
if sys.stdout and hasattr(sys.stdout, "buffer") and "utf" not in (sys.stdout.encoding or "").lower():
    _old_stdout = sys.stdout   # Referenz behalten, sonst schliesst GC den Puffer
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import numpy as np
import pandas as pd
import yfinance as yf
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from dataclasses import dataclass, field

OUT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "Scan_100")
os.makedirs(OUT, exist_ok=True)

# ---------------- Instrumente: (Anzeigename, [Yahoo-Kandidaten]) ----------------
INSTRUMENTS = [
 ("ES S&P500 Fut", ["ES=F"]), ("NQ Nasdaq100 Fut", ["NQ=F"]), ("YM DowJones Fut", ["YM=F"]),
 ("RTY Russell2000 Fut", ["RTY=F"]), ("DAX Futures", ["^GDAXI"]), ("EuroStoxx50 Fut", ["^STOXX50E"]),
 ("FTSE100 Fut", ["^FTSE"]), ("Nikkei225 Fut", ["^N225"]), ("HangSeng Fut", ["^HSI"]),
 ("ASX200 Fut", ["^AXJO"]), ("CAC40 Fut", ["^FCHI"]), ("IBEX35 Fut", ["^IBEX"]),
 ("SMI Fut", ["^SSMI"]), ("TSX Fut", ["^GSPTSE"]), ("FTSE MIB Fut", ["FTSEMIB.MI"]),
 ("Gold GC", ["GC=F"]), ("Silber SI", ["SI=F"]), ("Platin PL", ["PL=F"]), ("Palladium PA", ["PA=F"]),
 ("Kupfer HG", ["HG=F"]), ("Aluminium", ["ALI=F"]), ("Nickel", []), ("Zink", []), ("Blei", []),
 ("Eisenerz", []), ("Stahl HRC", ["HRC=F"]), ("Lithium (ETF LIT)", ["LIT"]),
 ("WTI Rohoel CL", ["CL=F"]), ("Brent Rohoel", ["BZ=F"]), ("Erdgas NG", ["NG=F"]),
 ("Heizoel HO", ["HO=F"]), ("Benzin RBOB", ["RB=F"]), ("Uran (Sprott)", ["SRUUF"]),
 ("Uran ETF URA", ["URA"]), ("Carbon Credits (KRBN)", ["KRBN"]), ("Propan", []), ("LNG", []),
 ("Weizen ZW", ["ZW=F"]), ("Mais ZC", ["ZC=F"]), ("Sojabohnen ZS", ["ZS=F"]),
 ("Sojaoel ZL", ["ZL=F"]), ("Sojamehl ZM", ["ZM=F"]), ("Kaffee KC", ["KC=F"]),
 ("Kakao CC", ["CC=F"]), ("Zucker SB", ["SB=F"]), ("Baumwolle CT", ["CT=F"]),
 ("Orangensaft OJ", ["OJ=F"]), ("Reis ZR", ["ZR=F"]), ("Hafer ZO", ["ZO=F"]),
 ("Live Cattle LE", ["LE=F"]), ("Feeder Cattle GF", ["GF=F"]), ("Lean Hogs HE", ["HE=F"]),
 ("EUR/USD", ["EURUSD=X"]), ("GBP/USD", ["GBPUSD=X"]), ("USD/JPY", ["JPY=X"]),
 ("USD/CHF", ["CHF=X"]), ("USD/CAD", ["CAD=X"]), ("AUD/USD", ["AUDUSD=X"]),
 ("NZD/USD", ["NZDUSD=X"]), ("EUR/GBP", ["EURGBP=X"]), ("EUR/JPY", ["EURJPY=X"]),
 ("GBP/JPY", ["GBPJPY=X"]), ("AUD/JPY", ["AUDJPY=X"]), ("CAD/JPY", ["CADJPY=X"]),
 ("CHF/JPY", ["CHFJPY=X"]), ("EUR/AUD", ["EURAUD=X"]), ("EUR/CAD", ["EURCAD=X"]),
 ("EUR/CHF", ["EURCHF=X"]), ("GBP/CAD", ["GBPCAD=X"]), ("GBP/AUD", ["GBPAUD=X"]),
 ("AUD/NZD", ["AUDNZD=X"]), ("NZD/CAD", ["NZDCAD=X"]),
 ("Bitcoin BTC", ["BTC-USD"]), ("Ethereum ETH", ["ETH-USD"]), ("Solana SOL", ["SOL-USD"]),
 ("XRP", ["XRP-USD"]), ("BNB", ["BNB-USD"]), ("Chainlink LINK", ["LINK-USD"]),
 ("Avalanche AVAX", ["AVAX-USD"]), ("Litecoin LTC", ["LTC-USD"]),
 ("Sui SUI", ["SUI20947-USD", "SUI-USD"]), ("Aptos APT", ["APT21794-USD", "APT-USD"]),
 ("Near NEAR", ["NEAR-USD"]), ("Toncoin TON", ["TON11419-USD", "TON-USD"]),
 ("Render RENDER", ["RENDER-USD", "RNDR-USD"]), ("Dogecoin DOGE", ["DOGE-USD"]),
 ("Cardano ADA", ["ADA-USD"]),
 ("Apple AAPL", ["AAPL"]), ("Microsoft MSFT", ["MSFT"]), ("Nvidia NVDA", ["NVDA"]),
 ("Amazon AMZN", ["AMZN"]), ("Meta META", ["META"]), ("Alphabet GOOGL", ["GOOGL"]),
 ("Tesla TSLA", ["TSLA"]), ("Broadcom AVGO", ["AVGO"]), ("Netflix NFLX", ["NFLX"]),
 ("AMD", ["AMD"]), ("Costco COST", ["COST"]), ("Visa V", ["V"]), ("Mastercard MA", ["MA"]),
]

LOOKBACK_DAYS = 240
WINDOW_BARS = 540
THREE_MONTH_BARS = 390
PIVOT_K = 3
MIN_TAPS = 3
MIN_TAPS_SAFETY = 2
MIN_SPACING = 6
MIN_DURATION = 90
MAX_ANGLE_DEG = 45.0
TAP_TOL_ATR = 0.25
BREACH_TOL_ATR = 0.15
FRESH_BREAK_BARS = 12       # Bruch in den letzten 12 Kerzen (~2 Tage) = "frisch"
MAX_SAFETY_DIST_ATR = 12.0  # Safety weiter weg als 12 ATR -> als "zu weit" markieren
MAX_APEX_BARS = 180         # Keil-Regel (Nutzer 15.07.2026, verschaerft am selben Tag
                            # von 540 auf 180): Action- und Safety-Line muessen
                            # KONVERGIEREN; ihr Schnittpunkt (Apex) muss innerhalb von
                            # 180 4h-Kerzen (~30 Handelstage / ~6 Wochen) vor uns liegen.
                            # Parallele oder quasi-parallele Linien sind KEIN Setup.

@dataclass
class Line:
    kind: str; i0: int; p0: float; i1: int; p1: float
    taps: list = field(default_factory=list)
    angle_deg: float = 0.0; duration: int = 0; score: float = 0.0; breaking_bar: int = -1
    def value_at(self, i): return self.p0 + (self.p1 - self.p0) * (i - self.i0) / (self.i1 - self.i0)

def fetch_4h(cands):
    for sym in cands:
        try:
            df = yf.download(sym, period=f"{LOOKBACK_DAYS}d", interval="1h",
                             auto_adjust=False, progress=False, multi_level_index=False)
        except Exception:
            continue
        if df is None or df.empty or len(df) < 200: continue
        df = df[["Open", "High", "Low", "Close", "Volume"]].dropna()
        o = df.resample("4h").agg({"Open": "first", "High": "max", "Low": "min",
                                   "Close": "last", "Volume": "sum"}).dropna()
        if len(o) < MIN_DURATION: continue
        return sym, o.tail(WINDOW_BARS).reset_index(names="Time")
    return None, None

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
    rise_3m = slope_per_bar * THREE_MONTH_BARS
    return math.degrees(math.atan(abs(rise_3m / (0.25 * price_ref))))

def find_lines(df, kind, a, piv):
    pts = piv[0] if kind == "support" else piv[1]
    price = df.Low.values if kind == "support" else df.High.values
    close = df.Close.values
    n = len(df); out = []
    for ai in range(len(pts)):
        for bi in range(ai + 1, len(pts)):
            i0, i1 = pts[ai], pts[bi]
            if i1 - i0 < MIN_SPACING: continue
            p0, p1 = price[i0], price[i1]
            ln = Line(kind, i0, float(p0), i1, float(p1))
            ref = float(np.median(close[max(0, i0):i1 + 1]))
            if ref <= 0: continue
            ln.angle_deg = norm_angle((p1 - p0) / (i1 - i0), ref)
            if ln.angle_deg > MAX_ANGLE_DEG: continue
            taps, breaking = [], -1
            for i in range(i0, n):
                lv = ln.value_at(i)
                tol_tap = TAP_TOL_ATR * a.iloc[i]; tol_brk = BREACH_TOL_ATR * a.iloc[i]
                if kind == "support":
                    if close[i] < lv - tol_brk: breaking = i; break
                    if price[i] <= lv + tol_tap:
                        if not taps or i - taps[-1] >= MIN_SPACING: taps.append(i)
                        elif price[i] < price[taps[-1]]: taps[-1] = i
                else:
                    if close[i] > lv + tol_brk: breaking = i; break
                    if price[i] >= lv - tol_tap:
                        if not taps or i - taps[-1] >= MIN_SPACING: taps.append(i)
                        elif price[i] > price[taps[-1]]: taps[-1] = i
            ln.taps = taps; ln.breaking_bar = breaking
            end = breaking if breaking > 0 else n - 1
            ln.duration = end - i0
            if len(taps) < MIN_TAPS_SAFETY or ln.duration < MIN_DURATION: continue
            ln.score = len(taps) * 100 + ln.duration * 0.1 - ln.angle_deg * 0.5
            out.append(ln)
    out.sort(key=lambda l: -l.score)
    kept = []
    for ln in out:
        if any(len(set(ln.taps) & set(k2.taps)) >= max(2, min(len(ln.taps), len(k2.taps)) - 1) for k2 in kept):
            continue
        kept.append(ln)
    return kept

def is_aplus(ln): return len(ln.taps) >= MIN_TAPS and ln.duration >= MIN_DURATION and ln.angle_deg < MAX_ANGLE_DEG

def converges(action, safety, ref_i):
    """Keil-Regel (Nutzer, 15.07.2026): Action- und Safety-Line muessen aufeinander
    zulaufen (konvergieren) - zwischen ihnen entsteht ein sich schliessender Keil.
    Parallel oder quasi-parallel ist unzulaessig. Kriterium: der Abstand (Gap)
    schrumpft nach rechts, und der Schnittpunkt (Apex) liegt hoechstens
    MAX_APEX_BARS Kerzen in der Zukunft."""
    sa = (action.p1 - action.p0) / (action.i1 - action.i0)
    ss = (safety.p1 - safety.p0) / (safety.i1 - safety.i0)
    gap = safety.value_at(ref_i) - action.value_at(ref_i)
    closing = (sa - ss) if gap > 0 else (ss - sa)   # >0 = Keil schliesst sich
    if closing <= 0:
        return False                                 # divergent oder exakt parallel
    return abs(gap) / closing <= MAX_APEX_BARS       # quasi-parallel (Apex zu fern) raus

def pick_safety(action, opp_lines, df, a):
    """NEU: naechstgelegene Gegenlinie am aktuellen Rand (statt Best-Score).
    Bedingungen: >=2 Taps, korrekte Seite, intakt, KONVERGENT (Keil),
    letzter Tap moeglichst jung."""
    n = len(df); ref_i = n - 1
    av = action.value_at(ref_i)
    best, best_d = None, None
    for ln in opp_lines:
        if len(ln.taps) < MIN_TAPS_SAFETY: continue
        if ln.breaking_bar > 0: continue   # WICHTIG: Safety muss intakt sein - darf keine Kerzen durchkreuzen (Nutzer-Regel 13.07.2026)
        sv = ln.value_at(ref_i)
        if action.kind == "support" and sv <= av: continue   # Resistance muss darueber liegen
        if action.kind == "resistance" and sv >= av: continue
        if not converges(action, ln, ref_i): continue        # Keil-Regel (Nutzer 15.07.2026)
        d = abs(sv - av) / max(a.iloc[ref_i], 1e-9)          # Abstand in ATR
        recency = (n - 1 - ln.taps[-1])                       # juengster Tap
        key = d + recency * 0.02                              # Naehe dominiert, Frische zaehlt mit
        if best is None or key < best_d:
            best, best_d = ln, key
    return best

def plot(df, name, sym, action, safety, a):
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
        if ln.breaking_bar > 0:
            ax.axvline(ln.breaking_bar, color="#ffffff", lw=0.8, ls=":", alpha=0.55)
            ax.plot(ln.breaking_bar, df.Close[ln.breaking_bar],
                    "v" if ln.kind == "support" else "^", ms=11, color="#ffffff", zorder=6)
    if action:
        tag = "A+" if is_aplus(action) else f"{len(action.taps)} Taps"
        stat = f"BRUCH @ {ln_time(df, action.breaking_bar)}" if action.breaking_bar > 0 else "intakt"
        draw(action, "#3fd0e0", "-", f"Action ({tag}, {len(action.taps)} Taps, {action.angle_deg:.0f} Grad, {stat})")
    if safety:
        dist = abs(safety.value_at(n-1) - action.value_at(n-1)) / max(a.iloc[n-1], 1e-9) if action else 0
        draw(safety, "#e0a526", "--", f"Safety ({len(safety.taps)} Taps, Abstand {dist:.1f} ATR)")
    ax.set_xlim(-2, n + 1); ax.margins(y=0.06)
    ax.grid(color="#1e2438", lw=0.5)
    ax.tick_params(colors="#9aa3b5", labelsize=8)
    for s in ax.spines.values(): s.set_color("#1e2438")
    step = max(1, n // 7)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([str(df.Time[i])[:10] for i in range(0, n, step)], color="#9aa3b5")
    ax.set_title(f"{name} ({sym}) - 4h - Strategie-3-Scan", color="#e8ecf5", fontsize=13, fontweight="bold")
    if action or safety:
        ax.legend(facecolor="#191f33", labelcolor="#e8ecf5", edgecolor="#1e2438", fontsize=9)
    fig.tight_layout()
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    fn = os.path.join(OUT, f"{safe}.png")
    fig.savefig(fn, dpi=95, facecolor="#0f1320")
    plt.close(fig)
    return fn

def ln_time(df, i): return str(df.Time[min(max(i,0), len(df)-1)])[:10]

def main():
    results = []
    for idx, (name, cands) in enumerate(INSTRUMENTS, 1):
        if not cands:
            results.append({"name": name, "status": "KEINE DATENQUELLE (nicht auf Yahoo/frei verfuegbar)", "score": -1})
            print(f"[{idx:3}/100] {name}: keine Datenquelle"); continue
        sym, df = fetch_4h(cands)
        if df is None:
            results.append({"name": name, "status": "keine/zu wenige Daten", "score": -1})
            print(f"[{idx:3}/100] {name}: keine Daten"); continue
        a = atr(df); piv = pivots(df)
        sup = find_lines(df, "support", a, piv)
        res = find_lines(df, "resistance", a, piv)
        all_lines = sorted(sup + res, key=lambda l: -l.score)
        action = next((l for l in all_lines if len(l.taps) >= MIN_TAPS), all_lines[0] if all_lines else None)
        safety = pick_safety(action, res if (action and action.kind == "support") else sup, df, a) if action else None
        n = len(df)
        entry = {"name": name, "sym": sym, "score": 0.0}
        if not action:
            entry["status"] = "keine gueltige Linie"; entry["score"] = -1
        else:
            fresh = action.breaking_bar > 0 and (n - 1 - action.breaking_bar) <= FRESH_BREAK_BARS
            old_break = action.breaking_bar > 0 and not fresh
            dist_atr = (abs(safety.value_at(n-1) - action.value_at(n-1)) / max(a.iloc[n-1], 1e-9)) if safety else 99
            ap = is_aplus(action)
            s = len(action.taps) * 10 - action.angle_deg * 0.3
            s += max(0.0, (MAX_SAFETY_DIST_ATR - min(dist_atr, MAX_SAFETY_DIST_ATR))) * 3
            if fresh: s += 40
            elif not action.breaking_bar > 0: s += 20
            if not ap: s -= 30
            if safety is None: s -= 25
            entry["score"] = round(s, 1)
            st = "BRUCH FRISCH" if fresh else ("Bruch alt" if old_break else "intakt")
            entry["status"] = (f"{'A+' if ap else 'kein A+'} | {action.kind} | {len(action.taps)} Taps | "
                               f"{action.angle_deg:.0f} Grad | {st} | Safety: "
                               f"{'-' if not safety else f'{len(safety.taps)} Taps, {dist_atr:.1f} ATR'}")
        plot(df, name, sym, action, safety, a)
        print(f"[{idx:3}/100] {name}: {entry['status']} | Score {entry['score']}")
        results.append(entry)

    results.sort(key=lambda r: -r["score"])
    lines = ["STRATEGIE-3-SCAN - RANKING (beste Kandidaten oben)", "=" * 78]
    for i, r in enumerate(results, 1):
        lines.append(f"{i:3}. [{r['score']:7.1f}] {r['name']:26} {r.get('status','')}")
    txt = "\n".join(lines)
    with open(os.path.join(OUT, "_Ranking.txt"), "w", encoding="utf-8") as f:
        f.write(txt)
    print("\n" + txt[:2500])
    print(f"\nFertig. Charts + _Ranking.txt in: {OUT}")

if __name__ == "__main__":
    main()
