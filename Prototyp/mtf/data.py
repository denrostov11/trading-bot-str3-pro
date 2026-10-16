# -*- coding: utf-8 -*-
"""Daten fuer die Mehrzeitrahmen-Analyse (Monat/Woche/Tag/4h/1h) - OHNE Look-ahead.

Regeln
- Tag: laengstmoegliche Tageshistorie (Yahoo "max", einmalig in Prototyp/mtf_cache/ abgelegt; bei Fehler
  KEIN Wiederholen - Fallback auf die eingefrorenen Backtest-Tagesdaten + aus 1h gebaute Tage).
- Woche (Mo-So) und Monat werden aus den Tageskerzen aggregiert. 4h kommt aus 1h ueber die Engine-Aggregation
  (gleicher Anker, nur finale Kerzen). 1h direkt.
- Jede Kerze hat eine Spalte End (Ende der Kerzenperiode, exklusiv). Fuer den Signalzeitpunkt (cutoff) zaehlen
  nur Kerzen mit End <= cutoff ("abgeschlossen"). Die zum Signalzeitpunkt LAUFENDE Monats-/Wochen-/Tageskerze
  wird NICHT fuer die Linienerkennung benutzt (konsistent zur Engine: nur finale Kerzen), aber als "unfertige"
  Kerze aus den 1h-Daten bis zum cutoff gebaut und hell dargestellt - so sieht man, wo der Kurs gerade steht,
  ohne dass eine nicht abgeschlossene Kerze Linien oder Bruchsignale beeinflusst.
Nur lesender Zugriff auf Laufdaten; geschrieben wird ausschliesslich in mtf_cache/.
"""
import os
import pandas as pd

PROTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MTF_CACHE = os.path.join(PROTO, "mtf_cache")
FROZEN_DIR = os.path.join(PROTO, "backtest_runtime", "frozen")
COLS = ["Time", "Open", "High", "Low", "Close", "Volume", "End"]


def safe(sym):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(sym))


def _utc(ts):
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


# ------------------------------------------------------------------ Laden
def with_end(df, delta):
    d = df.copy()
    d["Time"] = pd.to_datetime(d["Time"], utc=True)
    if "Volume" not in d.columns:
        d["Volume"] = 0.0
    d["End"] = d["Time"] + delta
    return d[COLS].reset_index(drop=True)


def load_1h(path):
    d = pd.read_csv(path)
    d["Time"] = pd.to_datetime(d["Time"], utc=True)
    return with_end(d.sort_values("Time").drop_duplicates("Time"), pd.Timedelta(hours=1))


def normalize_daily(df):
    """Yahoo-Tagesindex (Boersenzeitzone) -> Zeit = UTC-Mitternacht des LOKALEN Kalendertags."""
    d = df.copy()
    if "Time" not in d.columns:
        d = d.reset_index()
        d = d.rename(columns={d.columns[0]: "Time"})
    t = pd.to_datetime(d["Time"])
    if getattr(t.dt, "tz", None) is not None:
        t = t.dt.tz_localize(None)                  # lokales Datum behalten
    d["Time"] = t.dt.normalize().dt.tz_localize("UTC")
    return d


def fetch_daily_max(symbol, fetch_fn=None):
    """EIN Abruf der maximalen Tageshistorie. Gibt DataFrame oder None (bei Fehler: nicht wiederholen)."""
    try:
        if fetch_fn is not None:
            return fetch_fn(symbol)
        import yfinance as yf
        df = yf.download(symbol, period="max", interval="1d", auto_adjust=False, progress=False,
                         multi_level_index=False, timeout=30)
        if df is None or df.empty:
            return None
        return df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Open", "High", "Low", "Close"])
    except Exception:
        return None


def load_daily(symbol, h1=None, cache_dir=MTF_CACHE, frozen_dir=FROZEN_DIR, allow_fetch=True, fetch_fn=None):
    """Tageskerzen (mit End). Reihenfolge: mtf_cache -> einmaliger Yahoo-Abruf (in mtf_cache) ->
    Fallback eingefrorene Backtest-Tagesdaten (+ aus 1h gebaute spaetere Tage). Gibt (df, quelle)."""
    path = os.path.join(cache_dir, f"{safe(symbol)}__1d.csv")
    if os.path.exists(path):
        d = pd.read_csv(path)
        d["Time"] = pd.to_datetime(d["Time"], utc=True)
        return with_end(d, pd.Timedelta(days=1)), "mtf_cache"
    if allow_fetch:
        raw = fetch_daily_max(symbol, fetch_fn)
        if raw is not None and len(raw) > 100:
            d = normalize_daily(raw)[["Time", "Open", "High", "Low", "Close", "Volume"]]
            os.makedirs(cache_dir, exist_ok=True)
            tmp = path + ".tmp"
            d.to_csv(tmp, index=False)
            os.replace(tmp, path)
            return with_end(d, pd.Timedelta(days=1)), "yahoo_max"
    fz = os.path.join(frozen_dir, f"{safe(symbol)}_1d.csv")
    if os.path.exists(fz):
        d = pd.read_csv(fz)
        d["Time"] = pd.to_datetime(d["Time"], utc=True)
        d = with_end(normalize_daily(d), pd.Timedelta(days=1))
        if h1 is not None and len(h1):                # spaetere Tage aus 1h ergaenzen
            more = daily_from_1h(h1, after=d["End"].iloc[-1])
            d = pd.concat([d, more], ignore_index=True)
        return d, "eingefroren(+1h)"
    return None, "keine"


def daily_from_1h(h1, after=None):
    d = h1.copy()
    d["Day"] = d["Time"].dt.normalize()
    if after is not None:
        d = d[d["Day"] >= after]
    g = d.groupby("Day").agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
                             Close=("Close", "last"), Volume=("Volume", "sum"), n=("Open", "size")).reset_index()
    g = g[g["n"] >= 20].rename(columns={"Day": "Time"})     # nur (fast) vollstaendige Tage
    return with_end(g[["Time", "Open", "High", "Low", "Close", "Volume"]], pd.Timedelta(days=1))


# ------------------------------------------------------------------ Aggregation Woche / Monat
def _agg(daily, key, end_fn):
    g = daily.groupby(key, sort=True)
    out = g.agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"), Close=("Close", "last"),
                Volume=("Volume", "sum")).reset_index()
    out = out.rename(columns={out.columns[0]: "Time"})
    out["End"] = out["Time"].map(end_fn)
    return out[COLS]


def aggregate_week(daily):
    """Wochenkerzen Montag 00:00 UTC bis Montag 00:00 UTC (End = Beginn der Folgewoche)."""
    d = daily.sort_values("Time")
    key = d["Time"].dt.normalize() - pd.to_timedelta(d["Time"].dt.weekday, unit="D")
    return _agg(d.assign(_k=key), "_k", lambda t: t + pd.Timedelta(days=7))


def aggregate_month(daily):
    d = daily.sort_values("Time")
    key = d["Time"].dt.tz_localize(None).dt.to_period("M").dt.start_time.dt.tz_localize("UTC")
    return _agg(d.assign(_k=key), "_k", lambda t: t + pd.DateOffset(months=1))


# ------------------------------------------------------------------ No-Look-ahead
def closed_until(df, cutoff):
    """Nur abgeschlossene Kerzen: End <= cutoff."""
    c = _utc(cutoff)
    return df[df["End"] <= c].reset_index(drop=True)


def period_start(tf, cutoff):
    c = _utc(cutoff)
    if tf == "D":
        return c.normalize()
    if tf == "W":
        return c.normalize() - pd.Timedelta(days=c.weekday())
    if tf == "M":
        return pd.Timestamp(year=c.year, month=c.month, day=1, tz="UTC")
    raise ValueError(tf)


def partial_candle(h1, tf, cutoff):
    """Unfertige Kerze der laufenden Periode aus 1h-Daten bis cutoff (nur Daten <= cutoff!). None, wenn keine."""
    c = _utc(cutoff)
    start = period_start(tf, c)
    sub = h1[(h1["Time"] >= start) & (h1["End"] <= c)]
    if sub.empty:
        return None
    end = {"D": start + pd.Timedelta(days=1), "W": start + pd.Timedelta(days=7), "M": start + pd.DateOffset(months=1)}[tf]
    if end <= c:
        return None
    return {"Time": start, "Open": float(sub["Open"].iloc[0]), "High": float(sub["High"].max()),
            "Low": float(sub["Low"].min()), "Close": float(sub["Close"].iloc[-1]), "Volume": float(sub["Volume"].sum()),
            "End": end, "partial": True}


def four_hour(h1_raw, cutoff):
    """4h aus 1h ueber die Engine-Aggregation (Anker 00:00 UTC), nur finale Kerzen bis cutoff."""
    from engine import aggregate_4h
    raw = h1_raw[["Time", "Open", "High", "Low", "Close", "Volume"]]
    agg = aggregate_4h.aggregate(raw, anchor_hour=0, session_hours=None, data_cutoff=_utc(cutoff))
    fin = aggregate_4h.final_only(agg).reset_index(drop=True)
    d = fin[["Time", "Open", "High", "Low", "Close", "Volume"]].copy()
    d["End"] = pd.to_datetime(fin["end_utc"], utc=True)
    return d[COLS].reset_index(drop=True)


def build_timeframes(h1, daily, cutoff):
    """Alle fuenf Zeitrahmen zum Signalzeitpunkt `cutoff`. Rueckgabe: {tf: {"closed": df, "partial": dict|None}}.
    h1 = 1h-Kerzen (mit End), daily = Tageskerzen (mit End)."""
    c = _utc(cutoff)
    out = {}
    h1c = closed_until(h1, c)
    out["1h"] = {"closed": h1c, "partial": None}
    out["4h"] = {"closed": closed_until(four_hour(h1, c), c), "partial": None}
    dc = closed_until(daily, c)
    out["D"] = {"closed": dc, "partial": partial_candle(h1c, "D", c)}
    out["W"] = {"closed": closed_until(aggregate_week(dc), c), "partial": partial_candle(h1c, "W", c)}
    out["M"] = {"closed": closed_until(aggregate_month(dc), c), "partial": partial_candle(h1c, "M", c)}
    return out
