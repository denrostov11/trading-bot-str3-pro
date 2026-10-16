# -*- coding: utf-8 -*-
"""Sendet Ausstiege_im_Vergleich.pdf EINMAL per sendDocument an die System-Gruppe (gleicher Sender wie der
Bericht-Listener: notify.transport.RealTelegramTransport). Token/Chat-ID werden zur Laufzeit aus der
Konfiguration geladen und nie ausgegeben. Zahlen der Bildunterschrift kommen aus einzeltrades_pro1.csv.
Aufruf (Bot-venv): python ausstiege_senden.py"""
import os, sys, csv
HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = r"C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp"
sys.path.insert(0, PROTO)
from notify.report_listener import read_settings           # noqa: E402
from notify.transport import RealTelegramTransport         # noqa: E402

rows = list(csv.DictReader(open(os.path.join(HERE, "einzeltrades_pro1.csv"), encoding="utf-8-sig"), delimiter=";"))
num = lambda x: float(x.replace(",", "."))
pct = {v: sum(num(r[f"{v}_netto_pct"]) for r in rows if r[f"{v}_status"] == "closed") for v in ("IST", "B", "C+", "D")}
fmt = lambda x: f"{x:+.1f}".replace(".", ",").replace("-", "−") + " %"
caption = ("Ausstiegsregeln im Vergleich (Pro.1, Zwei-Monats-Papiertest): "
           + " | ".join(f"{v} {fmt(pct[v])}" for v in ("IST", "B", "C+", "D"))
           + " – Erklärung für Einsteiger im PDF.")
pdf = os.path.join(HERE, "Ausstiege_im_Vergleich.pdf")
assert os.path.exists(pdf) and len(caption) <= 1024
st = read_settings()
res = RealTelegramTransport(st["token"]).send_document(st["system_chat"], pdf, caption)
print("Versand:", "OK" if res.ok else "FEHLER", "message_id =", res.message_id)
print("Bildunterschrift:", caption)
