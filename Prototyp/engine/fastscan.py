# -*- coding: utf-8 -*-
"""Schneller Zyklus (A5): paralleler, vorsichtiger Yahoo-Abruf + paralleles Rechnen der Erkennung.

Aufgabenteilung (Ergebnisse bleiben IDENTISCH zum bisherigen sequentiellen Ablauf):
1. ABRUF (Threads, begrenzte Parallelitaet, Mindestabstand zwischen Anfragen, gemeinsames Backoff bei
   Fehlern/Rate-Limit, Sicherung "Pause nach vielen Fehlern in Folge"). Es wird nur die kurze Spanne geholt,
   die der lokale Cache noch nicht hat (additiv gemergt) - gleiche Quelle, gleiche Daten wie bisher.
2. ERKENNUNG (Prozesse): die rechenintensive Linien-Erkennung (Sekunden je Instrument) laeuft fuer alle
   zu bewertenden Kerzenfenster parallel auf mehreren Kernen. Die Ergebnisse werden unveraendert an
   orchestrate.analyze_instrument_history durchgereicht (precomputed); fehlt eines, rechnet dieses
   selbst nach (Fallback) - der Pool ist reine Beschleunigung.
3. BEWERTUNG (Hauptprozess, nacheinander): Baseline, Varianten, Ledger, Trades - Zustandsaenderungen
   passieren nur hier, nie parallel.

Die 4h-Aggregation wird nicht angefasst (Anker 00:00 UTC, final_only).
"""
import threading
import time as _time
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import pandas as pd

from . import orchestrate

COLS = ["Time", "Open", "High", "Low", "Close", "Volume"]
FULL_PERIOD_DAYS = 240            # wie bisher (dataaccess): volle Historie bei leerem/altem Cache
MIN_PERIOD_DAYS = 7
MAX_PERIOD_DAYS = 240
RATE_LIMIT_MARKERS = ("too many requests", "429", "ratelimit", "rate limit", "rate-limit")


# ------------------------------------------------------------------ Abrufperiode
def period_days_for(cache, symbol, now=None, safety_days=3):
    """Wie viele Tage 1h-Daten muessen geholt werden? Leerer/zu alter Cache -> volle 240 d (wie bisher);
    sonst nur die Luecke + Sicherheitsrand (Cache wird additiv gemergt, nie gekuerzt)."""
    now = pd.Timestamp(now) if now is not None else pd.Timestamp.now(tz="UTC")
    if now.tzinfo is None:
        now = now.tz_localize("UTC")
    try:
        d = cache.load(symbol, "1h") if cache is not None else None
    except Exception:
        d = None
    if d is None or len(d) < 300:
        return FULL_PERIOD_DAYS
    last = pd.Timestamp(d["Time"].iloc[-1])
    gap = (now - last).total_seconds() / 86400.0
    n = int(gap + safety_days + 0.999)
    return max(MIN_PERIOD_DAYS, min(MAX_PERIOD_DAYS, n))


def default_downloader_factory(period_for):
    """Downloader (symbol, timeout) -> DataFrame mit je Symbol angepasster Periode."""
    def dl(symbol, timeout):
        import yfinance as yf
        df = yf.download(symbol, period=f"{int(period_for(symbol))}d", interval="1h", auto_adjust=False,
                         progress=False, multi_level_index=False, timeout=timeout)
        if df is None or df.empty:
            raise ValueError(f"Leere Antwort fuer {symbol}")
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna()
    return dl


# ------------------------------------------------------------------ vorsichtiger Abruf
class Throttle:
    """Gemeinsame Bremse aller Abruf-Threads: Mindestabstand zwischen Anfragen + Backoff + Pause nach
    vielen Fehlern in Folge (Yahoo-Sperre vom 09.08. soll sich nicht wiederholen)."""
    def __init__(self, min_interval=0.15, pause_after_failures=6, pause_seconds=60.0, sleep_fn=None, clock=None,
                 max_pauses=2):
        self.min_interval = min_interval
        self.max_pauses = max_pauses                # danach gilt Yahoo als gesperrt: restliche Abrufe dieses Zyklus entfallen
        self.aborted = False
        self.pause_after = pause_after_failures
        self.pause_seconds = pause_seconds
        self.sleep = sleep_fn or _time.sleep
        self.clock = clock or _time.monotonic
        self._lock = threading.Lock()
        self._next_start = 0.0
        self._blocked_until = 0.0
        self.consecutive_failures = 0
        self.pauses = 0
        self.backoffs = 0

    def wait_turn(self):
        with self._lock:
            now = self.clock()
            start = max(now, self._next_start, self._blocked_until)
            self._next_start = start + self.min_interval
        delay = start - self.clock()
        if delay > 0:
            self.sleep(delay)

    def success(self):
        with self._lock:
            self.consecutive_failures = 0

    def failure(self, rate_limited=False, attempt=1):
        with self._lock:
            self.consecutive_failures += 1
            if rate_limited:
                self.backoffs += 1
                self._blocked_until = max(self._blocked_until, self.clock() + min(120.0, 10.0 * 2 ** (attempt - 1)))
            if self.consecutive_failures >= self.pause_after:
                self.pauses += 1
                self._blocked_until = max(self._blocked_until, self.clock() + self.pause_seconds)
                self.consecutive_failures = 0
                if self.pauses >= self.max_pauses:
                    self.aborted = True


def _is_rate_limit(exc):
    t = (type(exc).__name__ + " " + str(exc)).lower()
    return any(m in t for m in RATE_LIMIT_MARKERS)


def fetch_one(symbol, downloader, throttle, retries=2, timeout=30, backoff_seconds=2.0, sleep_fn=None, log=None):
    """Ein Symbol mit Retry/Backoff ueber die gemeinsame Bremse. -> (DataFrame|None, Fehlerklasse|"")"""
    sleep_fn = sleep_fn or _time.sleep
    last = ""
    for attempt in range(1, retries + 2):
        if getattr(throttle, "aborted", False):
            return None, "ABORTED_YAHOO_BLOCK"
        throttle.wait_turn()
        try:
            df = downloader(symbol, timeout)
            if df is None or len(df) == 0:
                raise ValueError("leeres Ergebnis")
            throttle.success()
            return df, ""
        except Exception as e:
            last = type(e).__name__
            throttle.failure(rate_limited=_is_rate_limit(e), attempt=attempt)
            if log is not None:
                log.append(f"{symbol}: Abruf-Versuch {attempt} fehlgeschlagen ({last})")
            if attempt <= retries:
                sleep_fn(backoff_seconds * 2 ** (attempt - 1))
    return None, last


def fetch_many(symbols, downloader, throttle=None, workers=4, **kw):
    """Holt viele Symbole parallel (begrenzt). Reihenfolge der Einreichung = Prioritaet.
    Generator: (symbol, df|None, fehler) in Fertigstellungs-Reihenfolge."""
    throttle = throttle or Throttle()
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = {ex.submit(fetch_one, s, downloader, throttle, **kw): s for s in symbols}
        for f in as_completed(futs):
            s = futs[f]
            try:
                df, err = f.result()
            except Exception as e:                       # darf nie den Zyklus stoppen
                df, err = None, type(e).__name__
            yield s, df, err


# ------------------------------------------------------------------ parallele Erkennung
def _detect_job(compat):
    """Laeuft im Worker-Prozess. Importiert scan_100 dort selbst."""
    return orchestrate.default_detector(compat)


def window_compat(fin, k, lo=0):
    return fin.iloc[lo:k + 1][COLS].reset_index(drop=True)


def plan_jobs(fin, since_time, max_replay, symbol=""):
    """Kerzenindizes, die orchestrate.analyze_instrument_history bewerten wird (gleiche Planung)."""
    times = pd.to_datetime(fin["Time"], utc=True).reset_index(drop=True)
    n = len(fin)
    start_k = orchestrate.plan_start(times, n, since_time, max_replay, symbol)
    return list(range(start_k, n)), times


class DetectPool:
    """Prozess-Pool fuer die Erkennung. Faellt der Pool aus, wird nichts vorberechnet - die Bewertung
    rechnet dann selbst (langsamer, aber gleiches Ergebnis)."""
    def __init__(self, max_workers=6, retry_after_s=300.0, clock=None):
        self.max_workers = max_workers
        self._ex = None
        self.broken = False                         # True, solange nach einem Ausfall noch nicht neu versucht wird
        self._retry_at = 0.0
        self._retry_after = retry_after_s
        self._clock = clock or _time.monotonic

    def _fail(self):
        self.broken = True
        self._retry_at = self._clock() + self._retry_after
        if self._ex is not None:
            try:
                self._ex.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            self._ex = None

    def _executor(self):
        if self.broken and self._clock() >= self._retry_at:
            self.broken = False                     # nach der Pause erneut versuchen (Pool neu aufbauen)
        if self._ex is None and not self.broken:
            try:
                import multiprocessing as mp
                self._ex = ProcessPoolExecutor(max_workers=self.max_workers, mp_context=mp.get_context("spawn"))
            except Exception:
                self._fail()
        return self._ex

    def submit(self, compat):
        ex = self._executor()
        if ex is None:
            return None
        try:
            return ex.submit(_detect_job, compat)
        except Exception:
            self._fail()
            return None

    def shutdown(self):
        if self._ex is not None:
            try:
                self._ex.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass
            self._ex = None


def collect(job_futures, timeout=600):
    """{(symbol, candle_iso): Future} -> {key: det} (nur erfolgreich berechnete)."""
    out = {}
    for key, fut in job_futures.items():
        if fut is None:
            continue
        try:
            out[key] = fut.result(timeout=timeout)
        except Exception:
            continue                                   # Fallback: Bewertung rechnet selbst
    return out
