# -*- coding: utf-8 -*-
"""Historische Datenbeschaffung + Einfrieren fuer den 18-Monats-Backtest (Abschnitt 3 des Backtest-Prompts).

- Voll-Range 1h (Yahoo max ~730 Tage) + Daily (mehrjaehrig) je Symbol, inkl. Vorlauf vor Testbeginn
  (fuer EMA200/ATR/Pivots/Trendlinien-Aufwaermung).
- Rohdaten UNVERAENDERT als CSV einfrieren -> reproduzierbar; ein Wiederholungslauf nutzt exakt
  dieselben Daten (Prompt Abschnitt 11). Einmal eingefroren wird NICHT ueberschrieben.
- daily_asof(): look-ahead-freier Daily-Ausschnitt - nur Tageskerzen, die zum Replay-Zeitpunkt
  bereits VOLLSTAENDIG abgeschlossen waren (Prompt: ein Daily-Wert ist erst nach Schluss der
  Tageskerze verfuegbar; kein Auffuellen mit zukuenftigen Schlusskursen).

Der Downloader ist INJIZIERBAR (Default yfinance) -> Tests laufen ohne Netz.
"""
import os
import pandas as pd

BT_1H_PERIOD = "730d"     # Yahoo-Maximum fuer 1h
BT_1D_PERIOD = "5y"       # Daily reicht mehrjaehrig zurueck (EMA200-Vorlauf locker gedeckt)
_COLS = ["Time", "Open", "High", "Low", "Close", "Volume"]


def _normalize(df):
    """yfinance-/roh-DataFrame -> Spalten Time,Open,High,Low,Close,Volume (Time = UTC)."""
    d = df.copy()
    if "Time" not in d.columns:
        d = d.reset_index()
        first = d.columns[0]
        if first != "Time":
            d = d.rename(columns={first: "Time"})
    d["Time"] = pd.to_datetime(d["Time"], utc=True)
    for c in _COLS:
        if c not in d.columns:
            d[c] = pd.NA
    return d[_COLS].dropna(subset=["Open", "High", "Low", "Close"]).reset_index(drop=True)


def _yf(symbol, interval, period, timeout=60):
    import yfinance as yf
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=False,
                     progress=False, multi_level_index=False, timeout=timeout)
    if df is None or df.empty:
        raise ValueError(f"Leere Antwort {symbol} {interval}")
    return df


def safe_name(symbol):
    """Dateisicherer Name (Yahoo-Symbole enthalten / = ^)."""
    return symbol.replace("/", "_").replace("=", "_").replace("^", "_")


def _read_frozen(path):
    d = pd.read_csv(path)
    d["Time"] = pd.to_datetime(d["Time"], utc=True)
    return d


def fetch_and_freeze(symbol, frozen_dir, dl_1h=None, dl_1d=None, timeout=60):
    """Friert 1h + Daily je Symbol als CSV ein (falls noch nicht vorhanden -> reproduzierbar).
    Bereits eingefrorene Dateien werden NICHT ueberschrieben und stattdessen geladen.
    Gibt {"1h": DataFrame|None, "1d": DataFrame|None}. None = dauerhafter Downloadfehler
    (wird NICHT geworfen; der Aufrufer behandelt das Symbol als quarantaenisiert)."""
    os.makedirs(frozen_dir, exist_ok=True)
    out = {}
    for interval, period, dl in (("1h", BT_1H_PERIOD, dl_1h), ("1d", BT_1D_PERIOD, dl_1d)):
        path = os.path.join(frozen_dir, f"{safe_name(symbol)}_{interval}.csv")
        if os.path.exists(path):
            out[interval] = _read_frozen(path)
            continue
        try:
            raw = dl(symbol) if dl else _yf(symbol, interval, period, timeout)
            norm = _normalize(raw)
            if len(norm) == 0:
                raise ValueError("leer nach Normalisierung")
        except Exception:
            out[interval] = None
            continue
        # Atomar einfrieren: erst vollstaendig in eine Temp-Datei, dann umbenennen. Sonst koennte ein
        # Abbruch eine abgeschnittene Historie hinterlassen, die spaeter als vollstaendig gilt.
        tmp = path + ".tmp"
        norm.to_csv(tmp, index=False)
        os.replace(tmp, path)
        out[interval] = norm
    return out


def daily_asof(daily_df, ts):
    """Look-ahead-frei: nur Tageskerzen, deren Handelstag VOR dem Datum von ts liegt.
    Die Tageskerze des laufenden Tages ist zu einem Intraday-Zeitpunkt noch nicht abgeschlossen
    und darf nicht verwendet werden. ts = tz-aware Timestamp (oder ISO-String)."""
    if daily_df is None or len(daily_df) == 0:
        return daily_df
    t = pd.Timestamp(ts)
    if t.tzinfo is None:
        t = t.tz_localize("UTC")
    times = pd.to_datetime(daily_df["Time"], utc=True)
    return daily_df[times.dt.normalize() < t.normalize()].reset_index(drop=True)
