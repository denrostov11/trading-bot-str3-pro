# CHANGELOG.md — Str.3 Pro

Format je Eintrag: Datum/Zeit · Beschreibung · Begründung · betroffene Dateien · alte→neue Parameter ·
Strategieversion · Migration · Tests · Versionskennung.

## 2026-07-15 — Phase A/B (Audit & bereinigte Spezifikation)
- Beschreibung: Vollaudit des Bestands (scan_100.py, watchlist.py, alert_bot.py) + bereinigte Spezifikation.
- Begründung: Master-Prompt „Str.3 Pro" — Aufbau eines auditierten Zwei-Monats-Paper-Tests.
- Betroffene Dateien: NUR neue Doku (AUDIT_REPORT.md, SPEC_CLEANED.md, VARIANT_MATRIX.csv, OPEN_QUESTIONS.md,
  DECISIONS.md, DATA_QUALITY.md, CHANGELOG.md, TEST_RESULTS.md, RUNBOOK.md, SYMBOL_STATUS.csv). KEIN Strategie-Code geändert.
- Parameter: keine geändert.
- Strategieversion: unverändert (Str.3 Pro.1, Bot gestoppt).
- Tests: noch keine (Phase G ausstehend).
- Versionskennung: Audit v0 (vor Freigabe).

## 2026-07-15 — Alle 13 offenen Entscheidungen bestätigt
- Beschreibung: Nutzer hat alle Punkte aus OPEN_QUESTIONS.md bestätigt („alles bestätigen").
- Auswirkung: verbindliche Werte in DECISIONS.md #1–#13; SPEC_CLEANED.md und VARIANT_MATRIX.csv eingearbeitet.
- Betroffene Dateien: DECISIONS.md, OPEN_QUESTIONS.md, SPEC_CLEANED.md (nur Doku; kein Strategie-Code).
- Nächster Blocker für produktive Aktivierung: bestandene Testsuite (Phase G, 22 QS-Fälle).
- Versionskennung: Spec v1 (freigegeben, noch nicht implementiert).

## 2026-07-15 — Prompt 2 (Zusatzpräzisierungen + Architektur-Folgeauftrag)
- Beschreibung: Verbindliche Präzisierungen mit Vorrang eingearbeitet; Architektur-Audit erstellt.
- Governance-Umkehr ggü. Block-Bestätigung: Apex-Kalendergrenze, Stop-ATR-Grenzen, S/R-Definition,
  Prozent-/Telegram-Reporting → zurück auf USER_DECISION_REQUIRED/DIAGNOSTIC_ONLY/NOT_CONFIGURED.
- Neue verbindliche Betriebsregeln: variantengetrennte Zustände, parent_signal_id, gemeinsamer Snapshot,
  Berichtsrhythmen (rollierend-30 ≠ Kalendermonat), Pro.7 diagnostisch, Pro.8 not_configured.
- Neue Dateien: ARCHITECTURE_PROPOSAL.md, DATA_FLOW.md, MIGRATION_PLAN.md, TEST_PLAN.md, RISK_REGISTER.md;
  AUDIT_REPORT.md (Abschnitte F/G), OPEN_QUESTIONS.md/DECISIONS.md/SPEC_CLEANED.md/VARIANT_MATRIX.csv aktualisiert.
- Betroffener Produktionscode: KEINER geändert. Warte auf ausdrückliche Freigabe.
- Versionskennung: Architektur-Audit v0 (vor Freigabe).

## 2026-07-15 — Testbetriebsmodus B + Telegram-Mehrkanal-Analyse
- Modus B bestätigt (autonomes Paper-Trading, Per-Trade-Info ohne Zustimmung) → DECISIONS.md/SPEC_CLEANED.md.
- Telegram-Mehrkanal-Spezifikation eingelesen (ergänzt Master-Prompt, ersetzt keine Strategie-/Datenregel).
- Analyse geliefert (KEIN Code): TELEGRAM_ARCHITECTURE.md (Audit, Zielarchitektur, Routing-Matrix,
  Konfig-/Queue-/Idempotenz-/Sicherheitsmodell, Testplan, Migrationsplan) + TELEGRAM_SETUP.md (Entwurf).
- Verbindlich übernommen: Telegram = reine Ausgabeschicht, lokale DB verbindliche Quelle; getrennte
  Varianten-Zustände; gemeinsamer Snapshot + parent_signal_id; rollierend-30 ≠ Kalendermonat.
- KRITISCH-Fund: Exception-Log kann Token-URL leaken (T1) → redact.py in Zielarchitektur.
- Betroffener Produktionscode: KEINER geändert (Analyse-Phase). Warte auf ausdrückliche Freigabe.

## 2026-07-15 — Telegram FREIGEGEBEN, Bau Increment 1 (entkoppelt)
- Nutzer: „ich gebe es frei und telegram soll jetzt gebaut werden."
- Ansatz: Telegram als isolierte, testbare Ausgabeschicht gebaut (Spec-Reihenfolge 1–3,6 + redact),
  NICHT an die noch nicht existierende Strategie-Engine verdrahtet (sonst Wegwerf-Code). Kein echter Versand.
- Neu (reiner Neucode, kein Eingriff in bestehende Produktion): `Prototyp/notify/` (__init__, redact,
  config, transport[+MockTransport], messages[16 Typen], router) + `Prototyp/tests/test_notify.py` (15 Tests,
  alle grün) + `Prototyp/.env.example` (nur Platzhalter). pytest ins venv installiert.
- Behebt vorab KRITISCH T1: redact() verhindert Token-Leak über Exception-URL.
- Bestehender Bot bleibt gestoppt/unberührt. Nächste Increments: persistente Queue+Idempotenz+Retry,
  Berichtszustellung+Terminierung, autorisierte Befehle, dann Live-Verdrahtung nach Engine-Bau.
- Versionskennung: notify v0.1 (entkoppelt, nicht aktiviert).

## 2026-07-15 — Telegram Increment 2+3: Teil A funktional komplett (entkoppelt)
- Increment 2: `notify/queue.py` (persistente, idempotente Queue; Retry/Backoff; Recovery; Zustellbericht)
  + tests/test_notify_queue.py (7 Tests).
- Increment 3: `notify/scheduling.py` (Perioden Europe/Berlin→UTC, Einmal-Versand, DST-sicher, rollierend-30
  ≠ Kalendermonat), `notify/commands.py` (Allowlist, nur lesend, kein eval/exec/Shell), `notify/dispatcher.py`
  (Router→Queue, keine Fehlleitung) + tests/test_notify_sched_cmd.py (9 Tests).
- Gesamt: 31 notify-Tests grün (Mock-Transport, kein echter Versand). Nutzer-Reihenfolge: erst A fertig, dann B.
- Betroffener Bestandscode: KEINER. Bestehender Bot bleibt gestoppt. Versionskennung: notify v0.3 (A komplett, entkoppelt).
- Offen für Live: reale Berichts-PDFs, RealTransport im Loop, echte Chat-IDs, Integrationstest mit Test-Gruppen.

## Datumskorrektur
- Hinweis: Die Audit-/Telegram-Arbeit (Phase A/B + Telegram Teil A) wurde tatsächlich am **2026-07-24**
  ausgeführt. Die „15.07.2026"-Stempel in vorherigen Einträgen sind ein Übertrag aus der früheren
  Projekt-Zeitleiste (Bot-Aktivität 10.–15.07.). Ab hier gilt das reale Datum 2026-07-24.
- 2026-07-24: Teil A abgeschlossen (31 Tests grün); Voll-Backup TradingBot_Backup_2026-07-24_1757.zip
  (lokal + OneDrive) als Startpunkt für Phase B (S0). Nächster Schritt: Phase B Datenzugriffsschicht (S1/S2).

## 2026-07-24 — Phase B Increment S1/S2: Datenzugriffsschicht (engine/)
- Neu (reiner Neucode, Bot unberührt): `Prototyp/engine/` — dataaccess (Retry/Backoff/Timeout/Batch,
  injizierbarer Downloader), cache (additiver CSV-Cache: Merge/Dedup/Monotonie, nie kürzen),
  aggregate_4h (Anker-Gitter + Session-Filter + completeness_ratio + is_final; final_only()).
- Behebt KRITISCH: A1 (unvollständige letzte 4h-Kerze → is_final=False, nicht signalfähig),
  A2 (Aggregation mit Anker/Session statt Mitternacht-resample), C1 (Cache), C2 (Retry).
- Tests: `tests/test_engine_data.py` (10) → gesamt **41 Tests grün** (31 notify + 10 engine).
- ABWEICHUNG von DECISION #13: Cache-Format vorerst CSV statt Parquet (pyarrow nicht installiert);
  Interface storage-agnostisch, Umstellung auf Parquet jederzeit möglich.
- OFFEN (nächste B-Etappen): S1 Charakterisierungstests der bestehenden Erkennung; korrekte Session-
  Kalender je Börse (aktuell 24/7 exakt, Session-Filter-Hook vorhanden); S4 Datenqualität/Rollover;
  S5 Baseline-Engine+Snapshot (Kausalfixes A3/B1/B2/B3); S6 Ledger; S7 Varianten; S8 Tracker.
- Versionskennung: engine v0.1 (Datenschicht, entkoppelt, nicht verdrahtet).

## 2026-07-24 — Phase B Increment S4/S5: Datenqualität + Baseline-Engine (engine/)
- Neu: `engine/quality.py` (Volumen-Validierung inkl. FX/Index/Einheitenwechsel; Rollover-Erkennung
  Gap+TrueRange nur für Futures; Duplikate/Monotonie; near_rollover) → behebt C4/C5.
- Neu: `engine/baseline.py` — unveränderlicher **Snapshot (frozen)** + deterministische **parent_signal_id**;
  Kausalfixes AKTIV: A3 (Trigger nur auf letzter finaler Kerze, Einstieg=Open-next-bar), B3 (Stop-Seiten-Guard
  → REJECTED_STOP), C4 (REJECTED_DATA_QUALITY nahe Rollover/schlechter Qualität). DIAGNOSTIC (nicht aktiv,
  weil NUTZERENTSCHEIDUNG offen): B1/B2 2R-Gate + „nächste Zone nicht überspringen" (would_reject_rr),
  ATR-Stop-Grenzen. config_hash/code_version im Snapshot.
- Tests: `tests/test_engine_baseline.py` (13) → gesamt **54 grün** (31 notify + 10 data + 13 baseline/quality).
- Governance eingehalten: offene Regeln (S/R-Definition, ATR-Grenzen, Apex-Kalender) NICHT produktiv
  aktiviert, nur diagnostisch berechnet.
- OFFEN (nächste B-Etappen): S6 Kandidaten-Ledger (auch REJECTED_*/DIAGNOSTIC persistieren), S7 Varianten-
  Engine (Pro.1–8/BE, variantengetrennte Zustände, gemeinsamer Snapshot), S8 Tracker (Open-next-bar,
  brutto+netto, MFE/MAE, Intrabar), S1 Charakterisierungstests der Erkennung auf Realdaten, Session-Kalender.
- Versionskennung: engine v0.2 (Baseline-Kausalkern, entkoppelt, nicht verdrahtet).

## 2026-07-24 — Phase B Increment S6/S7: Ledger + Varianten-Engine (engine/)
- Neu: `engine/ledger.py` (protokolliert JEDEN Kandidaten inkl. REJECTED_*/NOT_EVALUABLE/DIAGNOSTIC +
  jede Varianten-Bewertung; parent_signal_id/candidate_id/variant_evaluation_id; Neustart-fest) → behebt **D1**.
- Neu: `engine/variants.py` (Pro.1–8 bewerten den GEMEINSAMEN Snapshot; Zusatzfilter EMA200/RVOL/ATR-Regime/
  Kombi/Breakout/Trendqualität; Status PASS/FAIL/NOT_EVALUABLE/DIAGNOSTIC/NOT_CONFIGURED; Pro.7 diagnostisch,
  Pro.8 not_configured; fehlende Features → NOT_EVALUABLE, nie still bestanden) → behebt **D2**.
- Neu: `engine/features.py` (EMA, RVOL20, ATR-Perzentil, Breakout-Kennzahlen, Regressions-R², ADX, Choppiness).
- Neu: `engine/varstate.py` (variantengetrennte Zustände Präz. 2: je Variante eigene offene Trades/Cooldown/
  gehandelte Linien; Pro.2-Trade blockiert Pro.3 nicht; 1 Trade/Instrument + 24h-Cooldown + Linie-einmal PRO Variante).
- Tests: `tests/test_engine_variants.py` (13) → gesamt **67 grün** (31 notify + 36 engine).
- Damit sind alle 11 KRITISCH-Punkte technisch adressiert (A1,A2,A3,B1/B2 diagnostisch,B3,C1,C2,C4,C5,D1,D2).
  Governance: offene Regeln (S/R-Def, ATR-Grenzen, Apex-Kalender, 2R-Gate) weiterhin nur DIAGNOSTIC.
- OFFEN (nächste Etappen): S8 Tracker (Open-next-bar-Fill, brutto+netto, MFE/MAE, Intrabar, BE-0..4, Recovery),
  S9 Reporting-PDFs + Feature-Verdrahtung, S1 Charakterisierungstests auf Realdaten, Session-Kalender, dann
  Live-Verdrahtung Telegram + echte Chat-IDs.
- Versionskennung: engine v0.3 (Kandidaten-Ledger + Varianten + variantengetrennte Zustände, entkoppelt).

## 2026-07-24 — Phase B Increment S8: Paper-Trade-Tracker (engine/tracker.py)
- Neu: `engine/tracker.py` — simulate_trade (Fill = Open der nächsten Kerze + 0,05 ATR Slippage;
  brutto UND netto mit Klassenkosten FX/Index/Futures/Aktien/Krypto; MFE_R/MAE_R; Intrabar Stop-zuerst +
  AMBIGUOUS_INTRABAR; Break-even-Modi BE-0/BE-1/BE-2/BE-3/BE-4; R immer auf Original-Risiko) +
  PaperTrade/PaperTradeStore (neustart-fest, verbindliche lokale Quelle).
- Tests: `tests/test_engine_tracker.py` (9) → gesamt **76 grün** (31 notify + 45 engine).
- Behebt D3/D4/D8 (vollständiger Trade-Datensatz, Netto-Buchung, Recovery). BE ändert R-Bezug nicht.
- OFFEN (nächste/letzte Etappen vor Live): S9 Orchestrierung + Feature-Verdrahtung an Realdaten
  (yfinance→cache→aggregate→baseline→variants→ledger→tracker) + Reporting-PDFs; S1 Charakterisierungstests
  der scan_100-Erkennung auf Realdaten; Session-Kalender je Börse; dann Live-Verdrahtung Telegram
  (RealTransport + echte Chat-IDs + Integrationstest) + unveränderliche Testkonfiguration → Zwei-Monats-Start.
- Versionskennung: engine v0.4 (Tracker, entkoppelt, nicht verdrahtet).

## 2026-07-25 — Phase B Increment S9 + S1: Orchestrierung, Zyklus, Berichte, Runner, Charakterisierung
- Nutzer: „lass uns alles fertig machen … hiermit bestätige ich alles was bis Prompt 3 folgt" → Freigabe
  zum Fertigbauen des Kerns.
- Neu: `engine/orchestrate.py` (fetch→cache→aggregate(final)→Erkennung[scan_100, injizierbar]→baseline→
  features→variants→ledger; ein Instrument komplett), `engine/instruments.py` (Universum + Assetklassen/
  Session-Anker; Krypto 24/7 exakt, Rest Näherung), `engine/cycle.py` (Trade-Lebenszyklus: öffnen/füllen/
  verfolgen/schließen, variantengetrennt), `engine/reporting.py` (R-Kennzahlen je Variante + Vergleich +
  Rankings + Stichprobenschutz MIN_CLOSED_TRADES_FOR_RANKING=30; Prozentkennzahlen NOT_CONFIGURED),
  `engine/run_paper.py` (lauffähiger Paper-Runner, Modus B, lokal, KEIN Telegram, KEINE echten Orders).
- S1 Charakterisierungstest: reales BTC-Fixture (1414 4h-Kerzen) + Golden-Output der scan_100-Erkennung
  eingefroren (`tests/fixtures/`, `tests/test_characterization.py`) → sichert künftige Umbauten ab.
- Tests: `test_engine_orchestrate.py`(3) + `test_engine_cycle_report.py`(5) + `test_characterization.py`(1)
  → gesamt **85 grün** (31 notify + 53 engine + 1 charakterisierung).
- **Echter Dry-Run** über 12 gemischte Realinstrumente: 0 Fehler, alle Downloads ok, End-to-End-Fluss
  bewiesen (aktuell 12× NO_TRIGGER — realistisch). Runtime-Artefakte in `Prototyp/paper_runtime/`-Muster.
- STATUS: Engine-Kern funktional KOMPLETT & getestet. Alle 11 KRITISCH-Punkte adressiert; Governance strikt
  (offene Regeln nur diagnostisch). NOCH EXTERN OFFEN (Prompt 3 / Nutzerinput): Prozent-/Reporting-Spez
  (dann PDF-Berichte + %-Kennzahlen), echte 10 Telegram-Chat-IDs + User-ID (Live-Telegram), unveränderliche
  Testkonfiguration (Start/Ende/Zeit/„zwei Monate"), Börsen-Sessionkalender-Verfeinerung.
- Versionskennung: engine v1.0 (Kern komplett, lokal lauffähig, nicht produktiv gestartet).

## 2026-07-25 — Prompt 3: Prozent-Implementierung (§9) + Senior-Review (§10) + Rollout-Prep (§11/§12)
- Nutzer: „ich gebe erstmal auch alles frei … führe alles in Prompt 3 durch."
- §9 (Code): Prozentschicht zentral in tracker+reporting (gross/net LONG/SHORT, sum_pos/neg absolut,
  net_profit_pct, Ø/Median/best/worst, compounded, %-Drawdown). **Zwei KRITISCH-Bugs behoben:**
  P1 doppelte Slippage (brutto jetzt aus entry_open, Kosten EINMAL), P2 Drawdown zeitgeordnet (closed_ts).
  Tests: test_engine_percent.py (5) + angepasste Reporting-Tests → **90 grün**.
- §10 (Review, kein Code): REVIEW_REPORT.md, CRITICAL_FINDINGS.md (2 KRITISCH behoben, 0 offen),
  TEST_GAPS.md, REMEDIATION_PLAN.md, GO_NO_GO_CHECKLIST.md.
- §11 (Prep): PRE_FLIGHT_CHECKLIST.md, STAGED_ROLLOUT_PLAN.md, OPERATIONS_RUNBOOK.md, BACKUP_RESTORE_TEST.md.
  STUFE-1-Probelauf 24 Symbole: 0 Fehler, 213 s. Backup-Integrität geprüft (.env ausgeschlossen, 299 Dateien).
- §12: FINAL_GO_NO_GO.md = **NO-GO (kontrolliert)** — Start NICHT ausgeführt. Keine offenen KRITISCH-Befunde;
  7 zwingende Punkte offen (Testkonfig, Sizing/Kapital, Kontosim, Session-Kalender, Reporting-PDF,
  Telegram-Entscheidung, Stufenfreigabe). KEIN PAPER_TEST_STARTED.
- Versionskennung: engine v1.1 (Prozent + Fixes; startbereit, aber vor finalem Tor gehalten).

## 2026-07-25 — Prompt-3-Startentscheidungen + Reporting-Ausgabe
- Nutzerentscheidungen (DECISIONS.md): Start 00:00 Europe/Berlin am Fertigstellungstag; „zwei Monate"=2
  Kalendermonate (Default); KEIN Kapitalkonto → reine %-Auswertung; Session-Näherung akzeptiert;
  Reporting-PDF+Kurztext gewünscht; Telegram LIVE mit echten Chat-IDs; Stufenbetrieb erklärt.
- Neu: `engine/reporting_pdf.py` (short_text + build_variant_pdf + build_comparison_pdf, reine %-Auswertung,
  feste Kennzahlreihenfolge) + `tests/test_reporting_pdf.py` (2) → **92 Tests grün**.
- Wegfall Blocker: Sizing/Kapital + Kontosimulation entfallen (reine %-Auswertung).
- Verbleibend vor Start: Telegram-Live-Verdrahtung (braucht 10 Chat-IDs + User-ID vom Nutzer),
  Report-Zustellung anbinden, unveränderliche Testkonfiguration, STUFE 1→2 durchlaufen.
- Versionskennung: engine v1.2 (Reporting-Ausgabe; %-only).

## 2026-07-25 — Telegram Live-Setup + Integrationstest
- Nutzer hat 10 Gruppen angelegt + Bot @Str3_trading_alerts_bot aufgenommen. Chat-IDs + User-ID via
  `telegram_discover.py` ausgelesen; in `.env` eingetragen (STR3_PRO1..8/COMPARISON/SYSTEM_CHAT_ID,
  TELEGRAM_AUTHORIZED_USER_IDS=<DEINE_TELEGRAM_USER_ID>). .env um Mehrkanal-Keys ergänzt (Token unangetastet).
- Neu: `notify/live.py` (build_from_env + connectivity_test): baut TelegramConfig/RealTransport/Router aus .env.
- Konfig-Validierung: enabled, 8/8 Varianten-Gruppen + Vergleich + System, autorisierter Nutzer, 0 Warnungen.
- **Integrationstest mit echten Gruppen: 10/10 Nachrichten zugestellt** (deterministisches Routing bestätigt).
- Zuordnung vom Nutzer bestätigt („es passt alles").
- Live-Verdrahtung angebunden: `notify/live.py` TelegramService (Queue+Dispatcher+RealTransport, idempotent,
  retry, neustart-fest) + trade_opened/trade_closed/system/deliver_reports. cycle.run_cycle liefert neu
  geöffnete/geschlossene Trades; run_paper.run_once(telegram=True) sendet Trade-Alerts + System-Monitor.
- Live bestätigt: Zyklus-Monitor → System-Gruppe; Berichtszustellung (Kurztext + PDF) → 8 Varianten-Gruppen
  + Vergleich (OK, Queue leer). 94 Tests weiterhin grün. Secrets nur in .env.
- Damit Telegram-Live FERTIG. Nächster Schritt: STUFE 1 (kontinuierlicher Lauf 2–3 Tage).

## 2026-07-27 — STUFE 1 scharfgeschaltet (Option A, Nutzer)
- Nutzer: Option A (Stufen zuerst), STUFE 1 offizieller Start heute 27.07. 21:00 Europe/Berlin, Gesamttest 2 Monate.
- Neu: `engine/run_loop.py` — Dauer-Loop: wartet bis offiziellem Start, schreibt unveränderliches
  START_MANIFEST (Stufe/Start/Ende/code_version/config_hash/Universum/„keine echten Orders"/„Telegram nur
  Ausgabe"), sendet Startmeldung an System+Vergleich, dann Zyklus je Stunde (run_once telegram=True),
  Heartbeat alle 12h, robuste Fehlerbehandlung (Zyklusfehler stoppt Loop nie), kontrollierter Stopp via
  STOP-Datei, neustart-fest (Wiederaufnahme aus Manifest). System-Monitor im Zyklus nur bei Aktivität/Fehler.
- Start-/Stopp-Dateien: `STUFE1 starten.bat`, `STUFE1 stoppen.bat`.
- Testzyklus (--once, 24 Symbole): 0 Fehler, **2 frische Trigger erkannt (XRP-USD SHORT, GBP/USD SHORT),
  7 Paper-Trades über Varianten eröffnet** (Pro.1/3/4/7 bzw. Pro.1/4/7) — erste echte Erkennungs-Bestätigung.
  Danach STUFE-1-Ablage für sauberen 21:00-Start zurückgesetzt.
- Prozess läuft (pythonw, detached), wartet auf 21:00. STUFE 1 = 2–3 Tage, DANN STUFE 2, dann Haupttest.
  Dies ist NICHT der Zwei-Monats-Start; kein PAPER_TEST_STARTED (das kommt nach Stufen + GO/NO-GO).
