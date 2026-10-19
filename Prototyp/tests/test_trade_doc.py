# -*- coding: utf-8 -*-
"""B2 Trade-PDF statt PNG: Aufruf ueber mtf, Zeitlimit, Rueckfall auf PNG (dpi 220), Ein-/Ausschalten per JSON."""
import os, sys, time, json
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import trade_doc, live_settings
from engine.tracker import PaperTrade
from engine.ledger import Ledger
from engine.cache import BarCache


def _fake_worker_ok(args, q):
    with open(args["out"], "wb") as f:
        f.write(b"%PDF-1.4 fake")
    q.put(("ok", args["out"]))


def _fake_worker_hang(args, q):
    time.sleep(60)


def _fake_worker_error(args, q):
    q.put(("err", "MtfTimeout"))


def _trade():
    return PaperTrade(trade_id="a", variant_evaluation_id="v", parent_signal_id="PSIG-X", strategy_id="Str.3 Pro.1",
                      break_even="BE-0", symbol="BTC-USD", asset_class="crypto", direction="LONG", signal_time="2026-10-17T08:00:00+00:00",
                      stop_initial=90.0, target=120.0)


@pytest.fixture
def env(tmp_path):
    cache = BarCache(str(tmp_path / "c"))
    import pandas as pd
    cache.merge("BTC-USD", "1h", pd.DataFrame({"Time": pd.date_range("2026-10-01", periods=50, freq="h", tz="UTC"),
                                              "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}))
    lg = Ledger(str(tmp_path / "l.json"))
    lg.record_candidate("PSIG-X", "BTC-USD", "LONG", "ACCEPTED_PROVISIONAL", "2026-10-17T08:00:00+00:00", "t",
                        snapshot={"atr": 1.0, "action_anchor": [0, 1, 1, 1, "x", 3, 1.0], "safety_anchor": [0, 1, 1, 1, "x", 3, 1.0]})
    return tmp_path, cache, lg


def S(enabled=True, timeout=90, dpi=220):
    s = live_settings.load(os.path.join("none", "x.json"))
    s["trade_pdf"].update({"enabled": enabled, "timeout_s": timeout, "png_dpi": dpi})
    return s


def test_pdf_used_when_enabled_and_ok(env):
    tmp, cache, lg = env
    log = []
    pdf = lambda rt, t, ledger, c, to, lg_: trade_doc._make_pdf(rt, t, ledger, c, to, lg_, worker=_fake_worker_ok)
    p = trade_doc.make_attachment(str(tmp), _trade(), {}, lg, cache, log, settings=S(), pdf_fn=pdf,
                                  png_fn=lambda *a: pytest.fail("PNG darf nicht genutzt werden"))
    assert p.endswith(".pdf") and os.path.exists(p)


def test_fallback_to_png_with_dpi_220_on_error(env):
    tmp, cache, lg = env
    log = []
    got = {}
    pdf = lambda rt, t, ledger, c, to, lg_: trade_doc._make_pdf(rt, t, ledger, c, to, lg_, worker=_fake_worker_error)

    def png(rt, t, result, lg_, dpi):
        got["dpi"] = dpi
        return "x.png"
    p = trade_doc.make_attachment(str(tmp), _trade(), {}, lg, cache, log, settings=S(), pdf_fn=pdf, png_fn=png)
    assert p == "x.png" and got["dpi"] == 220 and any("Fehler MtfTimeout" in x for x in log)


def test_timeout_kills_worker_and_falls_back(env):
    tmp, cache, lg = env
    log = []
    t0 = time.time()
    pdf = lambda rt, t, ledger, c, to, lg_: trade_doc._make_pdf(rt, t, ledger, c, to, lg_, worker=_fake_worker_hang)
    p = trade_doc.make_attachment(str(tmp), _trade(), {}, lg, cache, log, settings=S(timeout=10), pdf_fn=pdf,
                                  png_fn=lambda *a: "fallback.png")
    assert p == "fallback.png" and time.time() - t0 < 40 and any("Zeitlimit" in x for x in log)


def test_disabled_in_json_goes_straight_to_png(env):
    tmp, cache, lg = env
    p = trade_doc.make_attachment(str(tmp), _trade(), {}, lg, cache, [], settings=S(enabled=False),
                                  pdf_fn=lambda *a: pytest.fail("PDF darf nicht versucht werden"), png_fn=lambda *a: "a.png")
    assert p == "a.png"


def test_missing_snapshot_or_data_falls_back(env):
    tmp, cache, lg = env
    t = _trade(); t.parent_signal_id = "UNBEKANNT"
    log = []
    p = trade_doc.make_attachment(str(tmp), t, {}, lg, cache, log, settings=S(), png_fn=lambda *a: "b.png")
    assert p == "b.png" and any("kein Snapshot" in x for x in log)


def test_pdf_exception_never_blocks_the_message(env):
    tmp, cache, lg = env

    def boom(*a):
        raise RuntimeError("kaputt")
    assert trade_doc.make_attachment(str(tmp), _trade(), {}, lg, cache, [], settings=S(), pdf_fn=boom,
                                     png_fn=lambda *a: None) is None


def test_png_default_dpi_is_220():
    import inspect
    from engine import trade_chart
    assert inspect.signature(trade_chart.render_trade_chart).parameters["dpi"].default == 220
    assert live_settings.DEFAULTS["trade_pdf"] == {"enabled": True, "timeout_s": 90, "png_dpi": 220}


def test_real_mtf_pdf_on_reference_trade(tmp_path):
    """Echter Aufruf von mtf.trade_pdf.make_trade_pdf auf einem Referenz-Trade (Kopie der Analysen-Daten)."""
    src = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                       "Analysen", "cplus_pro1", "daten_kopie")
    if not os.path.exists(os.path.join(src, "trades.json")) or not os.path.exists(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "mtf_cache", "SOL-USD__1d.csv")):
        pytest.skip("Referenzdaten/Tages-Cache nicht vorhanden")
    import dataclasses
    d = next(t for t in json.load(open(os.path.join(src, "trades.json"), encoding="utf-8"))
             if t["strategy_id"] == "Str.3 Pro.1" and t["symbol"] == "SOL-USD")
    names = {f.name for f in dataclasses.fields(PaperTrade)}
    t = PaperTrade(**{k: v for k, v in d.items() if k in names})
    t.exit_mode = "CPLUS"
    log = []
    p = trade_doc._make_pdf(str(tmp_path), t, Ledger(os.path.join(src, "ledger.json")), BarCache(os.path.join(src, "data_cache")), 90, log)
    assert p and os.path.getsize(p) > 20000, log
