# -*- coding: utf-8 -*-
"""Baseline-Engine: erzeugt je Kandidat GENAU EINEN unveraenderlichen Signal-Snapshot mit
parent_signal_id. Enthaelt die Kausalfixes:

  A3  - Trigger nur, wenn die Bruchkerze die GERADE abgeschlossene letzte (finale) 4h-Kerze ist;
        Einstieg = Open der NAECHSTEN Kerze (kein rueckdatierter Fill).
  B3  - Stop-Seiten-Guard (LONG stop<entry, SHORT stop>entry) -> sonst REJECTED_STOP (aktiv).
  C4  - Setup nahe ungeklaertem Rollover / schlechter Datenqualitaet -> REJECTED_DATA_QUALITY (aktiv).

DIAGNOSTIC (noch NICHT produktiv aktiv, weil NUTZERENTSCHEIDUNG offen, Praez. 7/8):
  B1/B2 - 2R-Gate & "naechste relevante S/R-Zone nicht ueberspringen": nur berechnet und als
          would_reject_rr protokolliert, NICHT als finale Ablehnung aktiviert.
  ATR-Stop-Grenzen - nur diagnostisch gespeichert.

Confirmed Regeln der Liniengeometrie (Taps/Spacing/Winkel/Dauer/Konvergenz/Safety intakt/Apex 180)
kommen aus der kanonischen Erkennung (scan_100) und werden hier vorausgesetzt.
Der Snapshot ist frozen und darf nach erster Speicherung nicht ueberschrieben werden.
"""
import hashlib
from dataclasses import dataclass, field, asdict

CODE_VERSION = "engine-0.2"

# Entscheidungen / Status
ACCEPTED_PROVISIONAL = "ACCEPTED_PROVISIONAL"
NO_FRESH_TRIGGER = "NO_FRESH_TRIGGER"
REJECTED_STOP = "REJECTED_STOP"
REJECTED_DATA_QUALITY = "REJECTED_DATA_QUALITY"


def make_config_hash(params: dict) -> str:
    raw = "|".join(f"{k}={params[k]}" for k in sorted(params))
    return "C" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:15]


def make_parent_signal_id(symbol, signal_time_iso, action_p0, action_slope):
    raw = f"{symbol}|{signal_time_iso}|{round(action_p0, 6)}|{round(action_slope, 8)}"
    return "PSIG-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def is_fresh_trigger(breaking_bar, n):
    """A3: nur die gerade abgeschlossene letzte (finale) Kerze darf einen Trigger ausloesen."""
    return breaking_bar == n - 1


def project_stop(safety_line, breaking_bar, direction, entry_price, atr_val):
    """Stop = Safety-Line-Projektion an Kerze (breaking_bar+4). Mit B3-Seiten-Guard.
    Gibt dict: stop, side_ok, reason, stop_atr (diagnostisch), stop_atr_in_range (diagnostisch)."""
    stop = float(safety_line.value_at(breaking_bar + 4))
    risk = abs(entry_price - stop)
    if direction == "LONG":
        side_ok = stop < entry_price
    else:
        side_ok = stop > entry_price
    stop_atr = risk / atr_val if atr_val else 0.0
    # DIAGNOSTIC: ATR-Grenzen (Vorschlag 0,5-6) - NICHT filternd bis Freigabe (Praez. 7)
    stop_atr_in_range = 0.5 <= stop_atr <= 6.0
    reason = "" if (side_ok and risk > 0) else ("WRONG_SIDE" if not side_ok else "ZERO_RISK")
    return {"stop": stop, "risk": risk, "side_ok": bool(side_ok and risk > 0),
            "reason": reason, "stop_atr": round(stop_atr, 3), "stop_atr_in_range": stop_atr_in_range}


def provisional_sr_zones(pivot_prices, atr_val, tol_atr=0.6, min_reactions=2):
    """PROVISORISCHE S/R-Zonen (Cluster aus Pivot-Reaktionen). Die endgueltige S/R-Definition ist
    NUTZERENTSCHEIDUNG (Praez. 8) - Ergebnis hier nur diagnostisch verwendbar."""
    pts = sorted(float(p) for p in pivot_prices)
    tol = tol_atr * atr_val
    zones, cluster = [], []
    for p in pts:
        if not cluster or p - cluster[-1] <= tol:
            cluster.append(p)
        else:
            if len(cluster) >= min_reactions:
                zones.append(sum(cluster) / len(cluster))
            cluster = [p]
    if len(cluster) >= min_reactions:
        zones.append(sum(cluster) / len(cluster))
    return zones


def nearest_zone_and_rr(direction, entry, stop, zones):
    """B2: die NAECHSTE relevante Zone in Handelsrichtung (kein Ueberspringen). rr zu genau
    dieser Zone. Gibt (zone, rr) oder (None, None)."""
    risk = abs(entry - stop)
    if risk <= 0:
        return None, None
    if direction == "LONG":
        cands = sorted(z for z in zones if z > entry + 0.5 * risk)
        if not cands:
            return None, None
        z = cands[0]
        return z, (z - entry) / risk
    else:
        cands = sorted((z for z in zones if z < entry - 0.5 * risk), reverse=True)
        if not cands:
            return None, None
        z = cands[0]
        return z, (entry - z) / risk


@dataclass(frozen=True)
class Snapshot:
    parent_signal_id: str
    symbol: str
    asset_class: str
    direction: str
    data_cutoff_time: str
    signal_time: str
    signal_close: float
    action_anchor: tuple            # (i0,p0,i1,p1,kind,taps,angle)
    safety_anchor: tuple
    atr: float
    sr_zones: tuple
    baseline_stop: float
    baseline_target: float
    baseline_rr: float
    data_quality_status: str
    code_version: str = CODE_VERSION
    config_hash: str = ""


@dataclass
class EvaluationResult:
    status: str
    snapshot: Snapshot = None
    diagnostics: dict = field(default_factory=dict)
    rejection_reason: str = ""


def evaluate(symbol, asset_class, direction, action, safety, n, df_final, atr_val,
             signal_time_iso, data_cutoff_iso, pivot_prices, data_quality_status,
             near_unexplained_rollover=False, config_params=None):
    """Baut aus einem erkannten Kandidaten eine EvaluationResult (+ Snapshot bei Annahme).
    action/safety = Linienobjekte (duck-typed: .value_at, .i0/p0/i1/p1/kind/taps/angle_deg)."""
    diagnostics = {}
    # A3: nur frischer Bruch auf der letzten finalen Kerze
    if not is_fresh_trigger(action.breaking_bar, n):
        return EvaluationResult(NO_FRESH_TRIGGER, rejection_reason="Bruch nicht auf letzter finaler Kerze")

    # C4: Datenqualitaet / Rollover
    if near_unexplained_rollover or data_quality_status not in ("OK",):
        return EvaluationResult(REJECTED_DATA_QUALITY,
                                rejection_reason=f"Datenqualitaet {data_quality_status} / Rollover")

    bb = action.breaking_bar
    entry = float(df_final["Close"].iloc[bb])          # provisorisch = Signal-Close; Fill = Open next bar (Tracker)
    ps = project_stop(safety, bb, direction, entry, atr_val)
    diagnostics["stop_atr"] = ps["stop_atr"]
    diagnostics["stop_atr_in_range_DIAGNOSTIC"] = ps["stop_atr_in_range"]

    # B3: Stop-Seiten-Guard (aktiv)
    if not ps["side_ok"]:
        return EvaluationResult(REJECTED_STOP, rejection_reason=ps["reason"], diagnostics=diagnostics)

    zones = provisional_sr_zones(pivot_prices, atr_val)
    zone, rr = nearest_zone_and_rr(direction, entry, ps["stop"], zones)
    # B1/B2: DIAGNOSTIC (S/R-Definition + 2R-Gate noch NUTZERENTSCHEIDUNG)
    diagnostics["nearest_zone"] = zone
    diagnostics["rr_provisional"] = None if rr is None else round(rr, 3)
    diagnostics["would_reject_rr_DIAGNOSTIC"] = (rr is None or rr < 2.0)

    cfg_hash = make_config_hash(config_params or {})
    psig = make_parent_signal_id(symbol, signal_time_iso, action.p0,
                                 (action.p1 - action.p0) / (action.i1 - action.i0))
    snap = Snapshot(
        parent_signal_id=psig, symbol=symbol, asset_class=asset_class, direction=direction,
        data_cutoff_time=data_cutoff_iso, signal_time=signal_time_iso, signal_close=entry,
        action_anchor=(action.i0, action.p0, action.i1, action.p1, action.kind,
                       len(action.taps), round(action.angle_deg, 2)),
        safety_anchor=(safety.i0, safety.p0, safety.i1, safety.p1, safety.kind,
                       len(safety.taps), round(safety.angle_deg, 2)),
        atr=round(atr_val, 6), sr_zones=tuple(round(z, 6) for z in zones),
        baseline_stop=round(ps["stop"], 6),
        baseline_target=None if zone is None else round(zone, 6),
        baseline_rr=None if rr is None else round(rr, 3),
        data_quality_status=data_quality_status, config_hash=cfg_hash,
    )
    return EvaluationResult(ACCEPTED_PROVISIONAL, snapshot=snap, diagnostics=diagnostics)
