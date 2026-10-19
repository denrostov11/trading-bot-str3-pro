# Parameter je Zeitrahmen (Skalierung der bar-basierten Erkennung)

| Parameter | 4h-Original | Tag | Woche | Monat | 1h | Regel |
|---|---|---|---|---|---|---|
| Analysefenster (Kerzen) | 540 | 360 | 156 | 72 | 540 | gewählt: 1h 22 Tage, 4h 90 Tage, Tag 1 Jahr, Woche 3 Jahre, Monat 6 Jahre |
| MIN_DURATION (Kerzen) | 90 | 60 | 26 | 12 | 90 | 90 · Fenster / 540 |
| MAX_APEX_BARS (Kerzen) | 180 | 120 | 52 | 24 | 180 | 180 · Fenster / 540 |
| Winkel-Normierung (Kerzen) | 390 | 260 | 113 | 52 | 390 | 390 · Fenster / 540 |
| MIN_SPACING zwischen Taps (Kerzen) | 6 | 5 | 3 | 3 | 6 | max(3, 6 · √(Fenster / 540)) |
| PIVOT_K (Fraktal) | 3 | 3 | 3 | 2 | 3 | 3 bei Fenster ≥ 150, sonst 2 |
| Safety-Tap-Alter (Monate) | 4 | 16 | 48 | 96 | 1 | Fensterdauer · 4/3 |
| Tap-/Bruch-Toleranz (ATR) | 0,25 / 0,15 | 0,25 / 0,15 | 0,25 / 0,15 | 0,25 / 0,15 | 0,25 / 0,15 | unverändert |
| Min. Taps Action (A+) / Safety | 3 / 2 | 3 / 2 | 3 / 2 | 3 / 2 | 3 / 2 | unverändert; Rückfall Kontextlinie: 2 (Tori) |
| Max. Winkel | 45° | 45° | 45° | 45° | 45° | unverändert |
| ATR-Periode | 14 | 14 | 14 | 14 | 14 | unverändert (einfacher Durchschnitt) |
