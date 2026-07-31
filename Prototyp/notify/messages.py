# -*- coding: utf-8 -*-
"""Typisierte Telegram-Nachrichtenmodelle (16 Typen) + Pflicht-Metadaten.

Jede Nachricht traegt zwingend: strategy_id, strategy_version, message_type, symbol,
signal_id/trade_id, target_chat_id, created_at_utc. Signal-/Trade-Meldungen tragen den
Hinweis "Paper-Trading - keine echte Order". Die Modelle enthalten KEINE Berechnung -
sie formatieren nur bereits vorhandene, lokal gespeicherte Werte.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone

# 16 Nachrichtentypen (Spec)
WATCHLIST_NEW = "WATCHLIST_NEW"
NEAR_TRIGGER = "NEAR_TRIGGER"
TRIGGER_CONFIRMED = "TRIGGER_CONFIRMED"
TRADE_OPENED = "TRADE_OPENED"
FILTER_REJECTED = "FILTER_REJECTED"                 # standardmaessig NICHT einzeln senden
STOP_MOVED = "STOP_MOVED"
TARGET_HIT = "TARGET_HIT"
STOP_HIT = "STOP_HIT"
BREAK_EVEN_EXIT = "BREAK_EVEN_EXIT"
TRADE_CANCELLED = "TRADE_CANCELLED"
DATA_QUALITY_REJECTED = "DATA_QUALITY_REJECTED"     # standardmaessig NICHT einzeln senden
WEEKLY_REPORT = "WEEKLY_REPORT"
ROLLING_30D_REPORT = "ROLLING_30D_REPORT"           # NIE als Kalendermonat bezeichnen
CALENDAR_MONTH_REPORT = "CALENDAR_MONTH_REPORT"     # optional, klar getrennt
STRATEGY_STATUS = "STRATEGY_STATUS"
SYSTEM_WARNING = "SYSTEM_WARNING"

ALL_TYPES = {
    WATCHLIST_NEW, NEAR_TRIGGER, TRIGGER_CONFIRMED, TRADE_OPENED, FILTER_REJECTED, STOP_MOVED,
    TARGET_HIT, STOP_HIT, BREAK_EVEN_EXIT, TRADE_CANCELLED, DATA_QUALITY_REJECTED, WEEKLY_REPORT,
    ROLLING_30D_REPORT, CALENDAR_MONTH_REPORT, STRATEGY_STATUS, SYSTEM_WARNING,
}

# Typen, die standardmaessig NICHT als Einzelmeldung gehen (nur aggregiert in Berichten)
AGGREGATE_ONLY = {FILTER_REJECTED, DATA_QUALITY_REJECTED}

# Signal-/Trade-Meldungen brauchen den Paper-Trading-Hinweis
_SIGNAL_TYPES = {WATCHLIST_NEW, NEAR_TRIGGER, TRIGGER_CONFIRMED, TRADE_OPENED, STOP_MOVED,
                 TARGET_HIT, STOP_HIT, BREAK_EVEN_EXIT, TRADE_CANCELLED}

PAPER_NOTICE = "Paper-Trading - keine echte Order."


def _utcnow():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class Message:
    strategy_id: str
    strategy_version: str
    message_type: str
    symbol: str = ""
    signal_id: str = ""
    trade_id: str = ""
    parent_signal_id: str = ""
    is_comparison: bool = False          # -> Vergleichsgruppe
    is_system: bool = False              # -> Systemgruppe
    body: str = ""                       # bereits formatierter Text (aus lokalen Daten)
    document_path: str = ""              # optionaler PDF-Anhang (Berichte)
    target_chat_id: str = ""             # wird vom Router gesetzt
    created_at_utc: str = field(default_factory=_utcnow)

    def __post_init__(self):
        if self.message_type not in ALL_TYPES:
            raise ValueError(f"Unbekannter message_type: {self.message_type}")
        if self.message_type == SYSTEM_WARNING:
            self.is_system = True
        if self.message_type in (WEEKLY_REPORT, ROLLING_30D_REPORT, CALENDAR_MONTH_REPORT,
                                  STRATEGY_STATUS) and not self.symbol:
            self.symbol = "-"

    def ref_id(self):
        """signal_id oder trade_id (Pflicht-Metadatum)."""
        return self.trade_id or self.signal_id or "-"

    def render_text(self) -> str:
        """Formatiert den finalen Nachrichtentext inkl. Kopf + ggf. Paper-Trading-Hinweis.
        KEINE Secrets, keine Berechnung - nur Darstellung uebergebener Werte."""
        head = f"{self.strategy_id} ({self.strategy_version}) - {self.message_type}"
        lines = [head]
        if self.symbol and self.symbol != "-":
            lines.append(f"Instrument: {self.symbol}")
        if self.body:
            lines.append(self.body)
        if self.message_type in _SIGNAL_TYPES:
            lines.append(PAPER_NOTICE)
        return "\n".join(lines)
