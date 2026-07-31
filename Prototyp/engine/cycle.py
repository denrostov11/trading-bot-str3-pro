# -*- coding: utf-8 -*-
"""Vorwaerts-Zyklus: Trade-Lebenszyklus je Variante (oeffnen -> fuellen -> verfolgen -> schliessen).

Nutzt varstate (variantengetrennte Zustaende), tracker (Fill/BE/MFE/MAE/netto) und den PaperTradeStore
(verbindliche lokale Quelle). Ein akzeptiertes Baseline-Signal kann pro bestehender Variante EINEN
virtuellen Trade eroeffnen (getrennte IDs, gemeinsame parent_signal_id). Einstieg = Open der naechsten
Kerze nach dem Signal (kein rueckdatierter Fill).
"""
import time as _time
import pandas as pd

from . import tracker as T
from . import variants as VAR
from .ledger import make_variant_eval_id


def _accepted_variants(result):
    """Varianten, die den gemeinsamen Snapshot ANGENOMMEN haben (PASS oder DIAGNOSTIC=Pro.7)."""
    return [d for d in result.get("variant_decisions", []) if d.accepted]


def open_trades_for_accepted(result, be_map, state_reg, trade_store, now):
    """Eroeffnet je annehmender Variante einen pending_fill-Trade, sofern der variantengetrennte
    Zustand es erlaubt (1 Trade/Instrument, Cooldown, Linie noch nicht gehandelt)."""
    if result.get("status") != "ACCEPTED_PROVISIONAL":
        return []
    opened = []
    symbol = result["symbol"]
    line_sig = result["action_sig"]
    for d in _accepted_variants(result):
        sid = d.strategy_id
        st = state_reg.get(sid)
        ok, _reason = st.can_open(symbol, line_sig, now)
        if not ok:
            continue
        be = be_map.get(sid, "BE-1")
        tid = f"{sid.replace(' ', '')}_{result['parent_signal_id']}_{be}"
        trade = T.PaperTrade(
            trade_id=tid,
            variant_evaluation_id=make_variant_eval_id(result["parent_signal_id"], sid, be),
            parent_signal_id=result["parent_signal_id"], strategy_id=sid, break_even=be,
            symbol=symbol, asset_class=result["asset_class"], direction=result["direction"],
            signal_time=result["signal_time"], status="pending_fill",
            stop_initial=result["baseline_stop"], target=result["baseline_target"] or 0.0,
            atr=result["atr"], line_sig=line_sig)
        if trade.target <= 0:
            # kein Ziel -> nicht handelbar (waere REJECTED_RR bei aktivem Gate); hier nicht oeffnen
            continue
        st.open(symbol, tid, line_sig)
        trade_store.add(trade)
        opened.append(tid)
    if opened:
        state_reg.save()
    return opened


def update_open_trades(symbol, compat, trade_store, state_reg, now):
    """Fuellt pending_fill-Trades (sobald die naechste Kerze existiert) und verfolgt offene Trades
    gegen die aktuellen Kerzen; schliesst sie bei Stop/Ziel/Break-even."""
    changed = 0
    times = pd.to_datetime(compat["Time"], utc=True)
    for t in trade_store.trades:
        if t.symbol != symbol or t.status == "closed":
            continue
        sig_t = pd.Timestamp(t.signal_time)
        after = times[times > sig_t]
        if after.empty:
            continue                       # naechste Kerze noch nicht da -> bleibt pending_fill
        entry_idx = after.index[0]
        entry_open = float(compat["Open"].iloc[entry_idx])
        bars = [{"High": float(compat["High"].iloc[i]), "Low": float(compat["Low"].iloc[i]),
                 "Open": float(compat["Open"].iloc[i]), "Close": float(compat["Close"].iloc[i])}
                for i in range(entry_idx, len(compat))]
        r = T.simulate_trade(t.direction, t.asset_class, t.atr, entry_open, t.stop_initial,
                             t.target, bars, be_mode=t.break_even)
        t.entry_time = pd.Timestamp(compat["Time"].iloc[entry_idx]).isoformat()
        t.entry_price = r.get("entry_price", entry_open)
        if r.get("status") == "closed":
            exit_idx = min(entry_idx + int(r.get("duration_bars", 1)) - 1, len(compat) - 1)
            exit_ts = pd.Timestamp(compat["Time"].iloc[exit_idx])
            r["exit_time"] = exit_ts.isoformat()
            r["closed_ts"] = float(exit_ts.timestamp())      # fuer zeitgeordnete Equity/Drawdown (Fix P2)
            t.status = "closed"; t.result = r
            state_reg.get(t.strategy_id).close(symbol, now)
            changed += 1
        else:
            t.status = "open"; t.result = r
    if changed:
        state_reg.save()
    trade_store._save()
    return changed


def run_cycle(bars_by_symbol, results_by_symbol, be_map, state_reg, trade_store, now=None):
    """Ein Zyklus ueber mehrere Instrumente:
    - `results_by_symbol`: je Symbol EIN Ergebnis-dict ODER eine LISTE von Ergebnis-dicts
      (mehrere nachgeholte Kerzen aus einer PC-Aus-Luecke; orchestrate.analyze_instrument_history).
    - `bars_by_symbol`: aktuelle (vollstaendige) compat-4h-Kerzen je Symbol (fuer Fill/Tracking).
    Reihenfolge: (1) offene Trades gegen die vollen Kerzen aktualisieren, (2) neue Setups eroeffnen
    (jede angenommene Kerze der Reihe nach), (3) erneut aktualisieren -> ein Trade, der komplett in
    der Aus-Zeit auf- und zuging, schliesst im selben Zyklus ab."""
    now = now or _time.time()
    before_closed = {t.trade_id for t in trade_store.trades if t.status == "closed"}
    before_active = {t.trade_id for t in trade_store.trades if t.status in ("open", "pending_fill")}
    summary = {"opened": 0, "closed": 0, "instruments": len(bars_by_symbol)}
    for symbol, compat in bars_by_symbol.items():
        summary["closed"] += update_open_trades(symbol, compat, trade_store, state_reg, now)
    touched = set()
    for symbol, result in results_by_symbol.items():
        rlist = result if isinstance(result, list) else [result]
        for r in rlist:
            n_open = len(open_trades_for_accepted(r, be_map, state_reg, trade_store, now))
            summary["opened"] += n_open
            if n_open:
                touched.add(symbol)
    # Zweiter Track-Durchgang nur fuer Symbole mit neuen Trades (idempotent, kein Doppelzaehlen)
    for symbol in touched:
        if symbol in bars_by_symbol:
            summary["closed"] += update_open_trades(symbol, bars_by_symbol[symbol],
                                                    trade_store, state_reg, now)
    # Neu geöffnete / geschlossene Trades dieses Zyklus (für Telegram-Alerts)
    summary["closed_trades"] = [t for t in trade_store.trades
                                if t.status == "closed" and t.trade_id not in before_closed]
    summary["opened_trades"] = [t for t in trade_store.trades
                                if t.status in ("open", "pending_fill") and t.trade_id not in before_active]
    return summary
