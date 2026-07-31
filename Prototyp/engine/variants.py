# -*- coding: utf-8 -*-
"""Varianten-Engine: Pro.1-Pro.8 bewerten den GEMEINSAMEN Snapshot mit ihren ZUSATZ-Filtern.

Verbindlich (Spec/Praez. 3,4):
- Alle Varianten bewerten exakt denselben unveraenderlichen Baseline-Snapshot (parent_signal_id).
- Eine Variante darf NIE rueckwirkend Trendlinie/Safety/Pivots/S/R-Zone aendern - nur zusaetzliche
  Filter auf bereits berechneten Features pruefen.
- Statuswerte: PASS / FAIL / NOT_EVALUABLE / DIAGNOSTIC / NOT_CONFIGURED.
- Fehlende Features -> NOT_EVALUABLE (nie stillschweigend als bestanden werten).

Break-even-Modi (BE-0..BE-4) sind KEIN Signalfilter, sondern Stop-Management im Tracker (S8) -
hier nicht enthalten.
"""
from dataclasses import dataclass, field

PASS = "PASS"
FAIL = "FAIL"
NOT_EVALUABLE = "NOT_EVALUABLE"
DIAGNOSTIC = "DIAGNOSTIC"
NOT_CONFIGURED = "NOT_CONFIGURED"


@dataclass
class VariantDecision:
    strategy_id: str
    status: str
    filter_values: dict = field(default_factory=dict)
    reason: str = ""

    @property
    def accepted(self):
        return self.status in (PASS, DIAGNOSTIC)   # DIAGNOSTIC (Pro.7) handelt weiter, nur ohne Schwelle


def _need(features, *keys):
    return all(k in features and features[k] is not None for k in keys)


def pro1(snapshot, f):
    # Reine Baseline: keine Zusatzfilter. Annahme kam bereits aus der Baseline-Engine.
    return VariantDecision("Str.3 Pro.1", PASS)


def pro2(snapshot, f):
    if not _need(f, "daily_close", "daily_ema200", "daily_bars"):
        return VariantDecision("Str.3 Pro.2", NOT_EVALUABLE, reason="Daily-Daten fehlen")
    if f["daily_bars"] < 250:
        return VariantDecision("Str.3 Pro.2", NOT_EVALUABLE, reason="<250 Tageskerzen")
    up = f["daily_close"] > f["daily_ema200"]
    ok = up if snapshot.direction == "LONG" else (not up)
    fv = {"daily_close": f["daily_close"], "daily_ema200": f["daily_ema200"]}
    return VariantDecision("Str.3 Pro.2", PASS if ok else FAIL, fv,
                           "" if ok else "Gegen Daily-EMA200-Richtung")


def pro3(snapshot, f):
    if not f.get("volume_usable"):
        return VariantDecision("Str.3 Pro.3", NOT_EVALUABLE, reason="VOLUME_NOT_AVAILABLE")
    if not _need(f, "rvol20"):
        return VariantDecision("Str.3 Pro.3", NOT_EVALUABLE, reason="RVOL fehlt")
    ok = f["rvol20"] >= 1.20
    return VariantDecision("Str.3 Pro.3", PASS if ok else FAIL, {"rvol20": round(f["rvol20"], 3)},
                           "" if ok else "RVOL<1.20")


def pro4(snapshot, f):
    if not _need(f, "atr_percentile"):
        return VariantDecision("Str.3 Pro.4", NOT_EVALUABLE, reason="ATR-Perzentil fehlt")
    p = f["atr_percentile"]
    ok = 20.0 <= p <= 90.0
    return VariantDecision("Str.3 Pro.4", PASS if ok else FAIL, {"atr_percentile": round(p, 1)},
                           "" if ok else "ATR-Regime ausserhalb 20-90")


def pro5(snapshot, f):
    if not f.get("volume_usable"):
        return VariantDecision("Str.3 Pro.5", NOT_EVALUABLE, reason="COMBINED_NOT_EVALUABLE")
    d2, d3, d4 = pro2(snapshot, f), pro3(snapshot, f), pro4(snapshot, f)
    subs = {"pro2": d2.status, "pro3": d3.status, "pro4": d4.status}
    if NOT_EVALUABLE in subs.values():
        return VariantDecision("Str.3 Pro.5", NOT_EVALUABLE, subs, "Teilfilter nicht auswertbar")
    ok = d2.status == PASS and d3.status == PASS and d4.status == PASS
    return VariantDecision("Str.3 Pro.5", PASS if ok else FAIL, subs)


def pro6(snapshot, f):
    if not _need(f, "body_ratio", "close_pos", "range_atr"):
        return VariantDecision("Str.3 Pro.6", NOT_EVALUABLE, reason="Breakout-Features fehlen")
    body_ok = f["body_ratio"] >= 0.50
    range_ok = 0.80 <= f["range_atr"] <= 2.50
    if snapshot.direction == "LONG":
        pos_ok = f["close_pos"] >= 0.75
    else:
        pos_ok = f["close_pos"] <= 0.25
    ok = body_ok and range_ok and pos_ok
    fv = {"body_ratio": f["body_ratio"], "close_pos": f["close_pos"], "range_atr": f["range_atr"]}
    return VariantDecision("Str.3 Pro.6", PASS if ok else FAIL, fv,
                           "" if ok else "Breakout-Qualitaet unzureichend")


def pro7(snapshot, f):
    # DIAGNOSTIC: nur protokollieren, KEINE Schwelle (Praez. 9).
    fv = {k: f.get(k) for k in ("adx", "choppiness", "r2") if k in f}
    return VariantDecision("Str.3 Pro.7", DIAGNOSTIC, fv, "diagnostisch, keine Schwelle")


def pro8(snapshot, f):
    # PRO8_NOT_CONFIGURED: handelt nicht (Praez. 10).
    return VariantDecision("Str.3 Pro.8", NOT_CONFIGURED, reason="PRO8_NOT_CONFIGURED")


REGISTRY = {
    "Str.3 Pro.1": pro1, "Str.3 Pro.2": pro2, "Str.3 Pro.3": pro3, "Str.3 Pro.4": pro4,
    "Str.3 Pro.5": pro5, "Str.3 Pro.6": pro6, "Str.3 Pro.7": pro7, "Str.3 Pro.8": pro8,
}


def evaluate_variants(snapshot, features, active_variants):
    """Bewertet den gemeinsamen Snapshot mit allen aktiven Varianten. Gibt Liste[VariantDecision].
    parent_signal_id bleibt fuer alle identisch (kommt aus dem Snapshot)."""
    out = []
    for sid in active_variants:
        fn = REGISTRY.get(sid)
        if fn is None:
            out.append(VariantDecision(sid, NOT_CONFIGURED, reason="unbekannte Variante"))
        else:
            out.append(fn(snapshot, features))
    return out
