# -*- coding: utf-8 -*-
"""
Str.3 Pro - Telegram-Ausgabeschicht (notify).

REINE Ausgabeschicht: gibt ausschliesslich bereits lokal gespeicherte, nachvollziehbare
Ergebnisse aus. Enthaelt KEINE Strategie-/Daten-/Trade-Berechnung (keine Duplikate der Engine).
Die lokale Datenbank ist die verbindliche Quelle. Ein Telegram-Fehler darf NIE einen Trade-
Zustand aendern, Daten verlieren oder die Strategiebewertung verfaelschen.

Aufbau (Spec-Schritte 1-13):
  config    - Konfig-Modell + Start-Validierung (REQUIRED/OPTIONAL/DISABLED_BY_CONFIGURATION)
  transport - gemeinsame Transportabstraktion (MockTransport fuer Tests, RealTelegramTransport)
  router    - deterministisches Routing strategy_id/message_type -> Ziel-Chat
  messages  - typisierte Nachrichtenmodelle (16 Typen) inkl. Paper-Trading-Hinweis
  redact    - maskiert Token/volle Chat-IDs in Logs/Fehlern (kein Secret-Leak)
  (folgt)   - queue (persistent, idempotent, Retry/Backoff), commands (autorisiert, nur lesend)

Stand: Increment 1 (config/transport/router/messages/redact + Tests). Noch nicht an die
Strategie-Engine verdrahtet (die existiert noch nicht) und nicht produktiv aktiviert.
"""
