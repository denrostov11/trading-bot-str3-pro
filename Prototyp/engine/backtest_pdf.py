# -*- coding: utf-8 -*-
"""PDF-Berichte fuer den Backtest (Etappe C2): je Variante EINE mehrseitige PDF
(Gesamtkennzahlen + Equity-Kurve + Monatsuebersicht) + eine Vergleichs-PDF.

Nutzt die bereits erzeugten JSON/CSV aus build_universe_reports (keine Neuberechnung) und die
Bausteine aus reporting_pdf (_ORDER/_n/short_text/build_comparison_pdf) - eine Darstellungsschicht.
Erzeugt den `reports`-Dict fuer notify.live.TelegramService.deliver_reports.
"""
import os, json, csv
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

from . import reporting_pdf as RP
from .backtest_report import VARIANT_LABELS, month_list

BG, FG, GOLD, RED, GREY = "#0f1320", "#e8ecf5", "#e0a526", "#ff5c6c", "#9aa3b5"


def _load(p):
    return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else {}


def _metrics_page(pdf, rep, title):
    fig = plt.figure(figsize=(8.27, 11.69), facecolor=BG)      # A4 hoch
    y = 0.95
    fig.text(0.07, y, title, color=GOLD, fontsize=15, fontweight="bold"); y -= 0.045
    fig.text(0.07, y, "REINE PROZENT-AUSWERTUNG (kein Kapitalkonto) + R", color=GREY, fontsize=9); y -= 0.05
    if rep.get("closed_trades", 0) == 0:
        fig.text(0.09, y, "Keine abgeschlossenen Trades.", color=FG, fontsize=12)
    else:
        for name, key, dec, sign in RP._ORDER:
            val = rep.get(key)
            if key == "hit_rate" and isinstance(val, (int, float)):
                val = val * 100
            fig.text(0.09, y, name, color=FG, fontsize=11)
            fig.text(0.64, y, RP._n(val, dec, sign) if not isinstance(val, str) else val,
                     color=FG, fontsize=11, fontweight="bold")
            y -= 0.032
        if rep.get("sample_flag") != "OK":
            y -= 0.01
            fig.text(0.07, y, "UNZUREICHENDE STICHPROBE (<30) - keine belastbare Aussage.",
                     color=RED, fontsize=10, fontweight="bold")
            y -= 0.03
        te = ((rep.get("abschluss_aufschluesselung") or {}).get("test_end_bewertungen") or {})
        if te.get("n"):
            y -= 0.01
            fig.text(0.07, y, f"Enthaelt {te['n']} TEST_END-Bewertung(en) mit {te['netto_r']:+.2f} R netto:",
                     color=GOLD, fontsize=9)
            fig.text(0.07, y - 0.02, "am Testende noch offene Positionen, zum letzten Schlusskurs bewertet "
                     "(kein regulaerer Ausstieg).", color=GREY, fontsize=8)
    fig.text(0.07, 0.05, "Historische Simulation - keine Handelsempfehlung. Paper-Trading, keine echte Order.",
             color=GREY, fontsize=8)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


def _equity_page(pdf, sid, eq_rows):
    fig = plt.figure(figsize=(8.27, 11.69), facecolor=BG)
    fig.text(0.07, 0.92, f"{sid} - Equity-Kurve (kumulierte Netto-R)", color=GOLD,
             fontsize=14, fontweight="bold")
    if not eq_rows:
        fig.text(0.09, 0.85, "Keine abgeschlossenen Trades.", color=FG, fontsize=12)
    else:
        ax = fig.add_axes([0.12, 0.30, 0.80, 0.55], facecolor=BG)
        ys = [r["cum_netto_r"] for r in eq_rows]
        ax.plot(range(len(ys)), ys, color=GOLD, lw=1.4)
        ax.axhline(0, color="#556", lw=0.8)
        for s in ax.spines.values():
            s.set_color("#556")
        ax.tick_params(colors=FG)
        ax.set_xlabel("Trade-Nr. (chronologisch)", color=FG)
        ax.set_ylabel("kumulierte Netto-R", color=FG)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


def _months_page(pdf, sid, months, variant_dir):
    fig = plt.figure(figsize=(8.27, 11.69), facecolor=BG)
    fig.text(0.07, 0.95, f"{sid} - Monatsuebersicht 01.2025-06.2026", color=GOLD,
             fontsize=14, fontweight="bold")
    y = 0.89
    fig.text(0.07, y, f"{'Monat':10}{'Trades':>8}{'Treffer%':>10}{'NettoR':>9}{'Netto%':>9}",
             color=GOLD, fontsize=10, family="monospace"); y -= 0.028
    for (yy, mm) in months:
        r = _load(os.path.join(variant_dir, f"Monat_{yy}-{mm:02d}.json"))
        hr = r.get("hit_rate")
        row = (f"{yy}-{mm:02d}   {r.get('closed_trades', 0):>6}"
               f"{(RP._n(hr * 100, 1) if isinstance(hr, (int, float)) else '-'):>10}"
               f"{RP._n(r.get('total_r_netto'), 1, True):>9}{RP._n(r.get('net_profit_pct'), 1, True):>9}")
        fig.text(0.07, y, row, color=FG, fontsize=10, family="monospace"); y -= 0.026
    fig.text(0.07, 0.05, "Monatswerte = im jeweiligen Monat GESCHLOSSENE Trades.", color=GREY, fontsize=8)
    pdf.savefig(fig, facecolor=BG); plt.close(fig)


def _equity_by_variant(universe_dir):
    eq = {}
    p = os.path.join(universe_dir, "_CSV_Audit", "equity_curve.csv")
    if os.path.exists(p):
        for row in csv.DictReader(open(p, encoding="utf-8")):
            v = row.get("cum_netto_r")
            eq.setdefault(row["strategy_id"], []).append(
                {"cum_netto_r": float(v) if v not in (None, "") else 0.0})
    return eq


def build_all(universe_dir, variants, start, end, label="Backtest 18M"):
    """Erzeugt je Variante <Label>_Bericht.pdf (Gesamt+Equity+Monate) + Vergleich_Bericht.pdf.
    Gibt den reports-Dict fuer TelegramService.deliver_reports."""
    months = month_list(start, end)
    eq = _equity_by_variant(universe_dir)
    reports = {"short_texts": {}, "variant_pdfs": {}}
    for sid in variants:
        lbl = VARIANT_LABELS.get(sid, sid.replace(" ", "_"))
        vdir = os.path.join(universe_dir, lbl)
        overall = _load(os.path.join(vdir, f"{lbl}_GESAMT.json"))
        pdf_path = os.path.join(vdir, f"{lbl}_Bericht.pdf")
        with PdfPages(pdf_path) as pdf:
            _metrics_page(pdf, overall, f"{sid} - GESAMT ({label})")
            _equity_page(pdf, sid, eq.get(sid, []))
            _months_page(pdf, sid, months, vdir)
        reports["variant_pdfs"][sid] = pdf_path
        reports["short_texts"][sid] = RP.short_text(overall, label) if overall else ""
    comp = _load(os.path.join(universe_dir, "_GESAMT_Vergleich", "GESAMT_alle-Varianten.json"))
    comp_path = os.path.join(universe_dir, "_GESAMT_Vergleich", "Vergleich_Bericht.pdf")
    if comp:
        RP.build_comparison_pdf(comp, comp_path)
        reports["comparison_pdf"] = comp_path
    return reports
