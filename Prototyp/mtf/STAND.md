# STAND mtf (Trade-PDF) – 16.10.2026

Auftrag: Trade-PDF für den Live-Einsatz ab 17.10.2026 härten. Arbeitsbereich: `Prototyp_v2/mtf/`, `Prototyp_v2/tests/test_mtf.py`, `Analysen/mtf_muster/v2/`.

## Erledigt
1. **Zeitlimit/Robustheit**: `budget.py` (60 s gesamt, 6 s je Zeitrahmen), `fastlines.py` (vektorisiert, identische Ergebnisse, Pivot-/Kandidaten-Obergrenze), `MtfTimeout`; fehlende Daten → „keine Daten“; kaputter Chart → „Chart nicht darstellbar“; atomare PDF-Ausgabe (`.part`).
2. **Top-down-Bewertung v2**: Struktur (3 Swings) + Lage + Bruch, Punkte, Urteil stützt/neutral/widerspricht + 1 Satz (`topdown.py`); README v2 dokumentiert; Tests.
3. **Safety Line höhere Zeitrahmen**: Apex halbes Fenster (Tag/Woche/Monat), Tap-Alter Tag 22 Monate; Messung + Begründung in `Analysen/mtf_muster/v2/Parameter_je_Zeitrahmen.md` (Safety gefunden: Tag 31→39 %, Woche 23→27 %, Monat 5→11 %).
4. **Live-Fähigkeit**: `analyse(..., c_plus=, live_info=, muster=, max_seconds=)` (alle optional, keyword-only); `entry_price` 0/None → „erwartet“; Text mit Variante, Symbol, Richtung, Signal-Schluss + Einstieg in deutscher Zeit, Einstiegskurs, Stop, Ziel bzw. C+, 1R, ATR, Top-down, Grund, `live_info`.
5. **Muster v2** in `Analysen/mtf_muster/v2/` (3 Nachrechnungen + 1 Live-Muster GBPAUD), alle < 260 KB, ≤ 3 s.
6. **Tests**: `tests/test_mtf.py` 57 Tests grün (Zeitlimit, keine Daten, Live ohne outcome, Bias-Regel, Signatur-Stabilität, scan_100-Gleichheit, kein Patchen von scan_100).
7. **Cache**: `Prototyp_v2/mtf_cache/` (3 CSV kopiert + GBPAUD neu per einmaligem Yahoo-Abruf), Pfad konfigurierbar (`MTF_CACHE_DIR`, `data.set_cache_dir`).

## Wichtig für den Aufrufer (anderer Agent)
* Öffentliche Signaturen unverändert kompatibel (neue Parameter optional). Standard-Label ist jetzt NICHT mehr „MUSTER“ (`muster=True`/`label=` setzt es).
* `MtfTimeout` fangen → auf PNG zurückfallen. `A["warnings"]` ins Log.
* `scan_100` wird nicht mehr gepatcht (`params.scan_params` nur noch für Tests).

## Offen / Schwächen
* Bias-Schwellen sind Setzungen; SOL Monat/Woche bleibt „widerspricht“ (echter Abwärtstrend, Gegentrend-Trade) – Entscheidung beim Nutzer, ob so gewollt.
* Safety Line auf Monat selten (Regelergebnis, wenig Swings).
* Telegram-Versand der PDF + Text nicht Teil dieses Auftrags (nichts gesendet).
* Gesamte Suite `Prototyp_v2/tests`: 318 grün (Endlauf). Zwischenlauf hatte 3 rote Tests des anderen Agenten (`test_report_listener.py`), danach von ihm behoben.
