# -*- coding: utf-8 -*-
"""Sendet Pro1_Baseline_Tradejournal.pdf EINMAL per sendDocument an die System-Gruppe (gleicher Sender wie der
Bericht-Listener). Token/Chat-ID werden zur Laufzeit geladen und nie ausgegeben. Zahlen aus journal_daten.json."""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, r"C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp")
from notify.report_listener import read_settings          # noqa: E402
from notify.transport import RealTelegramTransport        # noqa: E402

J = json.load(open(os.path.join(HERE, "journal_daten.json"), encoding="utf-8"))
t, m = J["tot"], J["meta"]
fmt = lambda x, d=1: (f"{x:+.{d}f}").replace(".", ",").replace("-", "−")
caption = (f"Pro.1 Baseline – Trade-Journal Zwei-Monats-Test bis {m['stichtag_berlin']}: {t['closed']} Trades, {t['win']}/{t['loss']}, "
           f"Gesamt {fmt(t['pct'])} %, Netto {fmt(t['r'], 2)} R. Alle Einstiege, Stops, Ziele und Ausstiege zum Nachprüfen im PDF.")
pdf = os.path.join(HERE, "Pro1_Baseline_Tradejournal.pdf")
assert os.path.exists(pdf) and len(caption) <= 1024 and m["matches_report"]
st = read_settings()
res = RealTelegramTransport(st["token"]).send_document(st["system_chat"], pdf, caption)
print("Versand:", "OK" if res.ok else "FEHLER", "message_id =", res.message_id)
print("Bildunterschrift:", caption)
