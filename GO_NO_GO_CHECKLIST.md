# GO_NO_GO_CHECKLIST.md — §10/§11

> Stand 2026-07-25. Kriterium GO nur, wenn erfüllt. Start des Zwei-Monats-Tests NUR bei allen zwingenden GO.

| # | Kriterium | Status | Zwingend? |
|---|-----------|--------|-----------|
| 1 | Keine offenen KRITISCH-Befunde | GO (C-1/C-2 behoben) | ja |
| 2 | Kausalität: keine Look-ahead/rückdatierten Fills | GO (A3, is_final) | ja |
| 3 | R- & Prozentrechnung zentral, konsistent, Kosten einmal | GO (P1 behoben, Tests) | ja |
| 4 | Drawdown zeitgeordnet (R & %) | GO (P2 behoben) | ja |
| 5 | Gemeinsamer Snapshot + parent_signal_id, variantengetrennt | GO (Tests) | ja |
| 6 | Ledger protokolliert alle Kandidaten inkl. REJECTED_* | GO | ja |
| 7 | Testsuite grün & deterministisch | GO (90 grün) | ja |
| 8 | Backup + Integrität (.env ausgeschlossen) | GO (verifiziert) | ja |
| 9 | Sizing-Modell + PAPER_CAPITAL + Kosten festgelegt | NO-GO (Default-ANNAHME, Nutzerbestätigung offen) | ja |
| 10 | Kontosimulation/Portfoliorendite definiert (oder bewusst „nur Trade-%") | NO-GO (Entscheidung offen) | ja |
| 11 | Session-Kalender akzeptiert (crypto-exakt / Rest Näherung) ODER nachgerüstet | NO-GO (Entscheidung offen) | ja |
| 12 | Reporting-PDF + Kurztext erzeugt & zugestellt | NO-GO (nicht gebaut) | ja, falls Berichte gefordert |
| 13 | Telegram live (Chat-IDs) ODER bewusst lokal-zuerst | NO-GO (Nutzerinput) | ja (eine Variante wählen) |
| 14 | Unveränderliche Testkonfiguration (Start/Ende/Zeitzone/„zwei Monate") | NO-GO (Nutzerinput) | ja |
| 15 | Symboluniversum + Aktivierungsstatus final | NO-GO (STUFE-Plan, Nutzerfreigabe) | ja |
| 16 | Notfall-Stopp + Wiederanlauf geprüft | TEILWEISE (Recovery getestet; Notfall-Stopp-Prozedur dokumentiert) | ja |
| 17 | Keine echten Order-/Brokerfunktionen aktiv | GO (per Design) | ja |

## Ergebnis
**GESAMT: NO-GO für den Zwei-Monats-Start** — 7 zwingende Kriterien (9–15) benötigen Nutzerentscheidungen
bzw. noch nicht gebaute Teile (Reporting-PDF/Live-Telegram). KEINE offenen KRITISCH-Befunde.
Der Engine-Kern ist startbereit; es fehlen Konfiguration/Reporting/Zustellung + Freigaben.
