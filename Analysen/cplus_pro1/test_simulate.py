# -*- coding: utf-8 -*-
"""Kleine Selbsttests der Ausstiegs-Simulation (synthetische Kerzen, LONG-Raum). Aufruf: python test_simulate.py"""
import numpy as np
from cplus_pro1 import simulate


def mk(rows, pre=3):
    """rows: Liste (O,H,L,C) ab der Einstiegskerze; davor `pre` neutrale Kerzen weit oberhalb."""
    a = [(130, 130, 130, 130)] * pre + list(rows)
    A = np.array(a, dtype=float)
    return A[:, 0], A[:, 1], A[:, 2], A[:, 3], pre


LINE = lambda i: 90.0          # flache Safety Line, E=100, risk=10, ATR=5


def run(var, rows):
    O, H, L, C, e = mk(rows)
    return simulate(var, O, H, L, C, LINE, e, 100.0, 10.0, 5.0, 1.0)


def test_b_close_exit_next_open():
    r = run("B", [(100, 105, 95, 100), (100, 102, 88, 89), (87, 90, 85, 88)])   # Close 89 < 90 -> Ausstieg Open naechste
    assert r["status"] == "closed" and r["outcome"] == "SAFETY_CLOSE" and r["exit_price"] == 87 and r["exit_idx"] == 5


def test_b_wick_below_line_does_not_exit():
    r = run("B", [(100, 105, 95, 100), (100, 102, 88, 95), (95, 99, 94, 97)])   # Docht 88 < 90, Close 95 -> bleibt offen
    assert r["status"] == "open"


def test_b_net_intrabar_and_gap():
    r = run("B", [(100, 105, 95, 100), (100, 102, 84, 86)])                      # Netz = 85, Tief 84 -> Netzpreis
    assert r["outcome"] == "NOTFALLNETZ" and r["exit_price"] == 85
    r = run("B", [(100, 105, 95, 100), (80, 82, 78, 79)])                        # Luecke: Open 80 < Netz -> zum Open
    assert r["outcome"] == "NOTFALLNETZ" and r["exit_price"] == 80


def test_cplus_stage2_and_stage3_then_profit_close():
    rows = [(100, 110, 99, 108),     # e   : Close +8  (<+15)
            (108, 120, 107, 116),    # +1  : Close 116 >= 115 -> Stufe 2, Schwelle 101
            (116, 135, 125, 130),    # +2  : Hoch 135
            (130, 131, 123, 128),    # +3
            (128, 129, 121, 126),    # +4
            (126, 127, 112, 124),    # +5  : Swing-Tief 112 (p)
            (124, 128, 118, 126),    # +6
            (126, 129, 120, 127),    # +7
            (127, 130, 122, 128),    # +8  : p bestaetigt (3 Kerzen danach hoeher) -> Schwelle 112-2,5 = 109,5
            (128, 128, 105, 108),    # +9  : Close 108 < 109,5 -> Ausstieg am Open der naechsten
            (107, 110, 100, 103)]
    r = run("C+", rows)
    assert r["stage2"] and r["stage3"]
    assert r["outcome"] == "GEWINNSCHWELLE_CLOSE" and r["exit_price"] == 107 and r["exit_idx"] == 3 + 10


def test_cplus_without_stage2_no_stage3():
    rows = [(100, 112, 99, 105), (105, 112, 104, 108), (108, 111, 100, 106), (106, 109, 96, 100),
            (100, 108, 98, 104), (104, 110, 101, 107), (107, 111, 103, 108)]
    r = run("C+", rows)
    assert not r["stage2"] and not r["stage3"] and r["status"] == "open"


def test_d_intrabar_stop_with_buffer_and_swing_trail():
    r = run("D", [(100, 105, 95, 100), (100, 102, 89.4, 95)])     # Stop = 90 - 0.5 = 89,5; Tief 89,4 -> Ausstieg zum Stop
    assert r["outcome"] == "STOP_INTRABAR" and r["exit_price"] == 89.5
    rows = [(100, 110, 99, 108), (108, 120, 107, 116), (116, 135, 125, 130), (130, 131, 123, 128),
            (128, 129, 121, 126), (126, 127, 112, 124), (124, 128, 118, 126), (126, 129, 120, 127),
            (127, 130, 122, 128), (128, 128, 105, 108)]
    r = run("D", rows)                                            # Swing 112-2,5=109,5 -> Tief 105 beruehrt -> Ausstieg zum Stop
    assert r["outcome"] == "STOP_INTRABAR" and abs(r["exit_price"] - 109.5) < 1e-9 and r["stage3"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
