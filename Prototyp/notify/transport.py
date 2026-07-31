# -*- coding: utf-8 -*-
"""Gemeinsame Transportabstraktion fuer Telegram.

- `Transport` = Schnittstelle (send_text / send_document) -> liefert SendResult oder wirft.
- `MockTransport` = fuer automatisierte Tests: sendet NICHTS real, zeichnet Aufrufe auf,
  kann gezielt Fehler simulieren (fuer Queue-/Retry-Tests spaeter).
- `RealTelegramTransport` = duenner HTTPS-Sender (requests). Wird in Unit-Tests NICHT benutzt.

Wichtig: Der Transport aendert niemals Trade-Zustaende. Fehler werden als Exception nach oben
gereicht; die (spaetere) Queue entscheidet ueber Retry/Backoff. Secrets werden nie geloggt.
"""
from dataclasses import dataclass, field
from .redact import redact, safe_error


@dataclass
class SendResult:
    ok: bool
    chat_id: str
    message_id: int = 0
    error: str = ""          # bereits redigiert


class TransportError(Exception):
    pass


class Transport:
    def send_text(self, chat_id: str, text: str) -> SendResult:
        raise NotImplementedError

    def send_document(self, chat_id: str, path: str, caption: str = "") -> SendResult:
        raise NotImplementedError


class MockTransport(Transport):
    """Testtransport: kein Netzwerk. Speichert alle Sendeaufrufe in `sent`.
    `fail_chats` = Menge von Chat-IDs, deren Zustellung fehlschlaegt (Simulation)."""
    def __init__(self, fail_chats=None):
        self.sent = []                       # Liste[dict]
        self.fail_chats = set(fail_chats or ())
        self._counter = 0

    def _deliver(self, kind, chat_id, payload, caption=""):
        if chat_id in self.fail_chats:
            raise TransportError(f"Simulierter Zustellfehler an {chat_id}")
        self._counter += 1
        rec = {"kind": kind, "chat_id": chat_id, "payload": payload, "caption": caption,
               "message_id": self._counter}
        self.sent.append(rec)
        return SendResult(ok=True, chat_id=chat_id, message_id=self._counter)

    def send_text(self, chat_id: str, text: str) -> SendResult:
        return self._deliver("text", chat_id, text)

    def send_document(self, chat_id: str, path: str, caption: str = "") -> SendResult:
        return self._deliver("document", chat_id, path, caption)

    # Test-Hilfen
    def texts_to(self, chat_id):
        return [r["payload"] for r in self.sent if r["kind"] == "text" and r["chat_id"] == chat_id]

    def chats_used(self):
        return {r["chat_id"] for r in self.sent}


class RealTelegramTransport(Transport):
    """Echter Sender. Nur im Betrieb genutzt, nie in Unit-Tests. Token kommt aus der Config,
    erscheint nie in Logs (redact bei Fehlern)."""
    def __init__(self, token: str, timeout: int = 40):
        self._api = f"https://api.telegram.org/bot{token}"
        self._timeout = timeout

    def send_text(self, chat_id: str, text: str) -> SendResult:
        import requests
        try:
            r = requests.post(f"{self._api}/sendMessage",
                              data={"chat_id": chat_id, "text": text}, timeout=self._timeout)
            j = r.json()
            if not j.get("ok"):
                raise TransportError(redact(str(j.get("description"))))
            return SendResult(ok=True, chat_id=chat_id,
                              message_id=j.get("result", {}).get("message_id", 0))
        except TransportError:
            raise
        except Exception as e:
            raise TransportError(safe_error(e))

    def send_document(self, chat_id: str, path: str, caption: str = "") -> SendResult:
        import requests
        try:
            with open(path, "rb") as f:
                r = requests.post(f"{self._api}/sendDocument",
                                  data={"chat_id": chat_id, "caption": caption[:1024]},
                                  files={"document": f}, timeout=max(self._timeout, 120))
            j = r.json()
            if not j.get("ok"):
                raise TransportError(redact(str(j.get("description"))))
            return SendResult(ok=True, chat_id=chat_id,
                              message_id=j.get("result", {}).get("message_id", 0))
        except TransportError:
            raise
        except Exception as e:
            raise TransportError(safe_error(e))
