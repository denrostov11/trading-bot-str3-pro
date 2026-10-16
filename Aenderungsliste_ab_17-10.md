# Änderungsliste für den Neustart am 17.10.2026 (nach Testende 12:00)

Gesammelt mit dem Nutzer am 15./16.10.2026. Umsetzung durch den Trading-Agenten erst nach „Go“.
Bis zum Testende wird am laufenden Zwei-Monats-Test nichts verändert.

## Varianten
1. Weiter laufen nur **Pro.1 (Baseline)** und **Pro.3 (Volumen)**.
2. **Pro.2 wird durch C+ ersetzt** (gleiche Einstiege wie Pro.1, C+-Ausstieg) und schreibt in die bisherige Pro.2-Gruppe.
3. Pro.4 bis Pro.8 werden abgeschaltet.
4. Danach benennt der Nutzer die Telegram-Gruppen um (Pro.1 Baseline, Pro.3 Volumen, C+). Ich gebe Bescheid, wenn es so weit ist.

## Gruppe „STR3 System“
5. Nur noch: **Bericht alle 2 Wochen** (sonntags 20:00) + **Bericht auf Abruf** mit `bericht`.
6. **Keine Mini-Meldungen** mehr: keine Zyklus-Meldungen („Zyklus …: Instrumente, Trigger, eröffnet …“), kein 12-h-Herzschlag, keine Start-Meldung.
7a. **Erinnerung an die Zeitumstellung** (Wunsch des Nutzers) in „STR3 System“:
   - Je eine Meldung am Vorabend um 20:00 und am Tag der Umstellung um 08:00.
   - Inhalt: die neuen Schlusszeiten der 4h-Kerzen in deutscher Zeit.
     - Winterzeit: 01, 05, 09, 13, 17, 21 Uhr.
     - Sommerzeit: 02, 06, 10, 14, 18, 22 Uhr.
   - Hinweis in der Meldung: Der Bot rechnet intern in UTC und läuft unverändert weiter.
   - Die Termine werden automatisch aus der Zeitzone Europe/Berlin bestimmt.
   - Nächste Umstellungen: So 25.10.2026 (auf Winterzeit), So 28.03.2027 (auf Sommerzeit).
7. **Einzige Ausnahme: kurze Ausfall-Meldung**, wenn ein Eingriff nötig ist (Bot abgestürzt oder hängt, keine Daten mehr, wiederholte Zyklusfehler). Eine Meldung pro Ausfall, keine Wiederholungen. Dazu eine Meldung, wenn der Bot wieder läuft.

## Trade-Meldungen
8. Statt des unscharfen Bilds kommt eine **Trade-PDF top-down**: Monat, Woche, Tag, 4h und 1h, jeweils ein eigener Chart, 2 Charts pro Seite, dazu eine Kurzbeschreibung. Gleiche Kurzbeschreibung als Telegram-Text. Die Muster liegen in `Analysen/mtf_muster/`, die Rückmeldung des Nutzers steht noch aus.
9. **Einstiegszeit klar und realistisch** (vom Nutzer am 15.10. bemerkt):
   - a) In der Meldung stehen in deutscher Zeit: Schlusszeit der Signal-Kerze, gebuchter Einstieg (Eröffnungskurs der nächsten 4h-Kerze), **aktueller Kurs beim Versand** und Abstand dazu in R.
   - b) Statt „open“ einen klaren Status: „Einstieg gebucht“ bzw. „wartet auf Einstieg“.
   - c) Den **Zyklus an die 4h-Schlusszeiten anpassen**: wenige Minuten nach jedem 4h-Schluss rechnen, nicht irgendwann in der Stunde. So kommt die Meldung schneller.
   - d) Im Papierhandel **zusätzlich einen realistischen Einstieg buchen**, nämlich den Kurs zum Zeitpunkt der Meldung, und beide Werte vergleichen (theoretisch gegen realistisch).

10a. **Die Meldung enthält zusätzlich:**
   - Uhrzeit, zu der der Trade eröffnet wird bzw. werden soll (deutsche Zeit)
   - gebuchten Einstiegskurs und aktuellen Kurs
   - Abstand des aktuellen Kurses zum Stop und zum Ziel, jeweils in Preis und in R
   - Damit ist sofort erkennbar, ob der Kurs schon stark abweicht.
10b. **Schnellere Kursermittlung:**
   - Der Zyklus startet 1–2 Minuten nach jedem 4h-Schluss.
   - Zuerst werden nur die Instrumente mit möglichem Signal geprüft, Abrufe laufen parallel.
   - Den aktuellen Kurs aus 1-Minuten-/5-Minuten-Daten holen.
   - Ziel: Meldung innerhalb von ca. 2–5 Minuten nach Kerzenschluss.
   - Wie verzögert die Yahoo-Kurse je Instrumentklasse sind, wird gemessen und in der Meldung angezeigt.
10c. **Vorwarnung 30 und 15 Minuten vor Kerzenschluss:**
   - Rein informativ, kein Einstieg.
   - Prüft mit der noch laufenden 4h-Kerze, ob der Kurs gerade jenseits der Action Line liegt.
   - Meldung: „Möglicher Bruch, Kerze schließt um …, aktuell … über/unter der Linie“.
   - Danach immer eine Auflösung: „bestätigt“ oder „nicht bestätigt“.
   - **Festgelegt (15.10.):**
     - Die Vorwarnungen gehen in die jeweilige Varianten-Gruppe (Pro.1, Pro.3, C+), nicht in „STR3 System“.
     - Nachtruhe vorerst 23:00–07:00, dann keine Vorwarnungen. Echte Trade-Meldungen kommen trotzdem.
   - Die Einstellungen stehen in einer eigenen Datei (an/aus, Zeitpunkte 30/15 Min., Nachtruhe, Gruppen), die der Bot bei jedem Durchlauf neu liest. So lässt sich alles **während des Tests ohne Neustart** ändern.
   - Vorwarnungen sind nur Information. Ein Ändern verfälscht das Testergebnis nicht.

## C+ und Tests
10. C+ als eigener Baustein, mit Tests jeder Stufe und Gegenprüfung durch Codex.
11. 18-Monats-Backtest: IST, B, C+, D und „Hälfte bei +2R verkaufen“. Walk-Forward (12 Monate wählen, 6 Monate prüfen).
12. Verbesserung für die Lücke in Stufe 2 von C+ prüfen (Beispiel GBPJPY).

## Auswertung des Zwei-Monats-Tests
13. Trades, die am 17.10. um 12:00 noch offen sind, werden **nicht gewertet**.
14. Abschlussbericht nur mit abgeschlossenen Trades.
