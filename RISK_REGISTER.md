# RISK_REGISTER.md — Str.3 Pro

> Stand: 15.07.2026. Schweregrad: KRITISCH (Ergebnis verfälschend) / HOCH / MITTEL / NIEDRIG.
> Jeder Eintrag: Risiko · Quelle · Auswirkung · Gegenmaßnahme · Reststatus.

| ID | Risiko | Quelle | Schwere | Gegenmaßnahme | Status |
|----|--------|--------|---------|---------------|--------|
| R1 | Analyse unvollständiger letzter 4h-Kerze → Phantomsignale | A1 (fetch_4h) | KRITISCH | is_final/completeness, Kerze erst bei Abschluss | offen (Migration S3) |
| R2 | 4h-Aggregation ohne TZ/Session/DST → falsche Kerzen | A2 | KRITISCH | aggregate_4h je Assetklasse | offen (S3) |
| R3 | Rückdatierter Einstieg / Look-ahead im Tracker | A3 | KRITISCH | Einstieg = Open next bar; kein Bruch >0 Kerzen alt eröffnen | offen (S5) |
| R4 | Sub-2R-Trades + Überspringen näherer S/R-Zonen | B1/B2 | KRITISCH | REJECTED_RR; nächste relevante Zone verbindlich | offen (S5), S/R-Def USER_DECISION |
| R5 | Kein Cache/Retry → Datenverlust & Zyklusausfälle | C1/C2 | KRITISCH | data.access + data.cache | offen (S2) |
| R6 | Kein Rollover-/Qualitätscheck → Futures-Verzerrung | C4 | KRITISCH | data.quality, REJECTED_DATA_QUALITY | offen (S4) |
| R7 | Volumen unvalidiert (FX/Index=0) → Fehlfilter Pro.3/5 | C5 | KRITISCH (Vol-Varianten) | Volumen-Validierung, VOLUME_NOT_AVAILABLE | offen (S4) |
| R8 | Abgelehnte Setups nicht protokolliert → kein Variantenvergleich | D1 | KRITISCH | candidate-Ledger | offen (S6) |
| R9 | Keine Varianten-Engine (nur Pro.1) | D2 | KRITISCH | variants/ + gemeinsamer Snapshot | offen (S7) |
| R10 | 0 automatisierte Tests → keine Regressionssicherung | D6 | KRITISCH | Testsuite vor Aktivierung | offen (S1) |
| R11 | Duplizierte Erkennungslogik (trendline_prototype.py veraltet) | Architektur | HOCH | eine kanonische Quelle, Altcode kennzeichnen | offen (S10) |
| R12 | Stille Regel-Aktivierung offener Grenzwerte | Governance | HOCH | Präz. 13: NOT_CONFIGURED/DIAGNOSTIC/USER_DECISION | kontrolliert |
| R13 | Umbau ändert Verhalten unbeabsichtigt | Migration | HOCH | Charakterisierungstests (Golden-Output) vor Entfernen | mitigiert (S1) |
| R14 | Prozent-/Telegram-Definition ohne Spez erfunden | Präz. 5/6 | MITTEL | NOT_CONFIGURED bis separate Spez | kontrolliert |
| R15 | Neustart-Inkonsistenz variantengetrennter Zustände | D8/Präz. 2 | MITTEL | Recovery-Check beim Start | offen (S8) |
| R16 | ATR bfill() Mini-Look-ahead (erste 14 Kerzen) | A5 | NIEDRIG | erste 14 Kerzen nicht signalfähig | offen (S5) |
| R17 | Sicherheit: Token/Orders | Sicherheitsabschnitt | HOCH | .env-only, nie ausgeben, keine Broker-Order, nur Besitzer-Chat-ID | eingehalten |
| R18 | „Zwei Monate" mehrdeutig / Auto-Start | Präz. 12 | MITTEL | unveränderliche Testkonfig, kein Auto-Start | offen (S11) |

## Telegram-Mehrkanal (aus Telegram-Spez)
| ID | Risiko | Quelle | Schwere | Gegenmaßnahme | Status |
|----|--------|--------|---------|---------------|--------|
| T1 | Token-Leak über Exception-URL im Log | alert_bot print(e) | KRITISCH | redact.py maskiert Token/URL/IDs; keine Secrets in Logs/Backups | offen (Telegram S1/S8) |
| T2 | Fehlleitung an falsche Variantengruppe | Routing | KRITISCH | deterministisches Routing; fehlende Varianten-Chat-ID → Warnung, KEIN Fallback | offen |
| T3 | Nachrichtenverlust/Duplikate bei Ausfall | aktuelle String-Queue | HOCH | persistente Queue + message_idempotency_key + Retry/Backoff + Recovery | offen |
| T4 | Telegram-Fehler verändert Trade-Zustand | Kopplung | KRITISCH | Telegram nur Ausgabeschicht; DB verbindlich; Fehler ändert nie Trades/stoppt keinen Scan | Designprinzip |
| T5 | Unautorisierter Befehlszugriff | nur Chat-ID-Check | HOCH | User-ID-Allowlist getrennt validieren; nur lesende /commands; kein eval/exec/Shell | offen |
| T6 | Doppelter Berichtsversand / DST-Fehler | Terminierung | MITTEL | Einmal-Versand je (typ, zeitraum, version); Europe/Berlin→UTC; DST-Test | offen |
| T7 | „rollierend-30" als Kalendermonat missverstanden | Benennung | NIEDRIG | strikte Kennzeichnung; optionaler CALENDAR_MONTH_REPORT separat | kontrolliert |

## Prozent-/Reporting-Audit (§9, 2026-07-25)
| ID | Risiko | Quelle | Schwere | Gegenmaßnahme | Status |
|----|--------|--------|---------|---------------|--------|
| P1 | Doppelte Einstiegs-Slippage: entry_price enthält Slippage UND cost_price zieht 2*slip erneut ab; brutto_r ist kein echtes Brutto | tracker.simulate_trade | KRITISCH | entry_open ungeslippt speichern; brutto aus entry_open; Kosten (fees+slippage beide Seiten) genau EINMAL im netto | offen (Migration) |
| P2 | Max-Drawdown nicht aus zeitgeordneter Equity (Trade-/Ledger-Reihenfolge statt Exit-Zeit) | reporting._max_drawdown_r | KRITISCH | Equity nach closed_ts sortieren, dann Drawdown (R und %) | offen |
| P3 | sum_negative_return_pct-Konvention (negativ vs. absolut) uneinheitlich | reporting | MITTEL | absolut ausweisen; net_profit_pct = pos − neg(abs) | offen (Bestätigung) |
| P4 | Portfoliorendite ≠ Σ Einzeltrade-% könnte vermischt werden | Reporting-Design | MITTEL | 4 strikt getrennte, unterschiedlich benannte Kennzahlen | Designregel |
| P5 | Offene Trades nicht als unrealisiert getrennt | reporting | MITTEL | offene Trades separat, kein Einfluss auf realisierte Kennzahlen | offen |

## Nicht prüfbar (NICHT_PRÜFBAR)
- Reale Korrektheit der Börsen-Sessionkalender ohne Referenzquelle.
- Yahoo-Volumenqualität je Instrument (nur empirisch über Laufzeit).
- Reale Intraday-Tiefe je Symbol (erst nach Cache-Aufbau messbar).
