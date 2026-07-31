# -*- coding: utf-8 -*-
"""Persistenter, additiver lokaler Kursdaten-Cache.

Grundsaetze (Spec <datenquelle>):
- Lokale Historie darf NIE durch einen kuerzeren Download geloescht werden.
- Download-Ergebnisse werden mit vorhandenem Cache zusammengefuehrt und nach Zeitstempel dedupliziert.
- Zeitreihe bleibt monoton steigend (nach Zeit sortiert, keine Duplikate).

Format vorerst CSV (dependency-frei; pyarrow/Parquet nicht installiert). Interface storage-agnostisch:
eine Datei je (symbol, interval). Zeitstempel als ISO-UTC in Spalte 'Time'.
"""
import os
import pandas as pd

_TIME = "Time"


def _safe(symbol):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(symbol))


class BarCache:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        os.makedirs(base_dir, exist_ok=True)

    def _path(self, symbol, interval):
        return os.path.join(self.base_dir, f"{_safe(symbol)}__{interval}.csv")

    def load(self, symbol, interval):
        """Gibt DataFrame (Spalte 'Time' als tz-aware UTC) oder None."""
        p = self._path(symbol, interval)
        if not os.path.exists(p):
            return None
        df = pd.read_csv(p)
        if _TIME not in df.columns or df.empty:
            return None
        df[_TIME] = pd.to_datetime(df[_TIME], utc=True)
        return df.sort_values(_TIME).reset_index(drop=True)

    @staticmethod
    def _normalize(df):
        """Bringt beliebiges Eingabe-df in Form: Spalte 'Time' (tz-aware UTC) + OHLCV."""
        d = df.copy()
        if _TIME not in d.columns:
            # Index ist der Zeitstempel
            d = d.reset_index()
            # erste Spalte als Time interpretieren
            first = d.columns[0]
            if first != _TIME:
                d = d.rename(columns={first: _TIME})
        d[_TIME] = pd.to_datetime(d[_TIME], utc=True)
        return d

    def merge(self, symbol, interval, new_df):
        """Fuehrt neue Bars additiv mit dem Cache zusammen (Union, Dedup, Sortierung) und
        persistiert. Der Cache wird NIE kleiner. Gibt das zusammengefuehrte DataFrame zurueck."""
        new = self._normalize(new_df)
        old = self.load(symbol, interval)
        if old is not None and len(old):
            combined = pd.concat([old, new], ignore_index=True)
        else:
            combined = new
        combined = (combined.dropna(subset=[_TIME])
                    .drop_duplicates(subset=[_TIME], keep="last")
                    .sort_values(_TIME).reset_index(drop=True))
        p = self._path(symbol, interval)
        combined.to_csv(p, index=False)
        return combined
