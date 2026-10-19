# -*- coding: utf-8 -*-
"""Lauffaehiger Paper-Runner (Modus B, KEINE echten Orders).

Ein Zyklus: Abruf -> Cache -> 4h-Aggregation(final) -> Erkennung -> Baseline-Snapshot -> Varianten ->
Ledger, danach Trades oeffnen/fuellen/verfolgen/schliessen und melden. Alle Ergebnisse liegen lokal
(verbindliche Quelle); Telegram ist reine Ausgabe.

Seit dem Neustart (17.10.2026):
- aktive Varianten: Str.3 Pro.1 (Baseline, BE-0), Str.3 Pro.3 (Volumen), Str.3 C+ (Pro.1-Einstiege, C+-Ausstieg)
- mode="full": alle Instrumente (Instrumente mit moeglichem Signal / offenen Trades zuerst), mode="track":
  nur Instrumente mit offenen/wartenden Trades (stuendliche Verfolgung zwischen den 4h-Schluessen)
- fast=True: paralleler, vorsichtiger Abruf + paralleles Rechnen der Erkennung (engine/fastscan.py);
  fast=False: wie bisher sequentiell (Ergebnisse identisch)
- KEINE Zyklus-Meldungen mehr an "STR3 System" (nur Ausfall-/Erholungsmeldungen aus run_loop)
"""
import os, json, time
from datetime import datetime, timezone, timedelta

import pandas as pd

from . import orchestrate, cycle as CY, reporting, fastscan, entry_booking
from .cache import BarCache
from .ledger import Ledger
from .tracker import PaperTradeStore
from .varstate import StateRegistry
from .instruments import load_universe

ACTIVE_VARIANTS = ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]
# Pro.1 = Basis-Kontrolle (BE-0); Pro.3 default BE-1 (unveraendert); C+ hat kein Break-even (eigener Ausstieg)
BE_MAP = {"Str.3 Pro.1": "BE-0", "Str.3 C+": "C+", "Str.3 D": "D"}


def _runtime_dir(base=None):
    base = base or os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "paper_runtime")
    os.makedirs(base, exist_ok=True)
    return base


def last_close_boundary(now):
    """Letzter 4h-Schluss (00/04/08/12/16/20 UTC) <= now."""
    now = pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    return now.floor("4h")


def _atomic_json(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def run_once(universe=None, base_dir=None, now=None, log=None, config_params=None, telegram=False,
             mode="full", priority_symbols=(), fast=False, pool=None, downloader=None, throttle=None,
             svc=None, doc_fn=None, quote_fn=None, book_fn=None, workers=4):
    """Fuehrt EINEN kontrollierten Zyklus aus. Gibt ein Monitoring-Dict zurueck.
    universe: Liste von Instrument-dicts (Default: alle). mode: "full" | "track".
    telegram=True sendet Trade-Meldungen (svc injizierbar fuer Tests). Keine Zyklus-Meldungen an System."""
    t_start = time.time()
    rt = _runtime_dir(base_dir)
    cache = BarCache(os.path.join(rt, "data_cache"))
    ledger = Ledger(os.path.join(rt, "ledger.json"))
    trades = PaperTradeStore(os.path.join(rt, "trades.json"))
    state = StateRegistry(os.path.join(rt, "state.json"))
    universe = universe if universe is not None else load_universe()
    now = now or datetime.now(timezone.utc)
    log = log if log is not None else []
    cfg = config_params or {"code_version": "engine-0.4"}
    inst_by_sym = {i["symbol"]: i for i in universe}

    wm_path = os.path.join(rt, "processed.json")
    watermark = {}
    if os.path.exists(wm_path):
        with open(wm_path, encoding="utf-8") as f:
            watermark = json.load(f)

    # --- Auswahl + Reihenfolge ---
    active_syms = {t.symbol for t in trades.trades if t.status in ("open", "pending_fill")}
    if mode == "track":
        order = [i for i in universe if i["symbol"] in active_syms]
    else:
        prio = set(priority_symbols) | active_syms
        order = [i for i in universe if i["symbol"] in prio] + [i for i in universe if i["symbol"] not in prio]
    phases = []
    if mode != "track" and (set(priority_symbols) | active_syms):
        first = [i for i in order if i["symbol"] in (set(priority_symbols) | active_syms)]
        rest = [i for i in order if i["symbol"] not in (set(priority_symbols) | active_syms)]
        phases = [first, rest]
    else:
        phases = [order]

    mon = {"start": now.isoformat(), "mode": mode, "fast": bool(fast), "instruments": 0, "no_data": 0,
           "no_trigger": 0, "accepted": 0, "rejected": 0, "opened": 0, "closed": 0, "errors": 0,
           "caught_up": 0, "telegram": "inaktiv"}

    notifier = None
    if telegram:
        try:
            if svc is None:
                from notify.live import TelegramService
                svc = TelegramService(ACTIVE_VARIANTS)
            if svc.enabled:
                from .notifier import TradeNotifier
                notifier = TradeNotifier(svc, trades, cache=cache, runtime_dir=rt, inst_by_sym=inst_by_sym,
                                         quote_fn=quote_fn, book_fn=book_fn, doc_fn=doc_fn, log=log)
        except Exception as e:
            mon["telegram"] = f"Fehler {type(e).__name__}"
            log.append(f"Telegram-Setup Fehler: {type(e).__name__}")

    res_by_psig = {}
    if fast:
        throttle = throttle or fastscan.Throttle()
        period_for = lambda s: fastscan.period_days_for(cache, s, now)
        downloader = downloader or fastscan.default_downloader_factory(period_for)

    for phase in phases:
        if not phase:
            continue
        results_by_symbol, bars_by_symbol = {}, {}
        if fast:
            scan = _scan_fast(phase, cache, ledger, watermark, now, cfg, log, mon, downloader, throttle, pool, workers)
        else:
            scan = _scan_sequential(phase, cache, ledger, watermark, now, cfg, log, mon, downloader)
        results_by_symbol, bars_by_symbol = scan
        def _next_open(sym, after_iso, _ph=phase):
            inst = inst_by_sym.get(sym, {})
            return entry_booking.book_entry(cache, sym, after_iso, inst.get("anchor_hour", 0), inst.get("session_hours"), now)
        cyc = CY.run_cycle(bars_by_symbol, results_by_symbol, BE_MAP, state, trades, now=now.timestamp(),
                           next_open_fn=_next_open)
        mon["opened"] += cyc["opened"]; mon["closed"] += cyc["closed"]
        for rlist in results_by_symbol.values():
            for r in rlist:
                res_by_psig[r.get("parent_signal_id")] = r
        if notifier is not None:
            try:
                notifier.doc_fn = doc_fn or _make_doc_fn(rt, res_by_psig, log, trades, cache, ledger, inst_by_sym)
                notifier.refresh_bookings()
                if notifier.notify_all():
                    mon["telegram"] = "gesendet"
                elif mon["telegram"] == "inaktiv":
                    mon["telegram"] = "aktiv"
            except Exception as e:
                mon["telegram"] = f"Fehler {type(e).__name__}"
                log.append(f"Telegram-Zustellung Fehler: {type(e).__name__}")
        if notifier is not None and notifier.first_sent_at and "first_alert_latency_s" not in mon:
            cb = last_close_boundary(now)
            mon["first_alert_latency_s"] = round((pd.Timestamp(notifier.first_sent_at) - cb).total_seconds(), 1)

    _atomic_json(wm_path, watermark)
    if mode != "track":
        cs_path = os.path.join(rt, "cycle_state.json")
        cs = {}
        try:
            cs = json.load(open(cs_path, encoding="utf-8"))
        except Exception:
            pass
        b_iso = last_close_boundary(now).isoformat()
        cs["passes"] = (int(cs.get("passes", 0)) + 1) if cs.get("last_full_boundary") == b_iso else 1
        cs["last_full_boundary"] = b_iso
        cs["last_full_end"] = datetime.now(timezone.utc).isoformat()
        _atomic_json(cs_path, cs)

    mon["candidates_total"] = len(ledger.candidates)
    mon["variant_evals_total"] = len(ledger.variant_evals)
    mon["open_trades"] = sum(1 for t in trades.trades if t.status in ("open", "pending_fill"))
    mon["closed_trades"] = sum(1 for t in trades.trades if t.status == "closed")
    mon["duration_s"] = round(time.time() - t_start, 1)
    mon["end"] = datetime.now(timezone.utc).isoformat()
    mon["log_tail"] = [str(x)[:160] for x in log[-5:]]
    _atomic_json(os.path.join(rt, "last_cycle_monitor.json"), mon)
    return mon


# ------------------------------------------------------------------ Abruf + Erkennung
def _handle_results(sym, results, full_compat, newest, watermark, mon, results_by_symbol, bars_by_symbol):
    if full_compat is None:                           # NO_DATA / INSUFFICIENT_HISTORY
        if results and results[0].get("status") == "NO_DATA":
            mon["no_data"] += 1
        return
    bars_by_symbol[sym] = full_compat                 # immer tracken, auch ohne neue Kerze
    if len(results) > 1:
        mon["caught_up"] += len(results)              # mehr als 1 Kerze = Luecke nachgeholt
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


def _scan_sequential(phase, cache, ledger, watermark, now, cfg, log, mon, downloader=None):
    results_by_symbol, bars_by_symbol = {}, {}
    for inst in phase:
        mon["instruments"] += 1
        sym = inst["symbol"]
        try:
            results, full_compat, newest = orchestrate.analyze_instrument_history(
                inst["name"], sym, inst["asset_class"], inst["is_futures"],
                ACTIVE_VARIANTS, ledger, since_time=watermark.get(sym), cache=cache,
                anchor_hour=inst["anchor_hour"], session_hours=inst["session_hours"],
                now=now, config_params=cfg, log=log, downloader=downloader)
        except Exception as e:
            mon["errors"] += 1
            log.append(f"{sym}: FEHLER {type(e).__name__}")
            continue
        _handle_results(sym, results, full_compat, newest, watermark, mon, results_by_symbol, bars_by_symbol)
    return results_by_symbol, bars_by_symbol


def _scan_fast(phase, cache, ledger, watermark, now, cfg, log, mon, downloader, throttle, pool, workers):
    """Paralleler Abruf (Threads) + parallele Erkennung (Prozesse); Bewertung danach nacheinander."""
    results_by_symbol, bars_by_symbol = {}, {}
    by_sym = {i["symbol"]: i for i in phase}
    merged, jobs, failed = {}, {}, set()
    for sym, df, err in fastscan.fetch_many([i["symbol"] for i in phase], downloader, throttle, workers=workers):
        if df is None:
            failed.add(sym)
            log.append(f"{sym}: Abruf fehlgeschlagen ({err})")
            continue
        inst = by_sym[sym]
        try:
            m = cache.merge(sym, "1h", df)
            merged[sym] = m
            fin, e = orchestrate._build_fin(sym, cache, None, inst["anchor_hour"], inst["session_hours"],
                                            now, log, df1h_merged=m)
            if fin is not None and pool is not None:
                ks, times = fastscan.plan_jobs(fin, watermark.get(sym), 200, sym)
                for k in ks:
                    jobs[(sym, times.iloc[k].isoformat())] = pool.submit(fastscan.window_compat(fin, k))
        except Exception as e:
            mon["errors"] += 1
            log.append(f"{sym}: FEHLER {type(e).__name__}")
            merged.pop(sym, None)
    precomputed = fastscan.collect(jobs) if jobs else None
    for inst in phase:                                   # Reihenfolge = Prioritaet
        sym = inst["symbol"]
        mon["instruments"] += 1
        if sym in failed:
            # Kein frischer Abruf -> Symbol in diesem Zyklus NICHT bewerten und NICHT verfolgen (wie frueher NO_DATA).
            # Ein Rueckgriff auf den Cache koennte noch unfertige 1h-Kerzen (z. B. aus einem frueheren Zwischenabruf) als
            # abgeschlossen werten. Wasserstand bleibt stehen -> das naechste Mal wird luckenlos nachgeholt.
            continue
        if sym not in merged:
            continue
        try:
            results, full_compat, newest = orchestrate.analyze_instrument_history(
                inst["name"], sym, inst["asset_class"], inst["is_futures"],
                ACTIVE_VARIANTS, ledger, since_time=watermark.get(sym), cache=cache,
                anchor_hour=inst["anchor_hour"], session_hours=inst["session_hours"],
                now=now, config_params=cfg, log=log, df1h_merged=merged[sym],
                precomputed=precomputed)
        except Exception as e:
            mon["errors"] += 1
            log.append(f"{sym}: FEHLER {type(e).__name__}")
            continue
        _handle_results(sym, results, full_compat, newest, watermark, mon, results_by_symbol, bars_by_symbol)
    if failed:
        mon["fetch_failed"] = mon.get("fetch_failed", 0) + len(failed)
        mon["no_data"] += 0
    return results_by_symbol, bars_by_symbol


# ------------------------------------------------------------------ Anhang (Trade-PDF / PNG)
def _make_doc_fn(rt, res_by_psig, log, trades, cache, ledger, inst_by_sym):
    """Liefert doc_fn(trade) -> Pfad (PDF bevorzugt, sonst PNG) oder None. Details in engine/trade_doc.py."""
    from . import trade_doc

    def fn(t):
        return trade_doc.make_attachment(rt, t, res_by_psig.get(t.parent_signal_id), ledger, cache, log)
    return fn
