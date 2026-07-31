# -*- coding: utf-8 -*-
"""Deterministisches Routing: bestimmt fuer jede Nachricht genau EIN Ziel.

Regeln (Spec):
- Varianten-Meldung -> AUSSCHLIESSLICH die zugehoerige Varianten-Gruppe.
- Vergleichs-/Uebersichtsmeldung -> Vergleichsgruppe.
- System-/Fehler-/Datenqualitaets-Meldung -> Systemgruppe, sonst Fallback Vergleichsgruppe.
- Fehlt die Chat-ID einer AKTIVEN Variante -> RoutingWarning (KEIN Fallback in andere Gruppe).
- AGGREGATE_ONLY-Typen werden nicht einzeln geroutet (nur aggregiert in Berichten).
"""
from .messages import AGGREGATE_ONLY
from .config import VARIANT_ENV


class RoutingWarning(Exception):
    """Nachricht kann nicht zugestellt werden (z. B. fehlende Varianten-Chat-ID).
    Bewusst KEINE stille Fehlleitung - der Aufrufer protokolliert/queued die Warnung."""


class SuppressedMessage(Exception):
    """Nachricht wird bewusst nicht als Einzelmeldung gesendet (AGGREGATE_ONLY)."""


class Router:
    def __init__(self, config):
        self.cfg = config

    def resolve(self, msg) -> str:
        """Liefert die Ziel-Chat-ID oder wirft RoutingWarning/SuppressedMessage.
        Setzt msg.target_chat_id bei Erfolg."""
        if msg.message_type in AGGREGATE_ONLY:
            raise SuppressedMessage(
                f"{msg.message_type} wird nur aggregiert in Berichten dargestellt, nicht einzeln.")

        if msg.is_system:
            target = self.cfg.system_target()   # System, sonst Vergleich
            if not target:
                raise RoutingWarning("Keine System- und keine Vergleichsgruppe konfiguriert.")
            msg.target_chat_id = target
            return target

        if msg.is_comparison:
            if not self.cfg.comparison_chat:
                raise RoutingWarning("Vergleichsgruppe (STR3_COMPARISON_CHAT_ID) fehlt.")
            msg.target_chat_id = self.cfg.comparison_chat
            return self.cfg.comparison_chat

        # Varianten-Meldung
        if msg.strategy_id not in VARIANT_ENV:
            raise RoutingWarning(f"Unbekannte strategy_id: {msg.strategy_id}")
        target = self.cfg.chat_for_variant(msg.strategy_id)
        if not target:
            # KEIN Fallback in eine andere Gruppe (Spec-Test 18)
            raise RoutingWarning(
                f"Fehlende Chat-ID fuer {msg.strategy_id} ({VARIANT_ENV[msg.strategy_id]}). "
                f"Nachricht wird NICHT an eine andere Gruppe umgeleitet.")
        msg.target_chat_id = target
        return target
