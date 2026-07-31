# TEST_GAPS.md — §10

> Stand 2026-07-25. 90 Tests grün. Bekannte Lücken (keine davon KRITISCH offen):
- Session-/DST-Aggregation nur für Krypto (24/7) getestet; RTH-Instrumente (Aktien/Futures) ohne
  Kalender-Fixture → Grenzfall-Tests fehlen (H-1).
- Kontosimulation (Portfolio, Parallel-Trades, Kapitalgrenze) nicht implementiert → keine Tests (H-2).
- End-to-End-Integration auf einem SYNTHETISCHEN Trigger (erzwungener A+-Bruch → Trade → Ergebnis) fehlt;
  bisher nur Wiring-Tests (injizierte Erkennung) + realer Dry-Run ohne aktuelle Trigger.
- Live-Telegram (RealTransport) nur strukturell; kein kontrollierter Integrationstest mit Test-Gruppen (§ Telegram 14).
- Reporting-PDF-Erzeugung + Telegram-Zustellung der Berichte nicht implementiert → keine Tests.
- Rollover-Erkennung nur auf synthetischem Ausreißer getestet; reale Rollover-Fälle nicht kalibriert.
- Lange-Laufzeit-/Recovery-unter-Last-Test (Absturz mitten im Zyklus) nicht durchgeführt.

## Empfohlene Ergänzungstests (vor STUFE 3 / Zwei-Monats-Start)
1. Synthetischer Ende-zu-Ende-Trigger mit bekanntem Ergebnis (Trade eröffnet, gefüllt, geschlossen, R/%).
2. RTH-Session-Fixture (Aktie) → korrekte 4h-Blöcke + is_final an Sessiongrenzen.
3. Kontosimulation (falls aktiviert): Kapitalgrenze bei N Parallel-Trades, compounded vs. fixed.
4. Telegram-Integrationstest mit dedizierten Test-Gruppen (kein Produktiv-Chat).
5. Crash-Recovery: Prozess-Kill mitten im Zyklus → konsistenter Wiederanlauf ohne Datenverlust.
