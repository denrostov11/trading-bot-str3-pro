# -*- coding: utf-8 -*-
"""Baut die Muster-Trade-PDFs v2 (Top-down nach Toris Methode): 3 Nachrechnungs-Muster (mit Ausgang/C+) + 1 Live-Muster
(Einstieg, ohne Ausgang). Nur lesen/rechnen; nichts wird gesendet, nichts live geschaltet.

Quelldaten (alles Kopien, read-only):
  Nachrechnung : Analysen/cplus_pro1/daten_kopie            (trades.json, ledger.json, data_cache/*.csv)
  Live-Muster  : Analysen/mtf_muster/v2/daten_kopie_live    (Kopie aus Prototyp/paper_runtime_2monate: trades.json, ledger.json, 1h-CSV)
Tageshistorie: Prototyp_v2/mtf_cache (einmaliger Yahoo-Abruf je Symbol, danach lokal).
Aufruf (Bot-venv):  python build_muster_v2.py
"""
import os, sys, json, time, warnings
V2 = r"C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp_v2"
sys.path.insert(0, V2)
import pandas as pd
from mtf import data as D, params as PR, trade_pdf as TP, telegram_text as TT
from engine import tracker as T

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
SRC = os.path.join(os.path.dirname(BASE), "cplus_pro1", "daten_kopie")
LIVE = os.path.join(HERE, "daten_kopie_live")
CHOICES = [("SOL-USD", "2026-08-17T04:00", "sol_long_2026-08-17"),
           ("GBPJPY=X", "2026-08-28T16:00", "gbpjpy_short_2026-08-28"),
           ("AUDUSD=X", "2026-09-02T00:00", "audusd_short_2026-09-02")]
LIVE_CHOICE = ("GBPAUD=X", "2026-10-15T04:00", "live_gbpaud_long_2026-10-15")


def _load(src_dir):
    trades = [t for t in json.load(open(os.path.join(src_dir, "trades.json"), encoding="utf-8")) if t["strategy_id"] == "Str.3 Pro.1"]
    led = json.load(open(os.path.join(src_dir, "ledger.json"), encoding="utf-8"))
    return trades, {c["parent_signal_id"]: c for c in led["candidates"]}


def _summary(name, sym, A, src, out, secs, extra=None):
    it = A["td"]["items"]
    s = {"name": name, "symbol": sym, "direction": A["direction"], "daily_source": src, "seconds": round(secs, 1),
         "pdf_bytes": os.path.getsize(out),
         "lines": {tf: ("ja" if A["ctxs"][tf].action is not None else "nein") for tf in ("M", "W", "D", "1h")} | {"4h": "ja (Signal)"},
         "kinds": {tf: A["ctxs"][tf].kind for tf in ("M", "W", "D", "1h")},
         "safety": {tf: A["ctxs"][tf].safety is not None for tf in ("M", "W", "D", "1h")},
         "topdown": f"{A['td']['count']} von 4", "verdicts": {tf: it[tf]["verdict"] for tf in ("M", "W", "D", "1h")},
         "scores": {tf: it[tf]["score"] for tf in ("M", "W", "D")}, "warnings": A["warnings"]}
    if extra:
        s.update(extra)
    return s


def main():
    summary = []
    trades, cand = _load(SRC)
    for sym, sig, name in CHOICES:
        t0 = time.time()
        t = next(x for x in trades if x["symbol"] == sym and x["signal_time"].startswith(sig))
        h1 = D.load_1h(os.path.join(SRC, "data_cache", D.safe(sym) + "__1h.csv"))
        daily, src = D.load_daily(sym, h1=h1)
        A = TP.analyse(t, cand[t["parent_signal_id"]]["snapshot"], h1, daily, T.cost_fraction(t["asset_class"]), muster=True)
        r = t["result"]
        TP.add_outcome(A, {"outcome": r["outcome"], "exit_time": r["exit_time"], "exit_price": r["exit_price"],
                           "netto_r": r["netto_r"], "net_pct": r["net_return_pct"]})
        out = os.path.join(HERE, f"Muster_{name}.pdf")
        TP.make_trade_pdf(out, A, TT.description(A))
        secs = time.time() - t0
        with open(os.path.join(HERE, f"Telegram_Text_{name}.txt"), "w", encoding="utf-8") as f:
            f.write(TT.telegram_draft(A) + "\n\n--- Entwurf, wird NICHT gesendet. Die PDF Muster_" + name + ".pdf würde angehängt. ---\n")
        summary.append(_summary(name, sym, A, src, out, secs, {"cplus_r": A.get("cplus_r"), "ist_r": r["netto_r"]}))
        print(name, os.path.getsize(out), "Bytes", round(secs, 1), "s", summary[-1]["verdicts"], summary[-1]["topdown"], A["warnings"])

    # ---- Live-Muster: Einstieg, KEIN Ausgang, KEINE C+-Auswertung; C+-Angaben + live_info wie im Live-Lauf
    sym, sig, name = LIVE_CHOICE
    trades, cand = _load(LIVE)
    t = next(x for x in trades if x["symbol"] == sym and x["signal_time"].startswith(sig))
    h1 = D.load_1h(os.path.join(LIVE, D.safe(sym) + "__1h.csv"))
    t0 = time.time()
    daily, src = D.load_daily(sym, h1=h1)
    last = h1.iloc[-1]
    live = {"price": float(last["Close"]), "time": last["End"]}          # Kopie-Stand = "jetzt" fuer das Muster
    A = TP.analyse(t, cand[t["parent_signal_id"]]["snapshot"], h1, daily, T.cost_fraction(t["asset_class"]),
                   c_plus={}, live_info=live, muster=False)
    out = os.path.join(HERE, f"Live_{name}.pdf")
    TP.make_trade_pdf(out, A, TT.description(A), label="Strategie 3 Pro · Live-MUSTER (Einstieg, ohne Ausgang) · Paper-Trading")
    secs = time.time() - t0
    with open(os.path.join(HERE, f"Telegram_Text_{name}.txt"), "w", encoding="utf-8") as f:
        f.write(TT.telegram_draft(A) + "\n\n--- Entwurf, wird NICHT gesendet. ---\n")
    summary.append(_summary(name, sym, A, src, out, secs))
    print(name, os.path.getsize(out), "Bytes", round(secs, 1), "s", summary[-1]["verdicts"], summary[-1]["topdown"], A["warnings"])

    with open(os.path.join(HERE, "zusammenfassung.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False, default=str)
    with open(os.path.join(HERE, "Parameter_je_Zeitrahmen.md"), "w", encoding="utf-8") as f:
        f.write(PR.param_doc_md())


if __name__ == "__main__":
    main()
