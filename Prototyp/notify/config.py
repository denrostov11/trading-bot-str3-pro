# -*- coding: utf-8 -*-
"""Telegram-Konfigurationsmodell + Start-Validierung.

Laedt Chat-IDs/Token/Parameter ausschliesslich aus einer env-artigen Quelle (dict), niemals
aus hartkodierten Werten. Validierung klassifiziert jeden Schluessel:
  REQUIRED               - noetig fuer eine aktive Funktion; fehlt -> Warnung
  OPTIONAL               - darf fehlen (definierter Fallback)
  DISABLED_BY_CONFIGURATION - Telegram/Funktion bewusst aus

Grundsatz: Eine fehlende Varianten-Chat-ID einer AKTIVEN Variante fuehrt NIE zu einem stillen
Fallback in eine andere Gruppe, sondern zu einer eindeutigen Warnung. Die Strategie laeuft
lokal weiter (Paper-Trading unberuehrt).
"""
from dataclasses import dataclass, field

# strategy_id -> ENV-Schluessel der Ziel-Chat-ID
VARIANT_ENV = {
    "Str.3 Pro.1": "STR3_PRO1_CHAT_ID",
    "Str.3 Pro.2": "STR3_PRO2_CHAT_ID",
    "Str.3 Pro.3": "STR3_PRO3_CHAT_ID",
    "Str.3 Pro.4": "STR3_PRO4_CHAT_ID",
    "Str.3 Pro.5": "STR3_PRO5_CHAT_ID",
    "Str.3 Pro.6": "STR3_PRO6_CHAT_ID",
    "Str.3 Pro.7": "STR3_PRO7_CHAT_ID",
    "Str.3 Pro.8": "STR3_PRO8_CHAT_ID",
}
COMPARISON_ENV = "STR3_COMPARISON_CHAT_ID"
SYSTEM_ENV = "STR3_SYSTEM_CHAT_ID"

REQUIRED = "REQUIRED"
OPTIONAL = "OPTIONAL"
DISABLED = "DISABLED_BY_CONFIGURATION"


@dataclass
class TelegramConfig:
    token: str = ""
    authorized_user_ids: frozenset = frozenset()
    variant_chats: dict = field(default_factory=dict)   # strategy_id -> chat_id (nur vorhandene)
    comparison_chat: str = ""
    system_chat: str = ""
    report_timezone: str = "Europe/Berlin"
    weekly_report_day: str = "Sunday"
    weekly_report_time: str = "20:00"
    rolling_30d_report_time: str = "20:30"
    max_retries: int = 5
    retry_backoff_seconds: int = 30
    enabled: bool = False

    def chat_for_variant(self, strategy_id):
        """Ziel-Chat einer Variante oder None (kein Fallback in andere Gruppe!)."""
        return self.variant_chats.get(strategy_id)

    def system_target(self):
        """Systemmeldungen -> Systemgruppe, sonst Fallback Vergleichsgruppe (Spec-Regel)."""
        return self.system_chat or self.comparison_chat or None


@dataclass
class ValidationItem:
    key: str
    status: str          # REQUIRED / OPTIONAL / DISABLED_BY_CONFIGURATION
    present: bool
    warning: str = ""


def load_and_validate(env: dict, active_variants):
    """Baut TelegramConfig aus env (dict) und liefert (config, [ValidationItem]).
    `active_variants` = iterable aktiver strategy_ids. Keine Ausnahme bei fehlenden Werten -
    stattdessen Warnungen im Report (Telegram darf die Strategie nicht blockieren)."""
    active = set(active_variants)
    report = []

    token = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    enabled = bool(token)
    report.append(ValidationItem("TELEGRAM_BOT_TOKEN", REQUIRED if enabled else DISABLED,
                                 bool(token),
                                 "" if token else "Kein Token -> Telegram DISABLED_BY_CONFIGURATION"))

    raw_users = (env.get("TELEGRAM_AUTHORIZED_USER_IDS") or "").strip()
    users = frozenset(u.strip() for u in raw_users.split(",") if u.strip())
    report.append(ValidationItem("TELEGRAM_AUTHORIZED_USER_IDS",
                                 REQUIRED if enabled else OPTIONAL, bool(users),
                                 "" if users else "Keine autorisierten User-IDs -> Befehle deaktiviert"))

    variant_chats = {}
    for sid, envkey in VARIANT_ENV.items():
        val = (env.get(envkey) or "").strip()
        is_active = sid in active
        if val:
            variant_chats[sid] = val
        status = REQUIRED if (enabled and is_active) else OPTIONAL
        warn = ""
        if enabled and is_active and not val:
            warn = (f"AKTIVE Variante {sid} ohne {envkey}: kein Telegram-Ziel. KEIN Fallback in "
                    f"andere Gruppe; lokale Auswertung laeuft weiter.")
        report.append(ValidationItem(envkey, status, bool(val), warn))

    comparison = (env.get(COMPARISON_ENV) or "").strip()
    report.append(ValidationItem(COMPARISON_ENV, REQUIRED if enabled else OPTIONAL, bool(comparison),
                                 "" if comparison or not enabled else "Vergleichsgruppe fehlt"))

    system = (env.get(SYSTEM_ENV) or "").strip()
    report.append(ValidationItem(SYSTEM_ENV, OPTIONAL, bool(system),
                                 "" if system else "Keine Systemgruppe -> Fallback auf Vergleichsgruppe"))

    def _int(key, default):
        try:
            return int(str(env.get(key)).strip())
        except (TypeError, ValueError):
            return default

    cfg = TelegramConfig(
        token=token, authorized_user_ids=users, variant_chats=variant_chats,
        comparison_chat=comparison, system_chat=system,
        report_timezone=(env.get("REPORT_TIMEZONE") or "Europe/Berlin").strip(),
        weekly_report_day=(env.get("WEEKLY_REPORT_DAY") or "Sunday").strip(),
        weekly_report_time=(env.get("WEEKLY_REPORT_TIME") or "20:00").strip(),
        rolling_30d_report_time=(env.get("ROLLING_30D_REPORT_TIME") or "20:30").strip(),
        max_retries=_int("TELEGRAM_MAX_RETRIES", 5),
        retry_backoff_seconds=_int("TELEGRAM_RETRY_BACKOFF_SECONDS", 30),
        enabled=enabled,
    )
    return cfg, report
