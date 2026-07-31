# -*- coding: utf-8 -*-
"""Live-Verdrahtung der Telegram-Ausgabeschicht aus der .env (RealTransport + Router + Queue).

Baut aus der lokalen .env eine TelegramConfig, einen echten Transport und den deterministischen
Router. Wird vom Betrieb genutzt, um bereits gespeicherte Ergebnisse auszugeben. Secrets kommen
ausschliesslich aus der .env; Token/Chat-IDs erscheinen nie in Logs (redact).
"""
import os
from .config import load_and_validate
from .transport import RealTelegramTransport
from .router import Router, RoutingWarning, SuppressedMessage
from .queue import PersistentQueue
from .dispatcher import Dispatcher
from . import messages as M

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Prototyp/
QUEUE_PATH = os.path.join(HERE, "notify_queue.json")


def read_env(path=None):
    path = path or os.path.join(HERE, ".env")
    vals = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); vals[k.strip()] = v.strip()
    return vals


def build_from_env(active_variants):
    cfg, report = load_and_validate(read_env(), active_variants)
    transport = RealTelegramTransport(cfg.token) if cfg.enabled else None
    return cfg, transport, Router(cfg), report


def connectivity_test(active_variants):
    """Sendet je Gruppe (Varianten, Vergleich, System) eine Verbindungs-Testnachricht.
    Gibt {chat_label: 'OK'|Fehlerklasse}. Nur ein einmaliger, klar markierter Test."""
    cfg, transport, router, _ = build_from_env(active_variants)
    if not cfg.enabled or transport is None:
        return {"_": "Telegram inaktiv (kein Token/keine Chat-IDs)"}
    results = {}

    def _send(msg, label):
        try:
            target = router.resolve(msg)
        except (RoutingWarning, SuppressedMessage) as e:
            results[label] = f"ROUTING: {type(e).__name__}"; return
        try:
            transport.send_text(target, msg.render_text())
            results[label] = "OK"
        except Exception as e:
            results[label] = type(e).__name__

    for sid in active_variants:
        body = ("Gruppe verbunden – Verbindungstest der Str.3-Pro-Mehrkanal-Ausgabe.\n"
                "Paper-Trading – keine echte Order.")
        _send(M.Message(sid, "v1", M.STRATEGY_STATUS, body=body), sid)
    _send(M.Message("Str.3 Pro.1", "v1", M.STRATEGY_STATUS, is_comparison=True,
                    body="Vergleichsgruppe verbunden – Verbindungstest. Paper-Trading."), "Vergleich")
    _send(M.Message("SYSTEM", "-", M.SYSTEM_WARNING,
                    body="Systemgruppe verbunden – Verbindungstest. Paper-Trading."), "System")
    return results


# ---------------- Betriebs-Service (Queue + Dispatcher + RealTransport) ----------------
class TelegramService:
    """Bündelt Config, RealTransport, persistente Queue und Dispatcher für den Live-Betrieb.
    Idempotent (message_idempotency_key), retry-fähig, neustart-fest. No-Op wenn Telegram inaktiv."""
    def __init__(self, active_variants):
        self.cfg, report = load_and_validate(read_env(), active_variants)
        self.enabled = self.cfg.enabled
        self.transport = RealTelegramTransport(self.cfg.token) if self.enabled else None
        self.queue = PersistentQueue(QUEUE_PATH, max_retries=self.cfg.max_retries,
                                     backoff_seconds=self.cfg.retry_backoff_seconds)
        self.dispatcher = Dispatcher(self.cfg, self.queue)

    def _flush(self):
        if self.enabled and self.transport is not None:
            return self.queue.process(self.transport)
        return (0, 0, 0)

    def send(self, msg, period=""):
        if not self.enabled:
            return "DISABLED"
        r = self.dispatcher.dispatch(msg, period=period)
        self._flush()
        return r

    def trade_opened(self, t):
        body = (f"{t.direction} · Einstieg geplant (Open nächste Kerze)\n"
                f"Stop: {t.stop_initial} · Ziel: {t.target}\nparent_signal_id: {t.parent_signal_id}")
        self.send(M.Message(t.strategy_id, "v1", M.TRADE_OPENED, symbol=t.symbol,
                            trade_id=t.trade_id, parent_signal_id=t.parent_signal_id, body=body))

    def trade_closed(self, t):
        r = t.result
        mt = {"TARGET": M.TARGET_HIT, "STOP": M.STOP_HIT, "BREAK_EVEN": M.BREAK_EVEN_EXIT}.get(
            r.get("outcome"), M.STOP_HIT)
        body = (f"{t.direction} beendet: {r.get('outcome')}\n"
                f"Ergebnis: {r.get('netto_r')} R netto · {r.get('net_return_pct')} % netto\n"
                f"Dauer: {r.get('duration_days')} Tage · parent_signal_id: {t.parent_signal_id}")
        self.send(M.Message(t.strategy_id, "v1", mt, symbol=t.symbol, trade_id=t.trade_id,
                            parent_signal_id=t.parent_signal_id, body=body))

    def system(self, text):
        self.send(M.Message("SYSTEM", "-", M.SYSTEM_WARNING, body=text),
                  period=str(int(__import__("time").time())))

    def deliver_reports(self, reports, days, label, active_variants):
        """Kurztext + PDF je Variante an ihre Gruppe; Vergleichs-PDF an die Vergleichsgruppe."""
        if not self.enabled:
            return "DISABLED"
        datestr = __import__("time").strftime("%Y-%m-%d")
        mtype = M.WEEKLY_REPORT if days == 7 else M.ROLLING_30D_REPORT
        for sid in active_variants:
            txt = reports["short_texts"].get(sid, "")
            pdf = reports["variant_pdfs"].get(sid, "")
            m = M.Message(sid, "v1", mtype, symbol="-", signal_id=f"{label}:{datestr}", body=txt)
            m.document_path = pdf
            self.send(m, period=f"{label}:{datestr}")
        comp = M.Message("Str.3 Pro.1", "v1", mtype, is_comparison=True, symbol="-",
                         signal_id=f"CMP:{label}:{datestr}", body=f"Variantenvergleich {label}")
        comp.document_path = reports.get("comparison_pdf", "")
        self.send(comp, period=f"CMP:{label}:{datestr}")
        return "OK"
