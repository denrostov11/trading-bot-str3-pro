# MIGRATION_PLAN.md — Str.3 Pro

> Stand: 15.07.2026 · VORSCHLAG. Umsetzung erst nach ausdrücklicher Nutzerfreigabe. Jeder Schritt hat einen
> sicheren Zwischenstand + Rückfallmöglichkeit. Keine Regeländerung stillschweigend; kein echter Handel.

## Grundprinzipien
- Bot bleibt gestoppt bis Testsuite grün (Präz. 12/13).
- Vor jedem Umbau der Erkennung: Golden-Output („Charakterisierungstest") des aktuellen Verhaltens auf
  festen Fixtures einfrieren → Umbau muss identische Linien/Taps liefern (nachgewiesene Gleichwertigkeit),
  bevor Altcode entfernt wird.
- Jeder Schritt = eigener Commit + Backup; Rückfall durch Auschecken/Backup-Zip + scan_100-Shim.
- Produktionsdaten (trades.json Altreihe, Charts, Berichte) werden NICHT gelöscht/überschrieben; neue Reihe
  startet versioniert.

## Schrittfolge (jeder Schritt einzeln freigeben)
**S0 — Sicherung & Fixtures (risikolos).** Voll-Backup; 3–5 reale 4h-Datensätze + synthetische Charts mit
bekanntem Sollergebnis als Fixtures einfrieren. Rückfall: keiner nötig.

**S1 — Testgerüst (kein Verhaltensänderung).** pytest aufsetzen; Charakterisierungstests für aktuelle
find_lines/converges/pick_safety/stop_and_target auf Fixtures (Golden-Output). Rückfall: Tests löschen.

**S2 — Datenzugriffsschicht (additiv).** `data/access.py` + `data/cache.py` (Retry/Backoff/Timeout/Batch,
Parquet additiv, Merge/Dedup/Monotonie). Läuft PARALLEL, ändert Erkennung nicht. Test 13/14/16.
Rückfall: alten fetch_4h behalten.

**S3 — Korrekte 4h-Aggregation + Vollständigkeit.** `data/aggregate_4h.py` (TZ/Session/DST/Anker,
is_final/completeness). Behebt A1/A2. Test 2. **Verhaltensänderung** → nur nach Freigabe aktiv schalten;
bis dahin Alt- und Neuaggregation parallel vergleichen (Diff-Report).

**S4 — Datenqualität/Rollover.** `data/quality.py`; REJECTED_DATA_QUALITY/SUSPECTED_ROLLOVER. Behebt C4/C5.
Test 17. Rückfall: Flags nur diagnostisch.

**S5 — Baseline-Engine + Snapshot + parent_signal_id.** `engine/baseline.py`: EIN unveränderlicher Snapshot;
Kausalfixes A3 (kein rückdatierter Einstieg; Einstieg = Open next bar) + B1/B2 (REJECTED_RR, keine näheren
Zonen überspringen) + B3 (Stop-Seiten-Guard). S/R-Definition bleibt USER_DECISION_REQUIRED — bis dahin
DIAGNOSTIC. Tests 3–12, 20. **Kernänderung** → ausführliche Freigabe.

**S6 — Candidate-Ledger (auch REJECTED_*).** `tracker/ledger.py`: JEDER geprüfte Kandidat protokolliert.
Behebt D1. Test 21.

**S7 — Varianten-Engine.** `variants/`: Pro.1(BE-0/BE-1) als aktive Kontrollen; Pro.2–6 als VORSCHLAG
(erst nach Freigabe aktiv), Pro.7 DIAGNOSTIC, Pro.8 NOT_CONFIGURED. Variantengetrennte Zustände (Präz. 2).
Gemeinsamer Snapshot (Präz. 4). Test 21/22. Behebt D2.

**S8 — Tracker mit Fill-/Kostenmodell + MFE/MAE + Intrabar.** `tracker/paper_trades.py`: Open-next-bar,
brutto+netto, Stop-zuerst, AMBIGUOUS_INTRABAR, Recovery-Check. Behebt D3/D4/D8. Test 18/19/20.

**S9 — Reporting/Charts/Notify konsolidiert.** gemeinsames `charts.py`; Berichte 7-Tage/rollierend-30/
Abschluss (Prozent NOT_CONFIGURED; Telegram NOT_CONFIGURED bis jeweilige Spez). Duplikate entfernen NUR nach
Gleichwertigkeitsnachweis.

**S10 — Altcode-Ausmusterung.** trendline_prototype.py als „historisch/veraltet" kennzeichnen (nicht löschen,
bis Gleichwertigkeit dokumentiert); scan_100-Shim entfernen, wenn alle Importe umgezogen sind.

**S11 — Testkonfiguration + Zwei-Monats-Start.** Unveränderliche Testkonfig (Start/Ende/Zeit/Zeitzone/
Definition „zwei Monate" — Präz. 12) in DECISIONS.md. Start nur wenn alle Tests grün.

## Abbruch-/Rückfallregeln
- Bricht ein Charakterisierungstest nach einem Umbau → Schritt zurückrollen, Ursache in RISK_REGISTER.
- Keine produktive Aktivierung offener Regeln (Präz. 13). Bei Zweifel: DIAGNOSTIC_ONLY.
