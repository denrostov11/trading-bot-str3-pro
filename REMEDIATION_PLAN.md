# REMEDIATION_PLAN.md — §10

> Stand 2026-07-25. Reihenfolge nach Priorität. KRITISCH-Punkte bereits behoben (C-1/C-2).

| # | Punkt | Priorität | Maßnahme | Tests | Blocker für Start? |
|---|-------|-----------|----------|-------|--------------------|
| R1 | C-1 Doppel-Slippage | KRITISCH | BEHOBEN | vorhanden | nein (erledigt) |
| R2 | C-2 Drawdown-Ordnung | KRITISCH | BEHOBEN | vorhanden | nein (erledigt) |
| R3 | H-2 Kontosimulation | HOCH | Portfolio-Konto mit Parallel-Trades + Kapitalgrenze ODER bewusst nur „Summe der Trade-%"+compounded ausweisen (Entscheidung) | Kontosim-Tests | ja, falls Portfoliorendite gefordert |
| R4 | H-1 Session-Kalender | HOCH | RTH-Kalender je Börse ODER STUFE 1/2 crypto-first + Näherung dokumentiert akzeptieren | RTH-Fixture | teilweise (Entscheidung) |
| R5 | Reporting-PDF + Kurztext + Telegram-Zustellung | HOCH | build_report je Variante (R+%-Block, feste Reihenfolge) + Vergleich + Filterwirkung; Zustellung via notify | Reporting-Tests | ja (Berichte gefordert) |
| R6 | Live-Telegram-Verdrahtung | HOCH | RealTransport im Loop + echte Chat-IDs (Nutzer) + Integrationstest Test-Gruppen | Integrationstest | nur falls Telegram-Live gewünscht (sonst lokal-zuerst) |
| R7 | Synthetischer E2E-Trigger-Test | MITTEL | erzwungener A+-Bruch-Fixture → Trade→Ergebnis | 1 Test | empfohlen |
| R8 | M-1 Duplikate (trendline_prototype, Plotcode) | MITTEL | als historisch kennzeichnen/konsolidieren nach Gleichwertigkeit | — | nein |
| R9 | M-2 baseline-rr vs. next-open | MITTEL | rr-Diagnose auf next-open umstellen (kosmetisch, diagnostisch) | — | nein |
| R10 | Testkonfiguration (Daten/Kapital/Sizing/Zeitraum) | HOCH | unveränderliche Config festschreiben (Nutzerentscheidung) | Config-Test | ja |
