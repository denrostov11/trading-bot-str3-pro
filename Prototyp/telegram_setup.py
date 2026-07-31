# -*- coding: utf-8 -*-
"""Einmalige Einrichtung: Verbindung testen, Chat-ID ermitteln, Testnachricht senden."""
import os, sys, io, re
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import requests

HERE = os.path.dirname(os.path.abspath(__file__))
ENV = os.path.join(HERE, ".env")

def read_env():
    vals = {}
    with open(ENV, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                vals[k.strip()] = v.strip()
    return vals

def write_chat_id(chat_id):
    with open(ENV, encoding="utf-8") as f:
        txt = f.read()
    txt = re.sub(r"TELEGRAM_CHAT_ID=.*", f"TELEGRAM_CHAT_ID={chat_id}", txt)
    with open(ENV, "w", encoding="utf-8") as f:
        f.write(txt)

env = read_env()
token = env.get("TELEGRAM_BOT_TOKEN", "")
if not token or "EINFUEGEN" in token:
    print("FEHLER: Kein Token in .env gefunden."); sys.exit(1)
API = f"https://api.telegram.org/bot{token}"

# 1) Verbindung testen
r = requests.get(f"{API}/getMe", timeout=15).json()
if not r.get("ok"):
    print("FEHLER: Token ungueltig ->", r.get("description")); sys.exit(1)
bot = r["result"]
print(f"Verbunden mit Bot: @{bot.get('username')} ({bot.get('first_name')})")

# 2) Chat-ID aus /start ermitteln
r = requests.get(f"{API}/getUpdates", timeout=15).json()
chats = {}
for u in r.get("result", []):
    msg = u.get("message") or u.get("edited_message")
    if msg and "chat" in msg:
        c = msg["chat"]
        chats[c["id"]] = f"{c.get('first_name','')} {c.get('last_name','')}".strip() or c.get("username", "?")
if not chats:
    print("FEHLER: Keine Nachricht gefunden. Bitte dem Bot in Telegram nochmal /start oder 'hallo' schreiben und dieses Skript erneut ausfuehren.")
    sys.exit(1)
chat_id = list(chats.keys())[-1]
print(f"Chat-ID gefunden: {chat_id} ({chats[chat_id]}) -> wird in .env gespeichert")
write_chat_id(chat_id)

# 3) Testnachricht senden
text = ("\U0001F7E2 Verbindung steht!\n\n"
        "Trading-Bot (Strategie 3) ist mit Telegram verbunden.\n"
        "Hier kommen kuenftig die Alerts an:\n"
        "\U0001F6A8 Trigger ausgeloest (Einstieg + Stop + Ziel)\n"
        "⚠️ Kurs naehert sich einem Trigger\n"
        "➕/➖ Setup neu / entfallen")
r = requests.post(f"{API}/sendMessage", data={"chat_id": chat_id, "text": text}, timeout=15).json()
print("Testnachricht gesendet!" if r.get("ok") else f"FEHLER beim Senden: {r.get('description')}")
