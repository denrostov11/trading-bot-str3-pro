# DATA_QUALITY.md — Datenquellen-Risiken & Qualitätsstatus

> Stand: 15.07.2026 (Phase A). Wird ab Phase C je Zyklus fortgeschrieben; Detailstatus je Symbol → SYMBOL_STATUS.csv.

## Bekannte Risiken der aktuellen Datenschicht (Yahoo Finance via yfinance)
1. **Kein lokaler Cache** — Intraday-Historie wird nicht gesichert. Yahoo liefert 1h nur ~730 Tage, 15m nur
   ~60 Tage. Ohne additive Persistenz gehen ältere Intraday-Daten unwiederbringlich verloren. (C1, KRITISCH)
2. **Kein Retry/Backoff/Timeout** — einzelne Ausfälle erzeugen stille Lücken. (C2, KRITISCH)
3. **4h-Aggregation ohne Zeitzone/Session/DST** — Kerzen falsch geschnitten; letzte Kerze oft unvollständig,
   wird aber analysiert. (A1/A2, KRITISCH)
4. **Kein Rollover-/Datenbruch-Check** — Futures-Sprünge verzerren Linien. (C4, KRITISCH)
5. **Volumen unvalidiert** — FX/Index liefern 0/kein echtes Börsenvolumen; für Pro.3/5 unbrauchbar bis
   Validierung. (C5, KRITISCH für Volumenvarianten)
6. **Fehlende Daten dürfen nie durch erfundene Preise ersetzt werden** — aktuell kein Auffüll-Mechanismus
   (gut), aber auch keine Kennzeichnung fehlender Bars.

## Zu erhebende Kennzahlen (ab Phase C, je Symbol in SYMBOL_STATUS.csv)
first_valid_timestamp, last_valid_timestamp, number_of_1h/4h/15m_bars, missing_bar_ratio, duplicate_count,
zero_volume_ratio, suspected_rollover_dates, expected_volume_quality, intraday_available, daily_available,
last_data_quality_status, enabled, disable_reason.

## Ausgelassene Instrumente (keine freie Yahoo-Quelle) — Stand Projekt
Nickel, Zink, Blei, Eisenerz, Propan, LNG → enabled=false, disable_reason="keine freie Datenquelle".
