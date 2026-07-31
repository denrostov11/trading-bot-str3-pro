# TRADING-BOT — MASTER-DOKUMENTATION (Wiederaufbau-Grundlage)

> Stand: 15.07.2026 · Diese Datei enthält ALLE Strategien, Kriterien, Parameter und den
> Projektverlauf. Zusammen mit dem Backup-Ordner reicht sie, um das Projekt auf einem
> neuen PC vollständig wiederherzustellen. Wird alle 12 h automatisch mitgesichert.

---

## 0. GRUNDSÄTZE (verbindlich, für alle Strategien)
- Zuerst **Paper-Trading** (kein echtes Geld); Live erst nach ausdrücklicher Freigabe des Nutzers.
- Alle Strategien gelten für **steigende UND fallende Kurse** (Long & Short).
- Claude ist **kein Anlageberater**, führt **keine echten Trades** aus, bewegt **kein Geld**.
  Der Bot analysiert und meldet; **der Nutzer prüft und entscheidet jeden Trade selbst**.
- Nutzer: Denis (denrostov11@gmail.com), Projektordner: `Desktop\Claude Code\Trading_Bot\`.

---

## 1. STRATEGIE 1 — Nachrichtengetriebene Trade-Auswahl
**Idee:** Zum Handelsstart die Nachrichtenlage auf 10–20 ausgewählten Seiten analysieren
und daraus den optimalen Trade ableiten (Long oder Short), mit Begründung.

**Analyse-Filter:** neue Technologien/Produkt-Releases · politische Lage & ganz aktuelle
politische Entscheidungen · neue Firmenverträge/Kooperationen · sonstige marktrelevante
Ereignisse für den anbrechenden Handelstag.

**Anlageklassen:** Aktien, Indizes, Währungen (FX), Krypto.

**Risiko:** Stop-Loss max. **2 %** des Gesamteinsatzes. Take-Profit **2–5 %**, aber
**dynamisch je Anlageklasse** (Indizes/FX bewegen sich intraday meist <1 %/Tag → enge
Ziele; Aktien/Krypto volatiler → weitere Ziele). Starres 2–5 %-Ziel wäre bei Indizes/FX
unrealistisch — die dynamische Anpassung ist zentral.

**Umsetzung:** Forward-Paper-Trading in **Echtzeit** (kein historisches Backtesting —
alte News nicht point-in-time rekonstruierbar → Look-Ahead-Bias). Start: **Alpaca**
(kostenloses Echtzeit-Paper-Konto, `alpaca-py`, Aktien+Krypto). Später **Interactive
Brokers Paper** (alle 4 Klassen). OANDA-Demo als FX-Option.

**Kosten:** ~0,05–0,60 €/Analyse (Haiku ~0,05 · Sonnet ~0,15 · Opus 4.8 ~0,25).
Szenarien: Sparsam ~1 €/Mo · Standard ~33 €/Mo · Premium ~130 €/Mo.

---

## 2. STRATEGIE 2 — Mean-Reversion / Fade überdehnter Bewegungen
**Idee:** Gegen einen Kurs setzen, der am Handelstag ggü. den letzten **2 Monaten
(Tagesbasis)** übermäßig stark gestiegen/gefallen ist. Erst **1–2 h beobachten**, dann
nur bei bestätigter Umkehr handeln. (Kriterium „übermäßige Bewegung" fließt zusätzlich
in die News-Analyse aus Strategie 1 ein.)

**Schwellen:** Aktien/Krypto **±5–10 %** · Indizes/FX **±1–2 %**.

**Einstiegs-Trigger (5-Minuten-Kerzen):**
- SHORT: Wert im Plus (s.o.), bildet **erstmals ein tieferes Hoch**, und eine 5-Min-Kerze
  **schließt unter dem Tief der Vorkerze**.
- LONG: Wert im Minus, bildet **erstmals ein höheres Tief**, und eine 5-Min-Kerze
  **schließt über dem Hoch der Vorkerze**.

**Risiko:** Stop max. **2 % des Tradewerts**; alternativ knapp über letztem Hoch (Short)
bzw. knapp unter letztem Tief (Long). Take-Profit **>1–2 % über dem Spread**.

**Veto (NICHT handeln):** veröffentlichte Quartalszahlen · angekündigte Übernahmen ·
Zulassungen/Gerichtsentscheidungen · andere sehr bedeutende Unternehmensnachrichten
(echter Katalysator — Kurs kann tagelang weiterlaufen). Außerdem: sehr geringe
Liquidität, Penny Stocks, extrem breite Spreads.

**Marktregime-Filter:** sehr starker Gesamtmarkt → keine Shorts gegen besonders starke
Werte; sehr schwacher Gesamtmarkt → keine Longs auf besonders schwache Werte.

**Backtesting:** über 5–10 Jahre sinnvoll (technischer Kern aus Kursdaten
rekonstruierbar; QuantConnect geeignet). Vorbehalte: News-Veto braucht historische News
point-in-time; Survivorship-Bias, Spread/Slippage, Short-Leihbarkeit.

**Kosten:** Sparsam ~1 €/Mo · Standard ~55–60 €/Mo · Premium ~320–370 €/Mo
(Treiber: Echtzeit-Intraday-Daten + 5–10 J. Minutenhistorie + hist. News).

---

## 3. STRATEGIE 3 — Trendlinien-Bruch (4h-Swing) ★ IN UMSETZUNG ★
> **Namenskonvention (13.07.2026):** Die reine Original-Strategie = **„Str.3 Pro.1"**.
> Weitere Filter-Varianten folgen als Pro.2, Pro.3, … — Ergebnisse werden je Prototyp
> getrennt getrackt, damit vergleichbar ist, welche Filter die Bilanz verbessern.
Quelle: PDF „Tori Trades – Trend Line Strategy" (`Downloads\Tori Trades Trendlines.pdf`).
Rein technisch, KEINE News nötig. Fokus **Futures**, längere Swing-Trades (kein Intraday).

**Instrumente (Original):** Platin PL1!, Rohöl CL1!, Gold GC, DOW YM
(CFDs: XPTUSD, WTI, XAUUSD, US30). Erweitert auf ~95 Instrumente (s. Scanner).

**A+-Trendlinien-Kriterien (ALLE müssen erfüllt sein):**
1. **3+ Taps** (Wicks) in die Linie vor dem Bruch (2 möglich, 3+ bevorzugt)
2. **6+ Kerzen Abstand** zwischen den Taps (gute Spacing)
3. **< 45° Steigung** (bezogen auf 3 Monate im Chart)
4. So gezeichnet, dass sie **möglichst viele Wicks** trifft
5. **> 3 Wochen Preisdaten** von Start bis Bruch

**Action-Line vs. Safety Line (WICHTIG — Nutzer-Korrektur vom 06.07.2026):**
Zwei GEGENLÄUFIGE Trendlinien bilden ein zusammenlaufendes Dreieck (Wedge):
- SHORT: Action = steigende Support-Linie (Taps = höhere Tiefs), Bruch nach unten.
  Safety = fallende Resistance-Linie DARÜBER (**≥2 Taps in Gegenrichtung**).
- LONG: Action = fallende Resistance-Linie (Taps = tiefere Hochs), Bruch nach oben.
  Safety = steigende Support-Linie DARUNTER (≥2 Taps in Gegenrichtung).
- **REGEL (Nutzer, 13.07.2026): Die Safety Line muss wie die Action-Line INTAKT sein —**
  **sie darf keine Kerzen(-schlüsse) durchkreuzen.** Wick-Berührungen = Taps sind erlaubt.
  Umsetzung: pick_safety() verwirft gebrochene Gegenlinien (breaking_bar > 0).
- **REGEL (Nutzer, 15.07.2026): Action- und Safety-Line müssen KONVERGIEREN (Keil).**
  Parallel oder quasi-parallel ist UNZULÄSSIG — die Linien müssen aufeinander zulaufen,
  zwischen ihnen entsteht ein sich schließender Keil. Umsetzung: converges() in
  scan_100.py — der Linien-Abstand muss nach rechts schrumpfen und der Schnittpunkt
  (Apex) darf höchstens MAX_APEX_BARS=**180** 4h-Kerzen (~30 Handelstage / ~6 Wochen)
  in der Zukunft liegen (15.07.2026 abends von 540 auf 180 verschärft).

**Einstieg/Stop/Ziel:**
- Einstieg: **4h-Kerze schließt jenseits der Action-Line**.
- Stop: an der Safety Line — mechanisch dort, wo die **4. Kerze nach dem Bruch** die
  Safety Line träfe.
- Take-Profit: nächste horizontale **S/R-Zone mit mind. 2R**. Optimierung: prüfen, ob
  Halten bis zum Bruch der aktuellen Trendlinie besser ist.
- **BREAK-EVEN-AUTOMATIK (Nutzer, 15.07.2026):** Läuft der Kurs nach Einstieg in
  Gewinnrichtung und kreuzt den Einstieg um mindestens die **Klassen-Schwelle**
  (**0,3 %** bei Währungen & Indizes — wachsen langsam · **1,0 %** bei Krypto, Aktien
  und anderen volatileren Produkten), wird der Stop automatisch von der Safety-Line
  auf **knapp jenseits des Einstiegs** nachgezogen (Puffer = 10 % der Schwelle, also
  0,03 % bzw. 0,1 %) → der Trade kann kein Geld mehr verlieren. Die Schwelle
  verhindert, dass ein kurzer Ausflug über den Einstieg den Trade fast bei null
  beendet. **Geprüft wird auf 15-MINUTEN-Kerzen (Schlusskurse, alle 15 Min) — dies ist
  der EINZIGE Mechanismus auf 15m; alle anderen Mechanismen nutzen ausschließlich
  1h/4h-Kerzen.** R-Ergebnisse bleiben auf den ORIGINAL-Stop bezogen (stop_initial);
  Ausstieg über den nachgezogenen Stop wird als 🟡 BREAK-EVEN gemeldet.
- Nur **EIN Versuch pro Trendlinie**. Futures-**Rollover** beachten.
- **REGEL (Nutzer, 15.07.2026): Pro Instrument nie zwei Trades gleichzeitig oder direkt
  hintereinander** — solange ein Trade offen ist, ist das Instrument gesperrt; nach
  Trade-Ende gilt eine **Abkühlzeit von 24 h**; ein neuer Trade braucht eine **neu
  konstruierte Linie** (Linien-Vergleich über Art + Ankerpreis + Steigung, nicht über
  den wandernden Bar-Index). Bei gesperrtem Instrument wird auch **kein Trigger-Alert**
  gesendet.

**Workflow (Nutzer-Vorgabe):** Bot macht die Vorarbeit (erkennt A+-Linien in Echtzeit,
Kandidaten so gewählt, dass der **Einstieg noch bevorsteht**), meldet Chancen per Alert
inkl. News-Daten; Nutzer prüft die Charts und entscheidet selbst. Erst Paper, später real.

**Ergänzungsvorschläge (Claude, optional):** Fehlausbruch-Filter (ATR-Puffer/Retest) ·
Volumen-/ATR-Bestätigung · Higher-Timeframe-Filter · Earnings-/Rollover-Blackout ·
Teilgewinn bei 1R + Break-even · RANSAC-Linien-Fit · 0,5–1 % Risiko/Trade, Expectancy tracken.

**Ehrliche Bewertung:** mechanisch & backtestbar (Pro) · Trendlinien-Automatik
anspruchsvoll, wenige Trades, Fehlausbrüche, ~35–45 % Trefferquote bei 2R üblich (Contra).
Gewinnerwartung ehrlich: falls Edge vorhanden ~5–20 %/Jahr; null/negativ möglich.
Mehrheit privater Algo-Trader verliert Geld. Erst Backtest+Paper = gemessene Zahlen.

---

## 4. TECHNISCHE UMSETZUNG (Stand 11.07.2026)

### 4.1 Umgebung
- **Python 3.12** (winget, `%LOCALAPPDATA%\Programs\Python\Python312`)
- venv: `Trading_Bot\Prototyp\venv` — Pakete: yfinance, pandas, numpy, matplotlib, requests
- Daten: **Yahoo Finance** (1h → 4h resampled, kostenlos). Später: IBKR (Echtzeit), QuantConnect/Databento (Backtest).

### 4.2 Erkennungs-Parameter (scan_100.py — Referenzwerte)
| Parameter | Wert | Bedeutung |
|---|---|---|
| WINDOW_BARS | 540 | Analysefenster (~3–4 Monate 4h-Kerzen) |
| THREE_MONTH_BARS | 390 | Winkel-Normierung (3 Monate) |
| PIVOT_K | 3 | Fractal-Pivots: Extrem von je 3 Kerzen links/rechts |
| MIN_TAPS / MIN_TAPS_SAFETY | 3 / 2 | A+-Action / Safety-Minimum |
| MIN_SPACING | 6 | Kerzen zwischen Taps |
| MIN_DURATION | 90 | Bars (> 3 Wochen) |
| MAX_ANGLE_DEG | 45 | normiert: Anstieg über 390 Bars relativ zu 25 % Referenzpreis |
| TAP_TOL_ATR / BREACH_TOL_ATR | 0.25 / 0.15 | Tap-/Bruch-Toleranz in ATR(14) |
| Watchlist: MAX_PROX_ATR / MAX_SAFETY_ATR | 5 / 10 | Kurs-Nähe zur Linie / max. Stop-Distanz |
| Alert: NEAR_ATR / TRIGGER_MAX_AGE | 1.0 / 3 | Vorwarnung / max. Bruch-Alter (Kerzen) |
| Safety-Auswahl | nächstgelegene Gegenlinie | Abstand in ATR am rechten Rand + Tap-Frische |
| MAX_APEX_BARS | 180 | Keil-Regel: Apex (Schnittpunkt) max. 180 Kerzen voraus |
| BE_CHECK_SECONDS | 900 | Break-even-Prüfung alle 15 Min (15m-Kerzen, NUR hierfür) |
| BE_TRIGGER_PCT | 0,3 % / 1,0 % | BE-Schwelle FX+Indizes / volatilere Produkte |
| BE_BUFFER_FRACTION | 0,1 | BE-Stop-Puffer = 10 % der Schwelle jenseits des Einstiegs |
| TRADE_COOLDOWN_H | 24 | Instrument-Abkühlzeit nach Trade-Ende |
| S/R-Zonen | Pivot-Cluster, Toleranz 0.6 ATR | Ziel = nächste Zone mit ≥2R |
| Score (Watchlist) | Taps×10 − Winkel×0,3 + (5−Nähe)×8 + (10−Safety)×2 | Ranking |

### 4.3 Dateien (alle in `Trading_Bot\`)
- `Strategien_1_bis_3_Zusammenfassung.docx` (v3.2, 15.07.2026) + `.pdf` (12 S.) — Gesamt-Doku,
  4 Charts; NEU: Safety-Line-Regel in C4, Umsetzungsstand als C10
- `Trading-Bot_Strategien_1-2_Praesentation.pptx` — 15 Folien (Str. 3 fehlt noch)
- `Strategie_3_Dialog.docx/.pdf` — kompletter Strategie-3-Dialog im Wortlaut, Runden 1–34,
  06.–13.07.2026 (48 S., fortgeschrieben am 15.07.2026; inkl. Prototyp-Erkennungscharts
  + Demo-Ergebnisbild)
- `Strategie3_*.png` — 4 Referenz-Beispielcharts
- `Prototyp\trendline_prototype.py` — Erkennung v1 (4 Instrumente)
- `Prototyp\scan_100.py` — Scanner (95 Instrumente + Ranking)
- `Prototyp\watchlist.py` — nur „Einstieg steht bevor"-Setups + Trigger-Box
- `Prototyp\alert_bot.py` — Telegram-Alert-Bot (läuft dauerhaft) + 12h-Backup
- `Prototyp\telegram_setup.py`, `resend_btc.py` — Hilfsskripte
- `Prototyp\state.json` (Alert-Dedup), `bot_config.json` (Nachtmodus/Queue/Offsets/Berichts-Zeitstempel)
- `Prototyp\trades.json` — Paper-Trade-Tracker (inkl. Linien-Anker je Trade)
- `Scan_100\`, `Watchlist\`, `Alerts\`, `Trades\` — generierte Charts + Rankings
- `Str.3 Pro.1\` — Kopien aller Trade-Bilder · `Str.3 Pro.1\Berichte\` — PDF-Berichte

### 4.4 Telegram-Bot
- Bot: **@Str3_trading_alerts_bot** · Chat-ID: <DEINE_TELEGRAM_USER_ID> (nur diese darf steuern; echter Wert nur in lokaler `.env`)
- Token: in `Prototyp\.env` (NICHT im Backup — beim BotFather per `/token` wieder abrufbar,
  bei Verlust `/revoke` + neu; danach Token neu in `.env` eintragen)
- Alerts: 🚨 Trigger (Chart + Einstieg/Stop/Ziel, deutsches Zahlenformat 64.380,04) ·
  ⚠️ <1 ATR Vorwarnung · Dedup via state.json · max 10 Msg/Zyklus
- Befehle: **„gute nacht"** (stumm, Queue) · **„guten morgen"** (Digest) · **„status"** · **„bilanz"** (Paper-Trading-Bilanz)
- **Paper-Trade-Tracker (13.07.2026):** Jeder Trigger mit Stop+Ziel eröffnet automatisch
  einen virtuellen Trade (`Prototyp\trades.json`, ein Versuch pro Trendlinie). Stündliche
  Prüfung: Stop oder Ziel von High/Low berührt? (konservativ: beide in einer Kerze → Stop
  zählt). Bei Abschluss: Telegram-Ergebnis ✅/❌ mit **Vorher/Nachher-Kombi-Bild**
  (`Trades\<id>_result.png`: Einstiegs-Chart oben, Ausgangs-Chart mit Einstieg/Stop/Ziel-
  Linien + Exit-Marker unten) und allen Daten: Richtung, Einstieg/Ausgang mit Zeiten,
  Stop/Ziel, Ergebnis in ±R und ±%, Dauer in Tagen. „bilanz" zeigt Trefferquote, Gesamt-R,
  letzte Trades, offene Positionen. Erster getrackter Trade: Bitcoin LONG @64.378,16
  (Stop 63.268,15 / Ziel 67.095,67 / 2,4R) vom 10.07.2026.
  **Duplikat-Schutz (15.07.2026):** `open_paper_trade()` prüft vor jedem neuen Trade:
  (1) kein offener Trade auf demselben Instrument, (2) 24 h Abkühlzeit
  (`TRADE_COOLDOWN_H`) nach dem letzten Trade des Instruments, (3) Linie noch nie
  gehandelt (`same_line()`: Art + Ankerpreis ±0,1 % + Steigung ±5 %). `line_sig()` ist
  seit 15.07. index-frei (`kind:p0:slope`); state.json wurde migriert. Trigger-Alerts
  werden bei offenem Trade auf dem Instrument komplett unterdrückt; Alert-Text sagt
  ehrlich, ob ein Paper-Trade eröffnet wurde. 12 parallele Alt-Duplikate (Kupfer, DAX,
  Heizöl, Palladium, Erdgas, AUD/JPY, EUR/AUD, CAD/JPY) am 15.07. als
  status=„cancelled" storniert — Bilanz/Berichte zählen nur „open"/„closed".
- Zyklus: Scan stündlich, Befehls-Poll minütlich
- Autostart: `TradingBot_AlertBot.vbs` im Windows-Startup-Ordner (pythonw, unsichtbar);
  manuell: `Alert-Bot starten.bat`. pythonw-Log: `Prototyp\bot_log.txt`.
  Hinweis: venv-pythonw zeigt 2 Prozesse (Launcher+Interpreter) = EINE Instanz.

---

### 4.5 Berichte & Bild-Auflösung (13.07.2026, Berichtsformat v4 = FINAL)
- Trade-Bilder (Alert-, Exit-, Vorher/Nachher-Kombi-Chart) in **300 DPI (~4K, ~3900 px)**.
- Kopien aller Trade-Bilder zusätzlich in `Trading_Bot\Str.3 Pro.1\`.
- **PDF-Berichte automatisch alle 7 + alle 30 Tage** → `Str.3 Pro.1\Berichte\`; Versand als
  Telegram-**Dokument** (unkomprimiert), Ankündigung beginnt mit 🤑🤑🤑.
- Telegram-Befehl „bericht" = 7-Tage-Bericht sofort auf Abruf.
- **Berichts-Aufbau (v4, vom Nutzer am 13.07.2026 abends abgenommen — verbindlich):**
  - **Seite 1 „GESAMTZUSAMMENFASSUNG – LETZTE 7 TAGE":** Trades/Trefferquote/Gesamt-R,
    bester & schwächster Trade **nach R gerankt, Anzeige mit R UND %**, offene Trades;
    dazu Aufschlüsselung: **Gewinn (Summe positive Trades, grün) · Verlust (Summe negative
    Trades, rot) · Ergebnis in % nach Verlusten (fett)**.
  - **Seite 2 „Gesamtzusammenfassung ALLER Trades":** gleiche Kennzahlen + gleiche
    Gewinn/Verlust/Netto-Aufschlüsselung über alle Trades seit Start, Beschriftung
    eindeutig „GESAMT-GEWINN (alle Trades)"; darunter **Equity-Kurve** (kumuliertes R).
  - **Trade-Liste:** alle Trades nach Datum; **Gewinner grün, Verlierer rot**.
  - **Detailseiten (Einstiegs- + Ausgangschart in 4K) nur für die Trades des
    Berichtszeitraums (letzte 7 Tage)** — frühere Trades erscheinen nur in der Liste.
  - Prozent-Logik: Summe der Einzeltrade-% bei gleichem Einsatz je Trade (Fußnote im Bericht).
- Trendlinien in Trigger- und Vorher/Nachher-Charts **dünn (lw≈1.0, kleine Tap-Marker)**,
  damit Kerzen sichtbar bleiben. Exit-Charts rekonstruieren die Linien aus den beim
  Trade-Open gespeicherten Ankern (`action_line`/`safety_line` in trades.json).
- **Regel für fiktive Demo-/Beispielcharts (Nutzer, 13.07.2026):** Sie MÜSSEN alle
  A+-Kriterien sichtbar erfüllen (Action-Line mit ≥3 markierten Wick-Taps, ≥6 Kerzen
  Abstand, <45°; Safety Line gegenläufig, ≥2 Taps, INTAKT; Stop = Safety-Projektion
  4. Kerze) — „daran steht oder fällt alles".

## 5. WIEDERAUFBAU AUF NEUEM PC (Kurzanleitung)
1. Claude Code installieren, diesen Backup-Ordner bereitlegen (OneDrive: `TradingBot_Backup`).
2. Claude diese Datei geben — sie enthält alle Strategien/Parameter. Memory-Ordner aus
   Backup nach `%USERPROFILE%\.claude\projects\C--Users-denro-Desktop-Claude-Code\memory\` kopieren.
3. Python 3.12 installieren (`winget install Python.Python.3.12`), venv anlegen,
   `pip install yfinance pandas numpy matplotlib requests`.
4. `Prototyp\`-Skripte aus Backup zurückkopieren; `.env` neu anlegen (Token via BotFather
   `/token`); `telegram_setup.py` ausführen (Chat-ID neu ermitteln).
5. `alert_bot.py --once` testen, dann VBS in den Startup-Ordner (siehe 4.4) und starten.

---

## 6. PROJEKT-CHRONOLOGIE (Kurzfassung)
- **06.07.2026:** Strategie 1 definiert (News-Analyse; Kosten €0,05–0,60/Analyse). Plattform-
  Entscheidung: QuantConnect verworfen (Look-Ahead), Forward-Paper via Alpaca. Word-Doku
  erstellt. Strategie 2 definiert (Fade + 5-Min-Trigger + Veto). Beide in ein Word-Dok
  (Pro/Contra + Kosten) + 15-Folien-Präsentation. Strategie 3 aus Tori-Trades-PDF
  entwickelt; Beispielcharts; **Nutzer-Korrektur Safety Line** (gegenläufig, ≥2 Taps) →
  Charts v2 bestätigt.
- **08.07.2026:** Strategie 3 als Teil C ins Word-Dok (4 Charts, Entwicklungs-/Betriebskosten,
  Fable-5-Aufwand ~6–11 Sessions / API ~60–250 €). Speicher-Skalierung 10→200 Kurse (RAM
  unkritisch, Engpass Datenabos). Gewinnerwartung ehrlich eingeordnet (~5–20 % falls Edge).
- **09.07.2026:** Strategie-3-Dialog als Word+PDF (1:1-Wortlaut, 15 Seiten).
- **10.07.2026:** GO für Python. Session 1: Python 3.12 + venv + Prototyp v1 (4 Futures,
  A+-Erkennung; WTI/Platin-Brüche korrekt gefunden). Nutzer-Feedback „Safety zu weit" →
  Fix (nächstgelegene Gegenlinie). 100er-Scan (95 Instrumente, Ranking; ohne Quelle:
  Nickel/Zink/Blei/Eisenerz/Propan/LNG). Nutzer-Vorgabe „Einstieg muss bevorstehen" →
  Watchlist (69 Setups, Trigger-Box). Session 2: Telegram-Bot eingerichtet (Token/Chat-ID),
  Alert-Bot live (stündlich, Stop/Ziel-Berechnung, Dedup), Autostart, Nachtmodus
  („gute nacht"/„guten morgen"/„status"). Format-Fix (6438e+04 → 64.380,04), BTC-Alert
  neu gesendet (LONG-Trigger, Einstieg 64.378,16, Stop 63.268,15, Ziel 67.095,67, 2,4R).
- **11.07.2026:** Backup-System eingerichtet (dieses Dokument + 12h-Auto-Backup lokal +
  OneDrive).
- **13.07.2026:** **Paper-Trade-Tracker** eingebaut (Bot verfolgt/bewertet seine eigenen
  Signale selbst, Vorher/Nachher-Ergebnisbild, Befehl „bilanz"). **Namenskonvention
  „Str.3 Pro.1"** festgelegt. Bilder auf 4K (300 DPI), eigener Ordner `Str.3 Pro.1\`,
  **automatische 7-/30-Tage-PDF-Berichte** (🤑🤑🤑-Ankündigung, Befehl „bericht").
  **Nutzer-Korrektur: Safety Line muss INTAKT sein (keine Kerzen-Durchkreuzung)** →
  pick_safety()-Fix. Dünne Trendlinien in allen Trade-Charts. Berichtsformat iterativ
  v2→v4 abgestimmt (Gewinn/Verlust-Aufschlüsselung, Ergebnis nach Verlusten, Detailseiten
  nur letzte 7 Tage, frühere Trades nur Liste grün/rot) — **v4 vom Nutzer abgenommen = final**.
- **14.–15.07.2026:** Bot läuft im Dauerbetrieb; erste echte Paper-Trade-Ergebnisse:
  BTC-LONG per Stop −1R (−1,72 %), dazu Mais, 2× NZD/USD, 2× AUD/JPY per Stop,
  EUR/CHF als erster Zielerreicher (+0,53R).
- **15.07.2026:** Alle Dokumente auf Gesamtstand gebracht (Zusammenfassung v3.2 mit C10,
  Dialog-Doku Runden 11–34, Master-Doku, Gedächtnis). **Nutzer-Regel umgesetzt:** keine
  Trades auf gleichem Instrument/gleicher Linie gleichzeitig oder direkt hintereinander;
  jeder Trade braucht eine neu konstruierte Linie → Instrument-Sperre + 24h-Abkühlzeit +
  index-freie Linien-Signatur im Bot; 12 Alt-Duplikate storniert; Bot neu gestartet.
- **15.07.2026 (abends):** Zwei weitere Nutzer-Regeln umgesetzt: **Keil-Regel**
  (Action/Safety müssen konvergieren, converges(); Apex-Grenze zunächst 540, noch am
  selben Abend auf **180** Kerzen verschärft; 6 nicht-konforme offene Trades storniert) und **Break-even-Automatik** (15m-Kerzen, 0,3 %/1,0 %
  Schwelle, Stop knapp jenseits Einstieg). Danach auf Nutzer-Anweisung **ALLE laufenden
  Trades und der Bot GESTOPPT** (Strategie-Anpassung): 19 offene Trades storniert,
  pythonw beendet, **Autostart deaktiviert** (VBS → `TradingBot_AlertBot.vbs.disabled`
  im Startup-Ordner). Gesamtspezifikation als eigenes Dokument erstellt
  (`Str.3_Pro.1_Gesamtspezifikation.docx/.pdf`).

## 7. OFFENE PUNKTE / NÄCHSTE SCHRITTE
- **BOT IST GESTOPPT (15.07.2026 abends, Nutzer-Anweisung — Strategie wird angepasst).**
  Wiederinbetriebnahme: (1) `Alert-Bot starten.bat` doppelklicken ODER pythonw mit
  alert_bot.py starten; (2) Autostart reaktivieren: im Startup-Ordner
  `TradingBot_AlertBot.vbs.disabled` zurück in `TradingBot_AlertBot.vbs` umbenennen.
  ACHTUNG: Solange der Bot steht, laufen auch KEINE 12h-Backups und keine Berichte.
- Beobachtungswoche Alert-Bot; Schwellen nach Nutzer-Feedback justieren.
- **Kriterien-Abgleich Bot vs. Strategie (aufgefallen 15.07.2026):**
  (a) OFFEN — Der Tracker eröffnet auch Paper-Trades mit **R:R < 2** (z. B. Erdgas 0,62R,
  EUR/CHF 0,53R) — laut Strategie ist das Ziel „nächste S/R-Zone mit MIND. 2R"; klären,
  ob solche Signale nur gewarnt (⚠️) oder gar nicht getrackt werden sollen.
  (b) ERLEDIGT 15.07.2026 — Mehrfach-Trades auf dasselbe Instrument/dieselbe Linie sind
  jetzt blockiert (Instrument-Sperre + 24h-Abkühlzeit + Neue-Linie-Pflicht, s. 4.4);
  12 Alt-Duplikate storniert.
- Erster echter 7-Tage-Bericht (fällig ~20.07.2026) im v4-Format prüfen.
- Backtest Strategie 3 über 5–10 Jahre (QuantConnect/Databento) → gemessene Trefferquote/Expectancy.
- Strategie 3 in die Präsentation (Teil C) übernehmen.
- Optional: Telegram→Claude-Brücke („Aufgaben von unterwegs") — Sicherheitskonzept nötig.
- Strategien 1 & 2 implementieren (nach Str.-3-Validierung).
