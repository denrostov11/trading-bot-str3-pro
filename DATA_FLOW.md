# DATA_FLOW.md — Str.3 Pro

> Stand: 15.07.2026. Beschreibt den AKTUELLEN Datenfluss (Ist) und den vorgeschlagenen SOLL-Fluss.

## 1. IST — aktueller Datenfluss (Bot gestoppt)
```
Yahoo (yfinance)                [KEIN Cache, kein Retry/Timeout — C1/C2 KRITISCH]
  └─ fetch_4h(): download 1h, period=240d
       └─ df.resample("4h").agg(...).dropna()     [Origin Mitternacht UTC, keine TZ/Session/DST — A2 KRITISCH]
            └─ tail(540) reset_index               [letzte Kerze evtl. UNVOLLSTÄNDIG — A1 KRITISCH]
                 ├─ atr()  [.bfill() — A5]
                 ├─ pivots(K=3)  [letzte 3 Bars nie Pivot — korrekt A6]
                 ├─ find_lines(support/resistance)  [Taps 0.25 ATR, Bruch 0.15 ATR]
                 ├─ is_aplus / converges / pick_safety  [Keil, Safety intakt — korrekt]
                 └─ analyze(): TRIGGER (Bruch ≤3 Kerzen alt) / NEAR / WATCH / NONE
                      └─ stop_and_target(): entry=Close[breakbar], stop=safety@(bb+4),
                                            ziel=erste S/R mit rr>=2 SONST cands[-1] (<2R!)  [B1/B2 KRITISCH]
                           └─ cycle(): Alert (Telegram) + open_paper_trade()
                                ├─ Dedup: sig_core/same_line, Instrument-Sperre, 24h-Cooldown
                                ├─ opened_ts = Time[breaking_bar]  [rückdatiert — A3 KRITISCH]
                                └─ trades.json (flach, EINE Reihe, nur Pro.1)  [keine Varianten — D2]
  check_open_trades(): re-fetch 4h, High/Low vs Stop/Ziel (Stop zuerst = konservativ)
  check_break_even(): re-fetch 15m alle 15 min, Stop -> knapp jenseits Einstieg  [einziger 15m-Pfad]
Zustände: state.json (Alert-Dedup) · trades.json (Trades) · bot_config.json (Laufzeit/Report-Stempel)
Ausgabe: Alerts/ · Trades/ · Str.3 Pro.1/ · Berichte/  + 12h-Backup (lokal + OneDrive)
```
Fehlend im Ist: Cache/Merge, Datenqualität/Rollover, abgelehnte-Setups-Log, Varianten, Snapshots,
config_hash/code_version, Tests.

## 2. SOLL — vorgeschlagener Datenfluss
```
data.access (Retry/Backoff/Timeout/Batch)
  └─ data.cache (Parquet additiv, Merge+Dedup, Monotonie, nie kürzen)
       └─ data.aggregate_4h (TZ/Session/DST-Anker, completeness_ratio, is_final)
            └─ data.quality (Rollover/Gap/Volumen/Duplikate -> data_quality_status)
                 └─ engine.baseline: EIN Snapshot je Kandidat (parent_signal_id, unveränderlich)
                      ├─ REJECTED_DATA_QUALITY / REJECTED_STOP / REJECTED_RR -> ledger (candidate-Log)
                      └─ variants.* (Pro.1..8 × BE): bewerten DENSELBEN Snapshot
                           ├─ variantengetrennte Zustände (offene Trades/Cooldown/Linien/Watchlist/Equity)
                           ├─ Fill = Open next bar; brutto+netto; Intrabar Stop-zuerst; MFE/MAE
                           └─ tracker.paper_trades + ledger (parent_signal_id/candidate_id/
                                                            variant_evaluation_id/trade_id)
  reporting: 7-Tage / rollierend-30 / Abschluss (Prozent NOT_CONFIGURED bis Spez)
  notify.telegram (NOT_CONFIGURED bis Telegram-Spez)
  runtime.loop: Monitoring je Zyklus, Recovery-Check bei Start
```

## 3. Zustands- & Persistenzlogik (Ist → Soll)
- IST: 3 flache JSON ohne Schema/Version; Pro.1-only; Recovery = einfaches Reload ohne Konsistenzprüfung.
- SOLL: versionierte Datensätze mit Schema; je Variante eigener Namespace (Präz. 2); Recovery-Check beim
  Start (offene Trades, Cooldowns, gehandelte Linien konsistent?); config_hash/code_version je Datensatz.
