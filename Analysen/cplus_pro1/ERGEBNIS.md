# Pro.1 im Zwei-Monats-Test: Ausstieg „C+“ gegen IST

Stand der Kursdaten: letzter finaler 4h-Kurs 12.10.2026 04:00 (UTC). Nur Pro.1, nur Lesen/Rechnen, Einstieg unverändert.

## Fazit

**Auf allen abgeschlossenen Trades wäre C+ besser gewesen**: +56,83 R / +226,5 % gegen IST +4,01 R / +81,9 %. Im direkten Paarvergleich (beide Varianten geschlossen, n=55) war C+ bei 32 Trades besser, bei 21 schlechter, bei 2 gleich (Median +0,12 R). **Aber:** 79 % des C+-Ergebnisses stammen aus nur 3 Krypto-Trades (SOL, ETH, BTC – alle drei mit Signal am 17.08., also dieselbe Marktphase). Ohne je die 3 größten Gewinner: C+ +12,19 R gegen IST −12,78 R. Bei Devisen gab es praktisch keinen Unterschied (C+ −8,03 R, IST −8,30 R); der Vorteil liegt im Krypto-Trendlauf (C+ +64,86 R, IST +11,76 R). Im „fairen“ Vergleich (nur Trades, die in allen vier Varianten geschlossen sind, n=33) war C+ **nicht** besser (−32,68 R gegen IST −24,07 R) – diese Auswahl besteht fast nur aus schnellen Verlierern.

## Plausibilitätscheck

- IST aus den Laufdaten: 65 geschlossen, +4,01 R, +81,9 %, 15 offen – trifft die Testzahlen (65 / +4,01 R / +81,9 %).
- IST mit der Engine-Funktion `simulate_trade` (BE-0, Ziel) auf den eigenen Kerzen nachgerechnet: **0 Abweichungen** bei 80 Trades.
- Safety-Linie bei Bruch+4 gegen `baseline_stop`: größte Abweichung 0.00024 R (bei allen 80 Trades). Bei 4 frühen Krypto-Trades (17.–21.08.) lag der damalige Kerzenindex 9 Kerzen tiefer (Cache wurde später rückwärts aufgefüllt); die Linie wurde dafür verschoben.
- Nicht einbezogen: 1 Trade ohne Einstiegskerze (JPY=X, Signal 12.10., pending_fill).

## Tabelle 1 – alle Pro.1-Trades (geschlossen = gewertet, offen = nicht gewertet)

| Variante | geschl. / offen | Gew. / Verl. | Treffer | Netto-R | Gesamt-% | Ø R | bester | schlechtester | Notfallnetz | Stufe 2 / 3 |
|---|---|---|---|---|---|---|---|---|---|---|
| IST | 65 / 15 | 31 / 34 | 47,7 % | +4,01 | +81,9 % | +0,06 | GBPJPY=X +9,43 | JPY=X −3,08 | 0 | – |
| B | 37 / 43 | 3 / 34 | 8,1 % | −36,37 | −58,5 % | −0,98 | NZDUSD=X +2,42 | JPY=X −6,19 | 9 | – |
| C+ | 59 / 21 | 26 / 33 | 44,1 % | +56,83 | +226,5 % | +0,96 | SOL-USD +20,48 | JPY=X −6,19 | 18 | 31 / 27 |
| D | 75 / 5 | 33 / 42 | 44,0 % | +69,83 | +185,0 % | +0,93 | GBPJPY=X +21,46 | JPY=X −5,70 | 0 | 0 / 67 |


Offene Trades nicht gewertet; ihr unrealisiertes R zum letzten Kurs (Summe): IST −1,03, B +158,91, C+ +3,88, D −1,14.

## Tabelle 2 – fairer Vergleich: nur Trades, die in ALLEN vier Varianten geschlossen sind (n=33)

| Variante | geschl. / offen | Gew. / Verl. | Treffer | Netto-R | Gesamt-% | Ø R | bester | schlechtester | Notfallnetz | Stufe 2 / 3 |
|---|---|---|---|---|---|---|---|---|---|---|
| IST | 33 / 0 | 5 / 28 | 15,2 % | −24,07 | −43,8 % | −0,73 | NZDUSD=X +3,71 | JPY=X −3,08 | 0 | – |
| B | 33 / 0 | 2 / 31 | 6,1 % | −34,88 | −46,5 % | −1,06 | NZDUSD=X +2,42 | JPY=X −6,19 | 7 | – |
| C+ | 33 / 0 | 3 / 30 | 9,1 % | −32,68 | −45,7 % | −0,99 | NZDUSD=X +2,42 | JPY=X −6,19 | 8 | 5 / 2 |
| D | 33 / 0 | 7 / 26 | 21,2 % | −25,27 | −27,2 % | −0,77 | GBPCAD=X +0,47 | JPY=X −5,70 | 0 | 0 / 22 |


## Zusatz – nur IST, C+ und D (ohne B), in allen dreien geschlossen (n=55)

| Variante | geschl. / offen | Gew. / Verl. | Treffer | Netto-R | Gesamt-% | Ø R | bester | schlechtester | Notfallnetz | Stufe 2 / 3 |
|---|---|---|---|---|---|---|---|---|---|---|
| IST | 55 / 0 | 27 / 28 | 49,1 % | +7,30 | +83,9 % | +0,13 | GBPJPY=X +9,43 | JPY=X −3,08 | 0 | – |
| C+ | 55 / 0 | 24 / 31 | 43,6 % | +57,22 | +227,1 % | +1,04 | SOL-USD +20,48 | JPY=X −6,19 | 17 | 27 / 23 |
| D | 55 / 0 | 28 / 27 | 50,9 % | +75,68 | +184,9 % | +1,38 | GBPJPY=X +21,46 | JPY=X −5,70 | 0 | 0 / 44 |


## Die 5 größten Unterschiede C+ gegen IST (beide geschlossen)

- **SOL-USD LONG**, Signal 17.08.2026: IST +0,75 R, C+ +20,48 R (Differenz +19,73 R). IST nahm am festen Ziel nur +0,75 R mit. C+ hat kein Ziel: Stufe 2 und Stufe 3 zogen die Schwelle am Swing nach, der Trend lief weiter, Ausstieg erst am 30.08.2026 (NOTFALLNETZ) bei +20,48 R.
- **ETH-USD LONG**, Signal 17.08.2026: IST +0,56 R, C+ +17,01 R (Differenz +16,45 R). IST nahm am festen Ziel nur +0,56 R mit. C+ hat kein Ziel: Stufe 2 und Stufe 3 zogen die Schwelle am Swing nach, der Trend lief weiter, Ausstieg erst am 23.08.2026 (NOTFALLNETZ) bei +17,01 R.
- **GBPJPY=X SHORT**, Signal 28.08.2026: IST +9,43 R, C+ −0,14 R (Differenz −9,56 R). IST traf das Ziel bei +9,43 R (bester Verlauf 11,5 R). C+ erreichte Stufe 2, hatte aber noch keinen bestätigten Swing; der Kurs fiel per Schlusskurs unter Einstand+Kosten zurück, Ausstieg bei −0,14 R – der Gewinn wurde zurückgegeben.
- **BTC-USD LONG**, Signal 17.08.2026: IST +1,27 R, C+ +7,16 R (Differenz +5,88 R). IST nahm am festen Ziel nur +1,27 R mit. C+ hat kein Ziel: Stufe 2 und Stufe 3 zogen die Schwelle am Swing nach, der Trend lief weiter, Ausstieg erst am 23.08.2026 (NOTFALLNETZ) bei +7,16 R.
- **EURJPY=X SHORT**, Signal 02.09.2026: IST +0,44 R, C+ +5,79 R (Differenz +5,35 R). IST nahm am festen Ziel nur +0,44 R mit. C+ hat kein Ziel: Stufe 2 und Stufe 3 zogen die Schwelle am Swing nach, der Trend lief weiter, Ausstieg erst am 18.09.2026 (NOTFALLNETZ) bei +5,79 R.

## Konzentration und Klassen

- IST: Summe +4,01 R; die 3 größten Trades 9,43, 3,71, 3,66 R; ohne diese 3: −12,78 R.
- B: Summe −36,37 R; die 3 größten Trades 2,42, 0,18, 0,17 R; ohne diese 3: −39,15 R.
- C+: Summe +56,83 R; die 3 größten Trades 20,48, 17,01, 7,16 R; ohne diese 3: +12,19 R.
- D: Summe +69,83 R; die 3 größten Trades 21,46, 17,38, 15,56 R; ohne diese 3: +15,44 R.
- Nach Klasse (Netto-R, geschlossene Trades): IST: fx −8,30 (45), crypto +11,76 (19), index +0,54 (1); C+: fx −8,03 (38), crypto +64,86 (21); D: fx +12,15 (53), crypto +57,84 (21), index −0,15 (1)

## Zusatzrechnung (NICHT gewertet): offene Trades zum letzten Kurs mitbewertet

Netto-R geschlossen + unrealisiert offen: IST +2,98, B +122,54, C+ +60,71, D +68,69. B hält viele Trades noch offen, die im Plus stehen – diese Gewinne sind unrealisiert und könnten verschwinden. Nach Nutzerentscheidung zählen offene Trades nicht; die Zahl dient nur dem Verständnis des Laufzeit-Effekts.

## Einordnung (ehrlich)

- **Kleine Stichprobe, nur 2 Monate**, nur Pro.1, 80 Trades, davon rund die Hälfte Devisen, 1 Marktphase (die großen Krypto-Gewinner starteten alle am 17.08.). Ein anderes Quartal kann das Bild drehen.
- **Ergebnis hängt an wenigen Ausreißern** (3 Krypto-Trades). R-Summen sind außerdem empfindlich, weil das ursprüngliche Risiko bei manchen Trades sehr klein ist (z. B. GBPJPY: 1 ATR).
- **Notfallnetz-Ausstiege bei C+ sind überwiegend Gewinn-Ausstiege**: Das Netz liegt 1 ATR unter der Gewinnschwelle und greift bei schnellen Rückschlägen/Lücken.
- **Parameter vorab festgelegt, nicht optimiert**: Stufe 2 bei +1,5R, Swing-Puffer 0,5 ATR, Notfallnetz 1 ATR, Rücksetzer ≥ 1 ATR, D-Puffer 0,1 ATR. Es wurde nichts angepasst.
- **Laufzeit-Effekt**: C+/B haben kein Ziel und bleiben länger offen (C+: 21 offen, IST: 15); offene Trades zählen nicht. Deshalb der faire Vergleich – der aber nur schnell beendete Trades enthält und daher ebenfalls verzerrt (zugunsten kurzer Verlierer).
- **4h-Näherung**: Kerzenweise Auswertung, Linienwert zum Kerzen-Index, Ausführung zum nächsten Open, Notfallnetz intrabar; Lücken zum Open (nicht geschönt). Bei Short ist alles gespiegelt.
- **Interpretationen**: Stufe 3 greift erst nach Stufe 2 (vorher bestätigte Swings werden nicht rückwirkend angewandt); bei D gilt die Swing-Nachführung ohne Stufe-2-Voraussetzung; der „vorherige Hoch“-Bezug des Rücksetzers ist das höchste Hoch seit Einstieg.
- Keine Empfehlung und keine Parameteränderung; das Ergebnis ist eine Rückrechnung an 2 Monaten.
