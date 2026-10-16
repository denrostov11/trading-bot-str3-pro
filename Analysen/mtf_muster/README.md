# Top-down-Muster-PDFs (Prototyp, nichts live)

Drei fiktive Muster aus dem laufenden Zwei-Monats-Paper-Test. Es wird nichts live geschaltet und nichts gesendet.

| Datei | Inhalt |
|---|---|
| `Muster_sol_long_2026-08-17.pdf` | SOL-USD LONG, Signal 17.08.2026: großer Trend, C+ +20,48 R gegen IST +0,75 R |
| `Muster_gbpjpy_short_2026-08-28.pdf` | GBP/JPY SHORT, Signal 28.08.2026: IST traf das Ziel (+9,43 R), C+ gab den Gewinn zurück (−0,14 R) |
| `Muster_audusd_short_2026-09-02.pdf` | AUD/USD SHORT, Signal 02.09.2026: typischer Devisen-Verlierer (IST −1,07 R, C+ −1,07 R) |
| `Telegram_Entwurf_*.txt` | Nachrichtenentwurf (9 Zeilen) im Format der bestehenden Trade-Meldung, würde zusammen mit der PDF gesendet |
| `Parameter_je_Zeitrahmen.md` | Skalierung der bar-basierten Erkennungsparameter |
| `zusammenfassung.json` | Linien je Zeitrahmen, Top-down-Ergebnis, Prüfwerte |
| `build_muster.py` | erzeugt alles (Bot-venv: `python build_muster.py`) |

Code: `Prototyp/mtf/` (neu), Tests: `Prototyp/tests/test_mtf.py` (15 Tests). Kein bestehender Engine-Code wurde geändert.

## Auswahl der drei Trades
- **SOL-USD LONG**: größter Trend der Stichprobe, zeigt, was ein festes Ziel abschneidet (C+ +20,48 R) – und dass die höheren Zeitrahmen (Monat, Woche) hier widersprachen.
- **GBP/JPY SHORT**: die Gegenprobe – ein großer Gewinn (IST +9,43 R), den C+ zwischen Stufe 2 und erstem Swing zurückgab.
- **AUD/USD SHORT**: der typische Devisen-Verlierer (Stop-Out bei etwa −1,1 R), damit die Muster nicht nur Gewinner zeigen.

## Entscheidungen
- **Unfertige Kerzen**: Die zum Signalzeitpunkt laufende Tages-/Wochen-/Monatskerze wird für Linien und Brüche NICHT benutzt (wie die Engine: nur abgeschlossene Kerzen). Sie wird aus den 1h-Daten bis zum Signalzeitpunkt gebaut und hell mit gestricheltem Rand gezeichnet, damit man sieht, wo der Kurs steht. Einheitlich in allen Zeitrahmen.
- **Kein Look-ahead**: Je Zeitrahmen nur Kerzen mit Ende ≤ Signalzeitpunkt (Signalzeitpunkt = Ende der 4h-Signalkerze). Der Verlauf nach dem Signal (4h-Chart, grau unterlegt) dient nur der Muster-Auswertung (IST/C+) und fließt nicht in die Linien ein. Getestet (`test_timeframes_unchanged_when_future_data_changes`).
- **Linien**: kanonische `scan_100`-Funktionen mit je Zeitrahmen skalierten Parametern. Kontextlinie = intakte A+-Linie (≥ 3 Taps), die dem Kurs am nächsten liegt; Rückfall nach Tori: 2 Berührungspunkte, Punkt B = jüngstes unberührtes Hoch/Tief. Keine gültige Linie → „keine gültige Linie nach unseren Regeln“.
- **Top-down (nur informativ, kein Filter)**: Bias = Steigung der Hauptlinie (steigend = Aufwärtstrend, fallend = Abwärtstrend, < 3° = seitwärts/keine Aussage). Gezählt werden Monat, Woche, Tag und 4h (das Signal selbst); 1h verfeinert nur.
- **Höherer Zeitrahmen im Chart**: Nur die Linien des nächsthöheren Zeitrahmens werden dünn gestrichelt eingezeichnet (Woche → Monat, Tag → Woche, 4h → Tag, 1h → 4h-Signallinien).

## Bekannte Schwächen
- SOL-USD: Der Cache der ersten Testtage wurde später rückwärts aufgefüllt (Index-Verschiebung um 9 Kerzen). Die Linie wird kalibriert (Stop stimmt auf 0,0002 R), aber die Anker liegen nicht exakt auf den heutigen Kerzen: 5 statt 6 Taps (Action) bzw. 4 statt 5 (Safety).
- Tageshistorie kommt aus Yahoo „max“ (Stand heute), nicht aus dem damaligen Datenstand; Wochen/Monate daraus sind Kalender-Wochen/-Monate (Mo–So bzw. Kalendermonat), keine Börsenwochen.
- Die Bias-Regel ist grob (nur Steigung der nächstliegenden Linie); die Safety Line fehlt auf den meisten höheren Zeitrahmen (kein konvergenter Partner).
- Bei flachen oder illiquiden Daten kann `find_lines` sehr langsam werden (viele gleiche Pivots) – im Live-Einsatz Zeitlimit vorsehen.
