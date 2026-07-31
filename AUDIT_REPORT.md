# AUDIT_REPORT.md — Str.3 Pro · Phase A (Audit)

> Stand: 15.07.2026 · Auditor: Claude (Opus 4.8) · Modus: reines Paper-Trading, KEINE Codeänderung in dieser Phase.
> Grundlage: tatsächlich gelesene Dateien — `scan_100.py` (vollständig), `watchlist.py` (vollständig),
> `alert_bot.py` (kausaler Kernpfad vollständig: fetch_4h, atr, pivots, find_lines, is_aplus, pick_safety,
> converges, sr_levels, stop_and_target, open_paper_trade+same_line/sig_core, check_open_trades,
> check_break_even, analyze, cycle, main), `state.json`, `trades.json`, `bot_config.json`, Datei-Inventar.
> NICHT zeilenweise auditiert (Priorität 4–5): `build_report`-Rumpf, `run_backup`, `composite_chart`,
> `demo_*`/`resend_btc`/`telegram_setup`/`trendline_prototype` (Hilfs-/Altskripte).

Legende Status: **korrekt** / **teilweise** / **falsch** / **nicht implementiert** / **nicht prüfbar**
Marker: KRITISCH = kausaler/datenintegritäts-Fehler mit Ergebnisverfälschung.

## A. Kausalität & Look-ahead

| ID | Soll-Regel | Datei:Funktion | Ist-Verhalten | Status | Risiko | Korrektur |
|----|-----------|----------------|---------------|--------|--------|-----------|
| A1 | Nur vollständig abgeschlossene 4h-Kerzen analysieren | scan_100.py:83 fetch_4h | `resample("4h").dropna()` behält die laufende, unfertige letzte Kerze (≥1h Daten reichen) | **falsch** KRITISCH | Trigger/Tap/Bruch auf Teilkerze → Phantomsignale | letzte Kerze nur wenn `is_final` (4/4 1h-Bars bzw. Sessionende); `completeness_ratio` speichern |
| A2 | 4h-Aggregation mit Börsenzeitzone, Session, DST, Ankerzeit | scan_100.py:92 | `resample("4h")` mit Default-Origin = Mitternacht UTC; keine TZ/Session/DST | **falsch** KRITISCH | Falsch geschnittene Kerzen → falsche OHLC, Taps, Brüche | je Instrument TZ+Sessionkalender+Anker (siehe SPEC_CLEANED §4h) |
| A3 | Kein rückdatierter Einstieg; Trigger nur beim Erst-Abschluss der Kerze | alert_bot.py:626 (TRIGGER_MAX_AGE=3), open_paper_trade opened_ts=Time[breaking_bar] | Bruch bis 3 Kerzen alt wird als Trigger eröffnet; opened_ts = Zeit der (evtl. alten) Bruchkerze; check_open_trades wertet danach bereits vergangene Kerzen aus | **falsch** KRITISCH | Look-ahead: „Ergebnis" bereits gelaufener Kerzen fließt ein | Trigger nur wenn Bruchkerze == gerade erst abgeschlossen; Einstieg in ZUKUNFT (nächste Kerze), nie Vergangenheit |
| A4 | Einstieg = Open der nächsten handelbaren Kerze (neuer Prompt) | stop_and_target:164 | Einstieg = `Close[breaking_bar]` (Signal-Close, idealisiert, ohne Slippage/Gebühr) | **teilweise** | Optimistischer Fill; widerspricht Ausführungsmodell | NUTZERENTSCHEIDUNG #1 (Close vs. Open-next) |
| A5 | ATR ohne Look-ahead | scan_100.py:102 atr | `.bfill()` füllt erste NaNs mit späteren Werten | **teilweise** | minimaler Look-ahead in ersten 14 Kerzen (weit in Vergangenheit) | erste 14 Kerzen nicht signalfähig; bfill dokumentieren/entfernen |
| A6 | Pivot erst nach 3 rechten Kerzen bestätigt | scan_100.py:104 pivots | `range(k, len-k)`, `min/max` über i-k..i+k → letzte 3 Kerzen nie Pivot | **korrekt** | — | beibehalten; als Test fixieren (QS #1) |

## B. Strategie-/Linienregeln

| ID | Soll-Regel | Datei:Funktion | Ist-Verhalten | Status | Risiko | Korrektur |
|----|-----------|----------------|---------------|--------|--------|-----------|
| B1 | Kein Trade wenn initiales R:R < 2,0 → REJECTED_RR | alert_bot.py:176,182 stop_and_target | Fallback `cands[-1]` liefert Ziel auch bei rr<2; Trade wird eröffnet, nur ⚠️ im Alert | **falsch** KRITISCH | Sub-2R-Trades verfälschen Bilanz | <2R ⇒ kein Trade, als REJECTED_RR protokollieren |
| B2 | Nächstgelegene relevante S/R-Zone darf nicht übersprungen werden | alert_bot.py:171-182 | Schleife sucht ERSTE Zone mit rr≥2 und überspringt nähere <2R-Zonen | **falsch** KRITISCH | Ziel „hinter" echtem Hindernis → unrealistisch | Ziel = nächste relevante Zone; wenn deren rr<2 ⇒ REJECTED_RR |
| B3 | Stop bei LONG unter, bei SHORT über Einstieg | stop_and_target:165 | `stop=safety.value_at(bb+4)` ohne Seiten-Guard | **teilweise** | i. d. R. korrekt durch Konstruktion, aber kein Schutz bei Apex-Überschuss | Guard: sonst REJECTED_STOP |
| B4 | Stop-Risiko > 0 UND in plausiblem ATR-Bereich | stop_and_target:168 | nur `risk<=0 → None`; kein ATR-Bereich | **teilweise** | Mikro-/Mega-Stops möglich | Bereich definieren (NUTZERENTSCHEIDUNG #8) |
| B5 | Action & Safety müssen konvergieren; Apex begrenzt | scan_100.py converges, MAX_APEX_BARS=180 | Gap-Schrumpfung + Apex ≤180 Kerzen geprüft | **korrekt** | — | Apex zusätzlich in Kalendertagen prüfen (NUTZERENTSCHEIDUNG #7) |
| B6 | Bruchkerze zählt nicht als Tap | scan_100.py:136-137 | Bruch-Check vor Tap-Check + `break` → Bruchkerze kein Tap | **korrekt** | Toleranzgrenze (== 0,25/0,15 ATR) nicht deterministisch getestet | QS #3/#4 ergänzen |
| B7 | Mindestdauer ≥ 21 Kalendertage (primär) | scan_100.py:148 MIN_DURATION=90 Bars | Prüfung über Bar-Anzahl, nicht Kalendertage | **teilweise** | bei Datenlücken weicht 90 Bars von 21 Tagen ab | zusätzlich reale Zeitstempel prüfen |
| B8 | ≥6 Kerzen zwischen Taps | scan_100.py:138,143 MIN_SPACING=6 | erzwungen | **korrekt** | — | als Test fixieren |
| B9 | Safety intakt (keine Kerzen-Durchkreuzung) | scan_100.py:189 | gebrochene Gegenlinien verworfen | **korrekt** | — | — |

## C. Datenquelle & Robustheit

| ID | Soll-Regel | Datei:Funktion | Ist-Verhalten | Status | Risiko | Korrektur |
|----|-----------|----------------|---------------|--------|--------|-----------|
| C1 | Lokaler Cache, Merge, Dedup, keine Historie-Löschung | — | KEIN Cache; fetch_4h lädt jedes Mal frisch, keine Persistenz, keine Dedup/Monotonie-Prüfung | **nicht implementiert** KRITISCH | Intraday-Historie geht verloren; 15m/1h nur ~60/730 Tage bei Yahoo | Datenzugriffsschicht mit Parquet-Cache + Merge |
| C2 | Retry, Backoff, Timeout, Fehlerprotokoll | scan_100.py:84-89 | `try/except: continue`, `yf.download` ohne Timeout/Retry | **nicht implementiert** KRITISCH | Zyklus-Ausfälle, stille Datenlücken | Wrapper mit Retry/Backoff/Timeout |
| C3 | Batch-Begrenzung großer Symbolmengen | main-Loop | 95 sequentielle Einzel-Downloads | **teilweise** | Rate-Limits, lange Zyklen | Batching |
| C4 | Rollover/Datenbruch erkennen (Gap, TR-Ausreißer), Setup sperren | — | keinerlei Rollover-/Qualitätsprüfung; Linien dürfen Sprünge überspannen | **nicht implementiert** KRITISCH | Futures-Verzerrungen | SUSPECTED_ROLLOVER + REJECTED_DATA_QUALITY |
| C5 | Volumen nur bei ≥95% gültig, kein Fake-FX-Volumen | scan_100.py:92 | Volume wird summiert, nie validiert; FX/Index=0 | **nicht implementiert** KRITISCH (für Pro.3/5) | Fehlfilter | Volumen-Validierung (VOLUME_NOT_AVAILABLE) |
| C6 | Keine still geschluckten Exceptions | mehrf. (copy_to_proto:253, tg_*:74,82, _anch:291, scan:88) | `except: pass/continue` ohne Log | **teilweise** | verborgene Fehler | strukturiertes Logging |

## D. Buchführung, Varianten, Betrieb

| ID | Soll-Regel | Datei:Funktion | Ist-Verhalten | Status | Risiko | Korrektur |
|----|-----------|----------------|---------------|--------|--------|-----------|
| D1 | Auch abgelehnte Setups protokollieren (REJECTED_*) | open_paper_trade | nur eröffnete/abgeschlossene Trades in trades.json; Ablehnungen fehlen | **nicht implementiert** KRITISCH | Variantenvergleich unmöglich | candidate-Log für ALLE geprüften Signale |
| D2 | Varianten-Engine Pro.1–8 + BE-0..4, getrennte IDs/Bilanzen, gemeinsamer Snapshot | — | nur Pro.1; keine Varianten | **nicht implementiert** KRITISCH | Kernauftrag offen | Varianten-Engine (Phase E) |
| D3 | Vollständiger paper_trade_datensatz (Snapshots, MFE/MAE, data_cutoff, config_hash, code_version) | open_paper_trade | minimale Felder; keine Snapshots/MFE/MAE/Hashes | **teilweise** | Nicht reproduzierbar | Datensatz erweitern |
| D4 | Netto-Ergebnis (Slippage+Gebühren) buchen | check_open_trades:399-403 | nur Brutto auf Idealpreisen | **nicht implementiert** | Ergebnis zu optimistisch | Kostenmodell je Assetklasse |
| D5 | Break-even R korrekt auf Original-Risiko | check_open_trades (stop_initial) | R bezieht sich auf stop_initial | **korrekt** (ungetestet) | — | QS ergänzen |
| D6 | Automatisierte Tests (22 Fälle) + synthetische Charts | — | 0 Tests vorhanden | **nicht implementiert** KRITISCH | keine Regressionssicherung | Testsuite (Phase G) |
| D7 | Persistente Notizdateien (10) | — | keine vorhanden (dieses Audit legt sie an) | **nicht implementiert** | kein persistentes Gedächtnis | angelegt in Phase A/B |
| D8 | Zustandswiederherstellung nach Neustart | trades.json/state.json/bot_config.json | persistieren; keine Konsistenzprüfung beim Start | **teilweise** | Inkonsistenzen unentdeckt | Recovery-Check + QS #18 |

## E. Nicht prüfbar (ohne zusätzliche Referenz/Zeit)
- Reale Korrektheit der Börsenzeitzonen/Sitzungskalender (keine Kalenderquelle im Projekt).
- Brauchbarkeit des Yahoo-Volumens je Instrument (nur empirisch über Laufzeit messbar).
- Tatsächliche Intraday-Tiefe je Symbol (Yahoo 1h ~730 T, 15m ~60 T) — muss gemessen und in SYMBOL_STATUS.csv geführt werden.
- Zeilengenaue Korrektheit von `build_report`/`run_backup`/`composite_chart` (nicht zeilenweise auditiert; Priorität 4–5).
- `demo_result.py`, `demo_fictional_report.py`, `resend_btc.py` (nur Kopf/Zweck erfasst; Einmal-/Demo-Skripte außerhalb Produktionspfad).

## F. Duplikate & Abhängigkeiten (Prompt-2-Ergänzung, 15.07.2026)
**Duplikate (KRITISCH für Wartbarkeit, nicht für Kausalität):**
- `trendline_prototype.py` = veraltete Zweitkopie der Erkennung (eigene Line/fetch_4h/atr/pivots/find_lines/
  is_aplus) OHNE converges/pick_safety-v2/index-Signatur. Nicht im Produktionspfad, aber irreführend → als
  historisch kennzeichnen, nicht als Quelle nutzen.
- Kerzen-/Linien-Plotcode 4–5-fach (scan_100.plot, watchlist.plot, alert_bot.alert_chart/exit_chart/
  composite_chart) → gemeinsames charts.py.
- `read_env()` doppelt (telegram_setup.py + alert_bot.py) → gemeinsames config.py.

**Kritische Abhängigkeiten:** yfinance (einzige Datenquelle, kein Fallback), requests (Telegram),
matplotlib, pandas/numpy; Word-COM nur für PDF-Export (offline). Single Point of Failure = Yahoo.
scan_100.py ist Import-Wurzel für watchlist.py UND alert_bot.py (Änderung dort wirkt auf beide).

**Fehlende Tests:** alle (0 vorhanden). Details/Plan → TEST_PLAN.md, Status → TEST_RESULTS.md.

## G. Auswirkung der Prompt-2-Präzisierungen aufs Audit
- Apex-KALENDERgrenze: NUTZERENTSCHEIDUNG (kein stiller Default; 180-Bar-Grenze bleibt als Nutzerwert).
- Stop-ATR-Grenzen: DIAGNOSTIC_ONLY (nicht filternd bis Freigabe).
- S/R-Definition: NUTZERENTSCHEIDUNG (vollständige algorithmische Definition nötig).
- Prozent-Reporting & Telegram-Verteilung: NOT_CONFIGURED bis separate Spezifikationen.
- Varianten: getrennte Zustände + parent_signal_id + gemeinsamer Snapshot verbindlich.
- Pro.7 DIAGNOSTIC_ONLY, Pro.8 PRO8_NOT_CONFIGURED; aktive Kontrollen nur Pro.1+BE-0 und Pro.1+BE-1.
