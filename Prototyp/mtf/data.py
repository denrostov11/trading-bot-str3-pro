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
Nur lesender Zugriff auf Laufdaten; geschrieben wird ausschliesslich in den Cache-Ordner.

Cache-Ordner (konfigurierbar): Umgebungsvariable MTF_CACHE_DIR, zur Laufzeit set_cache_dir(pfad) oder Argument cache_dir;
Standard Prototyp_v2/mtf_cache. Eingefrorene Backtest-Tagesdaten (Fallback): MTF_FROZEN_DIR bzw. Prototyp_v2/backtest_runtime/frozen.
Fehlende Daten fuehren NIE zu einer Ausnahme in build_timeframes: der betroffene Zeitrahmen ist dann leer ("keine Daten" im Chart).
"""
import os
import time
import pandas as pd

PROTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MTF_CACHE = os.environ.get("MTF_CACHE_DIR") or os.path.join(PROTO, "mtf_cache")
FROZEN_DIR = os.environ.get("MTF_FROZEN_DIR") or os.path.join(PROTO, "backtest_runtime", "frozen")
COLS = ["Time", "Open", "High", "Low", "Close", "Volume", "End"]
FETCH_RETRY_HOURS = 6.0       # nach fehlgeschlagenem Yahoo-Abruf fuer diesen Zeitraum NICHT erneut anfragen


def set_cache_dir(path):
    """Cache-Ordner zur Laufzeit umstellen (z. B. aus der Bot-Konfiguration)."""
    global MTF_CACHE
    MTF_CACHE = str(path)
    return MTF_CACHE


def empty_frame():
    """Leerer Kerzen-DataFrame mit den Standardspalten (Zeitspalten UTC)."""
    d = pd.DataFrame({"Time": pd.Series([], dtype="datetime64[ns, UTC]"), "Open": pd.Series([], dtype=float),
                      "High": pd.Series([], dtype=float), "Low": pd.Series([], dtype=float),
                      "Close": pd.Series([], dtype=float), "Volume": pd.Series([], dtype=float),
                      "End": pd.Series([], dtype="datetime64[ns, UTC]")})
    return d[COLS]


def is_empty(df):
    return df is None or len(df) == 0


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


def prepare(df, delta):
    """Kerzen-DataFrame aus beliebiger Quelle normalisieren: Spalte Time (UTC) – notfalls aus dem Index –, sortiert, ohne
    Duplikate, mit Volume und End (= Time + delta). None/leer -> leerer Rahmen."""
    if is_empty(df):
        return empty_frame()
    d = df.copy()
    if "Time" not in d.columns:
        d = d.reset_index()
        d = d.rename(columns={d.columns[0]: "Time"})
    d["Time"] = pd.to_datetime(d["Time"], utc=True)
    d = d.sort_values("Time").drop_duplicates("Time")
    if "End" in d.columns:
        d["End"] = pd.to_datetime(d["End"], utc=True)
        if "Volume" not in d.columns:
            d["Volume"] = 0.0
        return d[COLS].reset_index(drop=True)
    return with_end(d, delta)


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


def _fail_marker(path):
    return path + ".failed"


def _recently_failed(path):
    m = _fail_marker(path)
    try:
        return (time.time() - os.path.getmtime(m)) < FETCH_RETRY_HOURS * 3600
    except OSError:
        return False


def _mark_failed(path):
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(_fail_marker(path), "w", encoding="utf-8") as f:
            f.write(str(time.time()))
    except OSError:
        pass


def _extend_with_1h(d, h1):
    """Tage NACH dem Ende der Tagesreihe aus 1h-Kerzen ergaenzen (Cache kann aelter sein als die 1h-Daten)."""
    if h1 is None or not len(h1) or not len(d):
        return d
    more = daily_from_1h(h1, after=d["End"].iloc[-1])
    return pd.concat([d, more], ignore_index=True) if len(more) else d


def load_daily(symbol, h1=None, cache_dir=None, frozen_dir=None, allow_fetch=True, fetch_fn=None):
    """Tageskerzen (mit End). Reihenfolge: Cache -> einmaliger Yahoo-Abruf (in den Cache; nach Fehlschlag 6 h keine neue
    Anfrage) -> Fallback eingefrorene Backtest-Tagesdaten -> aus 1h gebaute Tage (kurze Historie). Spaetere Tage, die in der
    Tagesreihe fehlen, werden aus den 1h-Daten ergaenzt. Gibt (df, quelle); df=None, wenn nichts verfuegbar."""
    cache_dir = cache_dir or MTF_CACHE
    frozen_dir = frozen_dir or FROZEN_DIR
    path = os.path.join(cache_dir, f"{safe(symbol)}__1d.csv")
    if os.path.exists(path):
        try:
            d = pd.read_csv(path)
            d["Time"] = pd.to_datetime(d["Time"], utc=True)
            return _extend_with_1h(with_end(d, pd.Timedelta(days=1)), h1), "mtf_cache"
        except Exception:
            pass                                          # kaputte Cache-Datei: wie nicht vorhanden behandeln
    if allow_fetch and not _recently_failed(path):
        raw = fetch_daily_max(symbol, fetch_fn)
        if raw is not None and len(raw) > 100:
            d = normalize_daily(raw)[["Time", "Open", "High", "Low", "Close", "Volume"]]
            os.makedirs(cache_dir, exist_ok=True)
            tmp = path + ".tmp"
            d.to_csv(tmp, index=False)
            os.replace(tmp, path)
            return _extend_with_1h(with_end(d, pd.Timedelta(days=1)), h1), "yahoo_max"
        _mark_failed(path)                                # KEIN Wiederholen (Yahoo sparsam nutzen)
    fz = os.path.join(frozen_dir, f"{safe(symbol)}_1d.csv")
    if os.path.exists(fz):
        d = pd.read_csv(fz)
        d["Time"] = pd.to_datetime(d["Time"], utc=True)
        d = with_end(normalize_daily(d), pd.Timedelta(days=1))
        return _extend_with_1h(d, h1), "eingefroren(+1h)"
    if h1 is not None and len(h1):
        d = daily_from_1h(h1)
        if len(d):
            return d, "aus 1h gebaut (kurze Historie)"
    return None, "keine"


def daily_from_1h(h1, after=None):
    """Tageskerzen (UTC-Kalendertag) aus 1h-Kerzen; nur (fast) vollstaendige Tage. after: erst Tage ab diesem Zeitpunkt."""
    if h1 is None or not len(h1):
        return empty_frame()
    d = h1.copy()
    d["Day"] = d["Time"].dt.normalize()
    g = d.groupby("Day").agg(Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
                             Close=("Close", "last"), Volume=("Volume", "sum"), n=("Open", "size")).reset_index()
    full = max(3.0, 0.6 * float(g["n"].median()))            # Aktien: ~7 1h-Kerzen je Tag, FX/Krypto: 24
    g = g[g["n"] >= full]
    if after is not None:
        g = g[g["Day"] >= after]
    if not len(g):
        return empty_frame()
    g = g.rename(columns={"Day": "Time"})
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
    if is_empty(h1_raw):
        return empty_frame()
    from engine import aggregate_4h
    raw = h1_raw[["Time", "Open", "High", "Low", "Close", "Volume"]]
    agg = aggregate_4h.aggregate(raw, anchor_hour=0, session_hours=None, data_cutoff=_utc(cutoff))
    fin = aggregate_4h.final_only(agg).reset_index(drop=True)
    if not len(fin):
        return empty_frame()
    d = fin[["Time", "Open", "High", "Low", "Close", "Volume"]].copy()
    d["End"] = pd.to_datetime(fin["end_utc"], utc=True)
    return d[COLS].reset_index(drop=True)


def _safe(fn, *args):
    """Fehlende/defekte Daten ergeben einen leeren Zeitrahmen statt einer Ausnahme."""
    try:
        out = fn(*args)
        return empty_frame() if out is None else out
    except Exception:
        return empty_frame()


def build_timeframes(h1, daily, cutoff):
    """Alle fuenf Zeitrahmen zum Signalzeitpunkt `cutoff`. Rueckgabe: {tf: {"closed": df, "partial": dict|None}}.
    h1 = 1h-Kerzen (mit End), daily = Tageskerzen (mit End). Fehlende Daten (None/leer/defekt) -> leerer Zeitrahmen."""
    c = _utc(cutoff)
    out = {}
    h1c = _safe(closed_until, h1, c) if not is_empty(h1) else empty_frame()
    out["1h"] = {"closed": h1c, "partial": None}
    out["4h"] = {"closed": _safe(lambda: closed_until(four_hour(h1, c), c)), "partial": None}
    dc = _safe(closed_until, daily, c) if not is_empty(daily) else empty_frame()
    def part(tf):
        try:
            return partial_candle(h1c, tf, c) if len(h1c) else None
        except Exception:
            return None
    out["D"] = {"closed": dc, "partial": part("D")}
    out["W"] = {"closed": _safe(lambda: closed_until(aggregate_week(dc), c)) if len(dc) else empty_frame(), "partial": part("W")}
    out["M"] = {"closed": _safe(lambda: closed_until(aggregate_month(dc), c)) if len(dc) else empty_frame(), "partial": part("M")}
    return out
