# -*- coding: utf-8 -*-
"""A1/A6: aktive Varianten, neuer Lauf (Manifest, unbefristet, STOP), Startdateien ohne Windows-Aufgabe."""
import os, sys, json, time, threading, types
from datetime import datetime
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_active_variants_are_exactly_pro1_pro3_cplus():
    from engine import run_paper, run_loop
    assert run_paper.ACTIVE_VARIANTS == ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]
    assert run_loop.ACTIVE_VARIANTS == run_paper.ACTIVE_VARIANTS
    assert run_paper.BE_MAP == {"Str.3 Pro.1": "BE-0", "Str.3 C+": "C+", "Str.3 D": "D"}           # Pro.3 unveraendert BE-1 (Standard)


def test_variants_pro1_pro3_unchanged_and_pro2_pro4_to_8_not_evaluated_in_live():
    from engine import variants as V
    from engine import run_paper
    for sid in ["Str.3 Pro.2", "Str.3 Pro.4", "Str.3 Pro.5", "Str.3 Pro.6", "Str.3 Pro.7", "Str.3 Pro.8"]:
        assert sid not in run_paper.ACTIVE_VARIANTS
        assert sid in V.REGISTRY                                                      # Code fuer Backtests/alte Berichte bleibt
    snap = types.SimpleNamespace(direction="LONG")
    assert V.REGISTRY["Str.3 Pro.1"](snap, {}).status == V.PASS
    assert V.REGISTRY["Str.3 Pro.3"](snap, {"volume_usable": True, "rvol20": 1.2}).status == V.PASS
    assert V.REGISTRY["Str.3 Pro.3"](snap, {"volume_usable": True, "rvol20": 1.19}).status == V.FAIL
    assert V.REGISTRY["Str.3 C+"](snap, {}).status == V.PASS


def test_cplus_goes_to_the_pro2_chat():
    from notify.config import load_and_validate, VARIANT_ENV
    from notify.router import Router
    from notify import messages as M
    env = {"TELEGRAM_BOT_TOKEN": "T", "TELEGRAM_AUTHORIZED_USER_IDS": "1", "STR3_PRO1_CHAT_ID": "-1", "STR3_PRO2_CHAT_ID": "-2", "STR3_PRO3_CHAT_ID": "-3", "STR3_PRO6_CHAT_ID": "-6",
           "STR3_COMPARISON_CHAT_ID": "-9", "STR3_SYSTEM_CHAT_ID": "-8"}
    cfg, report = load_and_validate(env, ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"])
    assert VARIANT_ENV["Str.3 C+"] == "STR3_PRO2_CHAT_ID"
    r = Router(cfg)
    m = M.Message("Str.3 C+", "v1", M.TRADE_OPENED, symbol="X", trade_id="t")
    assert r.resolve(m) == "-2"
    assert Router(cfg).resolve(M.Message("Str.3 Pro.1", "v1", M.TRADE_OPENED, symbol="X", trade_id="t")) == "-1"
    assert not [x for x in report if x.warning]                                       # keine Warnungen fuer aktive Gruppen


def test_new_run_universe_is_94_instruments():
    from engine import run_loop
    assert len(run_loop._stufe2_syms()) == 94


def test_loop_manifest_unlimited_stop_file_and_resume(tmp_path, monkeypatch):
    from engine import run_loop, run_paper
    base = str(tmp_path / "paper_runtime_neustart")
    calls = []

    def fake_run_once(**kw):
        calls.append(kw["mode"])
        cs = {"last_full_boundary": "2999-01-01T00:00:00+00:00", "passes": 3}       # kein weiterer voller Zyklus
        os.makedirs(base, exist_ok=True)
        json.dump(cs, open(os.path.join(base, "cycle_state.json"), "w"))
        return {"accepted": 0, "opened": 0, "closed": 0, "errors": 0, "no_data": 0, "instruments": 3, "telegram": "inaktiv",
                "duration_s": 0.1}
    monkeypatch.setattr(run_paper, "run_once", fake_run_once)
    real_sleep = time.sleep
    shim = types.SimpleNamespace(**{k: getattr(time, k) for k in dir(time) if not k.startswith("_")})
    shim.sleep = lambda s: real_sleep(min(s, 0.05))
    monkeypatch.setattr(run_loop, "time", shim)
    syms = [("A", "A-USD"), ("B", "B-USD")]
    th = threading.Thread(target=lambda: run_loop.run(stage="NEUSTART", official_start=datetime.now(run_loop.TZ), base_dir=base,
                                                      syms=syms, unlimited=True, fast=False), daemon=True)
    th.start()
    for _ in range(100):
        if calls:
            break
        real_sleep(0.05)
    assert calls and calls[0] == "full"
    man = json.load(open(os.path.join(base, "START_MANIFEST.json"), encoding="utf-8"))
    assert man["unlimited"] is True and man["stage_end_local"] is None and man["stage"] == "NEUSTART"
    assert man["active_variants"] == ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"] and man["universe"] == ["A-USD", "B-USD"]
    assert man["code_version"] == run_loop.CODE_VERSION and man["config_hash"].startswith("C") and man["real_orders"] is False
    assert run_loop.CODE_VERSION > "engine-1.2"                                      # hoehere code_version als der alte Lauf
    # STOP-Mechanismus wie im alten Lauf
    open(os.path.join(base, "STOP"), "w").write("STOP")
    th.join(10)
    assert not th.is_alive()


def test_manifest_resume_keeps_original_start_and_hash(tmp_path, monkeypatch):
    from engine import run_loop, run_paper
    base = str(tmp_path / "rt")
    os.makedirs(base)
    man = {"stage": "NEUSTART", "start_local": "2026-10-17T12:20:00+02:00", "stage_end_local": None, "unlimited": True,
           "code_version": "engine-2.0", "config_hash": "Cabc"}
    json.dump(man, open(os.path.join(base, "START_MANIFEST.json"), "w"))
    open(os.path.join(base, "STOP"), "w").write("x")
    monkeypatch.setattr(run_paper, "run_once", lambda **kw: pytest.fail("kein Zyklus bei STOP"))
    run_loop.run(stage="X", official_start=None, base_dir=base, syms=[("A", "A-USD")], fast=False)
    assert json.load(open(os.path.join(base, "START_MANIFEST.json"))) == man            # Manifest unveraendert


def test_start_files_exist_and_use_no_scheduled_tasks():
    vbs = os.path.join(TB, "TradingBot_Neustart.vbs")
    start = os.path.join(TB, "NEUSTART-LAUF starten.bat")
    stop = os.path.join(TB, "NEUSTART-LAUF stoppen.bat")
    for p in (vbs, start, stop, os.path.join(TB, "umstellung_17-10.py"), os.path.join(TB, "warte_und_umstellen.py")):
        assert os.path.exists(p), p
        txt = open(p, encoding="utf-8").read().lower()
        for bad in ("schtasks", "register-scheduledtask", "taskscheduler", "new-scheduledtask"):
            assert bad not in txt, (p, bad)
    v = open(vbs, encoding="utf-8").read()
    assert "--neustart" in v and "paper_runtime_neustart\\STOP" in v and "Loop" in v and "Sleep 30000" in v   # Watchdog + STOP
    assert "run_loop.py" in v and "pythonw.exe" in v
    assert "paper_runtime_neustart\\STOP" in open(stop, encoding="utf-8").read()
    assert "TradingBot_Neustart.vbs" in open(start, encoding="utf-8").read()


def test_cli_has_neustart_flag():
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "engine", "run_loop.py"), encoding="utf-8").read()
    assert '"--neustart"' in src and "paper_runtime_neustart" in src and "unlimited=True" in src
