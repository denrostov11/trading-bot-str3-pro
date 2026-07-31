# -*- coding: utf-8 -*-
"""Berichtserzeugung: Telegram-Kurztext + PDF je Variante und Vergleich.

REINE PROZENT-AUSWERTUNG (Nutzerentscheidung 2026-07-25: kein Kapitalkonto, keine Positionsgröße,
keine Portfolio-Kontosimulation) - plus die R-Kennzahlen. Feste Kennzahlreihenfolge (Berichtskonsistenz).
Nutzt ausschliesslich reporting.variant_report / comparison (eine zentrale Berechnungsschicht).
"""
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages


def _n(v, dec=2, sign=False):
    """Deutsche Zahlenformatierung mit Komma."""
    if v is None:
        return "-"
    if isinstance(v, str):
        return v
    s = f"{v:+.{dec}f}" if sign else f"{v:.{dec}f}"
    return s.replace(".", ",")


def short_text(rep, label):
    """Telegram-Kurzzusammenfassung (vor dem PDF). Reine %-Auswertung + R."""
    sid = rep["strategy_id"]
    if rep.get("closed_trades", 0) == 0:
        return (f"{sid.upper()} – {label}\nGeschlossene Trades: 0\n"
                f"Noch keine abgeschlossenen Trades.\nPaper-Trading – keine echte Order.")
    lines = [
        f"{sid.upper()} – {label}",
        f"Geschlossene Trades: {rep['closed_trades']}",
        f"Trefferquote: {_n(rep['hit_rate'] * 100)} %",
        f"Gesamtergebnis: {_n(rep['total_r_netto'], 1, True)} R",
        f"Expectancy: {_n(rep['expectancy_r'], 2, True)} R je Trade",
        f"Summe Gewinnprozente: {_n(rep['sum_positive_return_pct'], 2, True)} %",
        f"Summe Verlustprozente: -{_n(rep['sum_negative_return_pct'], 2)} %",
        f"Reiner Nettogewinn: {_n(rep['net_profit_pct'], 2, True)} %",
        f"Durchschnitt je Trade: {_n(rep['average_return_pct'], 2, True)} %",
        f"Maximaler Drawdown: {_n(rep['max_drawdown_pct'], 2)} % (R: {_n(rep['max_drawdown_r'], 1)})",
        f"Offene Trades (unrealisiert): {rep.get('open_trades_unrealized', 0)}",
    ]
    if rep.get("sample_flag") != "OK":
        lines.append("Hinweis: UNZUREICHENDE STICHPROBE (<30 Trades) – keine belastbare Aussage.")
    lines.append("Hinweis: Summe der Einzeltrade-% bei gleichem Einsatz je Trade; kein Kapitalkonto.")
    lines.append("Paper-Trading – keine echte Order.")
    return "\n".join(lines)


# Feste Kennzahlreihenfolge (Berichtskonsistenz; Zeilen 10 Portfoliorendite entfällt = reine %-Auswertung)
_ORDER = [
    ("Anzahl Trades", "closed_trades", 0, False),
    ("Trefferquote %", "hit_rate", 2, False),          # *100 unten
    ("Gesamt-R (netto)", "total_r_netto", 2, True),
    ("Durchschnitt R", "avg_r", 2, True),
    ("Expectancy R", "expectancy_r", 2, True),
    ("Summe Gewinnprozente %", "sum_positive_return_pct", 2, True),
    ("Summe Verlustprozente %", "sum_negative_return_pct", 2, False),
    ("Netto-Gewinnprozent %", "net_profit_pct", 2, True),
    ("Durchschnitt Netto % je Trade", "average_return_pct", 2, True),
    ("Profit Factor", "profit_factor", 2, False),
    ("Max Drawdown R", "max_drawdown_r", 2, False),
    ("Max Drawdown %", "max_drawdown_pct", 2, False),
    ("Offene Trades (unrealisiert)", "open_trades_unrealized", 0, False),
]


def build_variant_pdf(rep, path, label):
    BG, FG, GOLD = "#0f1320", "#e8ecf5", "#e0a526"
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(8.27, 11.69), facecolor=BG)   # A4
        y = 0.95
        fig.text(0.07, y, f"{rep['strategy_id']} – {label}", color=GOLD, fontsize=18, fontweight="bold")
        y -= 0.04
        fig.text(0.07, y, "REINE PROZENT-AUSWERTUNG (kein Kapitalkonto) + R", color="#9aa3b5", fontsize=10)
        y -= 0.05
        for name, key, dec, sign in _ORDER:
            val = rep.get(key)
            if key == "hit_rate" and isinstance(val, (int, float)):
                val = val * 100
            fig.text(0.09, y, name, color=FG, fontsize=11)
            fig.text(0.62, y, _n(val, dec, sign) if not isinstance(val, str) else val,
                     color=FG, fontsize=11, fontweight="bold")
            y -= 0.035
        y -= 0.02
        if rep.get("sample_flag") != "OK":
            fig.text(0.07, y, "UNZUREICHENDE STICHPROBE (<30) – keine belastbare Aussage.",
                     color="#ff5c6c", fontsize=11, fontweight="bold"); y -= 0.04
        fig.text(0.07, 0.05, "Paper-Trading – keine echte Order. Prozent = gleicher Einsatz je Trade.",
                 color="#9aa3b5", fontsize=9)
        pdf.savefig(fig, facecolor=BG); plt.close(fig)
    return path


def build_comparison_pdf(comp, path):
    BG, FG, GOLD = "#0f1320", "#e8ecf5", "#e0a526"
    with PdfPages(path) as pdf:
        fig = plt.figure(figsize=(11.69, 8.27), facecolor=BG)   # A4 quer
        fig.text(0.05, 0.95, "Str.3 Pro – Variantenvergleich", color=GOLD, fontsize=18, fontweight="bold")
        y = 0.88
        hdr = f"{'Variante':14}{'Trades':>7}{'Treffer%':>9}{'Ges-R':>8}{'Netto%':>9}{'MaxDD%':>9}{'PF':>7}"
        fig.text(0.05, y, hdr, color=GOLD, fontsize=10, family="monospace"); y -= 0.03
        for r in comp["variants"]:
            hr = r.get("hit_rate")
            row = (f"{r['strategy_id'][-6:]:14}{r.get('closed_trades',0):>7}"
                   f"{(_n(hr*100,1) if isinstance(hr,(int,float)) else '-'):>9}"
                   f"{_n(r.get('total_r_netto'),1,True):>8}{_n(r.get('net_profit_pct'),1,True):>9}"
                   f"{_n(r.get('max_drawdown_pct'),1):>9}{_n(r.get('profit_factor'),1):>7}")
            fig.text(0.05, y, row, color=FG, fontsize=10, family="monospace"); y -= 0.028
        y -= 0.02
        fig.text(0.05, y, "Rankings (nur ausreichende Stichprobe):", color=GOLD, fontsize=11); y -= 0.03
        for name, lst in comp["rankings"].items():
            fig.text(0.06, y, f"{name}: " + (", ".join(s[-6:] for s in lst) if lst else "-"),
                     color=FG, fontsize=9); y -= 0.025
        fig.text(0.05, 0.05, comp["note"], color="#9aa3b5", fontsize=8, wrap=True)
        pdf.savefig(fig, facecolor=BG); plt.close(fig)
    return path
