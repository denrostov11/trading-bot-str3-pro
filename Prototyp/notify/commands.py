# -*- coding: utf-8 -*-
"""Autorisierte Telegram-Befehle (nur lesend).

Sicherheit (Spec <telegram_datenschutz_und_sicherheit>):
- Nur Nutzer aus der Allowlist (TELEGRAM_AUTHORIZED_USER_IDS) duerfen Befehle ausloesen.
- Chat-ID und User-ID werden getrennt validiert.
- Nur fest definierte /commands; unbekannte Eingaben loesen KEINE dynamische Code-/Shell-Ausfuehrung aus.
- KEIN eval/exec/Shell, keine Dateipfade/SQL aus Telegram, keine echten Orders, keine Konfigaenderung,
  keine Geheimnisse in Antworten.
- Reine Status-/Berichtsabfragen; Handler sind read-only Callbacks (spaeter aus der Engine).
"""
VARIANT_COMMANDS = {
    "/status", "/offene_trades", "/letzte_trades", "/bilanz", "/wochenbericht",
    "/bericht_30_tage", "/watchlist", "/parameter", "/datenstatus",
}
COMPARISON_COMMANDS = {
    "/vergleich", "/ranking", "/vergleich_7_tage", "/vergleich_30_tage", "/vergleich_gesamt",
    "/filterwirkung", "/systemstatus", "/datenqualitaet", "/offene_trades_alle",
}
ALL_COMMANDS = VARIANT_COMMANDS | COMPARISON_COMMANDS


class CommandResult:
    def __init__(self, status, text="", command=""):
        self.status = status        # OK / IGNORED_UNAUTHORIZED / UNKNOWN_COMMAND / NO_HANDLER
        self.text = text
        self.command = command


def normalize(text):
    """Erste Token als Kleinbuchstaben-Befehl; entfernt @botname-Suffix. Keine Auswertung von Inhalten."""
    if not text:
        return ""
    tok = text.strip().split()[0].lower()
    if "@" in tok:
        tok = tok.split("@", 1)[0]
    return tok


def handle(user_id, chat_id, text, authorized_user_ids, handlers):
    """handlers: dict command -> callable() -> str (read-only). Gibt CommandResult zurueck.
    Blockiert die Analyse-Engine nicht (Handler sind reine Leseoperationen)."""
    if str(user_id) not in {str(u) for u in authorized_user_ids}:
        # Unbekannte Nutzer erhalten nichts und loesen nichts aus.
        return CommandResult("IGNORED_UNAUTHORIZED")
    cmd = normalize(text)
    if cmd not in ALL_COMMANDS:
        # KEINE dynamische Ausfuehrung - nur klare Rueckmeldung.
        return CommandResult("UNKNOWN_COMMAND", command=cmd)
    fn = handlers.get(cmd)
    if fn is None:
        return CommandResult("NO_HANDLER", command=cmd)
    out = fn()                      # read-only Callback der Engine
    return CommandResult("OK", text=str(out), command=cmd)
