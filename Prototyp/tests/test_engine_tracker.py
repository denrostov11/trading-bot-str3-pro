# -*- coding: utf-8 -*-
"""Phase-B Increment S8 - Paper-Trade-Tracker.
QS-Tests: 18 (Neustart-Recovery), 20 (Intrabar Stop zuerst), + Fill=next-open, brutto/netto,
MFE/MAE, Break-even-Modi, Kosten je Klasse, R auf Original-Risiko."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import tracker as T


def bar(h, l, o=None, c=None):
    return {"High": h, "Low": l, "Open": o if o is not None else (h + l) / 2,
            "Close": c if c is not None else (h + l) / 2}


# Fill = Open der ersten Kerze + Slippage; Ziel getroffen
def test_fill_next_open_and_target():
    # LONG, entry_open=100, atr=2 -> Fill 100.1; stop 98, target 104
    bars = [bar(101, 99.9),           # Einstiegskerze, kein Stop/Ziel
            bar(104.5, 101)]          # Ziel 104 getroffen
    r = T.simulate_trade("LONG", "crypto", atr=2.0, entry_open=100.0, stop_initial=98.0,
                         target=104.0, bars=bars)
    assert r["status"] == "closed" and r["outcome"] == T.TARGET
    assert r["entry_price"] == 100.1                 # 100 + 0.05*2
    assert r["brutto_r"] > 0 and r["netto_r"] < r["brutto_r"]   # Kosten reduzieren

# Stop -> brutto_r = -1 auf Original-Risiko, netto < -1 (Kosten)
def test_stop_hit_full_r():
    bars = [bar(100.5, 97.5)]         # Low 97.5 < Stop 98 -> Stop
    r = T.simulate_trade("LONG", "crypto", atr=2.0, entry_open=100.0, stop_initial=98.0,
                         target=110.0, bars=bars)
    assert r["outcome"] == T.STOP
    assert round(r["brutto_r"], 2) == -1.0 and r["netto_r"] < -1.0

# Intrabar: Stop UND Ziel in einer Kerze -> Stop zuerst + ambiguous (Test 20)
def test_intrabar_stop_first():
    bars = [bar(120, 97.5)]           # trifft Ziel 104 UND Stop 98
    r = T.simulate_trade("LONG", "crypto", atr=2.0, entry_open=100.0, stop_initial=98.0,
                         target=104.0, bars=bars)
    assert r["outcome"] == T.STOP and r["ambiguous_intrabar"] is True

# MFE/MAE
def test_mfe_mae():
    bars = [bar(106, 99.0), bar(104.5, 101)]   # fav bis (106-100.1)/1.9, adv (100.1-99)/1.9
    r = T.simulate_trade("LONG", "crypto", atr=2.0, entry_open=100.0, stop_initial=98.0,
                         target=104.0, bars=bars)
    assert r["mfe_r"] >= 2.0 and r["mae_r"] > 0

# Break-even BE-3: 1R erreicht, dann Rueckkehr -> BREAK_EVEN statt Verlust
def test_break_even_be3():
    # risk ~ 1.9 (entry 100.1, stop 98.2). 1R ~ 102.0
    bars = [bar(102.5, 100.0),        # fav ~ (102.5-100.1)/1.9 = 1.26 >=1R -> BE-Move nach Kerze
            bar(101.0, 99.5)]         # faellt zurueck: Low 99.5 < BE-Stop (~100.14) -> BREAK_EVEN
    r = T.simulate_trade("LONG", "crypto", atr=2.0, entry_open=100.0, stop_initial=98.2,
                         target=110.0, bars=bars, be_mode="BE-3")
    assert r["outcome"] == T.BREAK_EVEN and r["be_moved"] is True
    assert r["brutto_r"] > -1.0                       # kein voller Verlust mehr

# BE-0: kein Nachziehen -> voller Stop
def test_break_even_be0_control():
    bars = [bar(102.5, 100.0), bar(101.0, 97.0)]
    r = T.simulate_trade("LONG", "crypto", atr=2.0, entry_open=100.0, stop_initial=98.2,
                         target=110.0, bars=bars, be_mode="BE-0")
    assert r["outcome"] == T.STOP and round(r["brutto_r"], 2) == -1.0

# Kosten je Klasse: Krypto teurer als Index
def test_costs_by_class():
    bars = [bar(104.5, 101)]
    rc = T.simulate_trade("LONG", "crypto", 2.0, 100.0, 98.0, 104.0, bars)
    ri = T.simulate_trade("LONG", "index", 2.0, 100.0, 98.0, 104.0, bars)
    assert rc["netto_r"] < ri["netto_r"]              # Krypto-Kosten hoeher -> weniger netto

# SHORT-Richtung
def test_short_target():
    bars = [bar(100.1, 95.5)]         # SHORT entry 99.9 (100-0.1), target 96
    r = T.simulate_trade("SHORT", "fx", atr=2.0, entry_open=100.0, stop_initial=102.0,
                         target=96.0, bars=bars)
    assert r["outcome"] == T.TARGET and r["brutto_r"] > 0

# Neustart-Recovery des Trade-Stores (Test 18)
def test_store_recovery(tmp_path):
    p = str(tmp_path / "trades.json")
    store = T.PaperTradeStore(p)
    store.add(T.PaperTrade(trade_id="T1", variant_evaluation_id="VE1", parent_signal_id="PSIG1",
                           strategy_id="Str.3 Pro.1", break_even="BE-0", symbol="GC=F",
                           asset_class="commodity", direction="LONG", signal_time="2026-07-20T16:00",
                           status="open"))
    store2 = T.PaperTradeStore(p)
    assert len(store2.trades) == 1 and store2.open_for("Str.3 Pro.1")[0].trade_id == "T1"
    store2.update("T1", status="closed")
    assert T.PaperTradeStore(p).trades[0].status == "closed"
