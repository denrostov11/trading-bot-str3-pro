# TELEGRAM_ARCHITECTURE.md — Str.3 Pro (Analyse & Zielarchitektur)

> Stand: 15.07.2026 · Status: ANALYSE-VORSCHLAG, KEIN Code geändert. Umsetzung erst nach ausdrücklicher
> Freigabe UND nach Abschluss/Freigabe des Strategie- und Daten-Audits (Master-Prompt).
> Priorität bei Konflikt (aus Spez): 1 Datenintegrität/Kausalität · 2 Paper-Trading-Sicherheit ·
> 3 Master-Spez · 4 gemeinsame Snapshots/Vergleichbarkeit · 5 lokale Speicherung · 6 Telegram · 7 Optik.
> Grundsatz: Telegram ist reine Ausgabeschicht; die lokale DB ist die verbindliche Quelle. Ein Telegram-
> Fehler darf NIE Trade-Zustände ändern, Daten verlieren oder die Strategiebewertung verfälschen.

## 1. Audit der bestehenden Telegram-Implementierung (tatsächlich gelesen)
| Element | Ist-Zustand (alert_bot.py / telegram_setup.py) | Bewertung ggü. neuer Spez |
|---|---|---|
| Bot/Token | 1 Token aus `.env`; `API=…/bot<token>` | ok (Token aus .env), aber siehe Sicherheit |
| Ziel | EINE `TELEGRAM_CHAT_ID` | **fehlend**: keine Mehrkanal-/Varianten-Zuordnung |
| Senden | `tg_text/tg_photo/tg_document` an einen Chat | keine Routing-Ebene, keine Nachrichten-Metadaten |
| „Queue" (Nachtmodus) | Liste von Strings in `bot_config.json` | **KRITISCH**: kein persistenter, idempotenter Zustell-Queue; kein Retry/Backoff; kann bei Absturz mitten im Schreiben doppeln/verlieren |
| Befehle | `getUpdates`, Substring-Match; nur Besitzer-`CHAT` | keine User-ID-Allowlist getrennt von Chat-ID; keine `/command`-Validierung |
| Fehler | `print("Telegram-Fehler:", e)` | **KRITISCH**: requests-Exception kann die API-URL MIT Token enthalten → Token-Leak im Log |
| read_env | doppelt in alert_bot.py + telegram_setup.py | Duplikat → zentrales config-Modul |
| Idempotenz | keine | **KRITISCH**: Neustart/Resend kann Duplikate erzeugen |
| Nachrichtentypen | implizit (Trigger/NEAR/Ergebnis/Bericht) | keine 16 typisierten Meldungen |

Fazit: Die vorhandene Schicht ist ein Einzelkanal-Sender ohne Routing/Queue/Idempotenz/Sicherheitshärtung.
Sie wird NICHT erweitert, sondern durch ein sauberes `notify/`-Paket ersetzt (Altpfad bleibt bis Umzug).

## 2. Betroffene Dateien / Funktionen
- alert_bot.py: `read_env`, `API`, `CHAT`, `tg_text`, `tg_photo`, `tg_document`, `notify_text`,
  `notify_photo`, `check_telegram_commands`, Nachtmodus-Queue in `bot_config.json`.
- telegram_setup.py: `read_env`, `write_chat_id`, getUpdates-Flow.
- bot_config.json: `muted`, `tg_offset`, `queue`.
- .env: `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` (wird zu Mehrkanal erweitert).

## 3. Zielarchitektur (Ausgabeschicht, keine Duplikate der Analyse)
```
str3pro/notify/
  config.py        # lädt/validiert Telegram-Konfig (REQUIRED/OPTIONAL/DISABLED_BY_CONFIGURATION)
  transport.py     # gemeinsame Transportabstraktion (real | MockTransport für Tests)
  router.py        # deterministisches Routing strategy_id/message_type -> chat
  queue.py         # persistente Zustell-Warteschlange + Idempotenz + Retry/Backoff + Recovery
  messages.py      # 16 typisierte Nachrichtenmodelle inkl. Pflichtfeldern + Paper-Trading-Hinweis
  commands.py      # autorisierte Statusbefehle (Allowlist, nur lesend)
  redact.py        # Redaction: Token/volle Chat-IDs nie in Logs/Fehlern/Backups
```
- Die Schicht liest NUR bereits lokal gespeicherte, nachvollziehbare Ergebnisse (DB = verbindliche Quelle).
- KEINE zweite Datenquelle/Cache/4h-Aggregation/Kandidatenerkennung/Trendlinien-/Paper-Trading-Engine.
- Alle Varianten nutzen denselben unveränderlichen Baseline-Snapshot + `parent_signal_id` (aus Master-Spez).

## 4. Routing-Matrix (deterministisch)
| strategy_id | Ziel-ENV | Einzelmeldungen | Berichte |
|---|---|---|---|
| Str.3 Pro.1 | STR3_PRO1_CHAT_ID | ausschließlich Pro.1-Gruppe | Pro.1 weekly/rolling30 |
| Str.3 Pro.2 | STR3_PRO2_CHAT_ID | nur Pro.2 | Pro.2 |
| … Pro.3–Pro.7 | STR3_PRO3..7_CHAT_ID | nur jeweilige Gruppe | jeweilige |
| Str.3 Pro.8 | STR3_PRO8_CHAT_ID | nur Pro.8 (Status PRO8_NOT_CONFIGURED bis Freigabe) | nur Status |
| Vergleich | STR3_COMPARISON_CHAT_ID | Vergleichs-/Übersichtsberichte, Rankings, Filterwirkung | ja |
| System | STR3_SYSTEM_CHAT_ID | Fehler/Datenqualität/Neustart/kritische Warnungen | — |

Regeln: (a) Varianten senden AUSSCHLIESSLICH an ihre Gruppe. (b) Fehlt STR3_SYSTEM_CHAT_ID → Systemmeldungen
an STR3_COMPARISON_CHAT_ID. (c) Fehlt eine VARIANTEN-Chat-ID bei aktiver Variante → klare Konfig-WARNUNG,
KEIN Fallback in eine andere Variantengruppe (Test 18). (d) FILTER_REJECTED und DATA_QUALITY_REJECTED werden
standardmäßig NICHT je Kandidat gesendet — nur in DB gespeichert und aggregiert in Berichten.

## 5. Nachrichtentypen (16) + Metadaten
Typen: WATCHLIST_NEW · NEAR_TRIGGER · TRIGGER_CONFIRMED · TRADE_OPENED · FILTER_REJECTED(aggregiert) ·
STOP_MOVED · TARGET_HIT · STOP_HIT · BREAK_EVEN_EXIT · TRADE_CANCELLED · DATA_QUALITY_REJECTED(aggregiert) ·
WEEKLY_REPORT · ROLLING_30D_REPORT · CALENDAR_MONTH_REPORT(optional, klar getrennt) · STRATEGY_STATUS ·
SYSTEM_WARNING.
Jede Meldung trägt zwingend: strategy_id, strategy_version, message_type, symbol, signal_id/trade_id,
target_chat_id, created_at_utc. Signal-/Trade-Meldungen zusätzlich alle Felder aus <telegram_signalmeldung>
(Richtung, Einstieg/Stop/Ziel, R:R, Taps, Linienalter in Kalendertagen, Winkel, Apex-Distanz, ATR(14),
Datenqualität, bestandene/nicht anwendbare Filter, parent_signal_id) + Hinweis „Paper-Trading – keine echte
Order". Einzelmeldungen v. a. für WATCHLIST_NEW, NEAR_TRIGGER, TRADE_OPENED, STOP_MOVED, TARGET/STOP_HIT,
BREAK_EVEN_EXIT — Rest aggregiert. rollierend-30 wird NIE als Kalendermonat bezeichnet.

## 6. Konfigurationsmodell (.env, Validierung beim Start)
Neue Schlüssel (Werte NUR in echter .env; .env.example nur leere/fiktive Platzhalter):
```
TELEGRAM_BOT_TOKEN=              # REQUIRED wenn Telegram aktiv
TELEGRAM_AUTHORIZED_USER_IDS=    # REQUIRED wenn Befehle aktiv (Allowlist, kommagetrennt)
STR3_PRO1..8_CHAT_ID=           # je aktiver Variante REQUIRED
STR3_COMPARISON_CHAT_ID=         # REQUIRED wenn Vergleich aktiv
STR3_SYSTEM_CHAT_ID=             # OPTIONAL (sonst Fallback Comparison)
REPORT_TIMEZONE=Europe/Berlin
WEEKLY_REPORT_DAY=Sunday
WEEKLY_REPORT_TIME=20:00
ROLLING_30D_REPORT_TIME=20:30
TELEGRAM_MAX_RETRIES=            # NUTZERENTSCHEIDUNG (Vorschlag 5)
TELEGRAM_RETRY_BACKOFF_SECONDS=  # NUTZERENTSCHEIDUNG (Vorschlag 30, exponentiell)
```
Start-Validierung klassifiziert je Schlüssel: REQUIRED · OPTIONAL · DISABLED_BY_CONFIGURATION. Fehlt eine
Chat-ID einer AKTIVEN Variante → eindeutige Warnung; Strategie läuft lokal weiter (Paper-Trading unberührt).

## 7. Warteschlangen- & Idempotenzmodell
Persistente Queue (lokale DB/JSON, Neustart-fest). Felder: queue_message_id, message_idempotency_key,
target_chat, strategy_id, message_type, payload_reference (Verweis auf DB-Datensatz, KEINE Geheimnisse),
created_at, next_retry_at, retry_count, last_error_class, delivery_status (PENDING/SENT/FAILED_PERMANENT).
Ablauf: Erzeugen → PENDING; Sendeversuch; Erfolg → SENT (+ telegram_message_id); Fehler → Backoff (exponentiell)
bis MAX_RETRIES → FAILED_PERMANENT (in Zustellungsbericht). `message_idempotency_key` = deterministisch aus
(strategy_id, message_type, signal_id/trade_id, period) → höchstens einmal zugestellt. Berichte: pro
(report_type, period, strategy_version) nur EINMAL (report-Datensatz mit report_id, file_hash, delivery_status,
retry_count, generated_at/sent_at in UTC; Zeiträume in REPORT_TIMEZONE bestimmt, als UTC gespeichert).

## 8. Sicherheitskonzept
- Token/volle Chat-IDs NIE in Logs/Fehlern/Berichten/Backups. **KRITISCH-Fix:** aktuelles
  `print("Telegram-Fehler:", e)` kann Token-haltige URL loggen → `redact.py` maskiert Token/URLs/IDs.
- Token/IDs ausschließlich aus `.env`; nie im Quellcode/Tests/Beispieldateien; `.env` nie in Versionskontrolle/Backup.
- Befehle: Allowlist `TELEGRAM_AUTHORIZED_USER_IDS`; User-ID UND Chat-ID getrennt validieren; unbekannte
  Nutzer erhalten nichts und lösen nichts aus. Nur feste, erlaubte `/command`s; Eingaben normalisieren.
- Verboten: eval/exec/Shell, beliebige Dateipfade/SQL aus Telegram, Konfigänderung ohne gesonderte
  Authentisierung + ausdrückliche Freigabe, echte Broker-/Order-Funktionen. Status/Berichte nur lesend,
  dürfen die Analyse-Engine nicht blockieren. Jede Signalmeldung enthält den Paper-Trading-Hinweis.

## 9. Testplan (Mock-Transport, keine echten Gruppen)
Die 30 Telegram-Tests aus <telegram_testanforderungen> werden in TEST_PLAN.md/TEST_RESULTS.md geführt
(Routing exklusiv je Variante, Vergleich/System-Routing, Fallback-Regeln, Queue/Idempotenz, Einmal-Versand je
Zeitraum/Version, Allowlist, Variantentrennung, parent_signal_id, Neustart-Recovery, keine Secrets in Logs,
Telegram-Ausfall ändert keine Trades/stoppt keinen Scan, rollierend-30 ≠ Kalendermonat, Europe/Berlin→UTC,
DST-Korrektheit, kein eval/exec, Paper-Trading-Hinweis, Zustellnachweise je Variante). Zusätzlich EIN
dokumentierter, kontrollierter manueller Integrationstest mit SEPARATEN Test-Gruppen (nicht produktiv).

## 10. Migrationsplan (Reihenfolge aus Spez, nachgelagert)
Erst NACH Freigabe des Strategie-/Daten-Audits: 1 Konfig+Validierung → 2 Transportabstraktion →
3 Routing → 4 persistente Queue → 5 Idempotenz → 6 Nachrichtenmodelle → 7 Variantenkanäle → 8 Vergleichsgruppe
→ 9 Systemgruppe → 10 Berichtszustellung → 11 autorisierte Befehle → 12 Unit-Tests → 13 Integrationstests
(Mock) → 14 kontrollierter Test mit Test-Gruppen → 15 Doku → 16 Nutzerfreigabe → 17 Aktivierung im Paper-
Betrieb. Jede Stufe ist rückrollbar; Altpfad bleibt bis zum Umzug. Keine Telegram-Komponente dupliziert
Strategie/Daten/Trade-Berechnung.
