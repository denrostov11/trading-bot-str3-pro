# TEST_RESULTS.md — Str.3 Pro

> Noch keine automatisierten Tests vorhanden (Phase G ausstehend). Geplante Testfälle (QS #1–#22, siehe
> Master-Prompt / Testplan in AUDIT-Antwort). Jeder Fall wird hier mit Status (pass/fail) und Datum geführt.

| # | Testfall | Status | Datum | Notiz |
|---|----------|--------|-------|-------|
| 1 | Pivot erst nach 3 rechten Kerzen bestätigt | offen | — | Code A6 vermutlich korrekt, Test fehlt |
| 2 | Unvollständige 4h-Kerze erzeugt keinen Trigger | offen | — | aktuell FALSCH (A1) |
| 3 | Bruchkerze nicht als Tap | offen | — | Code B6 vermutlich korrekt |
| 4 | Schluss an Toleranzgrenze deterministisch | offen | — | |
| 5 | Action-Line mit 2 Taps abgelehnt | offen | — | |
| 6 | Safety-Line mit 1 Tap abgelehnt | offen | — | |
| 7 | Parallele Linien abgelehnt | offen | — | converges() vorhanden |
| 8 | Divergierende Linien abgelehnt | offen | — | converges() vorhanden |
| 9 | Apex hinter erlaubtem Zeitraum abgelehnt | offen | — | MAX_APEX_BARS=180 |
| 10 | Stop auf falscher Seite abgelehnt | offen | — | Guard fehlt (B3) |
| 11 | Nächstes S/R < 2R → REJECTED_RR | offen | — | aktuell FALSCH (B1/B2) |
| 12 | Alter Bruch → kein rückdatierter Trade | offen | — | aktuell FALSCH (A3) |
| 13 | Doppelte Daten entfernt | offen | — | nicht implementiert (C1) |
| 14 | Cache bleibt bei kürzerem Download | offen | — | nicht implementiert (C1) |
| 15 | Fehlendes Volumen deaktiviert nur Volumenfilter | offen | — | |
| 16 | Yahoo-Ausfall stoppt nicht Gesamtbot | offen | — | teilweise (except:continue) |
| 17 | Rollover-Verdacht sperrt Setup | offen | — | nicht implementiert (C4) |
| 18 | Neustart stellt offene Trades wieder her | offen | — | teilweise |
| 19 | Gleiche Linie nicht erneut gehandelt | offen | — | same_line() vorhanden |
| 20 | Stop+Ziel gleiche Kerze → Stop | offen | — | Code konservativ, Test fehlt |
| 21 | Varianten teilen Signal-Snapshot | offen | — | Varianten fehlen (D2) |
| 22 | Parameteränderung → neue Versions-ID | offen | — | nicht implementiert |

## Telegram-Ausgabeschicht — Increment 1 (notify/) — 15.07.2026
Ausgeführt: `venv/python -m pytest tests/test_notify.py` → **15 passed**. Mock-Transport, keine echten Nachrichten.
| Spec-Test | Inhalt | Status |
|---|---|---|
| 1/2 | Pro.1-Meldung nur an Pro.1, Pro.8 nur an Pro.8 (+ alle 8 disjunkt) | pass |
| 3 | Vergleichsbericht → Vergleichsgruppe | pass |
| 4 | Systemfehler → Systemgruppe | pass |
| 17 | Fehlende Systemgruppe → Fallback Vergleichsgruppe | pass |
| 18 | Fehlende Varianten-Chat-ID → Warnung, KEIN Fallback in andere Gruppe | pass |
| 5 | Fehlende aktive Varianten-Chat-ID → klare Konfig-Warnung | pass |
| 14/25 | Token/ID nicht in Logs (redact, auch in URL) | pass |
| 29 | Signalmeldung enthält „Paper-Trading – keine echte Order" | pass |
| — | AGGREGATE_ONLY (FILTER_REJECTED) nicht einzeln geroutet; MockTransport zeichnet auf | pass |
## Telegram — Increment 2 (Queue) + Increment 3 (Terminierung/Befehle/Dispatcher) — 15.07.2026
Ausgeführt: `venv/python -m pytest tests/` → **31 passed** (15 + 7 + 9). Alles Mock, keine echten Nachrichten.
| Spec-Test | Inhalt | Status |
|---|---|---|
| 7 | Fehlgeschlagene Meldung → persistente Warteschlange | pass |
| 8/19 | Idempotenz: gleicher Key höchstens einmal (auch nach Sent) | pass |
| 27 | Retry/Backoff eskaliert → FAILED_PERMANENT + Zustellbericht | pass |
| 13 | Neustart stellt Queue/PENDING wieder her | pass |
| 26 | Geordnete Nachlieferung (created_at) | pass |
| 15/16 | Zustellfehler wirft nicht durch (kein Zyklus-Crash) | pass |
| 22 | Zeitraum in Europe/Berlin bestimmt, als UTC gespeichert | pass |
| 23 | DST-Wechsel → eindeutige Perioden, kein Doppel/Fehlen | pass |
| 9 | Bericht je (scope,type,period,version) nur einmal | pass |
| 21 | Rollierend-30 ≠ Kalendermonat (Label) | pass |
| 10 | Unautorisierter Nutzer ignoriert | pass |
| 24 | Unbekannter Befehl → keine Codeausführung | pass |
| 20/30 | Gleiche parent_signal_id → je Variante eigene Gruppe | pass |
| — | Fehlende Varianten-Chat-ID → Warnung, keine Fehlleitung (Dispatcher) | pass |
Noch offen (brauchen die Engine/Live): reale Berichts-PDF-Inhalte, RealTransport im Loop, echte Chat-IDs,
manueller Integrationstest mit Test-Gruppen (Spec-Schritt 14), Live-Tests 11/12/28.
