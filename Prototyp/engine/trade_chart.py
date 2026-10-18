# -*- coding: utf-8 -*-
"""Trade-Chart: rendert je Trade ein 4h-Chartbild mit den eingezeichneten Kriterien
(Action-/Safety-Trendlinie, Taps, Bruchkerze) UND den Trade-Levels (Einstieg/Stop/Ziel).

Stil wie die Erkennung (scan_100.plot): dunkler Hintergrund, duenne Linien, Tap-Kreise, Bruchmarker.
Reine Darstellung; keine Berechnung/keine Handelslogik. Nutzt Line-Objekte (value_at/i0/taps/kind/
breaking_bar) aus der Erkennung.
"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

BG, FG, GREY, CYAN, GOLD, GREEN, RED = "#0f1320", "#e8ecf5", "#9aa3b5", "#3fd0e0", "#e0a526", "#16c784", "#ea3943"


def render_trade_chart(df, name, sym, action, safety, direction, entry, stop, target,
                       out_path, variant="", dpi=220):
    """df = compat-4h (Spalten Time/Open/High/Low/Close, ganzzahliger Index). action/safety = Line-
    Objekte (oder None). entry/stop/target = Preis-Level. Speichert PNG unter out_path."""
    n = len(df)
    fig, ax = plt.subplots(figsize=(13, 6.8), facecolor=BG)
    ax.set_facecolor(BG)
    for i in range(n):
        o, h, l, c = df.Open[i], df.High[i], df.Low[i], df.Close[i]
        col = GREEN if c >= o else RED
        ax.plot([i, i], [l, h], color=col, lw=0.6, zorder=2)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-9),
                               facecolor=col, edgecolor=col, zorder=3))

    def draw(ln, color, style, label):
        xs = [ln.i0, n - 1]
        ax.plot(xs, [ln.value_at(x) for x in xs], color=color, ls=style, lw=2.0, zorder=4, label=label)
        for t in getattr(ln, "taps", []):
            if 0 <= t < n:
                ax.plot(t, ln.value_at(t), "o", ms=9, mfc="none", mec=color, mew=1.6, zorder=5)
        bb = getattr(ln, "breaking_bar", -1)
        if bb and bb > 0:
            ax.axvline(bb, color="#ffffff", lw=0.8, ls=":", alpha=0.55)
            ax.plot(bb, df.Close[bb], "v" if ln.kind == "support" else "^",
                    ms=12, color="#ffffff", zorder=6)

    if action is not None:
        draw(action, CYAN, "-", f"Action-Linie ({len(getattr(action, 'taps', []))} Taps, Bruch)")
    if safety is not None:
        draw(safety, GOLD, "--", f"Safety-Linie ({len(getattr(safety, 'taps', []))} Taps)")

    # Trade-Level
    ax.axhline(entry, color=FG, lw=1.2, ls="-", alpha=0.9, zorder=7)
    ax.text(0.5, entry, f" Einstieg {entry:.6g}", color=FG, fontsize=8, va="bottom", zorder=8)
    ax.axhline(stop, color=RED, lw=1.3, ls="--", zorder=7)
    ax.text(0.5, stop, f" Stop {stop:.6g}", color=RED, fontsize=8, va="bottom", zorder=8)
    if target:
        ax.axhline(target, color=GREEN, lw=1.3, ls="--", zorder=7)
        ax.text(0.5, target, f" Ziel {target:.6g}", color=GREEN, fontsize=8, va="bottom", zorder=8)

    ax.set_xlim(-2, n + 1); ax.margins(y=0.08)
    ax.grid(color="#1e2438", lw=0.5)
    ax.tick_params(colors=GREY, labelsize=8)
    for s in ax.spines.values():
        s.set_color("#1e2438")
    step = max(1, n // 7)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([str(df.Time[i])[:10] for i in range(0, n, step)], color=GREY)
    ax.set_title(f"{name} ({sym}) {direction} · {variant} · 4h · Strategie 3 Pro",
                 color=FG, fontsize=13, fontweight="bold")
    ax.legend(facecolor="#191f33", labelcolor=FG, edgecolor="#1e2438", fontsize=9, loc="best")
    fig.tight_layout()
    fig.savefig(out_path, dpi=dpi, facecolor=BG)
    plt.close(fig)
    return out_path
