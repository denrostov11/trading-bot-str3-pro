# PRE_FLIGHT_CHECKLIST.md — §11

> Vor jedem Stufen-/Teststart abzuhaken.
- [ ] Testkonfiguration eingefroren (Code-Version + config_hash) und gesichert.
- [ ] Sizing-Modell + PAPER_CAPITAL + Notional/Risk% festgelegt (unveränderlich).
- [ ] Break-even-Matrix je aktiver Variante festgelegt (Pro.1 BE-0 + BE-1 Kontrolle; weitere freigegeben).
- [ ] Gebühren/Slippage je Assetklasse bestätigt (FX 0,02% … Krypto 0,10% + 0,05 ATR).
- [ ] Start-/Endzeitpunkt + Berichtszeitzone Europe/Berlin gesetzt; „zwei Monate" definiert.
- [ ] Symboluniversum + Aktivierungsstatus (SYMBOL_STATUS.csv) final.
- [ ] Datenqualitäts-Mindestanforderungen aktiv (Rollover/Volumen/Vollständigkeit).
- [ ] Cache + 12h-Backup + OneDrive funktionsfähig; Restore getestet (BACKUP_RESTORE_TEST.md).
- [ ] Zustandswiederherstellung nach Neustart geprüft.
- [ ] (falls Telegram-Live) Test-Gruppen + Routing geprüft; Secrets nicht in Logs.
- [ ] Reporting-Erzeugung + (falls aktiv) PDF-Zustellung geprüft.
- [ ] Logging/Monitoring/Alarmierung aktiv; Notfall-Stopp getestet.
- [ ] Bestätigt: KEINE echten Order-/Brokerfunktionen aktiv; Telegram nur Ausgabe.
- [ ] Unveränderliche Baseline-Snapshots + parent_signal_id.
- [ ] Alle zwingenden GO/NO-GO-Kriterien = GO; keine offenen KRITISCH-Befunde.
