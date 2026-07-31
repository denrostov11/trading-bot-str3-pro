# RUNBOOK.md — Str.3 Pro (Betrieb)

> Stand: 15.07.2026. Der Bot ist GESTOPPT (Strategie-Anpassung). Dieses Runbook wird ab Phase C/H ausgebaut.

## Aktueller Zustand
- Bot pausiert; Autostart deaktiviert (`Startup\TradingBot_AlertBot.vbs.disabled`).
- Solange gestoppt: keine Scans, keine Break-even-Prüfung, keine Berichte, keine 12h-Backups.

## Manuelle Bedienung (Bestand)
- Einzelscan: `python scan_100.py` · Watchlist: `python watchlist.py`
- Alert-Bot ein Zyklus: `python alert_bot.py --once` · Dauerbetrieb: `python alert_bot.py`
- Nur Backup: `python alert_bot.py --backup`
- Wiederinbetriebnahme Autostart: Startup-VBS von `.disabled` zurückbenennen.

## Telegram-Ausgabeschicht (Prototyp/notify/, Stand 15.07.2026 — entkoppelt, nicht live)
- Module: config (Validierung REQUIRED/OPTIONAL/DISABLED), redact (kein Token-Leak), transport
  (MockTransport für Tests, RealTelegramTransport für Betrieb), messages (16 Typen), router
  (deterministisch, keine Fehlleitung), queue (persistent/idempotent/Retry/Recovery), scheduling
  (Perioden Europe/Berlin→UTC, Einmal-Versand, DST-sicher), commands (Allowlist, nur lesend), dispatcher.
- Tests: `cd Prototyp && venv/Scripts/python -m pytest tests/ -q` → 31 grün (Mock, kein echter Versand).
- Konfig: `Prototyp/.env.example` (nur Platzhalter). Echte Werte NUR in `.env` (nie in Backup/VCS).
- NICHT aktiv: noch nicht an die Strategie-Engine verdrahtet, kein echter Telegram-Versand, keine Chat-IDs.
- Deaktivieren: kein Token in .env → Telegram DISABLED_BY_CONFIGURATION; Paper-Trading/lokale Auswertung läuft weiter.

## Strategie-/Daten-Engine (Prototyp/engine/, Stand 2026-07-25 — Kern komplett, lokal lauffähig)
- Bausteine: dataaccess (Retry/Backoff/Batch), cache (additiver CSV-Cache), aggregate_4h (Anker+Session,
  is_final/completeness), quality (Volumen/Rollover), baseline (Snapshot+parent_signal_id, A3/B3/C4 aktiv,
  B1/B2/ATR diagnostisch), features, variants (Pro.1–8), ledger, varstate (variantengetrennt), tracker
  (Fill/BE-0..4/MFE/MAE/netto), orchestrate, instruments, cycle, reporting, run_paper.
- Tests: `cd Prototyp && venv/Scripts/python -m pytest tests/ -q` → **85 grün** (inkl. Charakterisierung).
- **Ein Paper-Zyklus (lokal, kein Telegram, keine echten Orders):**
  `venv/Scripts/python -c "from engine import run_paper; print(run_paper.run_once())"`
  → schreibt Cache/Ledger/Trades/State/Monitoring nach `Prototyp/paper_runtime/`. Zwei-Monats-Test wird
  NICHT automatisch gestartet.
- NOCH OFFEN vor Live: Prozent-/Reporting-Spez (PDF-Berichte + %-Kennzahlen), echte Telegram-Chat-IDs +
  User-ID, unveränderliche Testkonfiguration (Zeitraum), Börsen-Sessionkalender. Keine produktive
  Aktivierung/kein Zwei-Monats-Start vor Freigabe.
