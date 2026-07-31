# -*- coding: utf-8 -*-
"""Redaction: Bot-Token, vollstaendige Chat-IDs und User-IDs duerfen niemals im Klartext in
Logs, Fehlermeldungen, Berichten oder Backups erscheinen (Telegram-Sicherheitsregel).

Behebt KRITISCH-Fund T1: Der bisherige `print("Telegram-Fehler:", e)` konnte die Token-haltige
API-URL (https://api.telegram.org/bot<TOKEN>/...) ins Log schreiben. `redact()` maskiert das.
"""
import re

# Telegram-Bot-Token: <digits>:<35+ base64-ish chars>
_TOKEN_RE = re.compile(r"\b\d{6,}:[A-Za-z0-9_\-]{30,}\b")
# Token in einer api.telegram.org-URL
_URL_TOKEN_RE = re.compile(r"(api\.telegram\.org/bot)\d{6,}:[A-Za-z0-9_\-]{30,}", re.I)
# Lange (auch negative) numerische IDs (Chat-/User-IDs) - defensiv ab 6 Stellen
_LONGID_RE = re.compile(r"-?\d{6,}")


def mask_token(value: str) -> str:
    """Vollstaendiges Token -> unkenntlich."""
    if not value:
        return value
    return "<REDACTED_TOKEN>"


def mask_id(value) -> str:
    """Chat-/User-ID -> nur letzte 3 Stellen sichtbar, Rest maskiert (fuer Debug ohne Leak)."""
    s = str(value)
    digits = s.lstrip("-")
    if len(digits) <= 3:
        return "***"
    return ("-" if s.startswith("-") else "") + "***" + digits[-3:]


def redact(text: str) -> str:
    """Entfernt Token (auch in URLs) und maskiert lange IDs aus beliebigem Text
    (z. B. Exception-Strings), bevor er geloggt/versendet/gesichert wird."""
    if text is None:
        return text
    s = str(text)
    s = _URL_TOKEN_RE.sub(r"\1<REDACTED_TOKEN>", s)
    s = _TOKEN_RE.sub("<REDACTED_TOKEN>", s)
    s = _LONGID_RE.sub(lambda m: mask_id(m.group(0)), s)
    return s


def safe_error(exc: Exception) -> str:
    """Redigierte, log-sichere Darstellung einer Exception (Klasse + maskierte Nachricht)."""
    return f"{type(exc).__name__}: {redact(str(exc))}"
