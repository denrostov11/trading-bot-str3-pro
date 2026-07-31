# PERCENT_SPEC.md — Prozent- & Reporting-Spezifikation (Analyse, §9)

> Stand: 2026-07-25 · Status: ANALYSE-VORSCHLAG, KEIN Code geändert. Ergänzt Master- + Telegram-Spez,
> ersetzt keine Signal-/Varianten-/Ausführungs-/Datenqualitätsregel. Eine EINZIGE zentrale
> Berechnungsschicht für R UND Prozent (keine variantenspezifischen Formeln).

## 1. Audit vorhandener R-/Kosten-/Prozentberechnung (mit Prüfpunkten 1–10)
Grundlage: `engine/tracker.py` (simulate_trade) + `engine/reporting.py` (variant_report).

- **(1) Sind Gebühren/Slippage schon in Preis-/Ergebnisfeldern?** JA teilweise: In `simulate_trade` wird
  `entry = entry_open ± SLIP_ATR_PER_SIDE*atr` — die **Einstiegs-Slippage steckt bereits im entry_price**
  und damit im `brutto_r`. Zusätzlich zieht `cost_price = 2*slip + fee*(entry+exit)` beide Slippage-Seiten
  noch einmal ab.
- **(2) Doppelte Kostenbelastung?** **KRITISCH — JA.** Die Einstiegs-Slippage wird doppelt belastet:
  einmal über den verschlechterten `entry_price` (mindert bereits `brutto_r`), einmal über `2*slip` im
  `cost_price` (mindert `netto_r`). Außerdem ist `brutto_r` dadurch **kein echtes Brutto** (enthält schon
  Slippage). FIX: `brutto` aus UNGESLipptem `entry_open` rechnen; `netto` = brutto − Gebühren − Slippage
  (beide Seiten) genau EINMAL. Dafür muss `entry_open` (ungeslippt) zusätzlich gespeichert werden.
- **(3) SHORT-Vorzeichen korrekt?** JA im R-Pfad (`move = entry-exit` für SHORT). Für Prozent unten
  verbindlich definiert (gross_return_pct SHORT = (entry−exit)/entry·100).
- **(4) sum_negative_return_pct als positiver Verlustbetrag oder negativ?** Aktuell rechnet
  `reporting` mit `neg = sum(losses)` (negativ). Spec verlangt `sum_negative_return_pct = ABSOLUTE Summe`.
  → Vereinheitlichen: intern negativ tracken, im Bericht als **positiver Verlustbetrag** ausweisen und
  `net_profit_pct = sum_positive − sum_negative(abs)`. **ANNAHME**, bis bestätigt.
- **(5) Gleichzeitige Trades in der Kontosimulation?** Aktuell KEINE Kontosimulation (nur R + Summe der
  Einzeltrade-%). Portfoliorendite/Equity mit Parallel-Trades ist neu zu bauen.
- **(6) Genug Kapital für alle parallelen virtuellen Trades?** Muss das Positionsgrößenmodell garantieren
  (PAPER_CAPITAL / FIXED_NOTIONAL). Bei variantengetrennten Zuständen laufen je Variante mehrere Instrumente
  parallel → Kapitalbedarf = Σ Notional offener Trades. NUTZERENTSCHEIDUNG (Kapitalhöhe).
- **(7) FIXED_NOTIONAL vs FIXED_RISK sauber getrennt?** Noch nicht implementiert → im Datenmodell strikt
  trennen (zwei getrennte Kennzahlreihen).
- **(8) Portfoliorendite ≠ Summe der Trade-%?** Muss strikt getrennt bleiben (Spec). Werden als 4 klar
  benannte Kennzahlen geführt (s. §6).
- **(9) Drawdown aus zeitlich geordneter Equity-Kurve?** **KRITISCH — NEIN.** `reporting._max_drawdown_r`
  läuft über die Trades in Ledger-/Store-Reihenfolge, NICHT nach Exit-Zeit sortiert. FIX: Equity-Kurve nach
  `closed_ts`/exit_time sortieren, dann Drawdown. Gilt für R- UND Prozent-Drawdown.
- **(10) Offene Trades als unrealisiert getrennt?** Aktuell werten Berichte nur geschlossene Trades; offene
  werden nicht als unrealisiert ausgewiesen. FIX: offene Trades separat (unrealisiertes MFE/MAE, kein
  Einfluss auf realisierte Kennzahlen).

## 2. Verbindliche Formelsammlung (zentral, für ALLE Varianten identisch)
Je Trade (aus gespeicherten `entry_open`, `exit_price`, `direction`, Kosten):
```
gross_return_pct = (exit_price - entry_open)/entry_open*100         (LONG)
gross_return_pct = (entry_open - exit_price)/entry_open*100         (SHORT)
fees_pct     = fee_fraction(asset_class) * 2 * 100                  (Ein- + Ausstieg)
slippage_pct = (SLIP_ATR_PER_SIDE*atr*2)/entry_open * 100           (Ein- + Ausstieg, EINMAL)
net_return_pct = gross_return_pct - fees_pct - slippage_pct
winning_return_pct = net_return_pct если >0 sonst 0
losing_return_pct  = net_return_pct если <0 sonst 0
```
Je Variante:
```
sum_positive_return_pct = Σ net_return_pct über net>0
sum_negative_return_pct = |Σ net_return_pct über net<0|            (ABSOLUT, positiv ausgewiesen)
net_profit_pct          = sum_positive_return_pct - sum_negative_return_pct
average_return_pct      = Σ net_return_pct / n
median_return_pct       = Median(net_return_pct)
average_winner_pct      = Σ(net>0)/#Gewinner ; average_loser_pct = Σ(net<0)/#Verlierer
best_trade_pct / worst_trade_pct = max/min net_return_pct
```
Kennzeichnung: jeder Wert eindeutig **brutto** oder **netto**. „Reiner Nettogewinn in Prozent" =
`net_profit_pct`, in JEDEM Bericht deutlich ausgewiesen.

## 3. Datenmodell-Erweiterung (PaperTrade / result)
Neu je Trade: `entry_open` (UNGESLippt, nötig für echtes Brutto), `gross_return_pct`, `fees_pct`,
`slippage_pct`, `net_return_pct`, `notional`, `risk_capital`, `sizing_model`, `closed_ts` (für Zeitordnung).
Vorhandene R-Felder bleiben; Kosten werden GENAU EINMAL angewandt (Fix zu Prüfpunkt 2).

## 4. Positionsgrößenmodell (NUTZERENTSCHEIDUNG)
- **Modell A FIXED_NOTIONAL_PER_TRADE** (z. B. PAPER_CAPITAL=100000, FIXED_NOTIONAL=1000) — Basis für den
  Einzeltrade-Prozentvergleich (gleicher Einsatz je Trade → Prozente addierbar).
- **Modell B FIXED_RISK_PER_TRADE** (z. B. RISK_PER_TRADE_PCT=0,50) — Basis für die R-Auswertung.
- Empfehlung (Spec): **beide parallel** — R via FIXED_RISK, Einzeltrade-% via FIXED_NOTIONAL. Modell VOR
  Teststart festlegen, danach unverändert. Werte (Kapital/Notional/Risk%) = NUTZERENTSCHEIDUNG.

## 5. Equity-Kurven
- **Realisierte Equity je Variante:** zeitlich nach `closed_ts` geordnet; Schritt = net_return des Trades
  (Prozent-Equity mit FIXED_NOTIONAL; R-Equity mit FIXED_RISK). Drawdown aus DIESER geordneten Kurve.
- **Portfolio-Equity (optional Kontosimulation):** berücksichtigt Parallel-Trades + Positionsgröße →
  `portfolio_return_pct`, `compounded_return_pct` (mit Wiederanlage), `maximum_drawdown_pct`.
- **Vier strikt getrennte, unterschiedlich benannte Kennzahlen:** (1) Summe der Einzeltrade-% ·
  (2) Netto-Gewinnprozent bei gleichem Einsatz je Trade · (3) tatsächliche Kontoänderung (Portfolio) ·
  (4) kumulierte Rendite mit Wiederanlage. Nie vermischen/gleich benennen.

## 6. Berichtskennzahlen — feste Reihenfolge (identisch für Pro.1–8)
1 Anzahl Trades · 2 Trefferquote · 3 Gesamt-R · 4 Ø R · 5 Expectancy R · 6 Σ Gewinnprozente ·
7 Σ Verlustprozente · 8 Netto-Gewinnprozent · 9 Ø Netto-% je Trade · 10 Portfoliorendite nach Kosten ·
11 Profit Factor · 12 Max Drawdown in R · 13 Max Drawdown in Prozent · 14 offene Trades (unrealisiert
getrennt) · 15 Datenqualitätswarnungen. Zusätzlich Prozent-Block (Ø/Median/Gewinner/Verlierer/best/worst,
brutto+netto). Vergleichsbericht + Filterwirkung zusätzlich mit Prozentspalten und den 6 Prozent-Rankings.
Kurz-Textzusammenfassung je Telegram-Gruppe VOR dem PDF (Format wie Spec-Beispiel).

## 7. Konsistenzprüfung R ↔ Prozent
- EINE zentrale Funktion berechnet je Trade R und Prozent aus denselben `entry_open`/`exit_price`/Kosten.
- Kosten GENAU EINMAL (kein Doppelabzug). SHORT-Vorzeichen einheitlich.
- Plausibilität: sign(net_return_pct) == sign(netto_r) für jeden Trade (Testinvariante).
- Gleiche `parent_signal_id`/Trade-IDs/Zeiträume wie R-Auswertung; keine zweite Ergebnisquelle.

## 8. Migration bestehender Trades
- `entry_open` nachtragen (aus Fill rückrechenbar: entry_open = entry_price ∓ slip). Prozentfelder je Trade
  aus gespeicherten Preisen NEU berechnen. Kosten-Doppelzählung im Tracker beheben (Prüfpunkt 2), R-Werte
  konsistent neu ableiten. Drawdown auf zeitgeordnete Equity umstellen. KEINE Vermischung alter/neuer
  Parameter in derselben Ergebnisreihe (neue Versions-ID).

## 9. Testplan (Ergänzung)
- gross/net LONG & SHORT korrekt (Vorzeichen); net = gross − fees − slippage EINMAL (kein Doppelabzug).
- sign(net_return_pct) == sign(netto_r) je Trade.
- sum_negative_return_pct als positiver Betrag; net_profit_pct = pos − neg.
- Drawdown aus zeitgeordneter Equity (unsortierte Eingabe → korrekt sortiert).
- FIXED_NOTIONAL vs FIXED_RISK getrennt; Portfoliorendite ≠ Σ Einzeltrade-%.
- offene Trades unrealisiert getrennt; Parallel-Trades Kapitalbedarf ≤ PAPER_CAPITAL.
- identische zentrale Funktion für alle Varianten (keine Abweichung).

## 10. Offene NUTZERENTSCHEIDUNGEN
- **Positionsgrößenmodell + Werte:** FIXED_NOTIONAL (PAPER_CAPITAL, Notional) UND/ODER FIXED_RISK (Risk%);
  Empfehlung beide parallel. Konkrete Zahlen?
- **Kontosimulation (Portfolio) aktiv?** Falls ja: Startkapital, Umgang mit Parallel-Trades, Wiederanlage
  ja/nein (compounded).
- **fees_pct/slippage_pct-Werte:** bestätigt aus DECISION #5 (FX 0,02% … Krypto 0,10% je Seite; 0,05 ATR
  Slippage je Seite) — als Prozent-Grundlage übernehmen? (ANNAHME: ja)
- **sum_negative_return_pct** als positiver Betrag ausweisen (Empfehlung) — bestätigen.
- Hebel: standardmäßig KEINER (ANNAHME) — bestätigen.
