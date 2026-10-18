# Parameter je Zeitrahmen (Skalierung der bar-basierten Erkennung)

| Parameter | 4h-Original | Tag | Woche | Monat | 1h | Regel |
|---|---|---|---|---|---|---|
| Analysefenster (Kerzen) | 540 | 360 | 156 | 72 | 540 | gewählt: 1h 22 Tage, 4h 90 Tage, Tag 1 Jahr, Woche 3 Jahre, Monat 6 Jahre |
| MIN_DURATION (Kerzen) | 90 | 60 | 26 | 12 | 90 | 90 · Fenster / 540 |
| MAX_APEX_BARS (Kerzen) | 180 | 180 | 78 | 36 | 180 | Fenster / 3 (1h, 4h) bzw. Fenster / 2 (Tag, Woche, Monat) |
| Winkel-Normierung (Kerzen) | 390 | 260 | 113 | 52 | 390 | 390 · Fenster / 540 |
| MIN_SPACING zwischen Taps (Kerzen) | 6 | 5 | 3 | 3 | 6 | max(3, 6 · √(Fenster / 540)) |
| PIVOT_K (Fraktal) | 3 | 3 | 3 | 2 | 3 | 3 bei Fenster ≥ 150, sonst 2 |
| Safety-Tap-Alter (Monate) | 4 | 22 | 48 | 96 | 1 | Fensterdauer in Kalendertagen · 4/3 (Tag: 504 Kalendertage) |
| Tap-/Bruch-Toleranz (ATR) | 0,25 / 0,15 | 0,25 / 0,15 | 0,25 / 0,15 | 0,25 / 0,15 | 0,25 / 0,15 | unverändert |
| Min. Taps Action (A+) / Safety | 3 / 2 | 3 / 2 | 3 / 2 | 3 / 2 | 3 / 2 | unverändert; Rückfall Kontextlinie: 2 (Tori) |
| Max. Winkel | 45° | 45° | 45° | 45° | 45° | unverändert |
| ATR-Periode | 14 | 14 | 14 | 14 | 14 | unverändert (einfacher Durchschnitt) |

## Änderungen v2 (Safety Line auf Tag, Woche, Monat)

**Anlass.** Die Safety Line wurde auf den höheren Zeitrahmen kaum gefunden (in den ersten Mustern auf fast keinem). Geprüft wurde, ob
die Kriterien der Gegenlinie (`pick_safety`: mind. 2 Taps, intakt, richtige Seite, Safety-Tap-Alter, Konvergenz/Keil, Apex) dort zu
streng skaliert sind. Messung: 3 Symbole (SOL-USD, GBPJPY, AUDUSD) × 22 Stichtage (monatlich 01/2025–10/2026) × Tag/Woche/Monat,
jeweils nur Stichtage mit gültiger Action Line (Tag 62, Woche 60, Monat 55 Fälle).

**Ablehnungsgründe der Gegenlinien** (Summe über alle Fälle, Mehrfachnennung nicht möglich, Reihenfolge der Prüfung):

| Grund | Tag | Woche | Monat | Bewertung |
|---|---|---|---|---|
| bereits gebrochen (nicht intakt) | 835 | 337 | 157 | Regel des Nutzers, bleibt |
| divergent (Keil öffnet sich) | 278 | 112 | 17 | Keil-Regel des Nutzers, bleibt |
| Apex zu weit | 76 | 41 | 15 | **zu streng skaliert → gelockert** |
| Tap zu alt | 78 | 0 | 0 | **Skalierungsfehler (Handelstage statt Kalendertage) → korrigiert** |

**Anpassung 1 – Apex (`MAX_APEX_BARS`).** Original: Apex höchstens 180 4h-Kerzen voraus = ein Drittel des Analysefensters (540).
Bisherige Skalierung hielt das Drittel auch auf Tag/Woche/Monat (120 / 52 / 24 Kerzen). Höhere Zeitrahmen haben je Fenster viel
weniger Swings; ein Keil darf dort länger vor dem Apex stehen. Neu: **halbes Fenster** (Tag 180, Woche 78, Monat 36 Kerzen).
4h und 1h bleiben beim Originalwert 180 (Test sichert das).

**Anpassung 2 – Safety-Tap-Alter Tag.** Das Alter wird in Kalendermonaten geprüft, das Tagesfenster aber in Kerzen (360). Bei
Devisen/Aktien/Futures sind 360 Tageskerzen etwa 504 Kalendertage (Wochenenden fehlen). Mit 16 Monaten fielen Taps am linken
Fensterrand allein deshalb heraus. Neu: Fensterdauer des Tags = 504 Kalendertage → **22 Monate** (Woche 48, Monat 96 unverändert).

**Wirkung** (gleiche Stichproben, Safety Line gefunden / Fälle mit Action Line):

| | vorher | nachher |
|---|---|---|
| Tag | 19 / 62 (31 %) | 24 / 62 (39 %) |
| Woche | 14 / 60 (23 %) | 16 / 60 (27 %) |
| Monat | 3 / 55 (5 %) | 6 / 55 (11 %) |

(Anpassung 2 allein änderte in dieser Stichprobe nichts, ist aber systematisch richtig.) Geprüft und **nicht** geändert:
größere Fenster (Monat 96/120, Woche 208/260 Kerzen) — brachten keine zusätzlichen Safety Lines (Woche sogar weniger).
Ein Partner für irgendeine andere A+-Linie des Zeitrahmens existiert kaum öfter (Tag 26 / Woche 17 / Monat 6 von je ~60), eine
Umstellung der Auswahl der Hauptlinie lohnt also nicht.

**Rest.** Auf dem Monatsrahmen bleibt die Safety Line selten (rund jeder neunte Fall): 72 Kerzen ergeben nur ca. 10 Swings, die
meisten Gegenlinien sind schon gebrochen. Das ist das Ergebnis der Regeln, nicht ein Fehler. **Es wird nichts erfunden:** gibt es
keine gültige Linie, steht im Chart „keine gültige Linie nach unseren Regeln“ bzw. „keine gültige Safety Line nach unseren Regeln“.

**Technik (ohne Ergebnisänderung).** `fastlines.find_lines_fast` ersetzt die Python-Schleife von `scan_100.find_lines` durch eine
vektorisierte Variante (Ergebnisse identisch, per Test gegen scan_100 geprüft; ca. 15× schneller; flache Tagesdaten mit 400 Kerzen: Original 192 s allein für die Unterstützungsseite, jetzt 0,4 s für beide Seiten) und begrenzt die Suche hart:
höchstens 110 jüngste Pivots je Seite, höchstens 800 Kandidatenlinien vor der Duplikat-Bereinigung, Zeitbudget 6 s je Zeitrahmen
(danach „keine Linienaussage“). Normale Daten haben 10–70 Pivots je Seite, die Grenzen greifen dort nie. Die Zeitrahmen-Parameter werden als Argument übergeben; Konstanten von `scan_100` werden NICHT mehr verändert (sicher neben dem laufenden Engine-Code im selben Prozess).
