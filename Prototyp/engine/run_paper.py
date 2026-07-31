# -*- coding: utf-8 -*-
"""Lauffaehiger Paper-Runner (Modus B, lokal-zuerst, KEIN Telegram, KEINE echten Orders).

Ein Zyklus ueber das (Teil-)Universum: fetch -> cache -> 4h-Aggregation(final) -> Erkennung ->
Baseline-Snapshot -> Varianten -> Ledger, danach Trades oeffnen/fuellen/verfolgen/schliessen.
Alle Ergebnisse liegen lokal (verbindliche Quelle). Monitoring je Zyklus wird ausgegeben.

Der Zwei-Monats-Test wird NICHT automatisch gestartet - dieser Runner fuehrt kontrollierte Zyklen aus.
"""
import os, json, time
from datetime import datetime, timezone

from . import orchestrate, cycle as CY, reporting
from .cache import BarCache
from .ledger import Ledger
from .tracker import PaperTradeStore
from .varstate import StateRegistry
from .instruments import load_universe

# Aktive Kontroll-Konfiguration (Praez. 11): Pro.1 mit BE-0 und BE-1; weitere nur mit Freigabe.
ACTIVE_VARIANTS = ["Str.3 Pro.1", "Str.3 Pro.2", "Str.3 Pro.3", "Str.3 Pro.4",
                   "Str.3 Pro.5", "Str.3 Pro.6", "Str.3 Pro.7", "Str.3 Pro.8"]
BE_MAP = {"Str.3 Pro.1": "BE-0"}   # Basis-Kontrolle; restliche default BE-1 im Tracker/cycle


def _runtime_dir(base=None):
    base = base or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_runtime")
    os.makedirs(base, exist_ok=True)
    return base


def run_once(universe=None, base_dir=None, now=None, log=None, config_params=None, telegram=False):
    """Fuehrt EINEN kontrollierten Zyklus aus. universe = Liste von Instrument-dicts (Default: alle).
    telegram=True: sendet Trade-Alerts + System-Monitor an die konfigurierten Gruppen (via notify.live).
    Gibt ein Monitoring-Dict zurueck."""
    rt = _runtime_dir(base_dir)
    cache = BarCache(os.path.join(rt, "data_cache"))
    ledger = Ledger(os.path.join(rt, "ledger.json"))
    trades = PaperTradeStore(os.path.join(rt, "trades.json"))
    state = StateRegistry(os.path.join(rt, "state.json"))
    universe = universe if universe is not None else load_universe()
    now = now or datetime.now(timezone.utc)
    log = log if log is not None else []
    cfg = config_params or {"code_version": "engine-0.4"}

    # Wasserstand je Symbol (letzte bewertete finale 4h-Kerze) - fuer lueckenloses Nachholen,
    # wenn der PC zwischen zwei Zyklen aus war. Neustart-fest auf Platte.
    wm_path = os.path.join(rt, "processed.json")
    watermark = {}
    if os.path.exists(wm_path):
        with open(wm_path, encoding="utf-8") as f:
            watermark = json.load(f)

    mon = {"start": now.isoformat(), "instruments": 0, "no_data": 0, "no_trigger": 0,
           "accepted": 0, "rejected": 0, "opened": 0, "closed": 0, "errors": 0, "caught_up": 0}
    results_by_symbol = {}
    bars_by_symbol = {}
    for inst in universe:
        mon["instruments"] += 1
        sym = inst["symbol"]
        try:
            results, full_compat, newest = orchestrate.analyze_instrument_history(
                inst["name"], sym, inst["asset_class"], inst["is_futures"],
                ACTIVE_VARIANTS, ledger, since_time=watermark.get(sym), cache=cache,
                anchor_hour=inst["anchor_hour"], session_hours=inst["session_hours"],
                now=now, config_params=cfg, log=log)
        except Exception as e:
            mon["errors"] += 1
            log.append(f"{sym}: FEHLER {type(e).__name__}")
            continue
        if full_compat is None:                       # NO_DATA / INSUFFICIENT_HISTORY
            st = results[0].get("status")
            if st == "NO_DATA":
                mon["no_data"] += 1
            continue                                  # Wasserstand nicht vorruecken
        bars_by_symbol[sym] = full_compat             # immer tracken, auch ohne neue Kerze
        if len(results) > 1:
            mon["caught_up"] += len(results)          # mehr als 1 Kerze = Luecke nachgeholt
        accepted = [r for r in results if r.get("status") == "ACCEPTED_PROVISIONAL"]
        if accepted:
            mon["accepted"] += len(accepted)
            results_by_symbol[sym] = accepted
        for r in results:
            if (r.get("status") or "").startswith("REJECTED"):
                mon["rejected"] += 1
        if results and results[-1].get("status") == "NO_TRIGGER" and not accepted:
            mon["no_trigger"] += 1
        watermark[sym] = newest

    with open(wm_path, "w", encoding="utf-8") as f:
        json.dump(watermark, f, indent=1)

    cyc = CY.run_cycle(bars_by_symbol, results_by_symbol, BE_MAP, state, trades, now=now.timestamp())
    mon["opened"] = cyc["opened"]; mon["closed"] = cyc["closed"]

    if telegram:
        try:
            from notify.live import TelegramService
            svc = TelegramService(ACTIVE_VARIANTS)
            if svc.enabled:
                for t in cyc.get("opened_trades", []):
                    svc.trade_opened(t)
                for t in cyc.get("closed_trades", []):
                    svc.trade_closed(t)
                # System-Monitor nur bei Aktivität/Fehlern (kein stündlicher Spam)
                if mon["opened"] or mon["closed"] or mon["errors"]:
                    svc.system(f"Zyklus {mon['start'][:16]}: {mon['instruments']} Instrumente, "
                               f"Trigger {mon['accepted']}, eröffnet {mon['opened']}, "
                               f"geschlossen {mon['closed']}, Fehler {mon['errors']}. Paper-Trading.")
                mon["telegram"] = "gesendet"
            else:
                mon["telegram"] = "inaktiv"
        except Exception as e:
            mon["telegram"] = f"Fehler {type(e).__name__}"
            log.append(f"Telegram-Zustellung Fehler: {type(e).__name__}")
    mon["candidates_total"] = len(ledger.candidates)
    mon["variant_evals_total"] = len(ledger.variant_evals)
    mon["open_trades"] = sum(1 for t in trades.trades if t.status in ("open", "pending_fill"))
    mon["closed_trades"] = sum(1 for t in trades.trades if t.status == "closed")
    mon["end"] = datetime.now(timezone.utc).isoformat()
    with open(os.path.join(rt, "last_cycle_monitor.json"), "w", encoding="utf-8") as f:
        json.dump(mon, f, indent=1)
    return mon
