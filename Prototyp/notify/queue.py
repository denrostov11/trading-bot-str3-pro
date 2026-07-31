# -*- coding: utf-8 -*-
"""Persistente, idempotente Telegram-Zustell-Warteschlange mit Retry/Backoff und Recovery.

Grundsaetze (Spec <telegram_fehlerbehandlung>):
- Keine Meldung geht stillschweigend verloren: jeder Zustand wird auf Platte persistiert.
- Doppelte Meldungen verhindert ein `message_idempotency_key` (hoechstens einmal zugestellt).
- Begrenzte Wiederholungen mit exponentiellem Backoff; danach delivery_status=FAILED_PERMANENT.
- Telegram-Fehler aendern NIE einen Trade-Zustand (diese Klasse kennt keine Trades).
- Nach Neustart wird die Queue aus der Datei wiederhergestellt; ausstehende Meldungen werden
  in Erstellungsreihenfolge (created_at) nachgeliefert.
- Telegram ist nie die verbindliche Quelle - nur eine Zustellschicht.

Persistenzformat: eine JSON-Datei { "items": [ ... ], "sent_keys": [ ... ] }.
`sent_keys` merkt bereits zugestellte Idempotenz-Schluessel (fuer Dedup auch nach Aufraeumen).
"""
import json, os, hashlib
from dataclasses import dataclass, asdict, field

PENDING = "PENDING"
SENT = "SENT"
FAILED_PERMANENT = "FAILED_PERMANENT"


def make_idempotency_key(strategy_id, message_type, ref_id, period=""):
    """Deterministischer Schluessel aus (strategy_id, message_type, signal/trade-id, period).
    Gleiche Nachricht -> gleicher Schluessel -> hoechstens eine Zustellung."""
    raw = f"{strategy_id}|{message_type}|{ref_id}|{period}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


@dataclass
class QueueItem:
    queue_message_id: str
    message_idempotency_key: str
    target_chat: str
    strategy_id: str
    message_type: str
    payload_reference: str          # Verweis/ID auf lokalen Datensatz (keine Secrets)
    text: str = ""                  # gerenderte Nachricht (ohne Secrets) ODER Bild-Caption
    document_path: str = ""         # optionaler Anhang (Bericht)
    created_at: float = 0.0
    next_retry_at: float = 0.0
    retry_count: int = 0
    last_error_class: str = ""
    delivery_status: str = PENDING
    telegram_message_id: int = 0
    sent_at: float = 0.0


class PersistentQueue:
    def __init__(self, path, max_retries=5, backoff_seconds=30, clock=None):
        self.path = path
        self.max_retries = max_retries
        self.backoff = backoff_seconds
        self.clock = clock or __import__("time").time
        self.items = []          # list[QueueItem]
        self.sent_keys = set()
        self._seq = 0
        self._load()

    # ---------- Persistenz ----------
    def _load(self):
        if os.path.exists(self.path):
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            self.items = [QueueItem(**d) for d in data.get("items", [])]
            self.sent_keys = set(data.get("sent_keys", []))
            self._seq = data.get("seq", len(self.items))

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"items": [asdict(i) for i in self.items],
                       "sent_keys": sorted(self.sent_keys), "seq": self._seq},
                      f, indent=1)
        os.replace(tmp, self.path)   # atomar - kein halb geschriebener Zustand

    # ---------- Einreihen ----------
    def enqueue(self, target_chat, strategy_id, message_type, payload_reference,
                idempotency_key, text="", document_path=""):
        """Reiht eine Nachricht ein. Bereits gesehener Idempotenz-Schluessel -> No-Op (kein Duplikat)."""
        if idempotency_key in self.sent_keys:
            return None
        if any(i.message_idempotency_key == idempotency_key for i in self.items):
            return None
        self._seq += 1
        now = self.clock()
        item = QueueItem(
            queue_message_id=f"Q{self._seq:08d}",
            message_idempotency_key=idempotency_key,
            target_chat=target_chat, strategy_id=strategy_id, message_type=message_type,
            payload_reference=payload_reference, text=text, document_path=document_path,
            created_at=now, next_retry_at=now,
        )
        self.items.append(item)
        self._save()
        return item.queue_message_id

    # ---------- Verarbeiten ----------
    def process(self, transport):
        """Versucht alle faelligen PENDING-Items in created_at-Reihenfolge zuzustellen.
        Gibt (sent, failed_perm, still_pending) zurueck. Wirft NIE nach oben durch."""
        now = self.clock()
        due = sorted([i for i in self.items
                      if i.delivery_status == PENDING and i.next_retry_at <= now],
                     key=lambda i: i.created_at)
        sent = failed = 0
        for it in due:
            try:
                if it.document_path:
                    res = transport.send_document(it.target_chat, it.document_path, it.text)
                else:
                    res = transport.send_text(it.target_chat, it.text)
                it.delivery_status = SENT
                it.telegram_message_id = getattr(res, "message_id", 0)
                it.sent_at = now
                self.sent_keys.add(it.message_idempotency_key)
                sent += 1
            except Exception as e:               # Zustellfehler -> Retry/Backoff, kein Durchwerfen
                it.retry_count += 1
                it.last_error_class = type(e).__name__
                if it.retry_count > self.max_retries:
                    it.delivery_status = FAILED_PERMANENT
                    failed += 1
                else:
                    it.next_retry_at = now + self.backoff * (2 ** (it.retry_count - 1))
            self._save()
        still_pending = sum(1 for i in self.items if i.delivery_status == PENDING)
        return sent, failed, still_pending

    # ---------- Abfragen ----------
    def pending(self):
        return [i for i in self.items if i.delivery_status == PENDING]

    def failed_permanent(self):
        return [i for i in self.items if i.delivery_status == FAILED_PERMANENT]

    def delivery_report(self):
        """Zustellungsbericht: dauerhaft fehlgeschlagene Meldungen bleiben nachvollziehbar."""
        return [{"queue_message_id": i.queue_message_id, "strategy_id": i.strategy_id,
                 "message_type": i.message_type, "target_chat": i.target_chat,
                 "retry_count": i.retry_count, "last_error_class": i.last_error_class,
                 "delivery_status": i.delivery_status} for i in self.failed_permanent()]
