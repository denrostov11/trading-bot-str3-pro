# ARCHITECTURE_PROPOSAL.md — Str.3 Pro

> Stand: 15.07.2026 · VORSCHLAG, keine Umsetzung ohne Nutzerfreigabe. Ziel: aus dem gewachsenen
> Einzelskript-Prototyp eine wartbare, testbare, varianten- und kausalitätssichere Architektur machen —
> ohne dokumentierte Strategie-/Filterregeln stillschweigend zu ändern.

## 1. Bestandsaufnahme (tatsächlich gelesen)
| Datei | Zeilen~ | Rolle | Bewertung |
|-------|--------|-------|-----------|
| scan_100.py | ~300 | Kanonische Erkennung (Line, fetch_4h, atr, pivots, find_lines, is_aplus, pick_safety, converges) + Scan-Runner | Kern; enthält Daten- UND Erkennungs- UND Plot-Logik gemischt |
| watchlist.py | ~120 | Watchlist-Runner; importiert aus scan_100 | ok, aber dupliziert Plot-Code |
| alert_bot.py | ~1000 | Alles: Telegram, Stop/Ziel, Alert-/Exit-/Composite-Charts, Tracker, Break-even, Berichte, Backup, Loop | Monolith, zu groß, viele Verantwortlichkeiten |
| trendline_prototype.py | ~214 | v1-Erkennung, standalone | **DUPLIKAT** (veraltet: ohne converges/pick_safety/index-Sig) |
| telegram_setup.py | ~64 | Einmal-Setup Chat-ID | read_env dupliziert |
| demo_result.py / demo_fictional_report.py | ~1,5k/9,7k B | Demo-/Beispielbild-Generatoren (nicht zeilenweise auditiert) | Einmal-/Demo, außerhalb Produktionspfad |
| resend_btc.py | ~1,8k B | Einmal-Skript BTC-Nachricht (nicht zeilenweise auditiert) | Wegwerf |
| state.json / trades.json / bot_config.json | — | Zustand (Dedup / Trades / Laufzeit) | flach, ohne Schema/Version |

## 2. Erkannte Duplikate (KRITISCH für Wartbarkeit)
- **Erkennungslogik dreifach-Basis:** trendline_prototype.py hat eine EIGENE, veraltete Kopie von
  Line/fetch_4h/atr/pivots/find_lines/is_aplus. scan_100.py ist die kanonische v2. → trendline_prototype.py
  als produktive Quelle ausmustern (nur als historisches Artefakt kennzeichnen).
- **Plot-Code mehrfach:** scan_100.plot, watchlist.plot, alert_bot.alert_chart/exit_chart/composite_chart —
  4–5 fast identische Kerzen-Render-Funktionen. → gemeinsames `charts.py`.
- **read_env doppelt:** telegram_setup.py und alert_bot.py. → gemeinsames `config.py`.
- **fetch_4h/atr/pivots** in scan_100 UND trendline_prototype. → nur eine Quelle.

## 3. Vorgeschlagene Zielstruktur (Module, keine Regeländerung)
```
Trading_Bot/
  str3pro/                      # neues Paket (Produktionscode)
    __init__.py
    config.py                   # zentrale Konfig + .env-Loader + config_hash + code_version
    data/
      access.py                 # gekapselte Yahoo-Schicht: Retry/Backoff/Timeout/Batch
      cache.py                  # Parquet-Cache 1h/15m/Daily, additiv, Merge+Dedup, Monotonie
      aggregate_4h.py           # session-/TZ-/DST-korrekte 4h-Aggregation, is_final/completeness
      quality.py                # Rollover-/Gap-/Volumen-/Duplikat-Checks -> Datenqualitätsstatus
    engine/
      pivots.py                 # bestätigte Pivots (K=3)
      lines.py                  # find_lines, converges, pick_safety, ATR (kanonisch aus scan_100)
      sr_zones.py               # S/R-Definition (USER_DECISION_REQUIRED bis freigegeben)
      baseline.py               # Baseline-Signal-Engine -> unveränderlicher Snapshot + parent_signal_id
    variants/
      base.py                   # Variant-Interface (bewertet Snapshot -> pass/fail + reason)
      pro2_ema200.py ... pro8_structure.py
      breakeven.py              # BE-0..BE-4
    tracker/
      paper_trades.py           # variantengetrennte Zustände, Fill-Modell, Intrabar-Exit, MFE/MAE
      ledger.py                 # candidate-Log inkl. REJECTED_*; brutto+netto
    reporting/
      reports.py                # 7-Tage / rollierend-30 / Abschluss (Prozent NOT_CONFIGURED bis Spez)
      charts.py                 # gemeinsame Chart-Funktionen
    notify/
      telegram.py               # Verteilung (NOT_CONFIGURED bis Telegram-Spez)
    runtime/
      loop.py                   # Scan-Zyklus, Break-even-15m-Takt, Recovery, Monitoring
      backup.py                 # 12h-Backup
  tests/                        # pytest: 22 QS-Fälle + synthetische Charts
  data_cache/                   # Parquet (additiv)
  state/                        # variantengetrennte Zustände (statt flacher *.json)
```
- **Migrationsprinzip:** Bestehende scan_100.py bleibt zunächst als Kompatibilitäts-Shim (re-exportiert aus
  engine/), damit alert_bot/watchlist nicht sofort brechen. Schrittweise Umzug, jeder Schritt testgedeckt.

## 4. Datenmodelle (neu, versioniert)
- `Snapshot` (unveränderlich): parent_signal_id, data_cutoff_time, pivots+confirm_times, action_line,
  safety_line, tap_times, atr, sr_zones, signal_close, baseline_stop, baseline_target, r_initial, data_quality.
- `VariantEvaluation`: parent_signal_id, candidate_id, variant_evaluation_id, strategy_version, filter_values,
  filter_pass_fail, rejection_reason.
- `PaperTrade`: trade_id, variant_evaluation_id, entry_ref(next_open), simulated_fill, slippage, fees,
  stop_initial, target_initial, r_initial, actual_exit, brutto_R, netto_R, MFE_R, MAE_R, duration,
  data_quality_flags, code_version, config_hash, break_even_state.
- Persistenz: je Variante eigener Namespace (Präz. 2). JSON mit Schema-Version, später ggf. SQLite.

## 5. Nutzen / Risiko / Migrationsweg (Kurzfassung)
- **Nutzen:** Kausalität + Varianten sauber trennbar, testbar, reproduzierbar (config_hash), keine Duplikate.
- **Risiko:** Umbau kann Verhalten unbeabsichtigt ändern → Gegenmittel: Kanonische Logik 1:1 übernehmen,
  Charakterisierungs-Tests VOR Umzug (Golden-Output der aktuellen Erkennung auf Fixtures).
- **Rollback:** jeder Schritt in eigenem Commit/Backup; scan_100-Shim erlaubt Rückfall auf Altpfad.
- **Detaillierte Schritte:** siehe MIGRATION_PLAN.md.
