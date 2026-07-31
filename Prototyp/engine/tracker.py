# -*- coding: utf-8 -*-
"""Paper-Trade-Tracker (S8): simuliert Trades realistisch und wertet sie selbst aus.

Verbindliche Regeln:
- Einstieg = Open der NAECHSTEN handelbaren Kerze nach dem Signal (kein rueckdatierter Fill, A3).
- Slippage + Gebuehren je Assetklasse (bestaetigt): brutto UND netto parallel gefuehrt.
  Kosten je Seite: FX 0,02% · Index/Futures/Commodity 0,03% · Aktien 0,02% · Krypto 0,10%;
  zusaetzlich 0,05 ATR Slippage je Seite.
- Intrabar: beruehrt eine Kerze Stop UND Ziel -> konservativ STOP zuerst (AMBIGUOUS_INTRABAR).
- MFE_R / MAE_R (max. guenstige/unguenstige Auslenkung in R).
- Break-even-Modi BE-0..BE-4 (Stop-Management; BE aendert R-Bezug NICHT: R bleibt auf Original-Risiko).
- Neustart-fest (PaperTradeStore).
Ein Break-even-Stop garantiert wegen Kosten/Gaps keinen verlustfreien Ausgang -> es zaehlt das Netto.
"""
import json, os
from dataclasses import dataclass, asdict, field

TARGET = "TARGET"
STOP = "STOP"
BREAK_EVEN = "BREAK_EVEN"

SLIP_ATR_PER_SIDE = 0.05
COST_PER_SIDE = {
    "fx": 0.0002, "index": 0.0003, "futures": 0.0003, "commodity": 0.0003,
    "stock": 0.0002, "crypto": 0.0010,
}
# BE-1 Klassen-Schwellen (Prozent in Gewinnrichtung)
BE1_PCT_SLOW = 0.003   # FX/Index
BE1_PCT_FAST = 0.010   # sonst


def cost_fraction(asset_class):
    return COST_PER_SIDE.get((asset_class or "").lower(), 0.0003)


def _be1_pct(asset_class):
    ac = (asset_class or "").lower()
    return BE1_PCT_SLOW if ac in ("fx", "index") else BE1_PCT_FAST


def simulate_trade(direction, asset_class, atr, entry_open, stop_initial, target, bars,
                   be_mode="BE-0"):
    """bars: Liste von dicts mit High/Low (und optional Open/Close), ab der EINSTIEGSKERZE.
    Fill = entry_open (Open der ersten Kerze nach Signal) + Slippage. Gibt Ergebnis-dict."""
    long = direction == "LONG"
    slip = SLIP_ATR_PER_SIDE * atr
    # WICHTIG (Fix P1, kein Doppelabzug): R und Prozent beziehen sich auf den INTENDED Einstieg
    # entry_open (ungeslippt). Slippage + Gebuehren werden GENAU EINMAL als Kosten abgezogen.
    fill = entry_open + slip if long else entry_open - slip       # realistischer Fill (nur informativ)
    entry = entry_open
    risk = abs(entry - stop_initial)
    if risk <= 0:
        return {"error": "ZERO_RISK"}
    stop = float(stop_initial)
    be_moved = False
    mfe = mae = 0.0
    outcome = exit_price = None
    ambiguous = False
    be_buffer = 0.02 * atr

    dur = 0
    for i, bar in enumerate(bars):
        dur = i + 1
        hi = float(bar["High"]); lo = float(bar["Low"])
        # Auslenkungen (in R)
        fav = (hi - entry) / risk if long else (entry - lo) / risk
        adv = (entry - lo) / risk if long else (hi - entry) / risk
        mfe = max(mfe, fav); mae = max(mae, adv)
        # Exit-Pruefung mit AKTUELLEM Stop, Stop zuerst (konservativ)
        hit_stop = lo <= stop if long else hi >= stop
        hit_tgt = hi >= target if long else lo <= target
        if hit_stop and hit_tgt:
            ambiguous = True
            outcome = BREAK_EVEN if be_moved else STOP
            exit_price = stop; break
        if hit_stop:
            outcome = BREAK_EVEN if be_moved else STOP
            exit_price = stop; break
        if hit_tgt:
            outcome = TARGET; exit_price = target; break
        # Break-even-Move NACH den Exit-Checks dieser Kerze (kein Intrabar-Look-ahead)
        if be_mode != "BE-0" and not be_moved:
            trig = False
            if be_mode == "BE-2" and fav >= 0.75: trig = True
            elif be_mode == "BE-3" and fav >= 1.0: trig = True
            elif be_mode == "BE-4" and ((hi - entry) if long else (entry - lo)) >= atr: trig = True
            elif be_mode == "BE-1":
                move = (hi - entry) / entry if long else (entry - lo) / entry
                if move >= _be1_pct(asset_class): trig = True
            if trig:
                new_stop = entry + be_buffer if long else entry - be_buffer
                stop = max(stop, new_stop) if long else min(stop, new_stop)
                be_moved = True
    if outcome is None:
        return {"status": "open", "mfe_r": round(mfe, 3), "mae_r": round(mae, 3),
                "be_moved": be_moved, "stop_current": round(stop, 6), "duration_bars": dur}

    move = (exit_price - entry) if long else (entry - exit_price)
    brutto_r = move / risk                                   # echtes Brutto (aus entry_open)
    fee = cost_fraction(asset_class)
    cost_price = 2 * slip + fee * (abs(entry) + abs(exit_price))   # Slippage 2 Seiten EINMAL + Gebuehren
    netto_r = brutto_r - cost_price / risk
    # Prozentkennzahlen (zentrale Formeln; brutto aus entry_open, netto = brutto - fees - slippage EINMAL)
    gross_return_pct = move / entry * 100
    fees_pct = fee * 2 * 100
    slippage_pct = (2 * slip) / entry * 100
    net_return_pct = gross_return_pct - fees_pct - slippage_pct
    return {
        "status": "closed", "outcome": outcome,
        "entry_open": round(entry, 6), "entry_price": round(fill, 6),   # entry_open=R/%-Basis, entry_price=Fill
        "exit_price": round(exit_price, 6), "stop_initial": round(stop_initial, 6),
        "stop_final": round(stop, 6), "target": round(target, 6), "direction": direction,
        "brutto_r": round(brutto_r, 3), "netto_r": round(netto_r, 3),
        "gross_return_pct": round(gross_return_pct, 4), "fees_pct": round(fees_pct, 4),
        "slippage_pct": round(slippage_pct, 4), "net_return_pct": round(net_return_pct, 4),
        "mfe_r": round(mfe, 3), "mae_r": round(mae, 3), "ambiguous_intrabar": ambiguous,
        "be_moved": be_moved, "duration_bars": dur, "duration_days": round(dur * 4 / 24, 2),
    }


@dataclass
class PaperTrade:
    trade_id: str
    variant_evaluation_id: str
    parent_signal_id: str
    strategy_id: str
    break_even: str
    symbol: str
    asset_class: str
    direction: str
    signal_time: str
    status: str = "pending_fill"     # pending_fill / open / closed
    entry_time: str = ""
    entry_price: float = 0.0
    stop_initial: float = 0.0
    target: float = 0.0
    atr: float = 0.0
    line_sig: str = ""
    result: dict = field(default_factory=dict)
    code_version: str = "engine-0.3"
    config_hash: str = ""


class PaperTradeStore:
    """Neustart-feste Ablage aller Paper-Trades (verbindliche lokale Quelle)."""
    def __init__(self, path):
        self.path = path
        self.trades = []
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.trades = [PaperTrade(**d) for d in json.load(f)]

    def add(self, trade):
        self.trades.append(trade); self._save()

    def update(self, trade_id, **fields):
        for t in self.trades:
            if t.trade_id == trade_id:
                for k, v in fields.items():
                    setattr(t, k, v)
        self._save()

    def open_for(self, strategy_id):
        return [t for t in self.trades if t.strategy_id == strategy_id and t.status == "open"]

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump([asdict(t) for t in self.trades], f, indent=1)
        os.replace(tmp, self.path)
