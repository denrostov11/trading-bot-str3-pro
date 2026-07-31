# -*- coding: utf-8 -*-
"""Orchestrierung (S9): fuehrt den gesamten Fluss je Instrument zusammen -
fetch -> cache -> 4h-Aggregation(final) -> Erkennung -> Baseline-Snapshot -> Features -> Varianten -> Ledger.

Nutzt ausschliesslich die gemeinsamen Bausteine (KEINE Zweit-Engine). Die Erkennungsstufe ist
INJIZIERBAR (detect_fn) - Default = kanonische Erkennung aus scan_100 - damit Tests ohne Netz laufen.
Alle Varianten bewerten denselben unveraenderlichen Snapshot (gemeinsame parent_signal_id).
"""
from datetime import datetime, timezone
import pandas as pd

from . import dataaccess, aggregate_4h, quality, baseline, features as FEAT, variants as VAR

MIN_FINAL_BARS = 90


def default_detector(compat):
    """Kanonische Erkennung via scan_100. Gibt dict oder None (kein frischer A+-Trigger).
    Frischer Trigger = Bruch auf der letzten (finalen) Kerze (A3)."""
    import scan_100 as s100
    a = s100.atr(compat)
    piv = s100.pivots(compat)
    sup = s100.find_lines(compat, "support", a, piv)
    res = s100.find_lines(compat, "resistance", a, piv)
    n = len(compat)
    broken = [l for l in (sup + res) if l.breaking_bar == n - 1 and s100.is_aplus(l)]
    if not broken:
        return None
    action = max(broken, key=lambda l: l.score)
    direction = "SHORT" if action.kind == "support" else "LONG"
    opp = res if action.kind == "support" else sup
    safety = s100.pick_safety(action, opp, compat, a)   # erzwingt intakt + konvergent (Keil)
    if safety is None:
        return {"no_safety": True, "action": action, "direction": direction}
    pivot_prices = [float(compat["Low"].iloc[i]) for i in piv[0]] + \
                   [float(compat["High"].iloc[i]) for i in piv[1]]
    return {"action": action, "safety": safety, "direction": direction,
            "atr_last": float(a.iloc[-1]), "atr_series": a, "pivots": piv,
            "pivot_prices": pivot_prices, "n": n}


def _compute_features(compat, det, asset_class, daily_df=None):
    """Best-effort Feature-Berechnung. Fehlt etwas (z. B. Daily-Daten) -> Feature fehlt ->
    betroffene Variante wird NOT_EVALUABLE (nie stillschweigend bestanden)."""
    f = {}
    bb = det["n"] - 1
    o = float(compat["Open"].iloc[bb]); h = float(compat["High"].iloc[bb])
    l = float(compat["Low"].iloc[bb]); c = float(compat["Close"].iloc[bb])
    f.update(FEAT.breakout_metrics(o, h, l, c, det["atr_last"]))
    # Volumen
    vol_ok, _ = quality.validate_volume(compat, asset_class)
    f["volume_usable"] = vol_ok
    if "Volume" in compat.columns:
        rv = FEAT.rvol(list(compat["Volume"]), window=20)
        if rv is not None:
            f["rvol20"] = rv
    # ATR-Regime (Perzentil von ATR% ueber die letzten 100)
    atr_pct = [(float(det["atr_series"].iloc[i]) / float(compat["Close"].iloc[i]) * 100)
               for i in range(len(compat)) if float(compat["Close"].iloc[i]) > 0]
    p = FEAT.percentile_rank(atr_pct, window=100)
    if p is not None:
        f["atr_percentile"] = p
    # Trendqualitaet (Pro.7 diagnostisch)
    closes = list(compat["Close"]); highs = list(compat["High"]); lows = list(compat["Low"])
    f["r2"] = FEAT.linreg_r2(closes[-30:])
    f["adx"] = FEAT.adx(highs, lows, closes)
    f["choppiness"] = FEAT.choppiness(highs, lows, closes)
    # Daily-EMA200 (Pro.2/5) nur wenn Daily-Daten vorliegen
    if daily_df is not None and "Close" in daily_df.columns:
        dc = list(daily_df["Close"])
        e = FEAT.ema(dc, 200)
        if e is not None:
            f["daily_close"] = float(dc[-1]); f["daily_ema200"] = float(e)
            f["daily_bars"] = len(dc)
    return f


def _build_fin(symbol, cache, downloader, anchor_hour, session_hours, now, log):
    """Fetch -> cache/merge -> 4h-Aggregation -> final_only. Gibt (fin_df, error_dict).
    fin_df=None (und error_dict gesetzt) bei NO_DATA / INSUFFICIENT_HISTORY."""
    df1h = dataaccess.fetch(symbol, downloader=downloader, log=log)
    if df1h is None:
        return None, {"symbol": symbol, "status": "NO_DATA"}
    if cache is not None:
        df1h = cache.merge(symbol, "1h", df1h)
    else:
        df1h = aggregate_4h_time_col(df1h)
    agg = aggregate_4h.aggregate(df1h, anchor_hour=anchor_hour, session_hours=session_hours,
                                 data_cutoff=now)
    fin = aggregate_4h.final_only(agg)
    if len(fin) < MIN_FINAL_BARS:
        return None, {"symbol": symbol, "status": "INSUFFICIENT_HISTORY", "final_bars": int(len(fin))}
    return fin.reset_index(drop=True), None


def _evaluate_candle(name, symbol, asset_class, is_futures, active_variants, ledger,
                     fin_slice, cutoff_iso, config_params, detect_fn, daily_df=None, log=None):
    """Erkennung + Baseline + Ledger + Varianten auf GENAU EINEM 4h-Fenster (fin_slice), dessen
    LETZTE Kerze die zu bewertende (gerade final gewordene) Kerze ist. Sieht nur Daten bis zu
    dieser Kerze -> kein Look-ahead, auch beim Nachholen. cutoff_iso = Zeitpunkt, zu dem die
    Kerze final wurde (Realzeit fuer die aktuelle, Folgekerzen-Open beim Nachholen)."""
    compat = fin_slice[["Time", "Open", "High", "Low", "Close", "Volume"]].reset_index(drop=True)
    det = detect_fn(compat)
    if det is None:
        return {"symbol": symbol, "status": "NO_TRIGGER", "compat": compat}
    if det.get("no_safety"):
        return {"symbol": symbol, "status": "NO_CONVERGING_SAFETY", "compat": compat}

    n = det["n"]
    bb = n - 1
    signal_time = pd.Timestamp(compat["Time"].iloc[bb]).isoformat()
    dq = quality.data_quality(fin_slice, asset_class, is_futures)
    near = quality.near_rollover(signal_time, dq.get("suspected_rollover", []))

    res = baseline.evaluate(
        symbol, asset_class, det["direction"], det["action"], det["safety"], n, compat,
        det["atr_last"], signal_time, cutoff_iso, det["pivot_prices"], dq["status"],
        near_unexplained_rollover=near, config_params=config_params or {})

    # Kandidat immer protokollieren (auch abgelehnt) - D1
    snap = res.snapshot
    psig = snap.parent_signal_id if snap else \
        baseline.make_parent_signal_id(symbol, signal_time, det["action"].p0,
                                       (det["action"].p1 - det["action"].p0) /
                                       (det["action"].i1 - det["action"].i0))
    ledger.record_candidate(psig, symbol, det["direction"], res.status, signal_time, cutoff_iso,
                            rejection_reason=res.rejection_reason, diagnostics=res.diagnostics,
                            snapshot=(snap.__dict__ if snap else None) if hasattr(snap, "__dict__") else None)
    if res.status != baseline.ACCEPTED_PROVISIONAL:
        return {"symbol": symbol, "status": res.status, "parent_signal_id": psig,
                "reason": res.rejection_reason, "compat": compat}

    feats = _compute_features(compat, det, asset_class, daily_df=daily_df)
    decs = VAR.evaluate_variants(snap, feats, active_variants)
    for d in decs:
        ledger.record_variant_eval(psig, d.strategy_id, "v1", d.status,
                                   filter_values=d.filter_values, rejection_reason=d.reason)
    action = det["action"]
    action_sig = f"{action.kind}:{round(action.p0, 6)}:" \
                 f"{round((action.p1 - action.p0) / (action.i1 - action.i0), 8)}"
    return {"symbol": symbol, "status": "ACCEPTED_PROVISIONAL", "parent_signal_id": psig,
            "direction": det["direction"], "signal_time": signal_time,
            "asset_class": asset_class, "atr": det["atr_last"],
            "signal_close": snap.signal_close, "baseline_stop": snap.baseline_stop,
            "baseline_target": snap.baseline_target, "baseline_rr": snap.baseline_rr,
            "action_sig": action_sig,
            "variants": {d.strategy_id: d.status for d in decs},
            "variant_decisions": decs, "diagnostics": res.diagnostics, "compat": compat}


def analyze_instrument(name, symbol, asset_class, is_futures, active_variants, ledger,
                       downloader=None, cache=None, detect_fn=None, daily_df=None,
                       anchor_hour=0, session_hours=None, now=None, config_params=None,
                       log=None):
    """Fuehrt den kompletten Fluss fuer EIN Instrument aus (nur die aktuelle letzte Kerze).
    Gibt ein Ergebnis-dict (Status)."""
    detect_fn = detect_fn or default_detector
    now = now or datetime.now(timezone.utc)
    fin, err = _build_fin(symbol, cache, downloader, anchor_hour, session_hours, now, log)
    if err is not None:
        return err
    return _evaluate_candle(name, symbol, asset_class, is_futures, active_variants, ledger,
                            fin, now.isoformat(), config_params, detect_fn, daily_df, log)


def analyze_instrument_history(name, symbol, asset_class, is_futures, active_variants, ledger,
                               since_time=None, downloader=None, cache=None, detect_fn=None,
                               daily_df=None, anchor_hour=0, session_hours=None, now=None,
                               config_params=None, log=None, max_replay=200):
    """Wie analyze_instrument, aber holt LUECKEN nach (PC war zwischenzeitlich aus): bewertet jede
    seit `since_time` NEU abgeschlossene 4h-Kerze der Reihe nach als eigenes 'letzte-Kerze'-Fenster.
    Kein Look-ahead: jede Bewertung sieht nur Daten bis zu IHRER Kerze (Datenschnitt = Folgekerzen-Open).

    Gibt (results, full_compat, newest_time):
    - results      : Liste der Ergebnis-dicts je nachgeholter Kerze (chronologisch). Bei NO_DATA /
                     INSUFFICIENT_HISTORY eine Ein-Element-Liste mit dem Fehlerstatus.
    - full_compat  : alle finalen 4h-Kerzen (fuer Fill/Tracking der offenen Trades); None bei Fehler.
    - newest_time  : ISO-Zeit der neuesten finalen Kerze (neuer Wasserstand); bei Fehler = since_time.

    since_time=None (Erststart) -> nur die aktuelle letzte Kerze (KEIN History-Backfill der Vergangenheit).
    max_replay deckelt Extremluecken (Datenalterung); aeltere verpasste Kerzen werden dann ausgelassen."""
    detect_fn = detect_fn or default_detector
    now = now or datetime.now(timezone.utc)
    fin, err = _build_fin(symbol, cache, downloader, anchor_hour, session_hours, now, log)
    if err is not None:
        return [err], None, since_time

    full_compat = fin[["Time", "Open", "High", "Low", "Close", "Volume"]].reset_index(drop=True)
    times = pd.to_datetime(full_compat["Time"], utc=True)
    n = len(fin)

    if since_time is None:
        start_k = n - 1                      # Erststart: nur die aktuelle Kerze
    else:
        st = pd.Timestamp(since_time)
        newer = times.index[times > st]
        start_k = int(newer[0]) if len(newer) else n   # n => keine neue Kerze
    start_k = max(start_k, MIN_FINAL_BARS - 1)          # genug Historie fuer die Erkennung
    if n - start_k > max_replay:                        # Deckel gegen Extremluecken
        skipped = n - max_replay - start_k
        start_k = n - max_replay
        if log is not None:
            log.append(f"{symbol}: Luecke > {max_replay} Kerzen - {skipped} aelteste ausgelassen")

    results = []
    for k in range(start_k, n):
        cutoff_iso = times.iloc[k + 1].isoformat() if k + 1 < n else now.isoformat()
        results.append(_evaluate_candle(name, symbol, asset_class, is_futures, active_variants,
                                        ledger, fin.iloc[:k + 1], cutoff_iso, config_params,
                                        detect_fn, daily_df, log))
    newest_time = times.iloc[n - 1].isoformat()
    return results, full_compat, newest_time


def aggregate_4h_time_col(df):
    """Stellt sicher, dass ein 'Time'-Spalten-DataFrame vorliegt (fuer den Fall ohne Cache)."""
    d = df.copy()
    if "Time" not in d.columns:
        d = d.reset_index()
        first = d.columns[0]
        if first != "Time":
            d = d.rename(columns={first: "Time"})
    d["Time"] = pd.to_datetime(d["Time"], utc=True)
    return d
