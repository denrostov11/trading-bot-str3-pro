# -*- coding: utf-8 -*-
"""Variantengetrennte Zustaende (Praez. 2): je Strategievariante EIGENE offene Trades, Cooldowns
und bereits gehandelte Linien. Ein Trade in Pro.2 blockiert Pro.3 NICHT. Innerhalb derselben
Variante gilt: nur ein offener Trade pro Instrument, 24 h Cooldown, jede Linie nur einmal.

Persistenz-fest (JSON). Cooldown/Traded-Lines gelten pro Variante getrennt.
"""
import json, os

COOLDOWN_SECONDS = 24 * 3600


def _line_core(sig):
    """Index-freier Linienkern (kind:p0:slope) aus einer sig - Wiederverwendungssperre."""
    try:
        parts = str(sig).split(":")
        return (parts[0], float(parts[-2]), float(parts[-1]))
    except Exception:
        return None


class VariantState:
    """Zustand EINER Strategievariante."""
    def __init__(self, strategy_id):
        self.strategy_id = strategy_id
        self.open_symbols = {}      # symbol -> trade_id
        self.cooldown_until = {}    # symbol -> ts
        self.traded_lines = []      # list[sig]

    def can_open(self, symbol, line_sig, now):
        if symbol in self.open_symbols:
            return False, "INSTRUMENT_BUSY"
        cu = self.cooldown_until.get(symbol)
        if cu and now < cu:
            return False, "COOLDOWN"
        core = _line_core(line_sig)
        for s in self.traded_lines:
            c2 = _line_core(s)
            if core and c2 and c2[0] == core[0] \
               and abs(c2[1] - core[1]) <= abs(core[1]) * 1e-3 + 1e-9 \
               and abs(c2[2] - core[2]) <= max(abs(core[2]), abs(c2[2])) * 0.05 + 1e-12:
                return False, "LINE_ALREADY_TRADED"
        return True, ""

    def open(self, symbol, trade_id, line_sig):
        self.open_symbols[symbol] = trade_id
        self.traded_lines.append(line_sig)

    def close(self, symbol, now):
        self.open_symbols.pop(symbol, None)
        self.cooldown_until[symbol] = now + COOLDOWN_SECONDS

    def to_dict(self):
        return {"strategy_id": self.strategy_id, "open_symbols": self.open_symbols,
                "cooldown_until": self.cooldown_until, "traded_lines": self.traded_lines}

    @classmethod
    def from_dict(cls, d):
        s = cls(d["strategy_id"])
        s.open_symbols = dict(d.get("open_symbols", {}))
        s.cooldown_until = dict(d.get("cooldown_until", {}))
        s.traded_lines = list(d.get("traded_lines", []))
        return s


class StateRegistry:
    """Haelt je Variante einen VariantState; persistiert alle zusammen (Recovery nach Neustart)."""
    def __init__(self, path):
        self.path = path
        self.states = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            for sid, d in data.items():
                self.states[sid] = VariantState.from_dict(d)

    def get(self, strategy_id):
        if strategy_id not in self.states:
            self.states[strategy_id] = VariantState(strategy_id)
        return self.states[strategy_id]

    def save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({sid: s.to_dict() for sid, s in self.states.items()}, f, indent=1)
        os.replace(tmp, self.path)
