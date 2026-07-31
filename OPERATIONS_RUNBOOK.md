# OPERATIONS_RUNBOOK.md — §11 (Betrieb Paper-Test)

## Start (nur nach FINAL_GO_NO_GO = GO)
- Ein Zyklus (lokal, Modus B): `cd Prototyp && venv/Scripts/python -c "from engine import run_paper; print(run_paper.run_once())"`.
- Startmanifest schreiben: Startzeit UTC + Europe/Berlin, geplante Endzeit, code_version, config_hash,
  aktive Strategie-/BE-Versionen, Symboluniversum. Unveränderlich ablegen.

## Laufender Betrieb
- Zyklus je 4h (bzw. stündlicher Check). Nur abgeschlossene Kerzen. Keine rückwirkenden Änderungen.
- Berichte: 7-Tage (So 20:00) + rollierend-30 (20:30) Europe/Berlin. Rollierend-30 ≠ Kalendermonat.
- Monitoring je Zyklus: Instrumente, Downloads ok/fehl, Trigger, akzeptiert, eröffnet/geschlossen, Fehler,
  Laufzeit, code_version/config_hash. Kritische Fehler → System-Meldung (bei Live-Telegram) + Log.

## Notfall-Stopp (ohne Datenverlust)
- Prozess beenden (pythonw/Task). Zustände (ledger/trades/state/cache) liegen atomar auf Platte → konsistent.
- Sofort Backup: `venv/Scripts/python alert_bot.py --backup` (legacy) bzw. Zustandsdateien sichern.
- Ursache in RISK_REGISTER/CHANGELOG dokumentieren. Kein stilles Weiterlaufen bei Daten-/Zustandsfehler.

## Wiederanlauf
- Zustände werden beim Start automatisch geladen (Recovery getestet). Offene/pending Trades bleiben erhalten.
- Vor Wiederanlauf: Integrität prüfen (Dateien ladbar, keine .tmp-Reste). Dann Zyklus fortsetzen.

## Sicherheit
- Keine echten Orders/Broker. Telegram nur Ausgabe. Secrets nur in .env (nie Log/Backup/VCS).
