# OPEN_QUESTIONS.md — Status (nach Prompt 2)

> Prompt 2 („Verbindliche Zusatzpräzisierungen") hat VORRANG bei Mehrdeutigkeit und stuft mehrere am
> 15.07. bestätigte Defaults wieder zurück. Kein offener Grenzwert darf durch einen „sinnvollen Default"
> produktiv aktiviert werden. Zustände: NOT_CONFIGURED · DIAGNOSTIC_ONLY · USER_DECISION_REQUIRED.

## A. Bleiben gültig (durch Prompt 2 NICHT widerrufen)
- #1 Einstieg = Open der nächsten handelbaren Kerze — GÜLTIG.
- #2 Grundprinzip Sub-2R ⇒ REJECTED_RR (kein Trade) — GÜLTIG (Zonendefinition selbst siehe C).
- #5 Kosten brutto+netto parallel, Klassensätze + 0,05 ATR Slippage (Datenerfassung) — GÜLTIG.
  ABER: prozentuale Reporting-Definitionen NOT_CONFIGURED bis separate Prozent-/Reporting-Spez (Präz. 6).
- #6 Mindestdauer 21 Kalendertage + ≥6-Bar-Spacing — GÜLTIG.
- #9 Universum ~95, Erweiterung nach Tests — GÜLTIG.
- #10 4h-Anker je Assetklasse als Startannahme (ANNAHME) — GÜLTIG.
- #12 ATR-Regime (Pro.4) Fenster 100 / 20.–90. Perzentil — GÜLTIG.
- #13 Cache additiv — GÜLTIG. ABWEICHUNG: Format vorerst CSV statt Parquet (pyarrow nicht installiert);
  Interface storage-agnostisch, jederzeit auf Parquet umstellbar. Ort: `Prototyp/data_cache/` (bei Live).

## B. Vom Nutzer bereits explizit gesetzt (kein „stiller Default")
- Apex-BAR-Grenze = 180 4h-Kerzen (ausdrückliche Nutzeranweisung 15.07.). Bleibt.
  Präz. 1 stellt klar: Apex liegt bei aktivem Keil in der ZUKUNFT (nicht Vergangenheit), muss eindeutig
  berechenbar sein und nach den Ausgangspunkten liegen. — umgesetzt in converges().

## C. WIEDER GEÖFFNET / NEU OFFEN durch Prompt 2 (blockieren produktive Aktivierung)
- **NUTZERENTSCHEIDUNG — Apex-KALENDERgrenze (Präz. 1).** Meine frühere „≤45 Tage" war ein Default und ist
  zurückgezogen. Max. Apex-Distanz in Kalendertagen zusätzlich zu 180 Kerzen ist offen. Status:
  USER_DECISION_REQUIRED. (bis dahin nur Bar-Grenze aktiv, Kalendertage diagnostisch gespeichert)
- **NUTZERENTSCHEIDUNG — Stop-ATR-Grenzen (Präz. 7).** Meine „0,5–6 ATR" ist zurückgezogen. Min/Max
  Stop-Distanz nicht freigegeben. Status: DIAGNOSTIC_ONLY (Wert nur speichern, nicht filtern).
- **NUTZERENTSCHEIDUNG — vollständige S/R-Definition (Präz. 8).** Zu klären: Pivot-Grundlage · nötige
  Reaktionszahl · ATR-Zonenbreite · maximale Zonenalterung · Gewichtung Wicks vs. Schlusskurse ·
  Zusammenführung überlappender Zonen · Regel für bereits durchbrochene Zonen · Definition „nächstgelegene
  relevante Zone". Meine „≥2 Reaktionen, 0,6 ATR" ist nur ein Vorschlag. Status: USER_DECISION_REQUIRED.
- **NUTZERENTSCHEIDUNG — Prozent-/Reporting-Spezifikation (Präz. 6).** Trade-Rendite %, Summe +/−%,
  Netto-%, Kontorendite, Positionsgrößenmodell, Drawdown %, vor/nach Kosten. Keine eigene %-Berechnung
  bis zur separaten Spez. Status: NOT_CONFIGURED.
- **NUTZERENTSCHEIDUNG — Telegram-Verteilungs-Spezifikation (Präz. 5).** Separate verbindliche Spez.
  Status: NOT_CONFIGURED. TEILWEISE geklärt: Freigabe-/Informationsmodell = MODUS B (autonom, Per-Trade-
  Info-Nachrichten ohne Zustimmung) — bestätigt 15.07.; offen bleiben Format/Takt/Kanäle der Zustellung.
- **NUTZERENTSCHEIDUNG — Break-even-Matrix-Aktivierung (Präz. 11).** Aktiv nur die Mindest-Kontrollen
  Pro.1+BE-0 und Pro.1+BE-1; alle weiteren Kombinationen brauchen dokumentierte Freigabe.
  Status: USER_DECISION_REQUIRED (für weitere Kombinationen).
- **NUTZERENTSCHEIDUNG — Testzeitraum (Präz. 12).** Startdatum, Startzeit, Enddatum, Endzeit,
  Berichtszeitzone, Definition „zwei Monate". Kein Auto-Start ohne diese Angaben. Status:
  USER_DECISION_REQUIRED. #11-Bedingung „erst wenn 22 QS-Tests grün" bleibt zusätzlich bestehen.
- **Pro.7 (Präz. 9):** DIAGNOSTIC_ONLY — nach 2 Wochen KEINE automatische Schwellen-Aktivierung; nur mit
  schriftlicher Freigabe + neuer Versionsnummer + Parametern + Startdatum + getrennter Ergebnisreihe.
- **Pro.8 (Präz. 10):** PRO8_NOT_CONFIGURED — handelt erst nach vollständig algorithmisch definierter,
  freigegebener Daily-Marktstruktur. Keine stille HH/HL/LH/LL-Definition.

## D. Telegram-Mehrkanal (aus Telegram-Spez, vor Umsetzung zu klären)
- **NUTZERENTSCHEIDUNG — Telegram überhaupt aktiv?** Empfehlung: lokal-zuerst bauen (DB + PDF verbindlich),
  Telegram als optionale Ausgabeschicht, aktiv erst wenn du die 10 Gruppen erstellt hast. (kostet 0 Credits)
- **NUTZERENTSCHEIDUNG — Geheimnisse liefern:** 10 Chat-IDs (Pro.1–8, Vergleich, System) + deine
  autorisierte(n) User-ID(s). Diese trägst DU selbst in `.env` ein; ich hardcode nichts. Setup: TELEGRAM_SETUP.md.
- **NUTZERENTSCHEIDUNG — Retry-Parameter:** TELEGRAM_MAX_RETRIES (Vorschlag 5), TELEGRAM_RETRY_BACKOFF_SECONDS
  (Vorschlag 30, exponentiell).
- **NUTZERENTSCHEIDUNG — Berichtsterminierung bestätigen:** REPORT_TIMEZONE=Europe/Berlin, WEEKLY_REPORT_DAY=
  Sonntag, WEEKLY_REPORT_TIME=20:00, ROLLING_30D_REPORT_TIME=20:30.
- **NUTZERENTSCHEIDUNG — MIN_CLOSED_TRADES_FOR_RANKING=30** bestätigen (Varianten darunter =
  UNZUREICHENDE_STICHPROBE, keine „Gewinner"-Behauptung).
- **NUTZERENTSCHEIDUNG — optionaler CALENDAR_MONTH_REPORT** zusätzlich zum rollierenden 30-Tage-Bericht
  erzeugen? (klar getrennt gekennzeichnet). Vorschlag: optional ja.
- **NUTZERENTSCHEIDUNG — Systemgruppe:** STR3_SYSTEM_CHAT_ID konfigurieren (empfohlen) oder Fallback auf
  Vergleichsgruppe.

## Verbleibende Blocker vor produktiver Aktivierung
1. Alle Punkte unter C entschieden/definiert.
2. Bestandene Testsuite (Phase G, 22+ QS-Fälle) inkl. 30 Telegram-Tests (falls Telegram aktiv).
3. Unveränderliche Testkonfiguration mit Zeitraum-Parametern (Präz. 12) in DECISIONS.md hinterlegt.
4. Telegram (falls aktiv): 10 Ziele erstellt, .env befüllt, kontrollierter Test mit Test-Gruppen bestanden.
