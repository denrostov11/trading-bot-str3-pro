# DECISIONS.md — Entscheidungsprotokoll (Str.3 Pro)

> Jede getroffene Entscheidung mit Datum, Begründung, Auswirkung. Offene Punkte: siehe OPEN_QUESTIONS.md.

## Bereits entschieden (Nutzer, aus vorheriger Projektphase)
- 2026-07-13 — Safety Line muss INTAKT sein (keine Kerzen-Durchkreuzung). Umgesetzt.
- 2026-07-15 — Keine Doppel-Trades (Instrument-Sperre, 24 h Cooldown, Neue-Linie-Pflicht, index-freie Signatur).
- 2026-07-15 — Keil-Regel: Action & Safety müssen konvergieren; Apex ≤ 180 4h-Kerzen.
- 2026-07-15 — Break-even-Automatik (15m-Kerzen, 0,3 %/1,0 %-Schwelle, Puffer 10 %). [wird zu BE-1]
- 2026-07-15 — Bot + alle Trades gestoppt (Strategie-Anpassung). Autostart deaktiviert.

## Phase A/B (dieses Audit)
- 2026-07-15 — Phase A abgeschlossen: Audit dokumentiert in AUDIT_REPORT.md (11 KRITISCH-Punkte).
- 2026-07-15 — Phase B bereinigte Spezifikation als VORSCHLAG (SPEC_CLEANED.md); NICHT aktiviert bis Freigabe.
- 2026-07-15 — Keine Strategie-Codeänderung in Phase A/B (Auftrag: erst Audit+Freigabe).

## 2026-07-25 — Prompt-3-Startentscheidungen (Nutzer)
1. **Start:** 00:00 Uhr (Mitternacht) Europe/Berlin an dem Tag, an dem alles fertig ist.
   „Zwei Monate" = 2 KALENDERMONATE ab Start (ANNAHME/Default, Nutzer-Bestätigung noch offen).
2.+3. **KEIN Kapitalkonto — reine Prozent-Auswertung** (Gewinn/Verlust in %). Keine Positionsgröße,
   keine Portfolio-/Konto-Simulation, keine Wiederanlage-Kontorendite. Kennzahlen: Summe Gewinn-%,
   Summe Verlust-%, reiner Nettogewinn %, Ø/Median je Trade, best/worst + R-Kennzahlen. „Summe der
   Einzeltrade-% bei gleichem Einsatz je Trade". (Blocker Sizing/Kapital + Kontosim entfallen.)
4. **Session-Kalender-Näherung akzeptiert** (Krypto exakt; Aktien/Futures/FX Näherung, is_final schützt).
5. **Reporting: PDF + Telegram-Kurztext** — GEBAUT (engine/reporting_pdf.py, 92 Tests grün). Telegram-
   Zustellung wird mit der Live-Verdrahtung angebunden.
6. **Telegram LIVE mit echten Chat-IDs** — Nutzer erstellt 10 Gruppen + liefert Chat-IDs + User-ID
   (TELEGRAM_SETUP.md). Wiring folgt danach.
7. **Gestufter Probebetrieb** erklärt (STUFE 1→2→3); Vorgehen wie STAGED_ROLLOUT_PLAN.

## Bestätigt am 2026-07-15 (Nutzer: „alles bestätigen")
1. **Einstiegspreis:** Open der nächsten handelbaren Kerze nach bestätigtem 4h-Bruch (kein Look-ahead).
2. **Sub-2R:** kein Trade → als REJECTED_RR protokollieren.
3. **Relevante S/R-Zone:** ≥ 2 Pivot-Reaktionen, Cluster-Toleranz 0,6 ATR; Ziel = nächste solche Zone,
   kein Überspringen; wird sie nicht mit ≥ 2,0R erreicht ⇒ REJECTED_RR.
4. **Break-even-Matrix:** alle Hauptvarianten (Pro.2–8) mit BE-1; Pro.1 zusätzlich mit BE-0/BE-2/BE-3/BE-4
   als Kontrollreihe (Pro.1+BE-0 = reine Baseline).
5. **Kosten:** immer brutto UND netto parallel buchen. Netto je Seite: FX 0,02 % · Index 0,03 % ·
   Futures 0,03 % · Aktien 0,02 % · Krypto 0,10 %; zusätzlich 0,05 ATR Slippage je Seite.
6. **Mindestdauer:** 21 Kalendertage primär (reale Zeitstempel) + ≥ 6-Bar-Spacing; starre 90-Bar-Regel als
   Gate entfällt.
7. **Apex:** ≤ 180 4h-Kerzen UND ≤ 45 Kalendertage.
8. **Stop-Distanz:** 0,5 ATR ≤ Stop ≤ 6 ATR, sonst REJECTED_STOP.
9. **Universum:** vorerst die ~95; Erweiterung erst nach bestandener Testsuite (kuratierte Liquiditätsliste).
10. **4h-Anker/Session:** Assetklassen-Standardannahme (SPEC_CLEANED §4) als Startannahme, je Symbol in
    SYMBOL_STATUS verfeinern.
11. **Start Zwei-Monats-Uhr:** erst wenn alle 22 QS-Tests grün sind (Phase G); kein festes Datum.
12. **ATR-Regime (Pro.4):** Fenster 100 4h-Kerzen, Akzeptanz 20.–90. Perzentil.
13. **Cache:** `Prototyp/data_cache/` (Parquet, additiv, nie kürzen).

→ Damit sind alle Punkte aus OPEN_QUESTIONS.md entschieden. Nächster Blocker für produktive Aktivierung:
   bestandene Testsuite (Phase G).

## 2026-07-15 — Prompt 2 (Verbindliche Zusatzpräzisierungen) hat VORRANG
Prompt 2 stuft mehrere der oben bestätigten Defaults ausdrücklich zurück (kein „stiller Default" für offene
Regeln). Änderungen gegenüber der Block-Bestätigung:
- **Apex-Kalendergrenze** (frühere „≤45 Tage"): ZURÜCKGEZOGEN → USER_DECISION_REQUIRED (Präz. 1).
  Nur die vom Nutzer explizit gesetzte BAR-Grenze 180 bleibt. Apex liegt bei aktivem Keil in der ZUKUNFT.
- **Stop-ATR-Grenzen** (frühere „0,5–6 ATR"): ZURÜCKGEZOGEN → DIAGNOSTIC_ONLY (Präz. 7).
- **S/R-Definition** (frühere „≥2 Reaktionen/0,6 ATR"): nur Vorschlag → USER_DECISION_REQUIRED, vollständige
  algorithmische Definition nötig (Präz. 8).
- **Prozent-Reporting**: NOT_CONFIGURED bis separate Prozent-/Reporting-Spez (Präz. 6).
- **Telegram-Verteilung**: NOT_CONFIGURED bis separate Telegram-Spez (Präz. 5).
- **BE-Matrix**: aktiv nur Pro.1+BE-0 und Pro.1+BE-1; weitere Kombinationen brauchen dokumentierte Freigabe (Präz. 11).
- **Testzeitraum**: Start/Ende/Zeit/Zeitzone/„zwei Monate" müssen explizit gesetzt werden, kein Auto-Start (Präz. 12).

## 2026-07-15 — Testbetriebsmodus = MODUS B (autonom + Info) [Nutzer bestätigt]
- Der Zwei-Monats-Forward-Test läuft **vollautonom im Paper-Trading**. **Keine Per-Trade-Zustimmung** des
  Nutzers erforderlich (galt ohnehin nur für ECHTE Orders — die es hier nicht gibt).
- Alle Varianten (Pro.1–8) bewerten jedes Baseline-Signal automatisch über den gemeinsamen Snapshot; keine
  manuelle Auswahl → statistisch saubere, lückenlose Stichprobe.
- **Info-Nachrichten:** pro Trigger/Trade eine reine FYI-Meldung (keine Aktion nötig, blockiert nichts).
- Sicherheit unverändert: keine echten Orders, kein Geld, keine Broker-Anbindung. Autonom ≠ echter Handel.
- Abgrenzung: Das KONKRETE Telegram-Verteilformat/-Takt der Info- und Berichtsnachrichten bleibt
  NOT_CONFIGURED bis zur separaten Telegram-Spezifikation (Präz. 5). Modus B legt nur das Freigabe-/
  Informationsmodell fest, nicht die Zustellungsdetails.

## 2026-07-15 — Verbindliche Betriebsregeln aus Prompt 2 (übernommen)
- **Variantengetrennte Zustände (Präz. 2):** „ein offener Trade pro Instrument", Cooldown (24 h) und
  Linien-Wiederverwendung gelten PRO Variante (Pro.1–8 getrennt: offene/abgeschl. Trades, Cooldowns,
  gehandelte Linien, Watchlists, Equity, Statistik, Configversion, Berichtszustand). Pro.2 blockiert Pro.3 nicht.
- **Gemeinsame Ursprungssignale (Präz. 3):** unveränderliche `parent_signal_id` je Baseline-Kandidat;
  je Variante `candidate_id`, `variant_evaluation_id`, `trade_id`. Nachvollziehbar: wer akzeptierte/ablehnte,
  welcher Filter ablehnte, welches Ergebnis.
- **Gemeinsamer Snapshot (Präz. 4):** Baseline erzeugt Snapshot GENAU EINMAL (Daten-Endzeit, best. Pivots +
  Zeiten, Action/Safety, Tap-Zeiten, ATR, S/R-Zonen, Signal-Close, Baseline-Stop/Ziel, R:R, Datenqualität).
  Keine Variante wählt rückwirkend andere Linie/Pivots/Safety/Zone.
- **Berichtsrhythmen (Präz. 5):** wöchentlich (letzte 7 volle Kalendertage), rollierend 30 Tage (letzte 30
  volle Kalendertage — NICHT „Kalendermonat"), Abschlussbericht nach Testende.
- **Zustandsprinzip (Präz. 13):** jede nicht abschließend definierte Regel = NOT_CONFIGURED /
  DIAGNOSTIC_ONLY / USER_DECISION_REQUIRED; nie stiller Produktiv-Default.
