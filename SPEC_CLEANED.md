# SPEC_CLEANED.md — bereinigte Spezifikation (Vorschlag, Phase B)

> Stand: 15.07.2026 · Status: VORSCHLAG — vor produktiver Aktivierung sind die Punkte in
> OPEN_QUESTIONS.md / DECISIONS.md zu bestätigen. Bis dahin bleibt das System reines Paper-Trading.
> Verbindliche Grundlage der Zahlenwerte: Str.3_Pro.1_Gesamtspezifikation + Phase-B-Definitionen des Master-Prompts.

## 1. Kausalität (verbindlich)
1. Nur vollständig abgeschlossene Kerzen werden analysiert (`is_final == true`).
2. Ein 4h-Trigger entsteht ausschließlich beim ERSTMALIGEN Abschluss der betreffenden 4h-Kerze.
3. Kein rückdatierter Einstieg. Einstieg liegt immer in der Zukunft relativ zum Signalabschluss.
4. Pivot erst nach 3 vollständig geschlossenen rechten Kerzen bestätigt (K=3). — Code korrekt (A6).
5. Linien nutzen nur bestätigte Pivots und Daten ≤ Signalzeit.
6. Beim Signal wird ein unveränderlicher Snapshot gespeichert: Action-Line, Safety-Line, ATR, S/R-Zonen,
   alle Filterwerte, Pivot-Bestätigungszeiten, Tap-Zeiten, data_cutoff_time.

## 2. A+-Action-Line
- ≥ 3 zeitlich getrennte gültige Taps · ≥ 6 volle 4h-Kerzen zwischen Taps.
- Tap-Toleranz 0,25 · ATR(14); Bruch-Toleranz 0,15 · ATR(14); Bruchkerze zählt nicht als Tap.
- normierter Winkel < 45°.
- Mindestdauer: ≥ 21 Kalendertage (primär, reale Zeitstempel) + ≥ 6-Bar-Spacing. Starre 90-Bar-Regel
  entfällt als Gate. (bestätigt 15.07.2026)

## 3. Safety-Line (3 Regeln)
- ≥ 2 zeitlich getrennte gültige Taps in Gegenrichtung.
- INTAKT (keine Kerzen-Durchkreuzung; nur Wick-Taps).
- KONVERGENT: Gap schrumpft nach rechts; Apex eindeutig berechenbar, liegt nach den Ausgangspunkten und bei
  aktivem Keil in der ZUKUNFT; ≤ 180 4h-Kerzen (Nutzer-Wert 15.07.). KALENDERgrenze: USER_DECISION_REQUIRED
  (Präz. 1) — bis dahin nur diagnostisch, nicht filternd.

## 4. 4h-Aggregation (NEU zu bauen)
- Je Instrument: Börsenzeitzone, Sitzungskalender, reguläre Handelszeiten, feste 4h-Ankerzeit, DST,
  verkürzte Tage, Overnight-Sessions, Kennzeichnung unvollständiger Blöcke.
- Ein unvollständiger 4h-Block erzeugt NIE Trigger/Tap/Pivot/Bruch.
- Pro 4h-Kerze speichern: start_time_utc, end_time_utc, session_date, completeness_ratio,
  source_1h_bar_count, is_final.
- Assetklassen-Standardanker (bestätigt 15.07.2026 als Startannahme, je Symbol in SYMBOL_STATUS verfeinern):
  Krypto 00/04/08/12/16/20 UTC (24/7); US-Aktien/Index an regulärer Session verankert; FX an 22:00 UTC
  Tagesgrenze; Futures je CME-Session.

## 5. Einstieg / Stop / Ziel (bestätigt 15.07.2026)
- Einstieg: Open der nächsten handelbaren Kerze nach bestätigtem 4h-Bruch (kein rückdatierter Fill).
- Stop: eingefrorene Safety-Line-Projektion (Kerze Bruch+4). Guard: LONG stop<entry, SHORT stop>entry, sonst REJECTED_STOP.
- Stop-Risiko: > 0 zwingend. ATR-Min/Max-Grenzen DIAGNOSTIC_ONLY (Präz. 7) — Wert nur speichern, nicht
  filtern, bis Freigabe.
- Ziel: die tatsächlich NÄCHSTE relevante S/R-Zone, kein Überspringen näherer Zonen; wird sie nicht mit
  ≥ 2,0R erreicht ⇒ REJECTED_RR (kein Trade). Vollständige algorithmische S/R-Definition:
  USER_DECISION_REQUIRED (Präz. 8) — Vorschlag ≥2 Reaktionen/0,6 ATR ist noch nicht freigegeben.
- 1 Versuch pro Linie · 1 offener Trade pro Instrument · 24 h Cooldown · index-freie Liniensignatur.

## 6. Ausführungsmodell (bestätigt 15.07.2026)
- Immer brutto UND netto parallel buchen. Netto-Kosten je Seite: FX 0,02 % · Index 0,03 % · Futures 0,03 % ·
  Aktien 0,02 % · Krypto 0,10 %; zusätzlich 0,05 ATR Slippage je Seite.
- Speichern: signal_close, next_open, slippage, fees, brutto_R, netto_R. Kein rückdatierter Fill.

## 7. Intrabar-Exit
- Stop & Ziel in derselben Kerze ⇒ offiziell Stop zuerst (konservativ); Sensitivität „Ziel zuerst"
  separat; Kennzeichnung AMBIGUOUS_INTRABAR; Anzahl separat ausweisen.

## 8. Datenqualität & Rollover
- Volumen nur bei ≥95 % gültigen, nichtnegativen, plausiblen Werten (kein Fake-FX-Volumen).
- SUSPECTED_ROLLOVER via Gap + True-Range-Ausreißer + Kontacktwechsel-Nähe + Volumensprung.
- Linie darf keinen ungeklärten Rollover überspannen; Setup nahe Rollover ⇒ REJECTED_DATA_QUALITY.

## 9. Buchführung
- JEDER geprüfte Kandidat wird protokolliert (auch REJECTED_*), Felder siehe paper_trade_datensatz.
- Netto-Ergebnis buchen; MFE_R/MAE_R; code_version + config_hash je Datensatz.
- Break-even-R immer auf Original-Risiko (stop_initial).

## 9a. Variantengetrennte Zustände & Signal-Herkunft (Prompt 2, verbindlich)
- „1 offener Trade pro Instrument", 24 h Cooldown, Linien-Wiederverwendung gelten PRO Variante. Pro.1–8
  führen getrennt: offene/abgeschlossene Trades, Cooldowns, gehandelte Linien, Watchlists, Equity, Statistik,
  Configversion, Berichtszustand. Ein Trade in Pro.2 blockiert Pro.3 nicht.
- Baseline erzeugt je Kandidat GENAU EINEN unveränderlichen Snapshot (Daten-Endzeit, bestätigte Pivots +
  Zeiten, Action-Line, Safety-Line, Tap-Zeiten, ATR, S/R-Zonen, Signal-Close, Baseline-Stop, Baseline-Ziel,
  R:R, Datenqualität) und eine unveränderliche `parent_signal_id`.
- Jede Variante bewertet EXAKT diesen Snapshot; keine wählt rückwirkend andere Linie/Pivots/Safety/Zone.
- IDs je Varianten-Bewertung: `parent_signal_id` (gemeinsam) + `candidate_id` + `variant_evaluation_id` +
  `trade_id`. Damit nachvollziehbar: wer akzeptierte/ablehnte, welcher Filter ablehnte, welches Ergebnis.

## 9b. Berichtsrhythmen (Prompt 2, verbindlich)
- Wöchentlich: letzte 7 volle Kalendertage. Rollierend: letzte 30 volle Kalendertage (NICHT „Kalendermonat").
  Abschlussbericht nach Ende des freigegebenen Testzeitraums.
- Prozent-Reporting-Definitionen: NOT_CONFIGURED bis separate Prozent-/Reporting-Spez (Präz. 6).
- Telegram-Verteilung: NOT_CONFIGURED bis separate Telegram-Spez (Präz. 5).

## 9b1. Testbetriebsmodus = MODUS B (bestätigt 15.07.2026)
- Vollautonomes Paper-Trading, keine Per-Trade-Zustimmung. Alle Varianten bewerten jedes Signal automatisch.
- Pro Trigger/Trade eine reine Info-Nachricht (keine Aktion nötig). Keine echten Orders, kein Geld.
- Zustelldetails (Format/Takt/Kanal) NOT_CONFIGURED bis Telegram-Spez (Präz. 5).

## 9c. Variantenstatus
- Pro.7: DIAGNOSTIC_ONLY (ADX/Choppiness/R² nur protokollieren; keine Auto-Schwellen).
- Pro.8: PRO8_NOT_CONFIGURED (Daily-Marktstruktur erst nach algorithmischer Definition + Freigabe).
- Aktive Kontrollen: Pro.1+BE-0 und Pro.1+BE-1; weitere Kombinationen erst nach dokumentierter Freigabe.

## 10. Änderungskontrolle
- Jede Parameteränderung ⇒ neue Versions-ID + neues Startdatum; keine rückwirkende Neuberechnung
  in derselben Ergebnisreihe. Eintrag in CHANGELOG.md.
