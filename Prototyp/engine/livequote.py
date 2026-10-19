# -*- coding: utf-8 -*-
"""Aktueller Kurs aus 1-Minuten- bzw. 5-Minuten-Daten (Yahoo) fuer die Trade-Meldung, samt gemessener
Datenverzoegerung. NUR Information fuer die Meldung und fuer den "realistischen Einstieg" - die Wertung
der Strategie bleibt beim theoretischen Einstieg (Open der Folgekerze, 1h-Daten wie bisher).

Der Downloader ist injizierbar (Tests ohne Netz). Fehler/Leerantworten -> None (Meldung zeigt dann
"Kurs nicht verfuegbar"); ein Fehler hier darf nie einen Trade-Zustand veraendern.
"""
import json, os, time
from datetime import datetime, timezone
import pandas as pd

_INTERVALS = (("1m", "1d", 60), ("5m", "1d", 300))


def _default_downloader(symbol, interval, period, timeout=15):
    import yfinance as yf
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=False,
                     progress=False, multi_level_index=False, timeout=timeout)
    if df is None or df.empty:
        raise ValueError("leer")
    return df[["Open", "High", "Low", "Close"]].dropna()


def _utc(ts):
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def fetch_quote(symbol, downloader=None, now=None):
    """-> dict(price, bar_time, interval, delay_s, fetched_at) oder None.
    delay_s = Zeit seit Ende des letzten Kursbalkens (0, solange der Balken noch laeuft): misst, wie stark
    die Yahoo-Kurse hinterherhinken bzw. ob der Markt gerade ohne Kurse ist."""
    downloader = downloader or _default_downloader
    now = _utc(now) if now is not None else datetime.now(timezone.utc)
    now = pd.Timestamp(now)
    for interval, period, secs in _INTERVALS:
        try:
            df = downloader(symbol, interval, period)
            if df is None or len(df) == 0:
                continue
            df = df.dropna()
            last = df.iloc[-1]
            t0 = _utc(df.index[-1])
            end = t0 + pd.Timedelta(seconds=secs)
            delay = max(0.0, (now - end).total_seconds())
            return {"price": float(last["Close"]), "bar_time": t0.isoformat(), "interval": interval,
                    "delay_s": round(delay, 1), "fetched_at": now.isoformat()}
        except Exception:
            continue
    return None


def log_delay(runtime_dir, symbol, asset_class, quote):
    """Haengt die gemessene Verzoegerung je Instrumentklasse an quote_delays.jsonl an (Messreihe)."""
    try:
        rec = {"ts": datetime.now(timezone.utc).isoformat(), "symbol": symbol, "asset_class": asset_class,
               "interval": quote.get("interval") if quote else None,
               "delay_s": quote.get("delay_s") if quote else None, "ok": bool(quote)}
        with open(os.path.join(runtime_dir, "quote_delays.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except Exception:
        pass
