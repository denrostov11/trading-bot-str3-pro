# -*- coding: utf-8 -*-
"""Session-/vollstaendigkeitsbewusste Aggregation 1h -> 4h.

Behebt A1/A2: NICHT blindes resample ab Mitternacht. Stattdessen:
- Feste 4h-Ankergitter (anchor_hour in UTC; je Assetklasse konfigurierbar).
- Optionaler Session-Filter (welche UTC-Stunden handelbar sind) -> erwartete Barzahl je Block.
- Pro 4h-Block: start_utc, end_utc, session_date, Open/High/Low/Close/Volume,
  source_1h_bar_count, completeness_ratio, is_final.
- Ein Block ist NUR is_final, wenn er zeitlich abgeschlossen ist (end <= data_cutoff) UND alle
  erwarteten 1h-Bars vorliegen. Unvollstaendige Bloecke duerfen kein Signal/Tap/Pivot/Bruch erzeugen.
"""
import pandas as pd

_TIME = "Time"
_HOUR = 3600
_BIN = 4 * _HOUR


def _epoch(ts):
    return int(pd.Timestamp(ts).timestamp())


def aggregate(df_1h, anchor_hour=0, session_hours=None, data_cutoff=None):
    """df_1h: DataFrame mit Spalte 'Time' (tz-aware UTC) + Open/High/Low/Close[/Volume], 1h-Raster.
    anchor_hour: UTC-Stunde, an der ein 4h-Block beginnen darf (Gitter alle 4h ab dieser Stunde).
    session_hours: set von UTC-Stunden (0..23), die handelbar sind; None = 24/7 (alle Stunden).
    data_cutoff: Zeitpunkt (tz-aware) bis zu dem Daten als 'bekannt' gelten; Default = letzter Bar + 1h.
    Gibt DataFrame der 4h-Bloecke zurueck (nur strukturiert; Filterung is_final macht der Aufrufer)."""
    d = df_1h.copy()
    d[_TIME] = pd.to_datetime(d[_TIME], utc=True)
    d = d.dropna(subset=[_TIME]).sort_values(_TIME).reset_index(drop=True)
    if d.empty:
        return pd.DataFrame(columns=[_TIME, "start_utc", "end_utc", "session_date", "Open", "High",
                                     "Low", "Close", "Volume", "source_1h_bar_count",
                                     "completeness_ratio", "is_final"])
    has_vol = "Volume" in d.columns
    anchor_off = (anchor_hour % 4) * _HOUR
    if data_cutoff is None:
        cutoff = _epoch(d[_TIME].iloc[-1]) + _HOUR       # letzter 1h-Bar deckt [t, t+1h)
    else:
        cutoff = _epoch(data_cutoff)

    def bin_start(ep):
        return ep - ((ep - anchor_off) % _BIN)

    # erwartete Barzahl je Block (Session-Filter ueber die 4 Stunden-Slots)
    def expected_for(bs_ep):
        if session_hours is None:
            return 4
        cnt = 0
        for k in range(4):
            hh = int(((bs_ep + k * _HOUR) // _HOUR) % 24)
            if hh in session_hours:
                cnt += 1
        return max(cnt, 1)

    d["_bs"] = d[_TIME].map(lambda t: bin_start(_epoch(t)))
    rows = []
    for bs, g in d.groupby("_bs", sort=True):
        be = bs + _BIN
        src = len(g)
        exp = expected_for(bs)
        start_ts = pd.Timestamp(bs, unit="s", tz="UTC")
        end_ts = pd.Timestamp(be, unit="s", tz="UTC")
        row = {
            _TIME: start_ts, "start_utc": start_ts, "end_utc": end_ts,
            "session_date": start_ts.date().isoformat(),
            "Open": float(g["Open"].iloc[0]), "High": float(g["High"].max()),
            "Low": float(g["Low"].min()), "Close": float(g["Close"].iloc[-1]),
            "Volume": float(g["Volume"].sum()) if has_vol else 0.0,
            "source_1h_bar_count": src,
            "completeness_ratio": round(min(src / exp, 1.0), 4),
            "is_final": bool(be <= cutoff and src >= exp),
        }
        rows.append(row)
    return pd.DataFrame(rows).sort_values(_TIME).reset_index(drop=True)


def final_only(df_4h):
    """Nur abgeschlossene 4h-Bloecke - Basis fuer jede Signal-/Tap-/Pivot-/Bruch-Berechnung (A1)."""
    return df_4h[df_4h["is_final"]].reset_index(drop=True)


# Assetklassen-Standardanker (bestaetigt als Startannahme; je Symbol verfeinerbar)
CRYPTO_24_7 = dict(anchor_hour=0, session_hours=None)   # 00/04/08/12/16/20 UTC, alle Stunden
