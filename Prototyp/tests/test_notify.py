# -*- coding: utf-8 -*-
"""Increment-1-Tests der Telegram-Ausgabeschicht (Mock-Transport, keine echten Nachrichten).
Deckt ab: Routing-Exklusivitaet, Fallback-Regeln, fehlende Chat-ID ohne Fehlleitung,
Redaction (kein Token-Leak), Konfig-Validierung, Aggregate-Only-Unterdrueckung,
Paper-Trading-Hinweis. Zuordnung zu Spec-Telegram-Tests: 1,2,3,4,5,14,17,18,25,29."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from notify.config import load_and_validate, REQUIRED, DISABLED
from notify.router import Router, RoutingWarning, SuppressedMessage
from notify.transport import MockTransport
from notify import messages as M
from notify.redact import redact, mask_token, mask_id

FULL_ENV = {
    "TELEGRAM_BOT_TOKEN": "1234567890:AAHtestTokenTokenTokenTokenTokenTokenXYZ",
    "TELEGRAM_AUTHORIZED_USER_IDS": "123456789",
    "STR3_PRO1_CHAT_ID": "-1001", "STR3_PRO2_CHAT_ID": "-1002",
    "STR3_PRO3_CHAT_ID": "-1003", "STR3_PRO4_CHAT_ID": "-1004",
    "STR3_PRO5_CHAT_ID": "-1005", "STR3_PRO6_CHAT_ID": "-1006",
    "STR3_PRO7_CHAT_ID": "-1007", "STR3_PRO8_CHAT_ID": "-1008",
    "STR3_COMPARISON_CHAT_ID": "-1009", "STR3_SYSTEM_CHAT_ID": "-1010",
}
ALL_VARIANTS = list(M.__dict__ and [f"Str.3 Pro.{i}" for i in range(1, 9)])


def cfg(env, active=ALL_VARIANTS):
    c, _ = load_and_validate(env, active)
    return c


def msg(strategy_id, mtype=M.TRADE_OPENED, **kw):
    return M.Message(strategy_id=strategy_id, strategy_version="v1", message_type=mtype,
                     symbol="GC=F", signal_id="SIG-1", **kw)


# --- Routing-Exklusivitaet (Spec-Test 1,2) ---
def test_pro1_only_to_pro1():
    r = Router(cfg(FULL_ENV))
    assert r.resolve(msg("Str.3 Pro.1")) == "-1001"

def test_pro8_only_to_pro8():
    r = Router(cfg(FULL_ENV))
    assert r.resolve(msg("Str.3 Pro.8")) == "-1008"

def test_each_variant_disjoint():
    r = Router(cfg(FULL_ENV))
    targets = {sid: r.resolve(msg(sid)) for sid in ALL_VARIANTS}
    assert len(set(targets.values())) == 8   # alle verschieden


# --- Vergleich / System (Spec-Test 3,4,17) ---
def test_comparison_to_comparison_group():
    r = Router(cfg(FULL_ENV))
    m = M.Message("Str.3 Pro.1", "v1", M.WEEKLY_REPORT, is_comparison=True)
    assert r.resolve(m) == "-1009"

def test_system_to_system_group():
    r = Router(cfg(FULL_ENV))
    m = M.Message("SYSTEM", "v1", M.SYSTEM_WARNING)
    assert r.resolve(m) == "-1010"

def test_system_fallback_to_comparison_when_no_system_group():
    env = dict(FULL_ENV); env.pop("STR3_SYSTEM_CHAT_ID")
    r = Router(cfg(env))
    m = M.Message("SYSTEM", "v1", M.SYSTEM_WARNING)
    assert r.resolve(m) == "-1009"   # Fallback Vergleichsgruppe


# --- Fehlende Varianten-Chat-ID: KEIN Fallback (Spec-Test 18) ---
def test_missing_variant_chat_no_fallback():
    env = dict(FULL_ENV); env.pop("STR3_PRO3_CHAT_ID")
    r = Router(cfg(env))
    with pytest.raises(RoutingWarning):
        r.resolve(msg("Str.3 Pro.3"))
    # und andere Gruppen bleiben unberuehrt/korrekt
    assert r.resolve(msg("Str.3 Pro.2")) == "-1002"


# --- Aggregate-Only wird nicht einzeln geroutet ---
def test_filter_rejected_suppressed():
    r = Router(cfg(FULL_ENV))
    with pytest.raises(SuppressedMessage):
        r.resolve(msg("Str.3 Pro.3", mtype=M.FILTER_REJECTED))


# --- Konfig-Validierung (Spec-Test 5) ---
def test_missing_active_variant_chat_produces_warning():
    env = dict(FULL_ENV); env.pop("STR3_PRO4_CHAT_ID")
    c, report = load_and_validate(env, ALL_VARIANTS)
    item = next(i for i in report if i.key == "STR3_PRO4_CHAT_ID")
    assert item.status == REQUIRED and not item.present and item.warning

def test_no_token_disables_telegram():
    env = dict(FULL_ENV); env["TELEGRAM_BOT_TOKEN"] = ""
    c, report = load_and_validate(env, ALL_VARIANTS)
    assert c.enabled is False
    tok = next(i for i in report if i.key == "TELEGRAM_BOT_TOKEN")
    assert tok.status == DISABLED


# --- Redaction: kein Token/ID-Leak (Spec-Test 14,25) ---
def test_redact_removes_token_in_url():
    leak = ("HTTPError url: https://api.telegram.org/bot1234567890:AAHsecretsecretsecret"
            "secretsecretsecretXY/sendMessage")
    out = redact(leak)
    assert "AAHsecret" not in out and "1234567890:" not in out
    assert "<REDACTED_TOKEN>" in out

def test_mask_helpers():
    assert mask_token("1234567890:AAH...") == "<REDACTED_TOKEN>"
    assert mask_id("-1001234567") .endswith("567") and "***" in mask_id("-1001234567")


# --- Paper-Trading-Hinweis in Signalmeldung (Spec-Test 29) ---
def test_signal_message_has_paper_notice():
    m = msg("Str.3 Pro.1", mtype=M.TRADE_OPENED, body="Einstieg 2451.30")
    txt = m.render_text()
    assert M.PAPER_NOTICE in txt

def test_report_message_has_no_paper_notice():
    m = M.Message("Str.3 Pro.1", "v1", M.WEEKLY_REPORT, is_comparison=False)
    assert M.PAPER_NOTICE not in m.render_text()


# --- MockTransport sendet nichts real, zeichnet auf ---
def test_mock_transport_records():
    t = MockTransport()
    t.send_text("-1001", "hallo")
    assert t.texts_to("-1001") == ["hallo"]
    assert t.chats_used() == {"-1001"}
