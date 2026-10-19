# -*- coding: utf-8 -*-
"""Baut die MUSTER-Trade-PDFs (Top-down nach Toris Methode) fuer 3 ausgewaehlte Trades des Zwei-Monats-Tests.
Nur lesen/rechnen; nichts wird gesendet, nichts live geschaltet. Quelldaten: die Kopie in
Analysen/cplus_pro1/daten_kopie (read-only) + Tageshistorie aus Prototyp/mtf_cache (einmalig von Yahoo geholt)."""
import os, sys, json
PROTO = r"C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp"
sys.path.insert(0, PROTO)
import pandas as pd
from mtf import data as D, params as PR, trade_pdf as TP, telegram_text as TT
from engine import tracker as T

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(os.path.dirname(HERE), "cplus_pro1", "daten_kopie")
CHOICES = [("SOL-USD", "2026-08-17T04:00", "sol_long_2026-08-17"),
           ("GBPJPY=X", "2026-08-28T16:00", "gbpjpy_short_2026-08-28"),
           ("AUDUSD=X", "2026-09-02T00:00", "audusd_short_2026-09-02")]


def main():
    trades = [t for t in json.load(open(os.path.join(SRC, "trades.json"), encoding="utf-8")) if t["strategy_id"] == "Str.3 Pro.1"]
    led = json.load(open(os.path.join(SRC, "ledger.json"), encoding="utf-8"))
    cand = {c["parent_signal_id"]: c for c in led["candidates"]}
    summary = []
    for sym, sig, name in CHOICES:
        t = next(x for x in trades if x["symbol"] == sym and x["signal_time"].startswith(sig))
        snap = cand[t["parent_signal_id"]]["snapshot"]
        h1 = D.load_1h(os.path.join(SRC, "data_cache", D.safe(sym) + "__1h.csv"))
        daily, src = D.load_daily(sym, h1=h1)
        A = TP.analyse(t, snap, h1, daily, T.cost_fraction(t["asset_class"]))
        r = t["result"]
        ist = {"outcome": r["outcome"], "exit_time": r["exit_time"], "exit_price": r["exit_price"],
               "netto_r": r["netto_r"], "net_pct": r["net_return_pct"]}
        TP.add_outcome(A, ist)
        desc = TT.description(A)
        out = os.path.join(HERE, f"Muster_{name}.pdf")
        TP.make_trade_pdf(out, A, desc)
        draft = TT.telegram_draft(A)
        with open(os.path.join(HERE, f"Telegram_Entwurf_{name}.txt"), "w", encoding="utf-8") as f:
            f.write(draft + "\n\n--- Hinweis: Entwurf, wird NICHT gesendet. Die PDF Muster_" + name + ".pdf würde angehängt. ---\n")
        it = A["td"]["items"]
        summary.append({"name": name, "symbol": sym, "direction": A["direction"], "daily_source": src,
                        "lines": {tf: ("ja" if A["ctxs"][tf].action is not None else "nein") for tf in ("M", "W", "D", "1h")} | {"4h": "ja (Signal)"},
                        "kinds": {tf: A["ctxs"][tf].kind for tf in ("M", "W", "D", "1h")},
                        "safety": {tf: A["ctxs"][tf].safety is not None for tf in ("M", "W", "D", "1h")},
                        "topdown": f"{A['td']['count']} von 4", "supports": {tf: it[tf]["supports"] for tf in ("M", "W", "D", "4h")},
                        "rebuild_info": {k: (bool(v) if isinstance(v, (bool,)) or str(type(v)).endswith("bool_'>") else v) for k, v in A["info"].items()},
                        "cplus_r": A.get("cplus_r"), "ist_r": r["netto_r"], "pdf_bytes": os.path.getsize(out)})
        print(name, os.path.getsize(out), "Bytes", summary[-1]["lines"], summary[-1]["topdown"], A.get("cplus_r"))
    with open(os.path.join(HERE, "zusammenfassung.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False, default=str)
    with open(os.path.join(HERE, "Parameter_je_Zeitrahmen.md"), "w", encoding="utf-8") as f:
        f.write("# Parameter je Zeitrahmen (Skalierung der bar-basierten Erkennung)\n\n" + PR.param_table_md())


if __name__ == "__main__":
    main()
