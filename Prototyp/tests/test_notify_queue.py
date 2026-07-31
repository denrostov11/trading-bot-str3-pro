# -*- coding: utf-8 -*-
"""Increment-2-Tests: persistente Queue, Idempotenz, Retry/Backoff, Recovery, Zustellbericht.
Spec-Telegram-Tests: 7,8,13,19,26,27 (+ 15/16 sinngemaess: Ausfall wirft nicht durch)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from notify.queue import (PersistentQueue, make_idempotency_key, PENDING, SENT, FAILED_PERMANENT)
from notify.transport import MockTransport


class Clock:
    def __init__(self, t=1000.0): self.t = t
    def __call__(self): return self.t
    def tick(self, dt): self.t += dt


def q(tmp_path, clock, max_retries=3, backoff=30):
    return PersistentQueue(str(tmp_path / "queue.json"), max_retries=max_retries,
                           backoff_seconds=backoff, clock=clock)


def key(i): return make_idempotency_key("Str.3 Pro.1", "TRADE_OPENED", f"T{i}")


# 7: Fehlgeschlagene Meldung landet in persistenter Warteschlange
def test_failed_delivery_stays_pending(tmp_path):
    c = Clock(); queue = q(tmp_path, c)
    queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", "ref", key(1), text="hi")
    t = MockTransport(fail_chats={"-1001"})
    sent, failed, pend = queue.process(t)
    assert sent == 0 and pend == 1
    assert queue.pending()[0].retry_count == 1
    assert os.path.exists(queue.path)   # persistiert


# 8 + 19: Idempotenz - gleicher Key wird hoechstens einmal zugestellt
def test_idempotency_no_duplicate_enqueue(tmp_path):
    c = Clock(); queue = q(tmp_path, c)
    k = key(1)
    assert queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", "ref", k, text="a") is not None
    assert queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", "ref", k, text="a") is None
    assert len(queue.items) == 1

def test_idempotency_after_sent(tmp_path):
    c = Clock(); queue = q(tmp_path, c)
    k = key(2)
    queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", "ref", k, text="a")
    queue.process(MockTransport())
    # erneut mit gleichem Key -> kein neues Item
    assert queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", "ref", k, text="a") is None
    t = MockTransport(); queue.process(t)
    assert len(t.sent) == 0   # nichts erneut gesendet


# Retry/Backoff eskaliert und wird nach max_retries FAILED_PERMANENT (27)
def test_retry_backoff_then_permanent(tmp_path):
    c = Clock(); queue = q(tmp_path, c, max_retries=2, backoff=10)
    queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", "ref", key(3), text="hi")
    t = MockTransport(fail_chats={"-1001"})
    queue.process(t); assert queue.pending()[0].retry_count == 1
    c.tick(9); queue.process(t)                     # noch nicht faellig -> unveraendert
    assert queue.pending()[0].retry_count == 1
    c.tick(2); queue.process(t); assert queue.pending()[0].retry_count == 2
    c.tick(100); s, f, p = queue.process(t)         # 3. Versuch > max_retries=2
    assert f == 1 and p == 0
    assert queue.failed_permanent()[0].delivery_status == FAILED_PERMANENT
    assert queue.delivery_report()[0]["message_type"] == "TRADE_OPENED"


# 13: Recovery nach Neustart - Datei wird neu geladen, PENDING bleibt
def test_recovery_after_restart(tmp_path):
    c = Clock(); queue = q(tmp_path, c)
    queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", "ref", key(4), text="hi")
    queue.process(MockTransport(fail_chats={"-1001"}))   # bleibt PENDING
    # neue Instanz auf gleicher Datei
    queue2 = q(tmp_path, c)
    assert len(queue2.pending()) == 1
    assert queue2.pending()[0].message_idempotency_key == key(4)


# 26: Nach Wiederherstellung geordnete Nachlieferung (created_at-Reihenfolge)
def test_ordered_redelivery(tmp_path):
    c = Clock(); queue = q(tmp_path, c)
    for i in range(3):
        queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", f"r{i}", key(10 + i), text=f"m{i}")
        c.tick(1)
    t = MockTransport()
    queue.process(t)
    assert [r["payload"] for r in t.sent] == ["m0", "m1", "m2"]


# 15/16 sinngemaess: Zustellfehler wirft nicht nach oben durch (kein Crash des Zyklus)
def test_process_never_raises(tmp_path):
    c = Clock(); queue = q(tmp_path, c)
    queue.enqueue("-1001", "Str.3 Pro.1", "TRADE_OPENED", "ref", key(20), text="hi")
    # Transport, der eine unerwartete Exception wirft
    class Boom(MockTransport):
        def send_text(self, *a, **k): raise RuntimeError("boom")
    s, f, p = queue.process(Boom())
    assert s == 0 and p == 1   # sauber behandelt, kein Durchwerfen
