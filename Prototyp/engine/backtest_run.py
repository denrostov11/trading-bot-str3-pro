# -*- coding: utf-8 -*-
"""Backtest-Treiber (Etappe A2): chronologischer 18-Monats-Replay je Symbol.

- Nutzt eingefrorene Rohdaten (backtest_data) statt Live-Fetch.
- Erkennung/Baseline/Varianten je Kerze via orchestrate.analyze_instrument_history
  (look-ahead-frei; Daily je Kerze per daily_asof eingespeist -> EMA200 sauber).
- Trade-Lebenszyklus KERZENWEISE mit den bestehenden Live-Funktionen (cycle.update_open_trades /
  open_trades_for_accepted), damit Instrument-Sperre, 24h-Cooldown und Linie-einmal ZEITLICH
  korrekt greifen (nicht alle Signale in einem Rutsch). Jede Kerze wird nur gegen bereits
  geschlossene Kerzen ausgewertet -> kein Look-ahead auch im Zustandsautomaten.
- Warmup-Kerzen vor Testbeginn liefern Historie fuer die Erkennung, erzeugen aber KEINE Trades.

Reine Simulation; keine echten Orders. Ergebnisse (ledger/trades/state) liegen je Lauf lokal.
"""
import os
import pandas as pd

from . import orchestrate
from . import cycle as CY
from . import backtest_data as BD
from .ledger import Ledger
from .tracker import PaperTradeStore
from .varstate import StateRegistry

MAX_REPLAY = 10 ** 9      # Backtest: keine Luecken-Deckelung, ganzes Fenster replayen
DETECT_LOOKBACK = 540     # Erkennungsfenster (~4 Monate): kanonisches A+-Designfenster + machbar


def run_symbol(name, symbol, asset_class, is_futures, active_variants, frozen_1h, frozen_daily,
               start, end, ledger, store, state, be_map, anchor_hour=0, session_hours=None,
               config_params=None, log=None, detect_fn=None):
    """Backtestet EIN Symbol ueber [start, end]. frozen_1h/frozen_daily = eingefrorene Rohdaten
    (DataFrame mit Time,Open,High,Low,Close,Volume) oder None. Gibt Status-/Zaehl-dict."""
    start = pd.Timestamp(start); end = pd.Timestamp(end)
    if start.tzinfo is None: start = start.tz_localize("UTC")
    if end.tzinfo is None: end = end.tz_localize("UTC")
    if frozen_1h is None or len(frozen_1h) == 0:
        return {"symbol": symbol, "status": "NO_DATA_QUARANTINE"}

    dl = lambda s, t=None: frozen_1h        # injizierter "Downloader" liefert eingefrorene 1h-Daten
    # since_time ist ein EXKLUSIVER Wasserstand ("bis hierhin schon verarbeitet"). Damit die Kerze,
    # die genau zum Fensterbeginn oeffnet, mitbewertet wird (der Trade-Lebenszyklus unten schliesst
    # sie ebenfalls ein), liegt der Wasserstand 1 s VOR dem Start.
    results, full_compat, _ = orchestrate.analyze_instrument_history(
        name, symbol, asset_class, is_futures, active_variants, ledger,
        since_time=(start - pd.Timedelta(seconds=1)).isoformat(), downloader=dl, cache=None, detect_fn=detect_fn,
        daily_df=frozen_daily, daily_asof_fn=BD.daily_asof, anchor_hour=anchor_hour,
        session_hours=session_hours, now=end, config_params=config_params, log=log,
        max_replay=MAX_REPLAY, lookback_bars=DETECT_LOOKBACK)

    if full_compat is None:
        return {"symbol": symbol, "status": results[0].get("status")}

    # akzeptierte Signale nach Kerzenzeit (ISO) indizieren
    accepted_by_time = {}
    for r in results:
        if r.get("status") == "ACCEPTED_PROVISIONAL":
            accepted_by_time[pd.Timestamp(r["signal_time"]).isoformat()] = r

    times = pd.to_datetime(full_compat["Time"], utc=True)
    opened = 0
    for i in range(len(full_compat)):
        T = times.iloc[i]
        if T < start:                       # Warmup: nur Historie, kein Trading
            continue
        slice_i = full_compat.iloc[:i + 1]  # ausschliesslich bereits geschlossene Kerzen (kein Look-ahead)
        CY.update_open_trades(symbol, slice_i, store, state, T.timestamp())
        r = accepted_by_time.get(T.isoformat())
        if r is not None:
            opened += len(CY.open_trades_for_accepted(r, be_map, state, store, T.timestamp()))

    window_bars = int((times >= start).sum())
    return {"symbol": symbol, "status": "OK", "final_bars": int(len(full_compat)),
            "warmup_bars": int(len(full_compat) - window_bars), "window_bars": window_bars,
            "candidates": len(results), "accepted": len(accepted_by_time), "opened": opened}


def run_universe(universe, start, end, run_dir, active_variants, be_map, frozen_dir,
                 config_params=None, detect_fn=None, log=None, limit=None, progress=None):
    """Backtestet ein ganzes Universum in ein Lauf-Verzeichnis (ledger/trades/state lokal).
    Instrumente ohne Daten werden quarantaenisiert (NO_DATA_QUARANTINE), stoppen den Lauf nicht.
    Gibt (summary: list[dict], ledger, store)."""
    os.makedirs(run_dir, exist_ok=True)
    ledger = Ledger(os.path.join(run_dir, "ledger.json"))
    store = PaperTradeStore(os.path.join(run_dir, "trades.json"))
    state = StateRegistry(os.path.join(run_dir, "state.json"))
    log = log if log is not None else []
    insts = universe[:limit] if limit else universe
    summary = []
    for idx, inst in enumerate(insts):
        frozen = BD.fetch_and_freeze(inst["symbol"], frozen_dir)
        s = run_symbol(inst["name"], inst["symbol"], inst["asset_class"], inst["is_futures"],
                       active_variants, frozen["1h"], frozen.get("1d"), start, end,
                       ledger, store, state, be_map, inst["anchor_hour"], inst["session_hours"],
                       config_params, log, detect_fn)
        summary.append(s)
        if progress is not None:
            progress(idx + 1, len(insts), inst["symbol"], s)
    return summary, ledger, store
