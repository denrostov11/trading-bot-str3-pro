# STAGED_ROLLOUT_PLAN.md — §11

> Gestufter Probebetrieb VOR dem Zwei-Monats-Haupttest. Jede Stufe mit Erfolgs-/Abbruchkriterien.

## STUFE 1 — 20–30 Symbole, 2–3 Tage
- Ziel: Stabilität, Datenqualität, keine Fehler, Zykluszeiten.
- Erfolg: 0 unbehandelte Fehler; alle Zyklen < 20 min; Ledger/Trades/State konsistent nach Neustart;
  keine Secrets in Logs.
- Abbruch: wiederholte Downloadausfälle > 10 %; beschädigter Zustand; KRITISCH-Fehler.
- Stand: Einzelzyklus über 24 Symbole erfolgreich (0 Fehler, 213 s). Mehrtägiger Dauerlauf noch offen.

## STUFE 2 — ~100 Symbole, ~1 Woche
- Ziel: Skalierung, erste echte Trigger/Trades, Berichtserzeugung (7-Tage).
- Erfolg: stabile Zyklen; erste Paper-Trades korrekt getrackt; Wochenbericht erzeugt & (falls aktiv) zugestellt.
- Abbruch: Speicher-/Laufzeitprobleme; inkonsistente Bilanz; Reporting-Fehler.

## STUFE 3 — freigegebenes großes Universum
- Ziel: Voller Betrieb wie im Zwei-Monats-Test.
- Erfolg: alle GO/NO-GO-Kriterien GO; FINAL_GO_NO_GO grün.

## Übergreifend
- Kein rückwirkendes Ändern; jede Parameteränderung = neue Versions-ID + neues Startdatum.
- Notfall-Stopp jederzeit ohne Datenverlust (OPERATIONS_RUNBOOK.md).
- Prüfbericht je Stufe (Fehler, Laufzeiten, Trades, Datenqualität) vor Freigabe der nächsten Stufe.
