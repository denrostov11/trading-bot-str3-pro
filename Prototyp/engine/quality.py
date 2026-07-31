# -*- coding: utf-8 -*-
"""Datenqualitaet & Rollover-Erkennung (behebt C4/C5).

- Volumen darf nur genutzt werden, wenn >=95% gueltige, nichtnegative, plausible Werte vorliegen,
  nicht dauerhaft 0, kein Einheitenwechsel, kein volumenloser Index, kein Fake-FX-Volumen.
- SUSPECTED_ROLLOVER via Kombination aus Close-to-Open-Gap + True-Range-Ausreisser + Symboltyp Futures.
- Duplikate/Monotonie werden erkannt.
- Eine Linie darf keinen ungeklaerten Rollover ueberspannen; ein Setup nahe Rollover -> der Aufrufer
  (Baseline-Engine) verwirft es als REJECTED_DATA_QUALITY.
"""
import pandas as pd

VOLUME_OK = "OK"
VOLUME_NOT_AVAILABLE = "VOLUME_NOT_AVAILABLE"


def validate_volume(df, asset_class):
    """(usable: bool, reason). asset_class in {'fx','index','crypto','stock','commodity',...}."""
    ac = (asset_class or "").lower()
    if ac == "fx":
        return False, "FX_NO_CENTRAL_VOLUME"           # kein zentrales Boersenvolumen
    if "Volume" not in df.columns or len(df) == 0:
        return False, VOLUME_NOT_AVAILABLE
    v = pd.to_numeric(df["Volume"], errors="coerce")
    valid_ratio = float((v.notna() & (v >= 0)).mean())
    nonzero_ratio = float((v.fillna(0) > 0).mean())
    if valid_ratio < 0.95:
        return False, f"VOLUME_INVALID_RATIO={valid_ratio:.2f}"
    if nonzero_ratio == 0.0:
        return False, "VOLUME_ALL_ZERO"
    if ac == "index" and nonzero_ratio < 0.5:
        return False, "INDEX_VOLUME_UNRELIABLE"
    # grober Einheitenwechsel-Check: Median-Sprung zwischen erster/zweiter Haelfte
    vv = v.fillna(0)
    if len(vv) >= 20:
        m1 = vv.iloc[:len(vv) // 2].median()
        m2 = vv.iloc[len(vv) // 2:].median()
        if m1 > 0 and m2 > 0 and (max(m1, m2) / min(m1, m2)) > 100:
            return False, "VOLUME_UNIT_CHANGE_SUSPECTED"
    return True, VOLUME_OK


def _true_range(df):
    hl = df["High"] - df["Low"]
    hc = (df["High"] - df["Close"].shift()).abs()
    lc = (df["Low"] - df["Close"].shift()).abs()
    return pd.concat([hl, hc, lc], axis=1).max(axis=1)


def detect_rollover(df, is_futures, tr_mult=5.0, gap_mult=5.0, window=20):
    """Liefert Liste von session_date/Indexpositionen mit SUSPECTED_ROLLOVER.
    Nur fuer Futures relevant (andere Symbole: leere Liste)."""
    if not is_futures or len(df) < window + 2:
        return []
    tr = _true_range(df)
    med_tr = tr.rolling(window).median()
    gap = (df["Open"] - df["Close"].shift()).abs()
    med_gap = gap.rolling(window).median()
    flagged = []
    for i in range(1, len(df)):
        mt = med_tr.iloc[i]
        mg = med_gap.iloc[i]
        big_tr = pd.notna(mt) and mt > 0 and tr.iloc[i] > tr_mult * mt
        big_gap = pd.notna(mg) and mg > 0 and gap.iloc[i] > gap_mult * mg
        if big_tr or big_gap:
            when = df["session_date"].iloc[i] if "session_date" in df.columns else i
            flagged.append(when)
    return flagged


def data_quality(df, asset_class, is_futures, time_col="Time"):
    """Gesamtstatus-Dict fuer eine Zeitreihe."""
    dup = 0
    monotonic = True
    if time_col in df.columns:
        t = pd.to_datetime(df[time_col], utc=True, errors="coerce")
        dup = int(t.duplicated().sum())
        monotonic = bool(t.is_monotonic_increasing)
    v = pd.to_numeric(df["Volume"], errors="coerce") if "Volume" in df.columns else None
    zero_ratio = float((v.fillna(0) == 0).mean()) if v is not None else 1.0
    vol_ok, vol_reason = validate_volume(df, asset_class)
    rolls = detect_rollover(df, is_futures)
    status = "OK"
    if not monotonic or dup > 0:
        status = "TIMESERIES_ISSUE"
    return {
        "duplicate_count": dup,
        "monotonic": monotonic,
        "zero_volume_ratio": round(zero_ratio, 4),
        "volume_usable": vol_ok,
        "volume_reason": vol_reason,
        "suspected_rollover": rolls,
        "status": status,
    }


def near_rollover(setup_time_iso, rollover_dates, tol_days=2):
    """True, wenn ein Setup-Zeitpunkt in der Naehe eines ungeklaerten Rollovers liegt."""
    if not rollover_dates:
        return False
    setup = pd.Timestamp(setup_time_iso).date()
    for r in rollover_dates:
        try:
            rd = pd.Timestamp(r).date()
        except Exception:
            continue
        if abs((setup - rd).days) <= tol_days:
            return True
    return False
