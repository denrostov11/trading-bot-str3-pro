# -*- coding: utf-8 -*-
"""Hilfsskript: liest die Chat-IDs der Telegram-Gruppen aus, in die der Bot aufgenommen wurde.

Vorgehen des Nutzers VORHER:
  1. 10 Gruppen anlegen (Str3 Pro1..Pro8, Str3 Vergleich, Str3 System).
  2. Bot @Str3_trading_alerts_bot in JEDE Gruppe aufnehmen (Postrecht/Admin).
  3. In JEDER Gruppe einmal irgendetwas schreiben (damit der Bot die Gruppe 'sieht').
  4. Dem Bot einmal PRIVAT schreiben (fuer die eigene User-ID der Befehls-Allowlist).
Dann dieses Skript ausfuehren:  venv/Scripts/python telegram_discover.py

Es zeigt je Gruppe: Titel -> Chat-ID (negativ) und die eigene User-ID.
Der Bot-Token wird NIE ausgegeben. Trage die IDs anschliessend selbst in die .env ein.
"""
import os, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import requests

HERE = os.path.dirname(os.path.abspath(__file__))


def read_env():
    vals = {}
    with open(os.path.join(HERE, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); vals[k.strip()] = v.strip()
    return vals


def redact(text):
    return re.sub(r"\d{6,}:[A-Za-z0-9_\-]{30,}", "<TOKEN>", str(text))


def main():
    env = read_env()
    token = env.get("TELEGRAM_BOT_TOKEN", "")
    if not token:
        print("FEHLER: kein TELEGRAM_BOT_TOKEN in .env"); return
    api = f"https://api.telegram.org/bot{token}"
    try:
        r = requests.get(f"{api}/getUpdates", params={"timeout": 0}, timeout=20).json()
    except Exception as e:
        print("FEHLER beim Abruf:", redact(e)); return
    if not r.get("ok"):
        print("FEHLER:", redact(r.get("description"))); return

    groups = {}    # chat_id -> title
    users = {}     # user_id -> name
    for u in r.get("result", []):
        msg = u.get("message") or u.get("edited_message") or u.get("channel_post") or {}
        chat = msg.get("chat", {})
        if chat.get("type") in ("group", "supergroup", "channel"):
            groups[chat["id"]] = chat.get("title", "?")
        elif chat.get("type") == "private":
            frm = msg.get("from", {})
            users[frm.get("id")] = (frm.get("first_name", "") + " " + frm.get("last_name", "")).strip() \
                                   or frm.get("username", "?")

    print("\n=== Gefundene GRUPPEN (Titel -> Chat-ID) ===")
    if not groups:
        print("  (keine) - Bot in die Gruppen aufnehmen UND in jeder Gruppe eine Nachricht schreiben,")
        print("           dann dieses Skript erneut ausfuehren.")
    for cid, title in groups.items():
        print(f"  {title:28} -> {cid}")

    print("\n=== Eigene USER-ID (fuer TELEGRAM_AUTHORIZED_USER_IDS) ===")
    if not users:
        print("  (keine) - dem Bot einmal PRIVAT schreiben, dann erneut ausfuehren.")
    for uid, name in users.items():
        print(f"  {name:28} -> {uid}")

    print("\nHinweis: Telegram liefert nur die letzten ~24h an Updates. Falls eine Gruppe fehlt,")
    print("in ihr nochmal schreiben und Skript erneut laufen lassen. Trage die IDs in die .env ein:")
    print("  STR3_PRO1_CHAT_ID=... bis STR3_PRO8_CHAT_ID=..., STR3_COMPARISON_CHAT_ID=..., STR3_SYSTEM_CHAT_ID=...")
    print("  TELEGRAM_AUTHORIZED_USER_IDS=<deine User-ID>")


if __name__ == "__main__":
    main()
