# FINAL_GO_NO_GO.md — §12 (Endgültige Startprüfung)

> Stand: 2026-07-25. Der Zwei-Monats-Paper-Test startet NUR, wenn ALLE zwingenden Kriterien GO sind und
> KEIN KRITISCH-Befund offen ist. Dieses Dokument ist der letzte Tor-Check.

## Ergebnis: **NO-GO** (kontrolliert) — Start NICHT ausgeführt.
Begründung: Der Engine-Kern ist startbereit und ohne offene KRITISCH-Befunde (C-1/C-2 behoben, 90 Tests grün).
Es fehlen jedoch zwingende Konfigurations-/Reporting-/Freigabe-Punkte, die NICHT durch einen „sinnvollen
Default" ersetzt werden dürfen (Governance, Präz. 13).

## GO (erfüllt)
- Keine offenen KRITISCH-Befunde; Kausalität (A3/is_final), R+% zentral & konsistent (P1), Drawdown
  zeitgeordnet (P2), gemeinsamer Snapshot + parent_signal_id, Ledger inkl. REJECTED_*, 90 Tests grün,
  Backup+Integrität (.env ausgeschlossen), keine echten Orders/Broker, Telegram nur Ausgabe.

## Nutzerentscheidungen 2026-07-25 — Stand aktualisiert
1. **Testkonfiguration:** Start = 00:00 Europe/Berlin am Fertigstellungstag; **„zwei Monate" = 2 Kalendermonate**
   (bestätigt). Startdatum wird am Fertigstellungstag fixiert (unveränderliche Config). — offen bis Start.
2.+3. **GELÖST:** kein Kapitalkonto → reine %-Auswertung (kein Sizing/Portfolio). Blocker entfallen.
4. **GELÖST:** Session-Näherung akzeptiert (Krypto exakt).
5. **GELÖST (Erzeugung):** Reporting-PDF + Kurztext gebaut (reporting_pdf/run_reports, 94 Tests grün).
   Telegram-ZUSTELLUNG wird beim Telegram-Setup angebunden.
6. **Telegram live:** Gruppen werden **auf Nutzer-Go** angelegt; danach Chat-IDs → Live-Verdrahtung +
   Integrationstest. — offen (wartet auf Go).
7. **Staged Rollout bestätigt:** STUFE 1 (2–3 T) → STUFE 2 (~1 Woche) → STUFE 3, dann Haupttest. — auszuführen.

## Verbleibende zwingende Punkte vor GO
- Telegram-Setup (Nutzer-Go + Chat-IDs) + Live-Verdrahtung + Integrationstest.
- STUFE 1 + STUFE 2 erfolgreich durchlaufen (Erfolgskriterien STAGED_ROLLOUT_PLAN).
- Unveränderliche Testkonfiguration am Fertigstellungstag einfrieren (Start/Ende 2 Kalendermonate, code_version, config_hash).
- Danach FINAL_GO_NO_GO neu bewerten → bei allen GO ausdrückliche Startfreigabe → Start + PAPER_TEST_STARTED.

## Startmanifest (wird ERST beim tatsächlichen GO-Start erzeugt)
Beim Start zu protokollieren: Startzeit UTC + Europe/Berlin, geplante Endzeit, code_version, config_hash,
aktive Strategie-/BE-Versionen, Symboluniversum, Bestätigung „keine echten Orders", „Telegram nur Ausgabe",
Paper-Trading-Startmeldung. Erst danach: `PAPER_TEST_STARTED` melden.

## Nächster Schritt
Nutzer entscheidet Punkte 1–7. Danach: offene HOCH-Punkte (Reporting-PDF, ggf. Kontosim/Kalender/Telegram)
bauen + testen → FINAL_GO_NO_GO neu bewerten → bei allen GO ausdrückliche Startfreigabe → Start.
