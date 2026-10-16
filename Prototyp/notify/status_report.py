# -*- coding: utf-8 -*-
"""Zwischenstands-PDF des laufenden Zwei-Monats-Paper-Tests (nur LESEND).

Liest ausschliesslich die Laufdaten (trades.json, ledger.json, START_MANIFEST.json,
last_cycle_monitor.json) und das Log des Paper-Laufs. Es wird NICHTS in den Laufordner geschrieben;
die PDF landet in einem eigenen Ausgabeordner. Kennzahlen kommen aus der bestehenden zentralen
Berechnungsschicht (engine.reporting.variant_report) - keine zweite Formelquelle.

Regel (Nutzerentscheidung): Trades, die am Testende noch offen sind, werden nicht gewertet. Darum
stammen alle Kennzahlen NUR aus geschlossenen Trades; offene Trades erscheinen getrennt als
"offen, nicht gewertet".

PDF-Technik: matplotlib (PdfPages) aus der Bot-venv - dieselbe Umgebung wie der Listener, keine
zusaetzliche Abhaengigkeit, Umlaute ueber die mitgelieferte DejaVu-Schrift.
"""
import os, re, json, time, textwrap, subprocess
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages
from matplotlib.patches import Rectangle

from engine import reporting as REP
from engine.ledger import Ledger
from engine.tracker import PaperTradeStore
from .redact import redact

TZ = ZoneInfo("Europe/Berlin")
VARIANTS = [f"Str.3 Pro.{i}" for i in range(1, 9)]
CLASS_LABEL = {"fx": "Devisen", "crypto": "Krypto", "futures": "Futures", "index": "Indizes",
               "stock": "Aktien/ETFs", "commodity": "Rohstoffe"}
NE_REASON = {
    "Daily-Daten fehlen": "Tagesdaten fehlen im Live-Lauf",
    "VOLUME_NOT_AVAILABLE": "kein verwertbares Volumen (z. B. Devisen)",
    "COMBINED_NOT_EVALUABLE": "Kombi: Volumen nicht verfügbar",
    "Teilfilter nicht auswertbar": "Teilfilter (Tagesdaten/Volumen) nicht auswertbar",
    "RVOL fehlt": "RVOL nicht berechenbar",
    "<250 Tageskerzen": "weniger als 250 Tageskerzen",
}
NE_SHORT = {
    "Daily-Daten fehlen": "Tagesdaten fehlen",
    "VOLUME_NOT_AVAILABLE": "Volumen fehlt",
    "COMBINED_NOT_EVALUABLE": "Tagesdaten/Volumen fehlen",
    "Teilfilter nicht auswertbar": "Tagesdaten/Volumen fehlen",
    "RVOL fehlt": "Volumen fehlt",
    "<250 Tageskerzen": "Tagesdaten fehlen",
}
# Farben (druckfreundlich)
NAVY, GREY, LIGHT, LINEC = "#1f2d4d", "#5b6477", "#f1f3f8", "#c9d0de"
GREEN, AMBER, RED, BLUE = "#1a9e5c", "#d98e04", "#c0392b", "#2f6fb5"


# ------------------------------------------------------------------ Formatierung
def fnum(v, dec=2, sign=False):
    if v is None:
        return "–"
    try:
        s = f"{v:+.{dec}f}" if sign else f"{v:.{dec}f}"
    except (TypeError, ValueError):
        return str(v)
    return s.replace(".", ",").replace("-", "−")


def fprice(v):
    try:
        return f"{float(v):.6g}".replace(".", ",")
    except (TypeError, ValueError):
        return "–"


def total_pct(v):
    """Gesamt-% = bestehende Kennzahl Netto-% (Summe der Netto-Prozent aller GESCHLOSSENEN Trades,
    gleicher Einsatz je Trade, kein Kapitalkonto). None, wenn die Variante keine geschlossenen Trades hat."""
    return v["rep"]["net_profit_pct"] if v["closed"] else None


def pct_color(x):
    if x is None:
        return GREY
    return GREEN if x > 0 else (RED if x < 0 else "black")


def fpct(x):
    return "–" if x is None else fnum(x, 1, True) + " %"


def no_trade_reason(v):
    sid = v["sid"]
    if sid == "Str.3 Pro.8":
        return "nicht konfiguriert"
    if v["evals"] and v["counts"].get("NOT_EVALUABLE", 0) == v["evals"]:
        return NE_SHORT.get(v["ne_top"], "Daten fehlen")
    return "noch keine geschlossenen Trades" if v["open"] else "keine Trades"


def short_variant(sid):
    return sid.replace("Str.3 ", "")


def fdt(ts_iso):
    """ISO-Zeit (UTC oder mit Offset) -> 'TT.MM. HH:MM' Europe/Berlin."""
    try:
        d = datetime.fromisoformat(str(ts_iso).replace("Z", "+00:00"))
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone(TZ).strftime("%d.%m. %H:%M")
    except Exception:
        return "–"


def fdelta(td):
    secs = int(td.total_seconds())
    if secs <= 0:
        return "beendet"
    d, rem = divmod(secs, 86400)
    h, rem = divmod(rem, 3600)
    m = rem // 60
    return f"{d} Tage {h} Std. {m} Min."


# ------------------------------------------------------------------ Laden (read-only)
def _load_json(path, retries=3):
    for i in range(retries):
        try:
            with open(path, encoding="utf-8") as f:
                return json.load(f)
        except FileNotFoundError:
            return None
        except (ValueError, OSError):
            time.sleep(0.4)
    return None


def _process_alive(needle="run_loop.py"):
    """Best-effort: laeuft ein Prozess mit run_loop.py --zwei-monate? None = nicht feststellbar."""
    try:
        cmd = ("Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*run_loop.py*' "
               "-and $_.CommandLine -like '*zwei-monate*' } | Measure-Object | Select-Object -ExpandProperty Count")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
                           capture_output=True, text=True, timeout=20, creationflags=flags)
        return int((r.stdout or "0").strip() or 0) > 0
    except Exception:
        return None


_LOG_TS = re.compile(r"^\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?[+-]\d{2}:\d{2})\]")


def scan_log(log_path, now, hours=24, tail_bytes=400_000):
    """Zaehlt Fehlerzeilen der letzten `hours` Stunden im Lauf-Log (nur Tail wird gelesen)."""
    out = {"errors": 0, "samples": [], "readable": False}
    try:
        size = os.path.getsize(log_path)
        with open(log_path, "rb") as f:
            f.seek(max(0, size - tail_bytes))
            raw = f.read().decode("utf-8", errors="replace")
    except OSError:
        return out
    out["readable"] = True
    since = now - timedelta(hours=hours)
    cur_ok = False
    for line in raw.splitlines():
        m = _LOG_TS.match(line)
        if m:
            try:
                cur_ok = datetime.fromisoformat(m.group(1)) >= since
            except ValueError:
                cur_ok = False
            if cur_ok and ("ZYKLUSFEHLER" in line or "Telegram-Zustellung Fehler" in line
                           or re.search(r"err=([1-9]\d*)", line)):
                out["errors"] += 1
                out["samples"].append(redact(line.strip())[:110])
        elif cur_ok and line.startswith("Traceback"):
            out["errors"] += 1
    out["samples"] = out["samples"][-3:]
    return out


def collect(rt_dir, log_path=None, now=None, check_process=True):
    """Sammelt alle Berichtsdaten (read-only) in ein dict."""
    now = now or datetime.now(TZ)
    manifest = _load_json(os.path.join(rt_dir, "START_MANIFEST.json")) or {}
    monitor = _load_json(os.path.join(rt_dir, "last_cycle_monitor.json")) or {}
    ledger = Ledger(os.path.join(rt_dir, "ledger.json"))          # Konstruktor liest nur
    store = PaperTradeStore(os.path.join(rt_dir, "trades.json"))  # Konstruktor liest nur
    trades = store.trades

    def closed_of(sid=None):
        return [t for t in trades if (sid is None or t.strategy_id == sid) and t.status == "closed"
                and (t.result or {}).get("status") == "closed"]

    def open_of(sid=None):
        return [t for t in trades if (sid is None or t.strategy_id == sid)
                and t.status in ("open", "pending_fill")]

    variants = []
    for sid in VARIANTS:
        rep = REP.variant_report(ledger, trades, sid)
        cl = closed_of(sid)
        counts = ledger.counts_by_status(sid)
        total_evals = sum(counts.values())
        best = worst = None
        if cl:
            best = max(cl, key=lambda t: t.result.get("netto_r", 0))
            worst = min(cl, key=lambda t: t.result.get("netto_r", 0))
        note, ne_top = "", ""
        ne = counts.get("NOT_EVALUABLE", 0)
        if ne:
            reasons = {}
            for v in ledger.variant_evals_for(sid):
                if v["status"] == "NOT_EVALUABLE":
                    reasons[v.get("rejection_reason", "")] = reasons.get(v.get("rejection_reason", ""), 0) + 1
            top = max(reasons, key=reasons.get) if reasons else ""
            ne_top = top
            note = f"NOT_EVALUABLE bei {ne} von {total_evals} Signalen ({NE_REASON.get(top, top or 'Daten fehlen')})"
        if sid == "Str.3 Pro.8":
            note = "nicht konfiguriert (PRO8_NOT_CONFIGURED) – handelt nie"
        if sid == "Str.3 Pro.7":
            note = "nur Diagnose, ohne Filterschwelle – handelt jedes Signal"
        variants.append({"sid": sid, "rep": rep, "counts": counts, "evals": total_evals,
                         "open": len(open_of(sid)), "closed": len(cl), "best": best, "worst": worst,
                         "note": note, "ne_top": ne_top})

    # Instrumentklassen (nur geschlossene Trades fuer Kennzahlen)
    classes = {}
    for t in trades:
        c = classes.setdefault(t.asset_class, {"open": 0, "closed": 0, "net_r": 0.0, "net_pct": 0.0, "wins": 0})
        if t.status in ("open", "pending_fill"):
            c["open"] += 1
        elif t.status == "closed" and (t.result or {}).get("status") == "closed":
            c["closed"] += 1
            c["net_r"] += t.result.get("netto_r", 0.0)
            c["net_pct"] += t.result.get("net_return_pct", 0.0)
            if t.result.get("netto_r", 0.0) > 0:
                c["wins"] += 1

    open_trades = sorted(open_of(), key=lambda t: (t.strategy_id, t.entry_time or t.signal_time))
    last_closed = sorted(closed_of(), key=lambda t: t.result.get("closed_ts", 0), reverse=True)[:10]

    # Systemstatus
    stage_end = None
    if manifest.get("stage_end_local"):
        try:
            stage_end = datetime.fromisoformat(manifest["stage_end_local"])
        except ValueError:
            pass
    last_end = None
    if monitor.get("end"):
        try:
            last_end = datetime.fromisoformat(monitor["end"]).astimezone(TZ)
        except ValueError:
            pass
    alive = _process_alive() if check_process else None
    age_min = None if last_end is None else (now - last_end).total_seconds() / 60.0
    if alive is False:
        status, color = "NICHT AKTIV – kein Prozess gefunden", RED
    elif age_min is None:
        status, color = "UNBEKANNT – kein Zyklus-Protokoll gefunden", AMBER
    elif age_min <= 130:
        status, color = "LÄUFT", GREEN
    else:
        status, color = "VERZÖGERT – letzter Zyklus länger her (PC evtl. im Standby; holt beim Aufwachen nach)", AMBER
    logscan = scan_log(log_path, now) if log_path else {"errors": 0, "samples": [], "readable": False}

    n_cand = len(ledger.candidates)
    n_acc = sum(1 for c in ledger.candidates if c.get("status") == "ACCEPTED_PROVISIONAL")
    return {
        "now": now, "manifest": manifest, "monitor": monitor, "stage_end": stage_end,
        "variants": variants, "classes": classes, "open_trades": open_trades,
        "last_closed": last_closed,
        "totals": {"trades": len(trades), "open": len(open_of()), "closed": len(closed_of()),
                   "candidates": n_cand, "accepted": n_acc,
                   "rejected": n_cand - n_acc},
        "system": {"alive": alive, "status": status, "color": color, "last_end": last_end,
                   "age_min": age_min, "log": logscan},
    }


# ------------------------------------------------------------------ Kurztext (Bildunterschrift)
def caption(d):
    now, tot = d["now"], d["totals"]
    rest = "–"
    if d["stage_end"]:
        rest = fdelta(d["stage_end"] - now) + f" (bis {d['stage_end'].astimezone(TZ).strftime('%d.%m.%Y %H:%M')})"
    lines = [f"Str.3 Pro – Zwischenstand {now.strftime('%d.%m.%Y %H:%M')}",
             f"Restlaufzeit: {rest}",
             f"Trades: {tot['trades']} (geschlossen {tot['closed']}, offen {tot['open']} – nicht gewertet)",
             f"Signale: {tot['accepted']} akzeptiert, {tot['rejected']} abgelehnt",
             "Gesamt-% (alle abgeschlossenen Trades, nach Kosten):"]
    lines.append(" | ".join(f"{short_variant(v['sid'])} {fpct(total_pct(v))}"
                            for v in d["variants"] if v["closed"]) or "noch keine geschlossenen Trades")
    lines.append("Netto-R (nur geschlossene):")
    parts = []
    for v in d["variants"]:
        if v["closed"]:
            parts.append(f"{short_variant(v['sid'])} {fnum(v['rep']['total_r_netto'], 1, True)}")
        else:
            parts.append(f"{short_variant(v['sid'])} –")
    lines.append(" · ".join(parts))
    lines.append(f"System: {d['system']['status'].split(' –')[0]}")
    lines.append("Paper-Trading – keine echte Order.")
    return "\n".join(lines)[:1000]


# ------------------------------------------------------------------ PDF-Layout (matplotlib)
class _Doc:
    W, H, M = 595.0, 842.0, 38.0

    def __init__(self, pdf, stand):
        self.pdf, self.stand, self.page_no = pdf, stand, 0
        self.fig = self.ax = None
        self.y = 0.0
        self._new_page()

    def _new_page(self):
        if self.fig is not None:
            self._finish()
        self.page_no += 1
        self.fig = plt.figure(figsize=(self.W / 72, self.H / 72), facecolor="white")
        self.ax = self.fig.add_axes([0, 0, 1, 1])
        self.ax.set_xlim(0, self.W); self.ax.set_ylim(self.H, 0); self.ax.axis("off")
        self.ax.text(self.M, 24, "Str.3 Pro – Zwischenstand Zwei-Monats-Paper-Test", fontsize=8, color=GREY, va="center")
        self.ax.text(self.W - self.M, 24, self.stand, fontsize=8, color=GREY, va="center", ha="right")
        self.ax.plot([self.M, self.W - self.M], [34, 34], color=LINEC, lw=0.6)
        self.y = 50.0

    def _finish(self):
        self.ax.plot([self.M, self.W - self.M], [self.H - 34, self.H - 34], color=LINEC, lw=0.6)
        self.ax.text(self.M, self.H - 22, "Paper-Trading – keine echte Order. Keine Anlageberatung.",
                     fontsize=7.5, color=GREY, va="center")
        self.ax.text(self.W - self.M, self.H - 22, f"Seite {self.page_no}", fontsize=7.5, color=GREY,
                     va="center", ha="right")
        self.pdf.savefig(self.fig)
        plt.close(self.fig)
        self.fig = self.ax = None

    def close(self):
        if self.fig is not None:
            self._finish()

    def ensure(self, h):
        if self.y + h > self.H - 44:
            self._new_page()

    def title(self, txt, sub=None):
        self.ensure(40)
        self.ax.text(self.M, self.y + 14, txt, fontsize=17, fontweight="bold", color=NAVY, va="center")
        self.y += 26
        if sub:
            self.ax.text(self.M, self.y + 6, sub, fontsize=9, color=GREY, va="center")
            self.y += 16

    def heading(self, txt):
        self.ensure(34)
        self.y += 8
        self.ax.text(self.M, self.y + 7, txt, fontsize=11.5, fontweight="bold", color="#0f766e", va="center")
        self.y += 20

    def para(self, txt, size=8.5, color="black", bold=False, indent=0.0, gap=3.0):
        width = int((self.W - 2 * self.M - indent) / (size * 0.56))
        for line in textwrap.wrap(txt, width=max(20, width)) or [""]:
            self.ensure(size + 6)
            self.ax.text(self.M + indent, self.y + size / 2 + 1, line, fontsize=size, color=color, va="center",
                         fontweight="bold" if bold else "normal")
            self.y += size + 3.5
        self.y += gap

    def box(self, title, lines, color):
        size = 8.3
        width = int((self.W - 2 * self.M - 22) / (size * 0.56))
        wrapped = []
        for ln in lines:
            wrapped += textwrap.wrap(ln, width=width) or [""]
        h = 24 + len(wrapped) * (size + 3.4) + 4
        self.ensure(h + 6)
        x0, w = self.M, self.W - 2 * self.M
        self.ax.add_patch(Rectangle((x0, self.y), w, h, facecolor=color, alpha=0.10, edgecolor="none"))
        self.ax.add_patch(Rectangle((x0, self.y), 3.2, h, facecolor=color, edgecolor="none"))
        self.ax.text(x0 + 12, self.y + 11, title, fontsize=9.5, fontweight="bold", color=color, va="center")
        yy = self.y + 25
        for ln in wrapped:
            self.ax.text(x0 + 12, yy + size / 2, ln, fontsize=size, color="black", va="center")
            yy += size + 3.4
        self.y += h + 8

    def result_cards(self, variants):
        """Gesamt-% je Variante als grosse Zahl (4 Karten je Zeile)."""
        cw, ch, gap = (self.W - 2 * self.M - 3 * 6) / 4.0, 62.0, 6.0
        for row in range(2):
            self.ensure(ch + 6)
            for col in range(4):
                v = variants[row * 4 + col]
                x0 = self.M + col * (cw + gap)
                val = total_pct(v)
                c = pct_color(val)
                self.ax.add_patch(Rectangle((x0, self.y), cw, ch, facecolor=c, alpha=0.09, edgecolor="none"))
                self.ax.add_patch(Rectangle((x0, self.y), 3, ch, facecolor=c, edgecolor="none"))
                self.ax.text(x0 + 9, self.y + 11, short_variant(v["sid"]), fontsize=9, fontweight="bold",
                             color=NAVY, va="center")
                if val is None:
                    self.ax.text(x0 + 9, self.y + 31, "keine Trades", fontsize=12, fontweight="bold", color=GREY, va="center")
                    self.ax.text(x0 + 9, self.y + 50, no_trade_reason(v), fontsize=6.6, color=GREY, va="center")
                else:
                    r = v["rep"]
                    self.ax.text(x0 + 9, self.y + 31, fpct(val), fontsize=16, fontweight="bold", color=c, va="center")
                    self.ax.text(x0 + 9, self.y + 45, f"{v['closed']} Trades",
                                 fontsize=6.8, color=GREY, va="center")
                    self.ax.text(x0 + 9, self.y + 54, f"{r['winners']} Gewinner / {r['losers']} Verlierer",
                                 fontsize=6.8, color=GREY, va="center")
            self.y += ch + gap

    def bar_chart(self, variants, title):
        """Waagerechte Balken Gesamt-% je Variante mit Nulllinie (gruen/rot)."""
        rows = [(short_variant(v["sid"]), total_pct(v)) for v in variants]
        rh = 15.0
        self.ensure(len(rows) * rh + 24)
        self.ax.text(self.M, self.y + 6, title, fontsize=8.3, fontweight="bold", color=NAVY, va="center")
        self.y += 15
        vals = [x for _, x in rows if x is not None]
        lo, hi = min([0.0] + vals), max([0.0] + vals)
        span = (hi - lo) or 1.0
        left, right = self.M + 38, self.W - self.M - 52
        zx = left + (0 - lo) / span * (right - left)
        top = self.y
        for name, x in rows:
            self.ax.text(self.M, self.y + rh / 2, name, fontsize=8, va="center", color="black")
            if x is None:
                self.ax.text(zx + 4, self.y + rh / 2, "keine Trades", fontsize=7, va="center", color=GREY)
            else:
                bw = max(abs(x) / span * (right - left), 0.8)
                bx = zx if x >= 0 else zx - bw
                self.ax.add_patch(Rectangle((bx, self.y + 2.5), bw, rh - 5, facecolor=pct_color(x), edgecolor="none"))
                tx, ha = (zx + bw + 4, "left") if x >= 0 else (zx - bw - 4, "right")
                self.ax.text(tx, self.y + rh / 2, fpct(x), fontsize=7.4, va="center", ha=ha, color=pct_color(x),
                             fontweight="bold")
            self.y += rh
        self.ax.plot([zx, zx], [top, self.y], color="black", lw=0.8)
        self.y += 4

    def table(self, headers, rows, widths, aligns=None, size=7.6, row_colors=None, cell_style=None):
        """widths in Punkten (Summe = Seitenbreite). Zellen werden gekuerzt."""
        aligns = aligns or ["l"] * len(headers)
        scale = (self.W - 2 * self.M) / float(sum(widths))
        widths = [w * scale for w in widths]          # immer exakt auf Seitenbreite
        rh = size + 7.0
        xs = [self.M]
        for w in widths:
            xs.append(xs[-1] + w)

        def draw_row(vals, y, header=False, zebra=False, color=None, ri=None):
            if header:
                self.ax.add_patch(Rectangle((xs[0], y), xs[-1] - xs[0], rh, facecolor=NAVY, edgecolor="none"))
            elif zebra:
                self.ax.add_patch(Rectangle((xs[0], y), xs[-1] - xs[0], rh, facecolor=LIGHT, edgecolor="none"))
            for i, v in enumerate(vals):
                maxc = max(3, int((widths[i] - 6) / (size * 0.58)))
                s = str(v)
                if len(s) > maxc:
                    s = s[:maxc - 1] + "…"
                ha = {"l": "left", "r": "right", "c": "center"}[aligns[i]]
                x = xs[i] + 3 if ha == "left" else (xs[i + 1] - 3 if ha == "right" else (xs[i] + xs[i + 1]) / 2)
                ccol, cbold = (color or "black"), False
                if cell_style is not None and not header:
                    st = cell_style(ri, i, v)
                    if st:
                        ccol, cbold = st
                self.ax.text(x, y + rh / 2, s, fontsize=size, va="center", ha=ha,
                             color="white" if header else ccol,
                             fontweight="bold" if (header or cbold) else "normal")

        def head():
            self.ensure(rh * 2 + 4)
            draw_row(headers, self.y, header=True)
            self.y += rh

        head()
        for ri, r in enumerate(rows):
            if self.y + rh > self.H - 44:
                self._new_page(); head()
            draw_row(r, self.y, zebra=(ri % 2 == 1), color=(row_colors[ri] if row_colors else None), ri=ri)
            self.y += rh
        self.ax.plot([xs[0], xs[-1]], [self.y, self.y], color=LINEC, lw=0.6)
        self.y += 8


def build_pdf(d, path):
    """Erzeugt das Zwischenstands-PDF aus den gesammelten Daten. Gibt den Pfad zurueck."""
    now, tot, sysd = d["now"], d["totals"], d["system"]
    stand = now.strftime("Stand %d.%m.%Y %H:%M (Europe/Berlin)")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with PdfPages(tmp) as pdf:
        doc = _Doc(pdf, stand)
        doc.title("Zwischenstand Zwei-Monats-Paper-Test", f"Erstellt am {now.strftime('%d.%m.%Y um %H:%M Uhr')} (Europe/Berlin)")
        doc.heading("Gesamtergebnis je Gruppe (alle abgeschlossenen Trades)")
        doc.result_cards(d["variants"])
        doc.bar_chart(d["variants"], "Gesamt-% je Variante (nach Kosten)")
        doc.para("Summe der Netto-% aller abgeschlossenen Trades (nach Kosten), gleicher Einsatz je Trade; "
                 "offene Trades nicht gewertet.", size=7.4, color=GREY)
        man = d["manifest"]
        start = "–"
        if man.get("start_local"):
            try:
                start = datetime.fromisoformat(man["start_local"]).astimezone(TZ).strftime("%d.%m.%Y %H:%M") + " Uhr"
            except ValueError:
                pass
        end_txt = d["stage_end"].astimezone(TZ).strftime("%d.%m.%Y %H:%M") if d["stage_end"] else "–"
        rest = fdelta(d["stage_end"] - now) if d["stage_end"] else "–"
        doc.box("Testfenster und Restlaufzeit", [
            f"Start: {start}   ·   Ende: {end_txt} Uhr (Europe/Berlin)",
            f"Restlaufzeit: {rest}",
            f"Signale: {tot['candidates']} Kandidaten geprüft, {tot['accepted']} akzeptiert, {tot['rejected']} abgelehnt (Datenqualität/Rollover).",
            f"Trades gesamt: {tot['trades']}  ·  geschlossen: {tot['closed']}  ·  offen: {tot['open']} (offen = nicht gewertet).",
        ], BLUE)
        doc.box("Wichtig zur Wertung", [
            "Trades, die am 17.10. noch offen sind, werden NICHT gewertet (Nutzerentscheidung). Alle Kennzahlen in diesem "
            "Bericht stammen deshalb nur aus GESCHLOSSENEN Trades. Offene Trades sind als „offen, nicht gewertet“ gekennzeichnet.",
            "Kennzahlen sind brutto/netto nach Kosten und Slippage; Prozent = Summe der Einzeltrade-Prozent bei gleichem "
            "Einsatz je Trade (kein Kapitalkonto). Kleine Stichproben (unter 30 Trades) sind nicht belastbar.",
        ], AMBER)

        # Systemstatus
        mon = d["monitor"]
        le = sysd["last_end"].strftime("%d.%m.%Y %H:%M") if sysd["last_end"] else "–"
        age = "–" if sysd["age_min"] is None else (f"{int(sysd['age_min'])} Min." if sysd["age_min"] < 180
                                                    else f"{sysd['age_min'] / 60:.1f} Std.".replace(".", ","))
        alive = {True: "ja", False: "nein", None: "nicht feststellbar"}[sysd["alive"]]
        lg = sysd["log"]
        log_line = ("Log nicht lesbar" if not lg["readable"] else
                    ("keine Fehler in den letzten 24 Stunden" if lg["errors"] == 0 else
                     f"{lg['errors']} Fehlerzeile(n) in den letzten 24 Stunden"))
        lines = [
            f"Paper-Lauf: {sysd['status']}",
            f"Prozess aktiv: {alive}   ·   letzter Zyklus: {le} (vor {age})",
            f"Letzter Zyklus: {mon.get('instruments', '–')} Instrumente, Trigger {mon.get('accepted', '–')}, "
            f"eröffnet {mon.get('opened', '–')}, geschlossen {mon.get('closed', '–')}, Fehler {mon.get('errors', '–')}, "
            f"ohne Daten {mon.get('no_data', '–')}, Telegram: {mon.get('telegram', '–')}",
            f"Log: {log_line}",
        ] + [f"   · {s}" for s in lg["samples"]]
        doc.box("Systemstatus", lines, sysd["color"])

        # Vergleichstabelle
        doc.heading("Vergleich aller Varianten (nur geschlossene Trades)")
        rows = []
        for v in d["variants"]:
            r = v["rep"]
            if v["closed"]:
                rows.append([short_variant(v["sid"]), v["closed"], v["open"], r["winners"], r["losers"],
                             fnum(r["hit_rate"] * 100, 1) + " %", fnum(r["net_profit_pct"], 1, True) + " %",
                             fnum(r["total_r_netto"], 2, True), fnum(r["profit_factor"], 2),
                             fnum(r["max_drawdown_r"], 1)])
            else:
                rows.append([short_variant(v["sid"]), 0, v["open"], "–", "–", "–", "–", "–", "–", "–"])

        def _style(ri, ci, val):
            if ci != 6:
                return None
            sv = str(val)
            return (GREEN if sv.startswith("+") else RED if sv.startswith("−") else GREY, True)
        doc.table(["Variante", "Geschl.", "Offen", "Gew.", "Verl.", "Trefferq.", "Gesamt-%", "Netto-R", "PF", "MaxDD R"],
                  rows, [56, 48, 42, 40, 40, 62, 72, 62, 44, 53], ["l"] + ["r"] * 9, cell_style=_style)
        doc.para("Gesamt-% = Summe der Netto-% aller abgeschlossenen Trades. Gew./Verl. = Netto-R über/unter 0 (Break-even-Ausstiege mit Kosten zählen als Verlierer). "
                 "PF = Profit-Faktor. MaxDD R = größter Rückgang der R-Kurve. Pro.1 läuft mit BE-0, Pro.2–8 mit BE-1.",
                 size=7.5, color=GREY)

        # Je Variante
        doc.heading("Je Variante im Detail")
        for v in d["variants"]:
            r, c = v["rep"], v["counts"]
            sig = ", ".join(f"{k} {n}" for k, n in sorted(c.items())) or "keine Bewertungen"
            head = f"{short_variant(v['sid'])}  –  Signale bewertet: {v['evals']}  ({sig})"
            if v["closed"]:
                be = r.get("break_even_exits", 0)
                body = (f"Trades: {v['closed']} geschlossen, {v['open']} offen (nicht gewertet)  ·  Gewinner {r['winners']}, "
                        f"Verlierer {r['losers']}, davon Break-even-Ausstiege {be}  ·  Trefferquote {fnum(r['hit_rate'] * 100, 1)} %  ·  "
                        f"Netto-R {fnum(r['total_r_netto'], 2, True)}")
                bw = (f"Bester Trade: {v['best'].symbol} {fnum(v['best'].result['netto_r'], 2, True)} R   ·   "
                      f"Schlechtester: {v['worst'].symbol} {fnum(v['worst'].result['netto_r'], 2, True)} R")
                if r.get("sample_flag") != "OK":
                    bw += "   ·   Stichprobe < 30 (nicht belastbar)"
            else:
                body = f"Trades: 0 geschlossen, {v['open']} offen (nicht gewertet)"
                bw = ""
            doc.ensure(52)
            doc.para(head, size=8.6, bold=True, gap=0)
            doc.para(body, size=8.2, indent=8, gap=0)
            if bw:
                doc.para(bw, size=8.2, indent=8, gap=0)
            if v["note"]:
                doc.para("Hinweis: " + v["note"], size=8, indent=8, color=AMBER, gap=0)
            doc.y += 5

        # Instrumentklassen
        doc.heading("Aufteilung nach Instrumentklasse (alle Varianten zusammen)")
        rows = []
        for ac, c in sorted(d["classes"].items(), key=lambda kv: -(kv[1]["closed"] + kv[1]["open"])):
            hit = fnum(c["wins"] / c["closed"] * 100, 1) + " %" if c["closed"] else "–"
            rows.append([CLASS_LABEL.get(ac, ac), c["closed"] + c["open"], c["closed"], c["open"], hit,
                         fnum(c["net_r"], 2, True) if c["closed"] else "–",
                         fnum(c["net_pct"], 1, True) if c["closed"] else "–"])
        doc.table(["Klasse", "Trades gesamt", "Geschlossen", "Offen, ungewertet", "Trefferquote", "Netto-R", "Netto-%"],
                  rows, [100, 70, 70, 100, 70, 70, 77], ["l"] + ["r"] * 6)
        doc.para("Achtung: Die Varianten teilen sich dieselben Signale. Die Summen über alle Varianten zählen ein Signal "
                 "daher mehrfach – sie zeigen nur, WO gehandelt wird, nicht die Gesamtleistung.", size=7.5, color=GREY)

        # Offene Trades
        doc.heading(f"Offene Trades – offen, nicht gewertet ({len(d['open_trades'])})")
        rows = []
        for t in d["open_trades"]:
            res = t.result or {}
            state = "wartet auf Einstieg" if t.status == "pending_fill" else "offen"
            rows.append([short_variant(t.strategy_id), t.symbol, t.direction, state, fdt(t.entry_time) if t.entry_time else "–",
                         fprice(t.stop_initial), fprice(t.target), fnum(res.get("mfe_r"), 2), fnum(res.get("mae_r"), 2)])
        if rows:
            doc.table(["Variante", "Symbol", "Richtung", "Status", "Einstieg", "Stop", "Ziel", "MFE R", "MAE R"],
                      rows, [48, 80, 52, 78, 62, 66, 66, 52, 49],
                      ["l", "l", "l", "l", "l", "r", "r", "r", "r"], size=7.2)
            doc.para("MFE/MAE = bester/schlechtester bisheriger Verlauf in R. Offene Trades zählen in keiner Kennzahl.",
                     size=7.5, color=GREY)
        else:
            doc.para("Zurzeit keine offenen Trades.")

        # letzte geschlossene
        doc.heading("Die letzten geschlossenen Trades")
        rows, cols = [], []
        for t in d["last_closed"]:
            r = t.result
            rows.append([short_variant(t.strategy_id), t.symbol, t.direction, r.get("outcome", ""),
                         fnum(r.get("netto_r"), 2, True), fnum(r.get("net_return_pct"), 2, True),
                         fnum(r.get("duration_days"), 1), fdt(r.get("exit_time"))])
            cols.append(GREEN if r.get("netto_r", 0) > 0 else RED)
        if rows:
            doc.table(["Variante", "Symbol", "Richtung", "Ausgang", "Netto-R", "Netto-%", "Dauer (Tage)", "Geschlossen"],
                      rows, [52, 92, 56, 82, 60, 60, 70, 85], ["l", "l", "l", "l", "r", "r", "r", "l"],
                      size=7.4, row_colors=cols)
        else:
            doc.para("Noch keine geschlossenen Trades.")
        doc.close()
    os.replace(tmp, path)
    return path
