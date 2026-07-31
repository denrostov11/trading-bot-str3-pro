# TEST_PLAN.md — Str.3 Pro

> Stand: 15.07.2026 · VORSCHLAG. Framework: pytest im Ordner `tests/`. Zwei Arten: (1) synthetische Charts
> mit vorab EINDEUTIG bekanntem Sollergebnis, (2) Charakterisierungstests auf realen Fixtures (Golden-Output
> des aktuellen Verhaltens, um Umbauten gleichwertig zu halten). Der Zwei-Monats-Test startet erst, wenn
> ALLE Fälle grün sind (Präz. 12/13).

## A. Pflicht-Testfälle (QS #1–#22 aus Master-Prompt)
Status je Fall in TEST_RESULTS.md. Zuordnung Befund → Test:
1. Pivot erst nach 3 rechten Kerzen bestätigt. (A6)
2. Unvollständige 4h-Kerze erzeugt keinen Trigger/Tap/Pivot/Bruch. (A1/A2 — aktuell FAIL)
3. Bruchkerze nicht als Tap. (B6)
4. Schluss exakt an Toleranzgrenze deterministisch (0,25/0,15 ATR).
5. Action-Line mit 2 Taps abgelehnt.
6. Safety-Line mit 1 Tap abgelehnt.
7. Parallele Linien abgelehnt. (converges)
8. Divergierende Linien abgelehnt. (converges)
9. Apex hinter erlaubtem Zeitraum abgelehnt (Bar-Grenze 180; Kalendergrenze DIAGNOSTIC bis Entscheidung).
10. Stop auf falscher Seite des Einstiegs abgelehnt (B3 — Guard neu).
11. Nächste relevante S/R < 2R → REJECTED_RR (B1/B2 — aktuell FAIL; S/R-Def USER_DECISION_REQUIRED).
12. Alter Bruch → kein rückdatierter Trade (A3 — aktuell FAIL).
13. Doppelte Daten entfernt. (C1)
14. Lokaler Cache bleibt bei kürzerem Yahoo-Download erhalten. (C1)
15. Fehlendes Volumen deaktiviert ausschließlich den Volumenfilter (Pro.3/5). (C5)
16. Yahoo-Ausfall stoppt nicht den Gesamtbot. (C2)
17. Futures-Rollover-Verdacht sperrt Setup. (C4)
18. Neustart stellt offene Paper-Trades korrekt wieder her. (D8)
19. Gleiche Linie wird nicht erneut gehandelt — PRO VARIANTE. (Präz. 2)
20. Gleichzeitige Stop-/Zielberührung → konservativ Stop. (Intrabar)
21. Varianten erhalten denselben Signal-Snapshot (parent_signal_id). (Präz. 3/4)
22. Parameteränderung erzeugt neue Versions-ID (config_hash/code_version).

## B. Zusatztests aus Prompt-2-Präzisierungen
23. Variantengetrennte Zustände: offener Pro.2-Trade blockiert Pro.3 nicht; Cooldown/Linien pro Variante. (Präz. 2)
24. parent_signal_id identisch über alle Varianten desselben Kandidaten; candidate/variant_evaluation/trade_id eindeutig. (Präz. 3)
25. Snapshot-Unveränderlichkeit: keine Variante wählt andere Linie/Pivots/Safety/Zone. (Präz. 4)
26. Rollierender 30-Tage-Bericht nutzt letzte 30 volle Kalendertage (nicht Kalendermonat). (Präz. 5)
27. Kein Auto-Start des Zwei-Monats-Tests ohne vollständige Testkonfiguration. (Präz. 12)
28. Offene Regel (S/R-Grenzen, ATR-Stop-Grenzen, Apex-Kalender) bleibt DIAGNOSTIC_ONLY und filtert NICHT. (Präz. 13)
29. Pro.7 aktiviert nach 2 Wochen KEINE Schwellen automatisch. (Präz. 9)
30. Pro.8 handelt nicht im Status PRO8_NOT_CONFIGURED. (Präz. 10)
31. Netto-Buchung: brutto_R und netto_R getrennt; Kosten je Klasse + 0,05 ATR Slippage angewandt.
32. MFE_R/MAE_R korrekt aus Bar-Verlauf; Break-even-R auf stop_initial.

## C. Synthetische Fixtures (Sollergebnis bekannt)
- Sauberer Keil mit 3 Action-Taps + 2 Safety-Taps, frischer Bruch → gültiges Setup, R:R bekannt.
- Paralleler Kanal → abgelehnt (Test 7). Divergenz → abgelehnt (Test 8).
- Bruch auf unvollständiger letzter Kerze → kein Trigger (Test 2).
- Nächste S/R-Zone bei 1,4R → REJECTED_RR (Test 11).
- Rollover-Gap in der Mitte einer Linie → REJECTED_DATA_QUALITY (Test 17).

## D. Freigabekriterium
Alle A- und B-Fälle grün + C-Fixtures reproduzieren die erwarteten Sollergebnisse → erst dann darf die
unveränderliche Testkonfiguration gesetzt und die Zwei-Monats-Uhr gestartet werden.
