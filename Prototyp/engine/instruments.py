# -*- coding: utf-8 -*-
"""Instrumenten-Universum + Assetklassen-/Session-Konfiguration.

Leitet aus der bestehenden Liste (scan_100.INSTRUMENTS) je Symbol ab: asset_class, is_futures,
anchor_hour, session_hours. Krypto ist 24/7 EXAKT; FX/Index/Futures/Aktien nutzen vorerst einen
dokumentierten 24/7-Anker als Naeherung (der A1-Fix - unvollstaendige letzte Kerze nicht final -
wirkt unabhaengig davon). Praezise Boersen-Sessionkalender sind eine spaetere Verfeinerung.
"""

def classify(symbol):
    s = symbol
    if s.endswith("-USD"):
        return dict(asset_class="crypto", is_futures=False, anchor_hour=0, session_hours=None,
                    session_exact=True)
    if s.endswith("=X"):
        return dict(asset_class="fx", is_futures=False, anchor_hour=0, session_hours=None,
                    session_exact=False)   # FX ~24/5, Session-Naeherung
    if s.startswith("^"):
        return dict(asset_class="index", is_futures=False, anchor_hour=0, session_hours=None,
                    session_exact=False)
    if s.endswith("=F"):
        return dict(asset_class="futures", is_futures=True, anchor_hour=0, session_hours=None,
                    session_exact=False)
    return dict(asset_class="stock", is_futures=False, anchor_hour=0, session_hours=None,
                session_exact=False)


def load_universe():
    """Gibt Liste von dicts {name, symbol, asset_class, is_futures, anchor_hour, session_hours,
    session_exact} fuer alle Instrumente mit Datenquelle."""
    import scan_100 as s100
    out = []
    for name, cands in s100.INSTRUMENTS:
        if not cands:
            continue
        sym = cands[0]
        cfg = classify(sym)
        out.append(dict(name=name, symbol=sym, **cfg))
    return out
