# -*- coding: utf-8 -*-
"""Einmalig: aktuelle Bitcoin-Analyse als Telegram-Nachricht senden (korrigiertes Format)."""
import sys
from alert_bot import analyze, alert_chart, tg_photo, tg_text, val_fmt

def log(s):  # Konsole vertraegt kein Emoji -> nur ASCII ausgeben
    print(s.encode("ascii", "replace").decode())

r = analyze("Bitcoin BTC", ["BTC-USD"])
if r is None or r["status"] == "NONE":
    tg_text("Bitcoin: aktuell kein qualifiziertes Strategie-3-Setup.")
    log("kein Setup"); sys.exit(0)

if r["status"] == "TRIGGER":
    rr_txt = f"{r['rr']:.1f}R" if r.get("rr") else "-"
    warn = "" if (r.get("rr") or 0) >= 2 else "\n⚠️ Kein 2R-Ziel gefunden - Setup kritisch pruefen!"
    cap = (f"🚨 {r['direction']}-TRIGGER: Bitcoin BTC (Neuversand, korrigiertes Format)\n"
           f"4h-Schluss jenseits der Action-Line ({len(r['action'].taps)} Taps, {r['action'].angle_deg:.0f}°)\n"
           f"Einstieg: {val_fmt(r['entry'])}\n"
           f"Stop: {val_fmt(r['stop'])} (Safety-Line, 4. Kerze)\n"
           f"Ziel: {val_fmt(r['target'])} (S/R-Zone, {rr_txt}){warn}\n"
           f"Du pruefst - du entscheidest.")
    fn = alert_chart(r["df"], "Bitcoin BTC", r["sym"], r["action"], r["safety"],
                     r["entry"], r["stop"], r["target"], r["direction"])
    tg_photo(fn, cap)
    log("TRIGGER-Nachricht gesendet: " + cap.replace("\n", " | "))
else:  # NEAR oder WATCH
    lv = r["trigger_val"]
    cap = (f"{'⚠️ Fast am Trigger' if r['status']=='NEAR' else '👀 Watchlist'}: Bitcoin BTC (Neuversand, korrigiertes Format)\n"
           f"Action-Line: {len(r['action'].taps)} Taps, {r['action'].angle_deg:.0f}°, Kurs {r['prox']:.1f} ATR entfernt\n"
           f"Moeglicher {r['direction']} bei 4h-Schluss jenseits {val_fmt(lv)}.")
    log("Nachricht gesendet: " + cap.replace("\n", " | "))
