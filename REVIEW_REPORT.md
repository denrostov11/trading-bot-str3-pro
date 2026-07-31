# REVIEW_REPORT.md — Unabhängige Senior-Gesamtprüfung (§10)

> Stand: 2026-07-25 · Rolle: unabhängiger Senior Quant / Auditor / adversarialer Test-Engineer.
> Ziel: aktiv Fehler suchen, nicht bestätigen. Bewertung je Baustein; Varianten Pro.1–8 + BE-Modi.
> Kein Produktionscode geändert in dieser Prüfung. Detailbefunde: CRITICAL_FINDINGS.md / RISK_REGISTER.md.

## Methodik
Codegelesen: engine/* (dataaccess, cache, aggregate_4h, quality, baseline, features, variants, varstate,
tracker, orchestrate, instruments, cycle, reporting, run_paper), notify/*, tests/*. 90 Tests grün.
STUFE-1-Probelauf (24 Symbole, 0 Fehler, 213 s). Backup-Integrität geprüft (.env ausgeschlossen).

## Kernbewertung nach Prüfkategorien
| Kategorie | Befund |
|---|---|
| Look-ahead / rückdatierte Fills | A3 aktiv (Trigger nur letzte finale Kerze; Einstieg=Open-next-bar). OK. |
| Unvollständige Kerzen | is_final/completeness (A1) — nur finale Kerzen signalfähig. OK. |
| 1h→4h-Aggregation | Anker+Session, DST via zoneinfo. Krypto exakt; Aktien/Futures/FX Session-Näherung (offen). |
| Pivots | K=3, erst nach 3 rechten Kerzen bestätigt; letzte 3 nie Pivot. OK. |
| ATR/EMA/ADX/Choppiness/R²/RVOL | implementiert + getestet; ATR nutzt bfill (Mini-Look-ahead erste 14 Bars, unkritisch). |
| Prozent/R-Berechnung | zentral, EINE Schicht; brutto aus entry_open, Kosten EINMAL (P1 behoben); Vorzeichen konsistent. |
| Doppelte Kosten | P1 behoben + Test. |
| Drawdown | zeitgeordnet nach closed_ts (P2 behoben + Test). |
| Kostenannahmen | FX 0,02%/Index 0,03%/Krypto 0,10% je Seite + 0,05 ATR Slippage (Nutzer bestätigt). Plausibel. |
| Kontosimulation | Portfoliorendite NICHT_SIMULIERT (Parallel-Trade-Konto noch nicht modelliert) — offen. |
| Datenleckage Varianten / Snapshot | gemeinsamer unveränderlicher Snapshot + parent_signal_id; variantengetrennte Zustände. OK + Test. |
| parent_signal_id-Konsistenz | deterministisch, über alle Varianten identisch. OK + Test. |
| Duplikatcode / toter Code | trendline_prototype.py = veraltete Zweitkopie (nicht im engine-Pfad); Plotcode mehrfach. Aufräumen offen. |
| Zustände/Recovery | JSON atomar (os.replace); Neustart-Recovery getestet. Einprozess-Betrieb → geringe Race-Gefahr. |
| Telegram | Routing/Queue/Idempotenz/Redaction getestet (Mock); Live nicht verdrahtet; Secrets nie in Logs/Backup (verifiziert). |
| Tests | 90 grün, deterministisch (Charakterisierung auf fixem Fixture). Lücken: TEST_GAPS.md. |
| Performance/Speicher | ~9 s/Symbol; ~95 Symbole ≈ 15 min/Zyklus; Speicher unkritisch. OK für 4h-Takt. |

## Gesamturteil
Der Kausal- und Rechenkern ist solide und getestet; die zwei bei der Prüfung gefundenen KRITISCH-Fehler
(P1/P2) sind behoben. Es bestehen KEINE offenen KRITISCH-Befunde. Vor einem Zwei-Monats-Start sind mehrere
NICHT-kritische, aber verbindliche Punkte offen (Session-Kalender, Kontosimulation, Live-Telegram/Reports-PDF,
Testkonfiguration, Aufräumen Duplikate) — siehe GO_NO_GO_CHECKLIST.md.
