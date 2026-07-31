# -*- coding: utf-8 -*-
"""
Strategie 3 - ALERT-BOT (Session 2)
Ueberwacht alle Instrumente, erkennt Trigger (4h-Schluss jenseits einer intakten
A+ Action-Line) und meldet per Telegram: Einstieg, Stop (Safety-Line-Projektion
4. Kerze), Ziel (naechste S/R-Zone mit >=2R) + Chart-Bild.

Modi:
  python alert_bot.py --once   -> ein Zyklus (Test / manuell)
  python alert_bot.py          -> Endlosschleife, prueft jede Stunde
Meldungen (dedupliziert ueber state.json):
  TRIGGER  - Linie gebrochen -> komplette Trade-Eckdaten + Chart
  NAHE     - Kurs < 1 ATR vor der Linie -> Vorwarnung
  NEU      - neues A+-Setup in der Watchlist (nur Info)
Erststart: keine Einzel-Alerts, nur Zusammenfassung (verhindert Spam).
"""
import os, sys, io, json, time, math, argparse, traceback
_HERE = os.path.dirname(os.path.abspath(__file__))
if sys.stdout is None or not hasattr(sys.stdout, "buffer"):
    # Unsichtbarer Modus (pythonw): alles in Logdatei schreiben
    _log = open(os.path.join(_HERE, "bot_log.txt"), "a", encoding="utf-8", buffering=1)
    sys.stdout = _log
    sys.stderr = _log
elif "utf" not in (sys.stdout.encoding or "").lower():
    _old_stdout = sys.stdout   # Referenz behalten, sonst schliesst GC den Puffer
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
import requests
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

from scan_100 import (INSTRUMENTS, fetch_4h, atr, pivots, find_lines, is_aplus,
                      pick_safety, MIN_TAPS)

HERE = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(HERE, "state.json")
ALERT_DIR = os.path.join(os.path.dirname(HERE), "Alerts")
os.makedirs(ALERT_DIR, exist_ok=True)

MAX_PROX_ATR = 5.0
NEAR_ATR = 1.0
TRIGGER_MAX_AGE = 3       # Bruch max. 3 Kerzen alt -> noch als Trigger melden
MAX_MSGS_PER_CYCLE = 10

# ---------------- Telegram ----------------
def read_env():
    vals = {}
    with open(os.path.join(HERE, ".env"), encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); vals[k.strip()] = v.strip()
    return vals

ENV = read_env()
API = f"https://api.telegram.org/bot{ENV['TELEGRAM_BOT_TOKEN']}"
CHAT = ENV["TELEGRAM_CHAT_ID"]
CFG_FILE = os.path.join(HERE, "bot_config.json")

def load_cfg():
    if os.path.exists(CFG_FILE):
        with open(CFG_FILE, encoding="utf-8") as f: return json.load(f)
    return {"muted": False, "tg_offset": 0, "queue": [], "last_cycle": "", "last_counts": {}}

def save_cfg(cfg):
    with open(CFG_FILE, "w", encoding="utf-8") as f: json.dump(cfg, f, indent=1)

def tg_text(text):
    try:
        requests.post(f"{API}/sendMessage", data={"chat_id": CHAT, "text": text}, timeout=20)
    except Exception as e:
        print("Telegram-Fehler:", e)

def tg_photo(path, caption):
    try:
        with open(path, "rb") as f:
            requests.post(f"{API}/sendPhoto", data={"chat_id": CHAT, "caption": caption[:1024]},
                          files={"photo": f}, timeout=40)
    except Exception as e:
        print("Telegram-Foto-Fehler:", e)

def notify_text(cfg, text):
    """Nachricht senden - oder im Nachtmodus in die Warteschlange legen."""
    if cfg.get("muted"):
        cfg["queue"].append(text); save_cfg(cfg)
    else:
        tg_text(text)

def notify_photo(cfg, path, caption):
    if cfg.get("muted"):
        cfg["queue"].append(caption + f"\n(Chart gespeichert: {os.path.basename(path)})")
        save_cfg(cfg)
    else:
        tg_photo(path, caption)

def check_telegram_commands(cfg):
    """Verarbeitet eingehende Nachrichten: 'gute nacht', 'guten morgen', 'status'."""
    try:
        r = requests.get(f"{API}/getUpdates",
                         params={"offset": cfg.get("tg_offset", 0) + 1, "timeout": 0},
                         timeout=15).json()
    except Exception:
        return
    for u in r.get("result", []):
        cfg["tg_offset"] = u["update_id"]
        msg = u.get("message") or {}
        if str(msg.get("chat", {}).get("id")) != str(CHAT):
            continue  # nur der Besitzer darf steuern
        text = (msg.get("text") or "").strip().lower()
        if "gute nacht" in text:
            cfg["muted"] = True
            tg_text("🌙 Gute Nacht! Ich sammle Meldungen leise weiter und melde mich erst, "
                    "wenn du 'guten morgen' schreibst.")
            print("Nachtmodus AN")
        elif "guten morgen" in text:
            cfg["muted"] = False
            q = cfg.get("queue", [])
            if q:
                tg_text(f"☀️ Guten Morgen! Waehrend der Nacht gab es {len(q)} Meldung(en):")
                block = ""
                for item in q:
                    if len(block) + len(item) > 3500:
                        tg_text(block); block = ""
                    block += ("\n\n" if block else "") + item
                if block: tg_text(block)
                cfg["queue"] = []
            else:
                tg_text("☀️ Guten Morgen! Ueber Nacht gab es keine neuen Meldungen.")
            print("Nachtmodus AUS")
        elif text == "status":
            c = cfg.get("last_counts", {})
            tg_text(f"📊 Status (letzter Zyklus {cfg.get('last_cycle','-')}):\n"
                    f"Watch: {c.get('WATCH',0)} | Fast am Trigger: {c.get('NEAR',0)} | "
                    f"Trigger: {c.get('TRIGGER',0)}\n"
                    f"Nachtmodus: {'AN 🌙' if cfg.get('muted') else 'aus'}")
        elif text in ("bilanz", "trades"):
            tg_text(bilanz_text())
        elif text == "bericht":
            tg_text("📄 Erstelle Bericht (7 Tage) - einen Moment...")
            send_report(cfg, 7, "7-Tage")
    save_cfg(cfg)

# ---------------- S/R-Zonen + Stop/Ziel ----------------
def sr_levels(df, piv, a):
    """Horizontale S/R-Level aus Pivot-Clustern (Cluster-Toleranz 0.6 ATR)."""
    lows, highs = piv
    pts = sorted([float(df.Low[i]) for i in lows] + [float(df.High[i]) for i in highs])
    tol = 0.6 * float(a.iloc[-1])
    levels, cluster = [], []
    for p in pts:
        if not cluster or p - cluster[-1] <= tol: cluster.append(p)
        else:
            if len(cluster) >= 2: levels.append(sum(cluster) / len(cluster))
            cluster = [p]
    if len(cluster) >= 2: levels.append(sum(cluster) / len(cluster))
    return levels

def stop_and_target(df, action, safety, piv, a, direction):
    """Stop = Safety-Line-Wert an (Bruchkerze+4); Ziel = naechste S/R-Zone mit >=2R."""
    n = len(df)
    bb = action.breaking_bar if action.breaking_bar > 0 else n - 1
    entry = float(df.Close[bb])
    stop = float(safety.value_at(bb + 4)) if safety else None
    if stop is None: return entry, None, None, None
    risk = abs(entry - stop)
    if risk <= 0: return entry, stop, None, None
    levels = sr_levels(df, piv, a)
    target, rr = None, None
    if direction == "SHORT":
        cands = sorted([lv for lv in levels if lv < entry - 0.5 * risk], reverse=True)
        for lv in cands:
            r = (entry - lv) / risk
            if r >= 2.0: target, rr = lv, r; break
        if target is None and cands: target, rr = cands[-1], (entry - cands[-1]) / risk
    else:
        cands = sorted([lv for lv in levels if lv > entry + 0.5 * risk])
        for lv in cands:
            r = (lv - entry) / risk
            if r >= 2.0: target, rr = lv, r; break
        if target is None and cands: target, rr = cands[-1], (cands[-1] - entry) / risk
    return entry, stop, target, rr

# ---------------- Chart fuer Alert ----------------
def alert_chart(df, name, sym, action, safety, entry, stop, target, direction):
    n = len(df)
    fig, ax = plt.subplots(figsize=(13, 6.8), facecolor="#0f1320")
    ax.set_facecolor("#0f1320")
    for i in range(n):
        o, h, l, c = df.Open[i], df.High[i], df.Low[i], df.Close[i]
        col = "#16c784" if c >= o else "#ea3943"
        ax.plot([i, i], [l, h], color=col, lw=0.6, zorder=2)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-9),
                               facecolor=col, edgecolor=col, zorder=3))
    def draw(ln, color, style, label):
        xs = [ln.i0, n - 1]
        ax.plot(xs, [ln.value_at(x) for x in xs], color=color, ls=style, lw=1.0,
                alpha=0.85, zorder=4, label=label)
        for t in ln.taps:
            ax.plot(t, ln.value_at(t), "o", ms=6, mfc="none", mec=color, mew=1.2, zorder=5)
    draw(action, "#3fd0e0", "-", f"Action-Line ({len(action.taps)} Taps)")
    if safety: draw(safety, "#e0a526", "--", f"Safety Line ({len(safety.taps)} Taps)")
    if action.breaking_bar > 0:
        ax.axvline(action.breaking_bar, color="#ffffff", lw=0.9, ls=":", alpha=0.7)
    for val, col, lab in ((entry, "#ffffff", f"Einstieg {val_fmt(entry)}"),
                          (stop, "#ff5c6c", f"Stop {val_fmt(stop)}"),
                          (target, "#1fbf75", f"Ziel {val_fmt(target)}")):
        if val is not None:
            ax.axhline(val, color=col, lw=1.4, ls="--", alpha=0.9)
            ax.text(n * 0.995, val, "  " + lab, color=col, fontsize=10, fontweight="bold",
                    va="bottom", ha="right")
    ax.set_xlim(-2, n + 1); ax.margins(y=0.08)
    ax.grid(color="#1e2438", lw=0.5)
    ax.tick_params(colors="#9aa3b5", labelsize=8)
    for s in ax.spines.values(): s.set_color("#1e2438")
    step = max(1, n // 7)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([str(df.Time[i])[:10] for i in range(0, n, step)], color="#9aa3b5")
    ax.set_title(f"{name} ({sym}) - {direction}-TRIGGER - Strategie 3",
                 color="#e8ecf5", fontsize=13, fontweight="bold")
    ax.legend(facecolor="#191f33", labelcolor="#e8ecf5", edgecolor="#1e2438", fontsize=9)
    fig.tight_layout()
    safe = "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in name)
    fn = os.path.join(ALERT_DIR, f"ALERT_{safe}.png")
    fig.savefig(fn, dpi=300, facecolor="#0f1320")
    plt.close(fig)
    return fn

def val_fmt(v):
    """Kurs voll ausschreiben - nie wissenschaftliche Notation.
    Nachkommastellen je Groessenordnung: BTC 64380.04 | Gold 4123.50 | FX 1.6150 | DOGE 0.12345"""
    if v is None: return "-"
    a = abs(v)
    if a >= 100: return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")  # 64.380,04
    if a >= 1:   return f"{v:.4f}".replace(".", ",")                                       # 1,6150
    return f"{v:.6f}".rstrip("0").replace(".", ",")                                        # 0,12345

# ---------------- Paper-Trade-Tracker (Str.3 Pro.1) ----------------
PROTO = "Str.3 Pro.1"
TRADES_FILE = os.path.join(HERE, "trades.json")
TRADES_DIR = os.path.join(os.path.dirname(HERE), "Trades")
PROTO_DIR = os.path.join(os.path.dirname(HERE), "Str.3 Pro.1")
REPORTS_DIR = os.path.join(PROTO_DIR, "Berichte")
os.makedirs(TRADES_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

def copy_to_proto(path):
    """Bild zusaetzlich im Ordner Str.3 Pro.1 ablegen."""
    try:
        if path and os.path.exists(path):
            shutil.copy2(path, os.path.join(PROTO_DIR, os.path.basename(path)))
    except Exception:
        pass

def tg_document(path, caption):
    """Datei (z. B. PDF) unkomprimiert an Telegram senden."""
    try:
        with open(path, "rb") as f:
            requests.post(f"{API}/sendDocument",
                          data={"chat_id": CHAT, "caption": caption[:1024]},
                          files={"document": f}, timeout=120)
    except Exception as e:
        print("Telegram-Dokument-Fehler:", e)

def load_trades():
    if os.path.exists(TRADES_FILE):
        with open(TRADES_FILE, encoding="utf-8") as f: return json.load(f)
    return []

def save_trades(tr):
    with open(TRADES_FILE, "w", encoding="utf-8") as f: json.dump(tr, f, indent=1)

TRADE_COOLDOWN_H = 24  # Sperrzeit je Instrument nach Trade-Ende (Nutzer-Regel 15.07.2026)

# ---- Break-even-Automatik (Nutzer-Regel 15.07.2026) ----
# EINZIGER Mechanismus, der 15-Minuten-Kerzen nutzt - alles andere laeuft auf 1h/4h!
BE_CHECK_SECONDS = 900        # Pruefintervall: alle 15 Minuten
BE_TRIGGER_PCT_SLOW = 0.3     # Waehrungen & Indizes (wachsen langsam)
BE_TRIGGER_PCT_FAST = 1.0     # Krypto, Aktien, Rohstoffe u. a. volatilere Produkte
BE_BUFFER_FRACTION = 0.1      # Stop landet knapp jenseits des Einstiegs:
                              # Puffer = 10 % der Schwelle (0,03 % bzw. 0,1 %)
INDEX_FUT_SYMS = {"ES=F", "NQ=F", "YM=F", "RTY=F", "FTSEMIB.MI"}

def be_trigger_pct(sym):
    """Schwelle je Anlageklasse: 0,3 % fuer FX (=X) und Indizes (^... / Index-Futures),
    1,0 % fuer alles Volatilere (Krypto, Aktien, Rohstoffe, ETFs)."""
    if sym.endswith("=X") or sym.startswith("^") or sym in INDEX_FUT_SYMS:
        return BE_TRIGGER_PCT_SLOW
    return BE_TRIGGER_PCT_FAST

def fetch_15m(sym):
    import yfinance as yf
    df = yf.download(sym, period="1mo", interval="15m", auto_adjust=False,
                     progress=False, multi_level_index=False)
    if df is None or df.empty: return None
    return df[["Open", "High", "Low", "Close"]].dropna().reset_index(names="Time")

def check_break_even(cfg):
    """Nutzer-Regel 15.07.2026: Kreuzt der Kurs den Einstiegspunkt in Gewinnrichtung
    und laeuft mindestens die Klassen-Schwelle (0,3 % FX/Indizes, 1 % volatil) ueber
    (LONG) bzw. unter (SHORT) den Einstieg, wird der Stop automatisch von der
    Safety-Line auf knapp jenseits des Einstiegs nachgezogen -> der Trade kann kein
    Geld mehr verlieren. Geprueft wird auf 15m-Schlusskursen seit Trade-Eroeffnung."""
    trades = load_trades()
    changed = False
    for t in trades:
        if t["status"] != "open" or t.get("be_moved"): continue
        thr = be_trigger_pct(t["sym"]) / 100.0
        try:
            df = fetch_15m(t["sym"])
        except Exception:
            continue
        if df is None: continue
        lvl = t["entry"] * (1 + thr) if t["direction"] == "LONG" else t["entry"] * (1 - thr)
        hit = False
        for i in range(len(df)):
            try: ts = float(df.Time[i].timestamp())
            except Exception: continue
            if ts <= t["opened_ts"]: continue
            c = float(df.Close[i])
            if (t["direction"] == "LONG" and c >= lvl) or (t["direction"] == "SHORT" and c <= lvl):
                hit = True; break
        if not hit: continue
        buf = thr * BE_BUFFER_FRACTION
        new_stop = t["entry"] * (1 + buf) if t["direction"] == "LONG" else t["entry"] * (1 - buf)
        t["stop_initial"] = t["stop"]          # Original-Stop (Safety-Line) fuer die R-Rechnung
        t["stop"] = float(new_stop)
        t["be_moved"] = True
        t["be_time"] = time.strftime("%d.%m.%Y %H:%M")
        changed = True
        notify_text(cfg, f"🔒 Break-even: {t['name']} {t['direction']} ({t['proto']})\n"
                    f"Kurs lief ≥ {be_trigger_pct(t['sym'])} % in den Gewinn (15m-Pruefung).\n"
                    f"Stop von {val_fmt(t['stop_initial'])} auf {val_fmt(new_stop)} nachgezogen —\n"
                    f"dieser Trade kann kein Geld mehr verlieren.")
        print(f"Break-even gesetzt: {t['name']} Stop -> {new_stop}")
    if changed: save_trades(trades)

def sig_core(s):
    """Linien-Kern (Art, Ankerpreis, Steigung) aus einer sig — unabhaengig vom
    Bar-Index, der mit jedem Zyklus wandert. Versteht altes (4 Felder) und
    neues (3 Felder) Format."""
    try:
        parts = str(s).split(":")
        return (parts[0], float(parts[-2]), float(parts[-1]))
    except Exception:
        return None

def same_line(sig_a, sig_b):
    """Gleiche Trendlinie? Gleiche Art + gleicher Ankerpreis (0,1 %) und
    aehnliche Steigung (5 % — Re-Fits schwanken leicht)."""
    a, b = sig_core(sig_a), sig_core(sig_b)
    if not a or not b or a[0] != b[0]: return False
    p_tol = abs(a[1]) * 1e-3 or 1e-9
    s_tol = max(abs(a[2]), abs(b[2])) * 0.05 + 1e-12
    return abs(a[1] - b[1]) <= p_tol and abs(a[2] - b[2]) <= s_tol

def open_paper_trade(cfg, name, r, entry_chart_path):
    """Eroeffnet einen virtuellen Trade nach einem Trigger-Alert (nur mit Stop+Ziel).
    Nutzer-Regel vom 15.07.2026: pro Instrument nie zwei Trades gleichzeitig oder
    direkt hintereinander; jeder Trade braucht eine NEU konstruierte Linie."""
    if not (r.get("stop") and r.get("target")): return False
    trades = load_trades()
    mine = [t for t in trades if t["sym"] == r["sym"] or t["name"] == name]
    # 1) Instrument-Sperre: laeuft bereits ein Trade auf diesem Instrument?
    if any(t["status"] == "open" for t in mine):
        print(f"Trade uebersprungen ({name}): bereits ein offener Trade auf diesem Instrument")
        return False
    # 2) Abkuehlzeit: nicht direkt nach dem letzten Trade desselben Instruments
    now = time.time()
    if any(t.get("closed_ts") and now - float(t["closed_ts"]) < TRADE_COOLDOWN_H * 3600
           for t in mine):
        print(f"Trade uebersprungen ({name}): Abkuehlzeit ({TRADE_COOLDOWN_H} h) nach letztem Trade laeuft")
        return False
    # 3) Nur EIN Versuch pro Trendlinie — Linien-Kern statt Index vergleichen
    if any(same_line(t.get("sig", ""), r["sig"]) for t in mine):
        print(f"Trade uebersprungen ({name}): dieselbe Trendlinie wurde bereits gehandelt")
        return False
    bb = r["action"].breaking_bar
    try: opened_ts = float(r["df"].Time[bb].timestamp())
    except Exception: opened_ts = time.time()
    tid = time.strftime("%Y%m%d_%H%M") + "_" + "".join(c for c in name if c.isalnum())[:12]
    entry_copy = os.path.join(TRADES_DIR, f"{tid}_entry.png")
    try: shutil.copy2(entry_chart_path, entry_copy)
    except Exception: entry_copy = entry_chart_path
    def _anch(ln):
        try:
            return {"t0": float(r["df"].Time[ln.i0].timestamp()), "p0": float(ln.p0),
                    "t1": float(r["df"].Time[ln.i1].timestamp()), "p1": float(ln.p1)}
        except Exception:
            return None
    trades.append({
        "id": tid, "proto": PROTO, "name": name, "sym": r["sym"],
        "direction": r["direction"], "entry": float(r["entry"]),
        "stop": float(r["stop"]), "target": float(r["target"]),
        "rr": float(r.get("rr") or 0), "sig": r["sig"],
        "opened_ts": opened_ts, "opened": time.strftime("%d.%m.%Y %H:%M"),
        "entry_chart": entry_copy, "status": "open",
        "action_line": _anch(r["action"]),
        "safety_line": _anch(r["safety"]) if r.get("safety") else None,
    })
    save_trades(trades)
    copy_to_proto(entry_copy)
    print(f"Paper-Trade eroeffnet: {name} {r['direction']} @ {r['entry']}")
    return True

def exit_chart(df, t, exit_i, outcome):
    n = len(df)
    fig, ax = plt.subplots(figsize=(13, 6.2), facecolor="#0f1320")
    ax.set_facecolor("#0f1320")
    for i in range(n):
        o, h, l, c = df.Open[i], df.High[i], df.Low[i], df.Close[i]
        col = "#16c784" if c >= o else "#ea3943"
        ax.plot([i, i], [l, h], color=col, lw=0.6, zorder=2)
        ax.add_patch(Rectangle((i - 0.35, min(o, c)), 0.7, max(abs(c - o), 1e-9),
                               facecolor=col, edgecolor=col, zorder=3))
    # Trendlinien (duenn, aus den beim Einstieg gespeicherten Ankern)
    times = [float(x.timestamp()) for x in df.Time]
    med_dt = (times[-1] - times[0]) / max(1, len(times) - 1)
    def ts_idx(ts):
        if ts <= times[0]: return (ts - times[0]) / med_dt
        return min(range(len(times)), key=lambda i: abs(times[i] - ts))
    for L, col, style in ((t.get("action_line"), "#3fd0e0", "-"),
                          (t.get("safety_line"), "#e0a526", "--")):
        if not L: continue
        i0, i1 = ts_idx(L["t0"]), ts_idx(L["t1"])
        if abs(i1 - i0) < 1: continue
        slope = (L["p1"] - L["p0"]) / (i1 - i0)
        xs = [max(0, i0), n - 1]
        ax.plot(xs, [L["p0"] + slope * (x - i0) for x in xs],
                color=col, ls=style, lw=0.9, alpha=0.75, zorder=3.5)
    for val, col, lab in ((t["entry"], "#ffffff", "Einstieg"),
                          (t["stop"], "#ff5c6c", "Stop"),
                          (t["target"], "#1fbf75", "Ziel")):
        ax.axhline(val, color=col, lw=1.4, ls="--", alpha=0.9)
        ax.text(1, val, f" {lab} {val_fmt(val)}", color=col, fontsize=10, fontweight="bold", va="bottom")
    if exit_i is not None and 0 <= exit_i < n:
        ax.plot(exit_i, t["stop"] if outcome == "STOP" else t["target"],
                "X", ms=16, color="#ff5c6c" if outcome == "STOP" else "#1fbf75", zorder=6)
    ax.set_xlim(-2, n + 1); ax.margins(y=0.1)
    ax.grid(color="#1e2438", lw=0.5)
    ax.tick_params(colors="#9aa3b5", labelsize=8)
    for s in ax.spines.values(): s.set_color("#1e2438")
    step = max(1, n // 7)
    ax.set_xticks(range(0, n, step))
    ax.set_xticklabels([str(df.Time[i])[:10] for i in range(0, n, step)], color="#9aa3b5")
    ax.set_title(f"NACHHER: {t['name']} - Ausgang per {outcome}", color="#e8ecf5",
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    fn = os.path.join(TRADES_DIR, f"{t['id']}_exit.png")
    fig.savefig(fn, dpi=300, facecolor="#0f1320")
    plt.close(fig)
    return fn

def composite_chart(t, exit_png, result_r, pct, outcome):
    """Vorher/Nachher-Bild + Ergebniszeile."""
    fig = plt.figure(figsize=(13, 13.6), facecolor="#0f1320")
    gs = fig.add_gridspec(2, 1, height_ratios=[1, 1], hspace=0.06)
    for idx, (png, lab) in enumerate(((t["entry_chart"], "VORHER (Einstieg)"), (exit_png, "NACHHER (Ausgang)"))):
        ax = fig.add_subplot(gs[idx])
        try: ax.imshow(plt.imread(png))
        except Exception: pass
        ax.axis("off")
        ax.set_title(lab, color="#e0a526", fontsize=13, fontweight="bold", loc="left")
    win = outcome == "ZIEL"
    fig.suptitle(f"{'✔ GEWINN' if win else '✘ VERLUST'}  {result_r:+.1f}R ({pct:+.2f} %)  -  "
                 f"{t['name']} {t['direction']}  -  {t['proto']}",
                 color="#1fbf75" if win else "#ff5c6c", fontsize=15, fontweight="bold", y=0.995)
    fn = os.path.join(TRADES_DIR, f"{t['id']}_result.png")
    fig.savefig(fn, dpi=300, facecolor="#0f1320", bbox_inches="tight")
    plt.close(fig)
    return fn

def check_open_trades(cfg):
    """Prueft offene Paper-Trades gegen die neuesten Kurse (Stop/Ziel getroffen?).
    Konservativ: wird in derselben Kerze Stop UND Ziel beruehrt, zaehlt der Stop."""
    trades = load_trades()
    changed = False
    for t in trades:
        if t["status"] != "open": continue
        try:
            sym, df = fetch_4h([t["sym"]])
        except Exception:
            continue
        if df is None: continue
        outcome, exit_i = None, None
        for i in range(len(df)):
            try: bar_ts = float(df.Time[i].timestamp())
            except Exception: continue
            if bar_ts <= t["opened_ts"]: continue
            hi, lo = float(df.High[i]), float(df.Low[i])
            if t["direction"] == "SHORT":
                if hi >= t["stop"]: outcome, exit_i = "STOP", i; break
                if lo <= t["target"]: outcome, exit_i = "ZIEL", i; break
            else:
                if lo <= t["stop"]: outcome, exit_i = "STOP", i; break
                if hi >= t["target"]: outcome, exit_i = "ZIEL", i; break
        if not outcome: continue
        exit_price = t["stop"] if outcome == "STOP" else t["target"]
        # R immer auf das ORIGINAL-Risiko beziehen (vor Break-even-Verschiebung)
        risk = abs(t["entry"] - t.get("stop_initial", t["stop"])) or 1e-9
        move = (exit_price - t["entry"]) if t["direction"] == "LONG" else (t["entry"] - exit_price)
        result_r = move / risk if outcome == "STOP" else abs(t["target"] - t["entry"]) / risk
        pct = (t["entry"] - exit_price) / t["entry"] * 100 if t["direction"] == "SHORT" \
              else (exit_price - t["entry"]) / t["entry"] * 100
        days = (float(df.Time[exit_i].timestamp()) - t["opened_ts"]) / 86400
        t.update({"status": "closed", "outcome": outcome, "exit": float(exit_price),
                  "result_r": round(result_r, 2), "pct": round(pct, 2),
                  "closed": str(df.Time[exit_i])[:16], "days": round(days, 1),
                  "closed_ts": float(df.Time[exit_i].timestamp())})
        ex = exit_chart(df, t, exit_i, outcome)
        comp = composite_chart(t, ex, result_r, pct, outcome)
        t["result_chart"] = comp
        copy_to_proto(ex); copy_to_proto(comp)
        win = outcome == "ZIEL"
        head = "✅ GEWINN" if win else ("🟡 BREAK-EVEN" if t.get("be_moved") else "❌ VERLUST")
        cap = (f"{head} - Trade beendet: {t['name']} ({t['proto']})\n"
               f"Richtung: {t['direction']}\n"
               f"Einstieg: {val_fmt(t['entry'])} am {t['opened']}\n"
               f"Ausgang: {val_fmt(exit_price)} per {outcome} am {t['closed']}\n"
               f"Stop: {val_fmt(t['stop'])} | Ziel: {val_fmt(t['target'])}\n"
               f"Ergebnis: {result_r:+.1f}R ({pct:+.2f} %) | Dauer: {t['days']} Tage")
        notify_photo(cfg, comp, cap)
        print(f"Trade beendet: {t['name']} {outcome} {result_r:+.1f}R")
        changed = True
    if changed: save_trades(trades)

def bilanz_text():
    trades = load_trades()
    op = [t for t in trades if t["status"] == "open"]
    cl = [t for t in trades if t["status"] == "closed"]
    lines = [f"📒 Paper-Trading-Bilanz ({PROTO})"]
    if cl:
        wins = [t for t in cl if t["outcome"] == "ZIEL"]
        total_r = sum(t.get("result_r", 0) for t in cl)
        lines.append(f"Abgeschlossen: {len(cl)} | Gewinner: {len(wins)} | Verlierer: {len(cl)-len(wins)}")
        lines.append(f"Trefferquote: {len(wins)/len(cl)*100:.0f} % | Gesamt: {total_r:+.1f}R")
        for t in cl[-8:]:
            lines.append(f"  {'✅' if t['outcome']=='ZIEL' else '❌'} {t['name']} {t['direction']} {t.get('result_r',0):+.1f}R")
    else:
        lines.append("Noch keine abgeschlossenen Trades.")
    if op:
        lines.append(f"Offen: {len(op)}")
        for t in op:
            lines.append(f"  ⏳ {t['name']} {t['direction']} seit {t['opened']} (Einstieg {val_fmt(t['entry'])})")
    else:
        lines.append("Keine offenen Trades.")
    return "\n".join(lines)

# ---------------- PDF-Berichte (7 / 30 Tage) ----------------
def build_report(days, label, trades=None, now=None, demo_note=None):
    """PDF-Bericht: (1) Zusammenfassung letzte <days> Tage, (2) Gesamtzusammenfassung
    ALLER Trades inkl. Equity-Kurve, (3) Liste aller Trades, (4) je Zeitraum-Trade
    Datenseite + 4K-Bild."""
    from matplotlib.backends.backend_pdf import PdfPages
    trades_all = load_trades() if trades is None else trades
    now = now or time.time()
    closed_all = sorted([t for t in trades_all if t["status"] == "closed"],
                        key=lambda t: t.get("closed_ts", 0))
    closed_p = [t for t in closed_all if t.get("closed_ts", 0) >= now - days * 86400]
    opens = [t for t in trades_all if t["status"] == "open"]
    fn = os.path.join(REPORTS_DIR, f"Bericht_{label}_{time.strftime('%Y-%m-%d')}.pdf")
    BG, FG, MU, GN, RD, GOLD = "#0f1320", "#e8ecf5", "#9aa3b5", "#1fbf75", "#ff5c6c", "#e0a526"

    def stats(lst):
        wins = [t for t in lst if t.get("outcome") == "ZIEL"]
        tr = sum(t.get("result_r", 0) for t in lst)
        pc = sum(t.get("pct", 0) for t in lst)
        pos = sum(t.get("pct", 0) for t in lst if t.get("pct", 0) > 0)
        neg = sum(t.get("pct", 0) for t in lst if t.get("pct", 0) < 0)
        return wins, tr, pc, pos, neg

    with PdfPages(fn) as pdf:
        y = [0.9]
        fig = [None]
        def page():
            fig[0] = plt.figure(figsize=(11.69, 8.27), facecolor=BG); y[0] = 0.9
        def line(txt, color=FG, size=13, dy=0.05, bold=False, x=0.07, mono=False):
            fig[0].text(x, y[0], txt, color=color, fontsize=size,
                        fontweight="bold" if bold else "normal",
                        family="monospace" if mono else None)
            y[0] -= dy
        def flush():
            pdf.savefig(fig[0], facecolor=BG); plt.close(fig[0])

        # ---------- Seite 1: Zusammenfassung Zeitraum ----------
        page()
        line(f"TRADING-BERICHT - {label}", GOLD, 22, 0.08, True)
        line(f"{PROTO}  ·  erstellt am {time.strftime('%d.%m.%Y %H:%M', time.localtime(now))}", MU, 11, 0.06)
        if demo_note: line(demo_note, RD, 12, 0.06, True)
        line(f"GESAMTZUSAMMENFASSUNG - LETZTE {days} TAGE", FG, 16, 0.07, True)
        wins_p, tr_p, pc_p, pos_p, neg_p = stats(closed_p)
        line(f"Abgeschlossene Trades: {len(closed_p)}", FG, 13)
        if closed_p:
            line(f"Gewinner: {len(wins_p)}   Verlierer: {len(closed_p) - len(wins_p)}   "
                 f"Trefferquote: {len(wins_p) / len(closed_p) * 100:.0f} %", FG, 13)
            line(f"Ergebnis im Zeitraum: {tr_p:+.1f}R", GN if tr_p >= 0 else RD, 15, 0.05, True)
            line(f"Gewinn (Summe positive Trades): {pos_p:+.2f} %", GN, 13)
            line(f"Verlust (Summe negative Trades): {neg_p:+.2f} %", RD, 13)
            line(f"Ergebnis in % nach Verlusten: {pc_p:+.2f} %",
                 GN if pc_p >= 0 else RD, 16, 0.055, True)
            best = max(closed_p, key=lambda t: t.get("result_r", 0))
            worst = min(closed_p, key=lambda t: t.get("result_r", 0))
            line(f"Bester Trade im Zeitraum (nach R): {best['name']} {best['direction']} "
                 f"{best.get('result_r',0):+.1f}R ({best.get('pct',0):+.2f} %)", GN, 12)
            line(f"Schwaechster Trade im Zeitraum: {worst['name']} {worst['direction']} "
                 f"{worst.get('result_r',0):+.1f}R ({worst.get('pct',0):+.2f} %)", RD, 12)
        else:
            line("(Im Zeitraum wurden keine Trades abgeschlossen.)", MU, 12)
        line(f"Aktuell offene Trades: {len(opens)}", FG, 13, 0.05)
        for t in opens[:8]:
            line(f"   {t['name']}  {t['direction']}  seit {t['opened']}  "
                 f"(Einstieg {val_fmt(t['entry'])})", MU, 10.5, 0.037)
        flush()

        # ---------- Seite 2: Gesamtzusammenfassung ALLER Trades + Equity ----------
        page()
        wins_a, tr_a, pc_a, pos_a, neg_a = stats(closed_all)
        first_ts = closed_all[0].get("closed_ts", now) if closed_all else now
        span_days = max(1, round((now - first_ts) / 86400))
        line("GESAMTZUSAMMENFASSUNG - ALLE TRADES", GOLD, 18, 0.07, True)
        line(f"Seit Beginn der Aufzeichnung (~{span_days} Tage)", MU, 11, 0.055)
        if closed_all:
            avg_r = tr_a / len(closed_all)
            avg_d = sum(t.get("days", 0) for t in closed_all) / len(closed_all)
            line(f"Trades gesamt: {len(closed_all)}   Gewinner: {len(wins_a)}   "
                 f"Verlierer: {len(closed_all) - len(wins_a)}", FG, 13)
            line(f"Trefferquote: {len(wins_a) / len(closed_all) * 100:.0f} %   "
                 f"Durchschnitt: {avg_r:+.2f}R/Trade   Ø Dauer: {avg_d:.1f} Tage", FG, 13)
            line(f"GESAMTERGEBNIS (alle Trades): {tr_a:+.1f}R", GN if tr_a >= 0 else RD, 16, 0.05, True)
            line(f"Gewinn (Summe positive Trades): {pos_a:+.2f} %", GN, 13)
            line(f"Verlust (Summe negative Trades): {neg_a:+.2f} %", RD, 13)
            line(f"GESAMT-ERGEBNIS IN % NACH VERLUSTEN: {pc_a:+.2f} %",
                 GN if pc_a >= 0 else RD, 16, 0.045, True)
            line("(%-Angabe = Summe der Einzeltrade-Prozente bei gleichem Einsatz je Trade)", MU, 9, 0.045)
            # Equity-Kurve (kumulierte R)
            ax = fig[0].add_axes([0.08, 0.06, 0.86, 0.33], facecolor=BG)
            cum, acc = [0.0], 0.0
            for t in closed_all:
                acc += t.get("result_r", 0); cum.append(acc)
            ax.step(range(len(cum)), cum, where="post", color=GN if acc >= 0 else RD, lw=2.2)
            ax.fill_between(range(len(cum)), cum, step="post",
                            color=GN if acc >= 0 else RD, alpha=0.12)
            ax.axhline(0, color=MU, lw=0.8, ls="--")
            ax.set_title("Equity-Kurve (kumuliertes Ergebnis in R)", color=FG, fontsize=12)
            ax.set_xlabel("Trade Nr.", color=MU); ax.set_ylabel("R", color=MU)
            ax.grid(color="#1e2438", lw=0.5)
            ax.tick_params(colors=MU)
            for s in ax.spines.values(): s.set_color("#1e2438")
        else:
            line("(Noch keine abgeschlossenen Trades.)", MU, 12)
        flush()

        # ---------- Seite(n) 3: Liste aller Trades ----------
        per_page = 24
        for start in range(0, len(closed_all), per_page):
            chunk = closed_all[start:start + per_page]
            page()
            line(f"ALLE TRADES ({start + 1}-{start + len(chunk)} von {len(closed_all)})", GOLD, 15, 0.055, True)
            line(f"{'Nr':>3}  {'Datum':<12} {'Instrument':<22} {'Ri.':<6} {'Ausgang':<8} {'Ergebnis':>9} {'%':>8}",
                 MU, 10, 0.04, mono=True)
            for k, t in enumerate(chunk, start + 1):
                win = t.get("outcome") == "ZIEL"
                line(f"{k:>3}  {t.get('closed','')[:10]:<12} {t['name'][:22]:<22} "
                     f"{t['direction']:<6} {t.get('outcome',''):<8} "
                     f"{t.get('result_r',0):>+8.1f}R {t.get('pct',0):>+7.2f}%",
                     GN if win else RD, 10, 0.031, mono=True)
            flush()

        # ---------- Detailseiten: Trades des Zeitraums ----------
        for t in closed_p:
            page()
            win = t.get("outcome") == "ZIEL"
            line(f"{'GEWINN' if win else 'VERLUST'}  {t.get('result_r', 0):+.1f}R "
                 f"({t.get('pct', 0):+.2f} %)", GN if win else RD, 19, 0.075, True)
            line(f"{t['name']}  ·  {t['direction']}  ·  {t['proto']}", FG, 14, 0.06, True)
            line(f"Einstieg: {val_fmt(t['entry'])}  am {t['opened']}", FG, 12)
            line(f"Ausgang: {val_fmt(t.get('exit'))}  per {t.get('outcome')}  am {t.get('closed')}", FG, 12)
            line(f"Stop: {val_fmt(t['stop'])}   Ziel: {val_fmt(t['target'])}   "
                 f"Geplantes CRV: {t.get('rr', 0):.1f}R", FG, 12)
            line(f"Dauer: {t.get('days', '-')} Tage", FG, 12)
            flush()
            rc = t.get("result_chart")
            if rc and os.path.exists(rc):
                img = plt.imread(rc)
                h, w = img.shape[0], img.shape[1]
                figi = plt.figure(figsize=(13, 13 * h / w), facecolor=BG)
                axi = figi.add_axes([0, 0, 1, 1]); axi.imshow(img); axi.axis("off")
                pdf.savefig(figi, dpi=300, facecolor=BG); plt.close(figi)
    return fn, len(closed_p), len(opens), tr_p if closed_p else 0.0

def send_report(cfg, days, label):
    try:
        fn, n_closed, n_open, total_r = build_report(days, label)
        cap = (f"🤑🤑🤑 BERICHT LIEGT VOR!\n"
               f"{PROTO} - {label}-Bericht\n"
               f"Abgeschlossene Trades: {n_closed}"
               + (f" | Ergebnis: {total_r:+.1f}R" if n_closed else "")
               + f"\nOffene Trades: {n_open}\n"
               f"PDF mit 4K-Charts anbei - gespeichert in Str.3 Pro.1\\Berichte.")
        tg_document(fn, cap)
        print(f"Bericht gesendet: {fn}")
        return fn
    except Exception:
        print("Bericht-Fehler:\n" + traceback.format_exc())
        return None

# ---------------- Zustands-Logik ----------------
def line_sig(ln):
    # OHNE Bar-Index (der wandert mit jedem Zyklus) — sonst werden dieselbe Linie
    # und derselbe Trigger mehrfach gemeldet/gehandelt (Nutzer-Regel 15.07.2026)
    return f"{ln.kind}:{round(ln.p0,6)}:{round((ln.p1-ln.p0)/(ln.i1-ln.i0),8)}"

def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f: return json.load(f)
    return {}

def save_state(st):
    with open(STATE_FILE, "w", encoding="utf-8") as f: json.dump(st, f, indent=1)

def analyze(name, cands):
    """Liefert Status-Dict fuer ein Instrument oder None."""
    sym, df = fetch_4h(cands)
    if df is None: return None
    a = atr(df); piv = pivots(df)
    sup = find_lines(df, "support", a, piv)
    res = find_lines(df, "resistance", a, piv)
    n = len(df)
    # 1) Frisch gebrochene A+-Linie? (Trigger)
    broken = [l for l in (sup + res) if l.breaking_bar > 0
              and (n - 1 - l.breaking_bar) <= TRIGGER_MAX_AGE and is_aplus(l)]
    if broken:
        action = max(broken, key=lambda l: l.score)
        direction = "SHORT" if action.kind == "support" else "LONG"
        safety = pick_safety(action, res if action.kind == "support" else sup, df, a)
        entry, stop, target, rr = stop_and_target(df, action, safety, piv, a, direction) if safety else (float(df.Close[n-1]), None, None, None)
        return {"sym": sym, "df": df, "a": a, "status": "TRIGGER", "action": action,
                "safety": safety, "direction": direction, "entry": entry, "stop": stop,
                "target": target, "rr": rr, "sig": line_sig(action)}
    # 2) Intakte A+-Linie in Reichweite? (Watch/Near)
    intact = [l for l in (sup + res) if l.breaking_bar < 0 and is_aplus(l)]
    for action in sorted(intact, key=lambda l: -l.score):
        close = float(df.Close[n - 1]); lv = action.value_at(n - 1)
        atr_now = max(float(a.iloc[n - 1]), 1e-9)
        prox = (close - lv) / atr_now if action.kind == "support" else (lv - close) / atr_now
        if prox < 0 or prox > MAX_PROX_ATR: continue
        safety = pick_safety(action, res if action.kind == "support" else sup, df, a)
        if safety is None: continue
        direction = "SHORT" if action.kind == "support" else "LONG"
        return {"sym": sym, "df": df, "a": a, "status": "NEAR" if prox <= NEAR_ATR else "WATCH",
                "action": action, "safety": safety, "direction": direction,
                "prox": prox, "sig": line_sig(action), "trigger_val": lv}
    return {"sym": sym, "status": "NONE", "sig": ""}

def cycle(first_run, cfg):
    st = load_state()
    msgs = 0
    summary = {"TRIGGER": [], "NEAR": [], "NEW": []}
    counts = {"TRIGGER": 0, "NEAR": 0, "WATCH": 0, "NONE": 0}
    for name, cands in INSTRUMENTS:
        if not cands: continue
        try:
            r = analyze(name, cands)
        except Exception:
            print(f"{name}: Fehler\n{traceback.format_exc()}"); continue
        if r is None: continue
        counts[r["status"]] = counts.get(r["status"], 0) + 1
        prev = st.get(name, {})
        key = f"{r['status']}:{r['sig']}"
        already = prev.get("alerted") == key
        if r["status"] == "TRIGGER" and not already and not first_run and msgs < MAX_MSGS_PER_CYCLE:
            # Nutzer-Regel 15.07.2026: laeuft schon ein Trade auf dem Instrument,
            # wird auch KEIN neuer Trigger-Alert dazu gesendet (nur Status merken)
            if any(t["status"] == "open" and (t["sym"] == r["sym"] or t["name"] == name)
                   for t in load_trades()):
                st[name] = {"alerted": key}
                print(f"TRIGGER unterdrueckt ({name}): offener Trade auf diesem Instrument")
                continue
            fn = alert_chart(r["df"], name, r["sym"], r["action"], r["safety"],
                             r["entry"], r["stop"], r["target"], r["direction"])
            opened = False
            try:
                opened = open_paper_trade(cfg, name, r, fn)
            except Exception:
                print("Trade-Open-Fehler:\n" + traceback.format_exc())
            rr_txt = f"{r['rr']:.1f}R" if r.get("rr") else "-"
            warn = "" if (r.get("rr") or 0) >= 2 else "\n⚠️ Kein 2R-Ziel gefunden - Setup kritisch pruefen!"
            paper = ("📒 Paper-Trade eroeffnet - Ergebnis kommt automatisch." if opened
                     else "📒 Kein neuer Paper-Trade (Abkuehlzeit oder Linie bereits gehandelt).")
            cap = (f"🚨 {r['direction']}-TRIGGER: {name} ({PROTO})\n"
                   f"4h-Schluss jenseits der Action-Line ({len(r['action'].taps)} Taps, {r['action'].angle_deg:.0f}°)\n"
                   f"Einstieg: {val_fmt(r['entry'])}\n"
                   f"Stop: {val_fmt(r['stop'])} (Safety-Line, 4. Kerze)\n"
                   f"Ziel: {val_fmt(r['target'])} (S/R-Zone, {rr_txt}){warn}\n"
                   f"{paper}\n"
                   f"Du pruefst - du entscheidest.")
            notify_photo(cfg, fn, cap); msgs += 1
            st[name] = {"alerted": key}
            summary["TRIGGER"].append(name)
            print(f"TRIGGER gemeldet: {name}")
        elif r["status"] == "NEAR" and not already and not first_run and msgs < MAX_MSGS_PER_CYCLE:
            notify_text(cfg, f"⚠️ Fast am Trigger: {name}\n"
                    f"Kurs nur {r['prox']:.1f} ATR von der Action-Line ({len(r['action'].taps)} Taps).\n"
                    f"Moeglicher {r['direction']} bei 4h-Schluss jenseits {val_fmt(r['trigger_val'])}.")
            msgs += 1
            st[name] = {"alerted": key}
            summary["NEAR"].append(name)
            print(f"NEAR gemeldet: {name}")
        elif r["status"] == "WATCH":
            if prev.get("alerted", "").startswith("NONE") or not prev:
                summary["NEW"].append(name)
            st[name] = {"alerted": key}
        else:
            st[name] = {"alerted": key}
    save_state(st)
    cfg["last_cycle"] = time.strftime("%d.%m. %H:%M")
    cfg["last_counts"] = counts
    save_cfg(cfg)
    return summary

CYCLE_SECONDS = 3600   # Scan jede Stunde
POLL_SECONDS = 60      # Telegram-Befehle jede Minute pruefen
BACKUP_SECONDS = 12 * 3600   # Voll-Backup alle 12 Stunden
KEEP_BACKUPS = 14            # so viele Zip-Archive behalten

# ---------------- 12h-Backup ----------------
import zipfile, shutil, glob as _glob

TRADING_BOT_DIR = os.path.dirname(HERE)
BACKUP_DIR = os.path.join(TRADING_BOT_DIR, "Backup", "Archiv")
CLAUDE_PROJ = os.path.join(os.path.expanduser("~"), ".claude", "projects",
                           "C--Users-denro-Desktop-Claude-Code")
EXCLUDE_NAMES = {".env", "venv", "__pycache__", "bot_stdout.txt", "bot_stderr.txt"}

def _add_tree(zf, root, arcprefix, exts=None):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_NAMES]
        for fn in filenames:
            if fn in EXCLUDE_NAMES: continue
            if exts and not any(fn.lower().endswith(e) for e in exts): continue
            full = os.path.join(dirpath, fn)
            try:
                zf.write(full, os.path.join(arcprefix, os.path.relpath(full, root)))
            except Exception:
                pass

def run_backup():
    """Sichert Strategie-Doku, Code, Bot-Zustand, Charts UND kompletten Claude-Verlauf
    (Transkripte + Memory) als Zip - lokal + OneDrive. Ohne .env (Token via BotFather)."""
    os.makedirs(BACKUP_DIR, exist_ok=True)
    ts = time.strftime("%Y-%m-%d_%H%M")
    zpath = os.path.join(BACKUP_DIR, f"TradingBot_Backup_{ts}.zip")
    with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as zf:
        # 1) Trading_Bot: Dokumente + Referenzcharts (nur Top-Level-Dateien)
        for fn in os.listdir(TRADING_BOT_DIR):
            full = os.path.join(TRADING_BOT_DIR, fn)
            if os.path.isfile(full):
                zf.write(full, os.path.join("Trading_Bot", fn))
        # 2) Master-Doku + Code + Bot-Zustand + generierte Charts
        _add_tree(zf, os.path.join(TRADING_BOT_DIR, "Backup"), "Trading_Bot/Backup", exts=[".md"])
        _add_tree(zf, HERE, "Trading_Bot/Prototyp", exts=[".py", ".json", ".txt"])
        for sub in ("Scan_100", "Watchlist", "Alerts"):
            _add_tree(zf, os.path.join(TRADING_BOT_DIR, sub), f"Trading_Bot/{sub}")
        # 3) Kompletter Claude-Chatverlauf (Transkripte) + Memory
        if os.path.isdir(CLAUDE_PROJ):
            _add_tree(zf, CLAUDE_PROJ, "Claude_Projekt")
    # Rotation: nur die neuesten KEEP_BACKUPS behalten
    zips = sorted(_glob.glob(os.path.join(BACKUP_DIR, "TradingBot_Backup_*.zip")))
    for old in zips[:-KEEP_BACKUPS]:
        try: os.remove(old)
        except Exception: pass
    # OneDrive-Kopie (ausser Haus)
    od = os.environ.get("OneDrive") or os.path.join(os.path.expanduser("~"), "OneDrive")
    if os.path.isdir(od):
        oddir = os.path.join(od, "TradingBot_Backup")
        os.makedirs(oddir, exist_ok=True)
        shutil.copy2(zpath, oddir)
        odz = sorted(_glob.glob(os.path.join(oddir, "TradingBot_Backup_*.zip")))
        for old in odz[:-KEEP_BACKUPS]:
            try: os.remove(old)
            except Exception: pass
        print(f"Backup erstellt + OneDrive: {os.path.basename(zpath)} "
              f"({os.path.getsize(zpath)/1e6:.1f} MB)")
    else:
        print(f"Backup erstellt (lokal): {os.path.basename(zpath)}")
    return zpath

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--backup", action="store_true", help="nur Backup erstellen und beenden")
    args = ap.parse_args()
    if args.backup:
        run_backup(); return
    first_run = not os.path.exists(STATE_FILE)
    cfg = load_cfg()
    last_cycle = 0.0
    last_be_check = 0.0
    if first_run:
        pass  # Startmeldung kommt nach dem ersten Zyklus
    while True:
        cfg = load_cfg()
        check_telegram_commands(cfg)
        if time.time() - last_cycle >= CYCLE_SECONDS or args.once:
            t0 = time.time()
            print(f"\n--- Zyklus {time.strftime('%Y-%m-%d %H:%M')} ---")
            try:
                s = cycle(first_run, cfg)
                if first_run:
                    tg_text("🤖 Alert-Bot gestartet (Erstlauf).\n"
                            "Watchlist initialisiert - ab jetzt melde ich Trigger, "
                            "Fast-am-Trigger und neue Setups automatisch.\n\n"
                            "Befehle: 'gute nacht' 🌙 / 'guten morgen' ☀️ / 'status' 📊 / 'bilanz' 📒")
                    first_run = False
                print(f"Zyklus fertig in {time.time()-t0:.0f}s | Trigger: {len(s['TRIGGER'])} | Near: {len(s['NEAR'])}")
                check_open_trades(cfg)   # offene Paper-Trades auf Stop/Ziel pruefen
            except Exception:
                print("Zyklus-Fehler:\n" + traceback.format_exc())
            last_cycle = time.time()
            if args.once: break
        # Break-even-Pruefung alle 15 Minuten (15m-Kerzen - NUR fuer diesen Mechanismus)
        if time.time() - last_be_check >= BE_CHECK_SECONDS:
            try:
                check_break_even(cfg)
            except Exception:
                print("Break-even-Fehler:\n" + traceback.format_exc())
            last_be_check = time.time()
        # Berichte: alle 7 und alle 30 Tage (Zeitstempel persistent)
        now = time.time()
        if "last_report_7" not in cfg: cfg["last_report_7"] = now; save_cfg(cfg)
        if "last_report_30" not in cfg: cfg["last_report_30"] = now; save_cfg(cfg)
        if now - cfg["last_report_7"] >= 7 * 86400:
            send_report(cfg, 7, "7-Tage")
            cfg["last_report_7"] = now; save_cfg(cfg)
        if now - cfg["last_report_30"] >= 30 * 86400:
            send_report(cfg, 30, "30-Tage")
            cfg["last_report_30"] = now; save_cfg(cfg)
        # 12h-Backup (Zeitstempel persistent in bot_config.json)
        if time.time() - cfg.get("last_backup", 0) >= BACKUP_SECONDS:
            try:
                run_backup()
                cfg["last_backup"] = time.time(); save_cfg(cfg)
            except Exception:
                print("Backup-Fehler:\n" + traceback.format_exc())
        time.sleep(POLL_SECONDS)

if __name__ == "__main__":
    main()
