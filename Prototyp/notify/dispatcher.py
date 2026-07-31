# -*- coding: utf-8 -*-
"""Dispatcher: verbindet Router + Queue. Nimmt fertige Message-Objekte (aus lokalen Daten),
routet deterministisch und reiht sie idempotent in die persistente Queue ein.

- AGGREGATE_ONLY-Typen werden nicht einzeln zugestellt (SuppressedMessage -> uebersprungen).
- Eine RoutingWarning (z. B. fehlende Varianten-Chat-ID) fuehrt NICHT zu Fehlleitung; sie wird
  als Systemwarnung gemeldet (falls System-/Vergleichsgruppe existiert) und protokolliert.
- Der Dispatcher berechnet NICHTS strategisches - er gibt nur bereits gespeicherte Ergebnisse aus.
"""
from .router import Router, RoutingWarning, SuppressedMessage
from .queue import make_idempotency_key
from . import messages as M


class Dispatcher:
    def __init__(self, config, queue):
        self.cfg = config
        self.router = Router(config)
        self.queue = queue
        self.warnings = []

    def dispatch(self, msg, period=""):
        """Routet + reiht ein. Gibt queue_message_id, 'SUPPRESSED' oder 'WARNING' zurueck."""
        try:
            target = self.router.resolve(msg)
        except SuppressedMessage:
            return "SUPPRESSED"
        except RoutingWarning as w:
            self._warn(msg, str(w))
            return "WARNING"
        key = make_idempotency_key(msg.strategy_id, msg.message_type, msg.ref_id(), period)
        qid = self.queue.enqueue(
            target_chat=target, strategy_id=msg.strategy_id, message_type=msg.message_type,
            payload_reference=msg.ref_id(), idempotency_key=key,
            text=msg.render_text(), document_path=msg.document_path,
        )
        return qid or "DUPLICATE"

    def _warn(self, msg, text):
        self.warnings.append({"strategy_id": msg.strategy_id, "message_type": msg.message_type,
                              "warning": text})
        target = self.cfg.system_target()
        if not target:
            return
        sysmsg = M.Message(strategy_id="SYSTEM", strategy_version="-",
                           message_type=M.SYSTEM_WARNING, body=text)
        try:
            key = make_idempotency_key("SYSTEM", M.SYSTEM_WARNING,
                                       f"{msg.strategy_id}:{msg.message_type}")
            self.queue.enqueue(target_chat=target, strategy_id="SYSTEM",
                               message_type=M.SYSTEM_WARNING, payload_reference="-",
                               idempotency_key=key, text=sysmsg.render_text())
        except Exception:
            pass   # Telegram-/Queue-Fehler darf nie durchschlagen
