# Trade-PDF v2 (Top-down Monat → Woche → Tag → 4h → 1h) – gehärtet für den Live-Einsatz

Stand 16.10.2026. Code: `Prototyp_v2/mtf/`, Tests: `Prototyp_v2/tests/test_mtf.py` (57 Tests). Nichts wird gesendet, kein Engine-Code wurde geändert.
Fortschritt/Zwischenstand: `Prototyp_v2/mtf/STAND.md`. Parameter und Messungen: `Parameter_je_Zeitrahmen.md`.

## Dateien in diesem Ordner
| Datei | Inhalt |
|---|---|
| `Muster_sol_long_2026-08-17.pdf`, `Muster_gbpjpy_short_2026-08-28.pdf`, `Muster_audusd_short_2026-09-02.pdf` | die drei Nachrechnungs-Muster (mit IST-Ausgang und C+-Auswertung) |
| `Live_gbpaud_long_2026-10-15.pdf` | **Live-Muster**: echter offener Trade (GBPAUD LONG, Signal 15.10.2026), Stand Einstieg, ohne Ausgang, mit C+-Angaben und `live_info` |
| `Telegram_Text_*.txt` | Text unter der PDF (Entwurf, wird nicht gesendet) |
| `zusammenfassung.json` | Linien/Safety/Urteile/Laufzeiten/Größen je Muster |
| `build_muster_v2.py` | erzeugt alles (Bot-venv: `python build_muster_v2.py`) |
| `daten_kopie_live/` | Kopie von `trades.json`, `ledger.json`, 1h-Daten (aus `Prototyp/paper_runtime_2monate`, read-only kopiert) |

## Seitenaufbau
S.1 Monat + Woche · S.2 Tag + 4h · S.3 1h + Kurzbeschreibung. Jeder Zeitrahmen hat einen eigenen Chart mit Textkasten (Urteil + 1 Satz Begründung).
Die Analyse baut sichtbar von oben nach unten auf: Linien des nächsthöheren Zeitrahmens stehen dünn gestrichelt im darunterliegenden Chart.
Vektor-PDF (TrueType-Schrift eingebettet, Umlaute und Zeichen ✓ ✗ → − geprüft), ca. 250 KB, zoomen ohne Qualitätsverlust.

## Top-down-Bewertung (neu, rein informativ, kein Filter)
Je Zeitrahmen Monat, Woche, Tag werden **Punkte** vergeben:

| Teil | Regel | Punkte |
|---|---|---|
| **Struktur** | die letzten 3 bestätigten Swing-Hochs und Swing-Tiefs (Fraktal-Pivots des Zeitrahmens); Preise innerhalb 0,1 ATR gelten als gleich | Hochs **und** Tiefs steigend +2 · nur eine Seite steigt, andere ohne Richtung +1 · fallend −2 / −1 · gegenläufig (Ausweitung/Verengung) oder gemischt 0 |
| **Lage** | Kurs relativ zu den nächsten intakten A+-Linien (je eine Unterstützung und ein Widerstand) | über steigender/waagerechter Unterstützung +1 · unter fallendem/waagerechtem Widerstand −1 · beides 0 (Keil/Range). Fallende Unterstützung und steigender Widerstand zählen nicht |
| **Bruch** | Schlusskurs-Bruch einer A+-Linie in den letzten 6 (Monat) / 8 (Woche) / 10 (Tag) Kerzen, Kurs liegt noch jenseits | Widerstand nach oben +1 · Unterstützung nach unten −1 |

Summe ≥ +2 Aufwärtstrend, ≤ −2 Abwärtstrend, sonst „kein klares Bild“. Verdikt zur Trade-Richtung: **stützt** (Trend = Richtung), **widerspricht** (Gegentrend), **neutral**.
Fehlende Daten, zu wenig Swings oder Zeitbudget überschritten → neutral mit Hinweis. 4h zählt per Definition als Stütze (dort liegt das Signal), 1h wird bewertet, aber nicht mitgezählt.
Beispiel (Textkasten): *„Woche: widerspricht die SHORT-Richtung (+3) – Aufwärtstrend: höhere Tiefs, Hochs ohne klare Richtung · Kurs über steigender Unterstützung · Widerstand nach oben gebrochen (vor 6 Kerzen).“*
Die für Lage und Bruch benutzten Linien stehen grau gepunktet bzw. strichpunktiert im Chart.

**Ergebnis der Muster:** SOL (LONG): Monat −3, Woche −2 → beide „widersprechen“, Tag neutral. Die Begründung ist jetzt sichtbar (tiefere Hochs/Tiefs, Kurs unter fallendem Widerstand): SOL war im
Monats- und Wochenchart tatsächlich im Abwärtstrend (Höchst ~295, jetzt ~75), der Trade war ein Gegentrend-Ausbruch, der gelaufen ist. Das ist ein Befund der Regel, kein Fehler – ob
„widerspricht“ bei einem gelaufenen Trade störend wirkt, ist Ihre Entscheidung (die Bewertung bleibt informativ und ändert nichts am Trade). GBPJPY SHORT: Monat/Woche Aufwärtstrend → widersprechen.
AUDUSD SHORT: Monat neutral (−1), Woche widerspricht (+3), Tag neutral. GBPAUD LONG (live): alle neutral.

## Safety Line auf Tag/Woche/Monat
Ursache analysiert (Messung über 3 Symbole × 22 Stichtage, siehe `Parameter_je_Zeitrahmen.md`): Hauptgründe für abgelehnte Gegenlinien sind „bereits gebrochen“ und „divergent“ – beides
Regeln des Nutzers, bleiben. Zu streng skaliert waren (1) der Apex (jetzt halbes statt Drittel-Fenster auf Tag/Woche/Monat; 4h/1h bleiben bei 180) und (2) das Safety-Tap-Alter des Tags
(504 statt 360 Kalendertage → 22 statt 16 Monate). Wirkung: Safety gefunden Tag 31 % → 39 %, Woche 23 % → 27 %, Monat 5 % → 11 %. Auf dem Monatsrahmen bleibt sie selten (wenig Swings) –
dann steht im Chart „keine gültige Safety Line nach unseren Regeln“, bzw. „keine gültige Linie nach unseren Regeln“. Es wird nichts erfunden.

## Live-API (Aufrufer: Engine/Notify)
```python
from mtf import trade_pdf as TP, telegram_text as TT, budget
A = TP.analyse(trade, snapshot, h1, daily, fee_fraction,          # unverändert
               c_plus={} | True | {"stage2_r":1.5,"swing_buf_atr":0.5,"net_atr":1.0},   # optional: "kein Ziel, Ausstieg nach C+" + +1,5R-Marke
               live_info={"price": 1.915, "time": ts},           # optional: aktueller Kurs; r_now/dist_stop/dist_target/stop_current/pnl_pct optional (sonst berechnet)
               muster=False, max_seconds=None)                   # max_seconds Standard 60 (Umgebung MTF_MAX_SECONDS)
TP.make_trade_pdf(out_path, A, TT.description(A), label=None, max_seconds=None)
text = TT.telegram_draft(A)     # < 1024 Zeichen, auch als Caption nutzbar; Alias TT.telegram_text
```
* `trade`: `symbol, direction, signal_time` (Beginn der 4h-Signalkerze, UTC), `stop_initial`, `entry_price` (gebucht; 0/None → „erwartet“, Kurs = Schluss der Signalkerze), optional `target` (None bei C+), `entry_time`, `strategy_id`, `parent_signal_id`, `atr`.
* `snapshot`: `action_anchor`, `safety_anchor`, `atr` (wie im Ledger); `None`/defekt → PDF ohne Trade-Linien, Hinweis in `A["warnings"]`.
* `h1`, `daily`: DataFrames (`Time` UTC, OHLC[, Volume, End]); `None`/leer → „keine Daten“ im Chart. Ohne `daily` holt `data.load_daily(symbol, h1=h1)` die Tageshistorie (Cache → einmaliger Yahoo-Abruf → Rückfall).
* **Zeitlimit:** `analyse` + `make_trade_pdf` zusammen ≤ 60 s, sonst `budget.MtfTimeout` (keine Teildatei, geschrieben wird in `<pfad>.part` und atomar umbenannt) → Aufrufer fällt auf das PNG zurück. Je Zeitrahmen 6 s für die Linien-Suche (danach „keine Linienaussage“, PDF entsteht trotzdem).
* Nach dem Aufruf: `A["warnings"]` (Liste degradierter Teile) für das Log.
* Standard-Label der Kopfzeile ist jetzt „Strategie 3 Pro · Paper-Trading – keine echte Order“ (früher „MUSTER – fiktiver Trade“); `muster=True` bzw. `label=` setzt es wieder.
* Cache-Ordner: `MTF_CACHE_DIR` (Umgebung) bzw. `data.set_cache_dir(pfad)`; Standard `Prototyp_v2/mtf_cache` (Dateien aus `Prototyp/mtf_cache` dorthin kopiert, `Prototyp` unverändert). Nach fehlgeschlagenem Yahoo-Abruf 6 Stunden keine neue Anfrage.

## Robustheit / Zeitlimit (Aufgabe 1)
`find_lines` des Originals braucht bei flachen Daten Minuten (400 flache Tageskerzen: **192 s** allein für die Unterstützungsseite). Neu: `fastlines.find_lines_fast` – vektorisiert, **identische Ergebnisse** (Test gegen `scan_100`),
höchstens 110 jüngste Pivots je Seite, höchstens 800 Kandidatenlinien, Zeitbudget; flache Daten jetzt **0,4 s**. Der Worst-Case (flache 1h-/Tagesdaten über Jahre, alle Zeitrahmen) braucht 3,8 s für die gesamte PDF.
Außerdem **kein Patchen von `scan_100`-Konstanten mehr** (die Zeitrahmen-Parameter werden als Argument übergeben): der Engine-Code im selben Prozess sieht nie fremde Werte (Test sperrt `setattr` auf `scan_100`).
Fehlerhafte/fehlende Daten: leerer Zeitrahmen → „keine Daten“; kaputter Chart → „Chart nicht darstellbar“, PDF bleibt vollständig.

## Muster: Größe, Laufzeit (analyse + PDF, Cache warm)
| PDF | Größe | Laufzeit | Seiten | Urteile M / W / D |
|---|---|---|---|---|
| Muster_sol_long_2026-08-17 | 254 451 B | 1,9 s | 3 | widerspricht / widerspricht / neutral |
| Muster_gbpjpy_short_2026-08-28 | 254 691 B | 2,5 s | 3 | widerspricht / widerspricht / neutral |
| Muster_audusd_short_2026-09-02 | 256 467 B | 2,8 s | 3 | neutral / widerspricht / neutral |
| Live_gbpaud_long_2026-10-15 | 251 378 B | 2,5 s (erster Lauf inkl. einmaligem Yahoo-Abruf der Tageshistorie 3,8 s) | 3 | neutral / neutral / neutral |

Alle < 1 MB, Umlaute und Sonderzeichen korrekt (Text per pypdf extrahiert, Schriften eingebettet, keine fehlenden Glyphen), 0 Warnungen.

## Bekannte Schwächen
* SOL-USD: Cache-Index der ersten Testtage verschoben (siehe README v1) – Linie kalibriert, Taps 5 statt 6 (Action) bzw. 4 statt 5 (Safety).
* Tageshistorie kommt aus Yahoo „max“ (Stand heute), Wochen/Monate sind Kalenderwochen/-monate; jüngere Tage ergänzt aus den 1h-Daten (UTC-Tage; kleine Abweichung zu Börsentagen an der Nahtstelle).
* Safety Line auf Monat/Woche bleibt selten (Regelergebnis); Bias-Regel ist eine einfache Punkteregel, kein statistisch validierter Filter – Schwellen (3 Swings, 0,1 ATR, 6/8/10 Kerzen, ±2) sind Setzungen.
* 1R im Live-Modus = |gebuchter Einstieg − Stop|; die Engine kann 1R anders (roher Eröffnungskurs) rechnen – Abweichung nur Slippage-Größe.
* Das Live-Muster nutzt die Daten der Kopie von heute früh als „jetzt“; `live_info` ist hier aus der letzten 1h-Kerze gebildet (der Aufrufer liefert im Betrieb den echten Kurs).
* Instrumente mit lückenhaften 1h-Daten (Futures/Aktien, Sessions): unvollständige 4h-Blöcke fehlen (wie in der Engine); fehlt die Signalkerze, entsteht die PDF ohne Trade-Linien.
* Gesamte Suite `Prototyp_v2/tests`: 318 Tests grün (ein früherer Zwischenlauf hatte 3 rote Tests des anderen Agenten in `test_report_listener.py`, später behoben).
