# -*- coding: utf-8 -*-
"""Erzeugt ein BEISPIEL-Ergebnisbild (Vorher/Nachher) mit dem BTC-Trade als Demo."""
import os, sys
from alert_bot import fetch_4h, exit_chart, composite_chart, tg_photo, val_fmt, TRADES_DIR

t = {
    "id": "DEMO_Bitcoin", "proto": "Str.3 Pro.1", "name": "Bitcoin BTC (BEISPIEL)",
    "sym": "BTC-USD", "direction": "LONG",
    "entry": 64378.16, "stop": 63268.15, "target": 67095.67, "rr": 2.4,
    "opened": "10.07.2026 23:20",
    "entry_chart": os.path.abspath(os.path.join("..", "Alerts", "ALERT_Bitcoin_BTC.png")),
}
sym, df = fetch_4h([t["sym"]])
if df is None:
    print("keine Daten"); sys.exit(1)
exit_i = len(df) - 1
outcome = "ZIEL"                      # Demo: wir tun so, als waere das Ziel erreicht
result_r, pct = 2.4, (t["target"] - t["entry"]) / t["entry"] * 100
ex = exit_chart(df, t, exit_i, outcome)
comp = composite_chart(t, ex, result_r, pct, outcome)
cap = (f"🧪 BEISPIELBILD (Demo - kein echtes Ergebnis!)\n"
       f"So sieht die Meldung aus, wenn ein Trade beendet ist:\n\n"
       f"✅ GEWINN - Trade beendet: Bitcoin BTC (Str.3 Pro.1)\n"
       f"Richtung: LONG\n"
       f"Einstieg: {val_fmt(t['entry'])} am {t['opened']}\n"
       f"Ausgang: {val_fmt(t['target'])} per ZIEL am 14.07.2026 08:00\n"
       f"Stop: {val_fmt(t['stop'])} | Ziel: {val_fmt(t['target'])}\n"
       f"Ergebnis: +2.4R (+4.22 %) | Dauer: 3.4 Tage")
tg_photo(comp, cap)
print("Beispielbild erstellt und an Telegram gesendet:", comp)
