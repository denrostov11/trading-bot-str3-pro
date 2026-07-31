# CRITICAL_FINDINGS.md — §10

> Schweregrad · Wahrscheinlichkeit · Auswirkung · Dateien · Nachweis · Korrektur · Tests.
> Stand 2026-07-25. KRITISCH-Befunde: 2 gefunden, 2 BEHOBEN. Aktuell 0 offene KRITISCH-Befunde.

## BEHOBEN
### C-1 (KRITISCH) Doppelte Einstiegs-Slippage / unechtes Brutto  — BEHOBEN
- Wahrscheinlichkeit: sicher (jeder Trade). Auswirkung: Netto-Ergebnisse verfälscht (zu pessimistisch),
  Brutto nicht sauber.
- Datei: engine/tracker.py (simulate_trade). Nachweis: entry_price enthielt Slippage UND cost_price zog
  2*slip erneut ab.
- Korrektur: R/% aus entry_open (ungeslippt); Slippage+Gebühren genau EINMAL im Netto. entry_open + fill
  getrennt gespeichert.
- Tests: test_engine_percent.test_no_double_slippage, test_sign_consistency_r_and_pct. Status: grün.

### C-2 (KRITISCH) Max-Drawdown nicht zeitgeordnet — BEHOBEN
- Wahrscheinlichkeit: sicher, sobald >1 Trade. Auswirkung: falscher Drawdown (R und %).
- Datei: engine/reporting.py. Nachweis: Drawdown lief über Ledger-/Store-Reihenfolge statt Exit-Zeit.
- Korrektur: Equity nach closed_ts sortiert; cycle setzt closed_ts/exit_time.
- Tests: test_engine_percent.test_drawdown_time_ordered. Status: grün.

## OFFEN (nicht KRITISCH, aber vor Zwei-Monats-Start zu klären)
- H-1 (HOCH): Session-Kalender für Aktien/Futures/FX nur Näherung (24/7-Anker). is_final schützt vor
  unvollständigen Kerzen, aber Blockgrenzen können bei RTH-Instrumenten leicht abweichen. → nur Krypto
  „session_exact". Empfehlung: STUFE 1/2 crypto-lastig oder Kalender nachrüsten.
- H-2 (HOCH): Kontosimulation (Portfoliorendite mit Parallel-Trades) nicht implementiert →
  portfolio_return_pct = NICHT_SIMULIERT. Summe-der-Trade-% + compounded vorhanden; echtes Konto offen.
- M-1 (MITTEL): trendline_prototype.py veraltete Zweitkopie der Erkennung (nicht im engine-Pfad) →
  als „historisch" kennzeichnen/entfernen nach Gleichwertigkeit (Charakterisierung deckt scan_100 ab).
- M-2 (MITTEL): baseline-rr-Diagnose nutzt signal_close als provisorischen Einstieg, Tracker nutzt
  next-open — kleine Inkonsistenz, nur diagnostisch (2R-Gate ist ohnehin DIAGNOSTIC).
- M-3 (MITTEL): Cache CSV statt Parquet (pyarrow fehlt) — funktional gleichwertig; dokumentiert.
- L-1 (NIEDRIG): ATR bfill Mini-Look-ahead in ersten 14 Bars (weit in Vergangenheit, ohne Wirkung auf Trigger).
