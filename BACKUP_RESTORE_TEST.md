# BACKUP_RESTORE_TEST.md — §11

> Stand 2026-07-25.

## Durchgeführt
- Voll-Backup erzeugt: `TradingBot_Backup_2026-07-25_2303.zip` (lokal `Backup/Archiv/` + OneDrive).
- Integritätsprüfung (zip.testzip): OK. 299 Dateien.
- Inhaltsprüfung: enthält MASTER_Strategie_Doku, engine/ (16), notify/ (10), tests/ (11), ledger, trades.
- Secret-Schutz: **.env NICHT im Backup enthalten** (verifiziert) — Token/Chat-IDs bleiben lokal.

## Restore-Prozedur (dokumentiert)
1. Backup-Zip aus `Backup/Archiv/` bzw. OneDrive an neuen Ort entpacken.
2. `.env` NEU anlegen (Token via BotFather /token; Chat-IDs neu eintragen) — nicht im Backup.
3. venv anlegen + `pip install yfinance pandas numpy matplotlib requests pytest`.
4. Testsuite laufen lassen: `venv/Scripts/python -m pytest tests/ -q` → muss grün sein.
5. Zustände (ledger/trades/state/cache) sind im Backup enthalten → Wiederanlauf konsistent.

## Offen
- Voller physischer Restore auf frischem System noch nicht durchgespielt (nur Integritäts-/Inhaltsprüfung).
  Vor STUFE 3 empfohlen: einmal komplett in ein Testverzeichnis entpacken + Testsuite dort ausführen.
