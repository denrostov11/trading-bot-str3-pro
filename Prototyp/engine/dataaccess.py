# -*- coding: utf-8 -*-
"""Gekapselte Datenzugriffsschicht mit Retry, Backoff, Timeout und Batch.

Der eigentliche Downloader ist INJIZIERBAR (Default: yfinance). Dadurch laufen Tests ohne
Netzwerk. Grundsaetze (Spec <datenquelle>):
- Jede Abfrage mit Retry/Backoff/Timeout und Fehlerprotokoll.
- Ein einzelner Downloadfehler stoppt NIE den gesamten Zyklus (Batch isoliert Fehler je Symbol).
- Fehlende Daten werden nie durch erfundene Preise ersetzt (bei Misserfolg: None + Log).
"""
import time as _time


def _default_downloader(symbol, timeout):
    """Realer Downloader (yfinance). Wird in Unit-Tests NICHT verwendet."""
    import yfinance as yf
    df = yf.download(symbol, period="240d", interval="1h", auto_adjust=False,
                     progress=False, multi_level_index=False, timeout=timeout)
    if df is None or df.empty:
        raise ValueError(f"Leere Antwort fuer {symbol}")
    return df[["Open", "High", "Low", "Close", "Volume"]].dropna()


def fetch(symbol, downloader=None, retries=3, backoff_seconds=2, timeout=30,
          sleep_fn=None, log=None):
    """Laedt 1h-Daten mit Retry/Backoff. Gibt DataFrame oder None (nach erschoepften Versuchen).
    Wirft NICHT nach oben durch - Fehler werden protokolliert."""
    downloader = downloader or _default_downloader
    sleep_fn = sleep_fn or _time.sleep
    attempt = 0
    last_err = None
    while attempt <= retries:
        try:
            df = downloader(symbol, timeout)
            if df is None or len(df) == 0:
                raise ValueError("leeres Ergebnis")
            return df
        except Exception as e:                       # kontrollierter Retry
            last_err = e
            attempt += 1
            if log is not None:
                log.append(f"{symbol}: Versuch {attempt} fehlgeschlagen ({type(e).__name__})")
            if attempt > retries:
                break
            sleep_fn(backoff_seconds * (2 ** (attempt - 1)))
    if log is not None:
        log.append(f"{symbol}: dauerhaft fehlgeschlagen ({type(last_err).__name__})")
    return None


def fetch_batch(symbols, downloader=None, batch_size=20, **kw):
    """Laedt viele Symbole in begrenzten Batches. Ein Fehler je Symbol beeintraechtigt die
    anderen nicht. Gibt (results: dict[symbol]=df|None, log: list)."""
    results, log = {}, kw.pop("log", None)
    if log is None:
        log = []
    syms = list(symbols)
    for i in range(0, len(syms), batch_size):
        for sym in syms[i:i + batch_size]:
            results[sym] = fetch(sym, downloader=downloader, log=log, **kw)
    return results, log
