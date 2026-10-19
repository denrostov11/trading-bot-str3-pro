# -*- coding: utf-8 -*-
"""Kopiert (READ-ONLY auf der Quelle) trades.json, ledger.json und die 1h-Caches der Pro.1-Symbole in daten_kopie/."""
import os, json, shutil, time
import pandas as pd
SRC = r"C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp\paper_runtime_2monate"
DST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "daten_kopie")
os.makedirs(os.path.join(DST, "data_cache"), exist_ok=True)
safe = lambda s: "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))
for name in ("trades.json", "ledger.json", "START_MANIFEST.json"):
    for _ in range(5):
        shutil.copyfile(os.path.join(SRC, name), os.path.join(DST, name))
        try:
            json.load(open(os.path.join(DST, name), encoding="utf-8")); break
        except ValueError:
            time.sleep(1)
trades = json.load(open(os.path.join(DST, "trades.json"), encoding="utf-8"))
syms = sorted({t["symbol"] for t in trades if t["strategy_id"] == "Str.3 Pro.1"})
for s in syms:
    fn = f"{safe(s)}__1h.csv"
    for _ in range(5):
        shutil.copyfile(os.path.join(SRC, "data_cache", fn), os.path.join(DST, "data_cache", fn))
        d = pd.read_csv(os.path.join(DST, "data_cache", fn))
        if len(d) and pd.notna(d.iloc[-1]).all():
            break
        time.sleep(1)
print("kopiert:", len(syms), "Symbole;", sum(1 for t in trades if t["strategy_id"] == "Str.3 Pro.1"), "Pro.1-Trades")
