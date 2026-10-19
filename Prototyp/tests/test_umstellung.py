# -*- coding: utf-8 -*-
"""Umstellungs-Skript (umstellung_17-10.py) und Wartebot (warte_und_umstellen.py): Fake-Baum in tmp_path, simulierte
Uhr, alle Aussenwirkungen (Telegram, Prozesse, Tests, bat-Dateien) als Hooks. Nichts davon beruehrt das echte System."""
import os, sys, json, zipfile, importlib.util, time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import pytest

TB = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))      # Trading_Bot
TZ = ZoneInfo("Europe/Berlin")


def load(name, fname):
    p = os.path.join(TB, fname)
    if not os.path.exists(p):
        pytest.skip(f"{fname} nicht vorhanden")
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


U = load("umstellung_17_10", "umstellung_17-10.py")
W = load("warte_und_umstellen", "warte_und_umstellen.py")


class Clock:
    def __init__(self, t):
        self.t = t

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += timedelta(seconds=s)


def w(path, text="x"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


@pytest.fixture
def tree(tmp_path):
    root = tmp_path / "Trading_Bot"
    proto, v2 = root / "Prototyp", root / "Prototyp_v2"
    w(str(proto / ".env"), "GEHEIM")
    w(str(proto / "venv" / "Scripts" / "python.exe"), "py")
    w(str(proto / "venv" / "lib" / "big.bin"), "venv-inhalt")
    w(str(proto / "engine" / "run_loop.py"), "ALT run_loop")
    w(str(proto / "engine" / "unveraendert.py"), "gleich")
    w(str(proto / "notify" / "live.py"), "ALT live")
    w(str(proto / "paper_runtime_2monate" / "trades.json"), "[]")
    w(str(proto / "paper_runtime_2monate" / "data_cache" / "BTC.csv"), "daten")
    w(str(proto / "report_listener_runtime" / "state.json"), "{}")
    w(str(proto / "backtest_runtime" / "frozen" / "x.csv"), "bt")
    end = datetime(2026, 10, 17, 12, 0, tzinfo=TZ)
    w(str(proto / "paper_runtime_2monate" / "START_MANIFEST.json"),
      json.dumps({"stage": "ZWEI-MONATS-TEST", "start_local": "2026-08-17T12:00:00+02:00", "stage_end_local": end.isoformat()}))
    w(str(v2 / "engine" / "run_loop.py"), "NEU run_loop")
    w(str(v2 / "engine" / "unveraendert.py"), "gleich")
    w(str(v2 / "engine" / "exit_cplus.py"), "NEU exit")
    w(str(v2 / "engine" / "__pycache__" / "x.pyc"), "bytecode")
    w(str(v2 / "notify" / "live.py"), "NEU live")
    w(str(v2 / "tests" / "test_x.py"), "def test_x(): pass")
    w(str(v2 / ".env"), "AUCH-GEHEIM")                       # darf nie kopiert werden
    w(str(v2 / "paper_runtime_neustart" / "x.json"), "{}")   # Laufzeitordner im v2: nie kopieren
    w(str(v2 / "scan_100.py"), "scan")
    w(str(v2 / "requirements.txt"), "pandas")
    w(str(v2 / "BAU_STAND.md"), "stand")
    w(str(root / "TradingBot_Neustart.vbs"), "vbs")
    w(str(root / "NEUSTART-LAUF starten.bat"), "bat")
    w(str(root / "Bericht-Listener starten.bat"), "bat")
    w(str(root / "Bericht-Listener stoppen.bat"), "bat")
    startup = root / "Startup"
    w(str(startup / "TradingBot_2Monate.vbs"), "alt")
    w(str(startup / "TradingBot_BerichtListener.vbs"), "lst")
    return root


class Sim:
    """Simulierte Aussenwelt."""
    def __init__(self, root, now):
        self.root = str(root)
        self.clock = Clock(now)
        self.sent, self.docs, self.cmds = [], [], []
        self.old_alive = True
        self.old_idle = True
        self.age = 900                                   # Sekunden seit Ende des letzten Zyklus des alten Laufs
        self.lst_alive = True
        self.new_alive = False
        self.tests_ok = True
        self.killed = []
        self.report_ok = True
        self.new_run_ok = True
        self.send_fails = False
        self.variants_ok = True

    def cfg(self, **kw):
        c = U.Cfg(root=self.root, startup_dir=os.path.join(self.root, "Startup"), now=self.clock.now, sleep=self.clock.sleep,
                  send_text=self.send_text, send_doc=self.send_doc, proc_alive=self.alive, proc_idle=lambda p: self.old_idle,
                  proc_kill=self.kill, run_tests=self.tests, run_cmd=self.cmd, build_report=self.report,
                  cycle_age=lambda: self.age, variant_check=lambda: [("Varianten inkl. D", self.variants_ok, "")], **kw)
        return c

    def send_text(self, t):
        if self.send_fails:
            raise RuntimeError("telegram down")
        self.sent.append(t)

    def send_doc(self, p, cap):
        self.docs.append((p, cap))

    def alive(self, pat):
        if "zwei-monate" in pat:
            return self.old_alive
        if "report_listener" in pat:
            return self.lst_alive
        if "neustart" in pat:
            return self.new_alive
        return False

    def kill(self, pat):
        self.killed.append(pat)
        if "zwei-monate" in pat:
            self.old_alive = False
        if "report_listener" in pat:
            self.lst_alive = False
        return 1

    def tests(self, d):
        self.tests_dir = d
        return self.tests_ok, "5 passed"

    def cmd(self, argv):
        name = os.path.basename(argv[-1])
        self.cmds.append(name)
        if name == "Bericht-Listener stoppen.bat":
            self.lst_alive = False
        elif name == "Bericht-Listener starten.bat":
            self.lst_alive = True
        elif name == "NEUSTART-LAUF starten.bat" and self.new_run_ok:
            self.new_alive = True
            rt = os.path.join(self.root, "Prototyp", "paper_runtime_neustart")
            w(os.path.join(rt, "START_MANIFEST.json"), "{}")
            w(os.path.join(rt, "last_cycle_monitor.json"), json.dumps({"instruments": 94, "no_data": 0, "errors": 0, "duration_s": 120}))
        return 0

    def report(self, rt, out, now):
        if not self.report_ok:
            raise RuntimeError("bericht kaputt")
        w(out, "P" * 6000)
        return "Abschlussbericht Kurztext"


AFTER = datetime(2026, 10, 17, 12, 15, tzinfo=TZ)
BEFORE = datetime(2026, 10, 17, 11, 0, tzinfo=TZ)


def tree_files(root, sub):
    out = {}
    for dp, dn, fn in os.walk(os.path.join(str(root), sub)):
        for f in fn:
            p = os.path.join(dp, f)
            out[os.path.relpath(p, str(root))] = open(p, "rb").read()
    return out


# ------------------------------------------------------------------ dry-run
def test_dry_run_changes_nothing_sends_nothing(tree):
    before = {s: tree_files(tree, s) for s in ("Prototyp", "Prototyp_v2", "Startup")}
    sim = Sim(tree, BEFORE)
    rc = U.run(sim.cfg(), dry=True)
    assert rc == 0
    assert sim.sent == [] and sim.docs == [] and sim.cmds == [] and sim.killed == []
    after = {s: tree_files(tree, s) for s in ("Prototyp", "Prototyp_v2", "Startup")}
    assert before == after                                              # kein Byte veraendert
    assert not os.path.exists(os.path.join(str(tree), "Sicherungen")) and not os.path.exists(os.path.join(str(tree), "umstellung_log.txt"))
    assert os.path.exists(os.path.join(str(tree), "Startup", "TradingBot_2Monate.vbs"))


def test_dry_run_reports_plan_and_fails_on_problems(tree):
    sim = Sim(tree, BEFORE)
    sim.tests_ok = False
    assert U.run(sim.cfg(), dry=True) == 1                              # rote Tests -> FAIL
    sim2 = Sim(tree, BEFORE)
    os.remove(os.path.join(str(tree), "TradingBot_Neustart.vbs"))
    assert U.run(sim2.cfg(), dry=True) == 1
    sim3 = Sim(tree, BEFORE)
    sim3_cfg = sim3.cfg()
    os.rename(os.path.join(str(tree), "Prototyp", ".env"), os.path.join(str(tree), "Prototyp", ".env_weg"))
    assert U.run(sim3_cfg, dry=True) == 1                               # ohne .env nicht startbar


def test_dry_run_before_end_is_ok_with_note(tree):
    sim = Sim(tree, BEFORE)
    cfg = sim.cfg()
    assert U.run(cfg, dry=True) == 0
    assert any("noch nicht erreicht" in l for l in cfg.log_lines)


# ------------------------------------------------------------------ go: Erfolgsweg
def test_go_full_success_path(tree):
    sim = Sim(tree, AFTER)
    cfg = sim.cfg()
    rc = U.run(cfg, dry=False)
    assert rc == 0, "\n".join(cfg.log_lines[-15:])
    # 1 alter Lauf: STOP gesetzt, schlafend -> beendet
    assert os.path.exists(os.path.join(str(tree), "Prototyp", "paper_runtime_2monate", "STOP")) and sim.killed[0] == "run_loop.py|zwei-monate"
    # 2 Abschlussbericht gesendet
    assert len(sim.docs) == 1 and sim.docs[0][1].startswith("Abschlussbericht")
    # 3 ZIP ohne venv und ohne .env, mit Daten
    with zipfile.ZipFile(os.path.join(str(tree), "Sicherungen", "Prototyp_vor_Neustart_2026-10-17.zip")) as z:
        names = z.namelist()
    assert any(n.endswith("trades.json") for n in names) and any(n.endswith("BTC.csv") for n in names)
    assert not any("venv" in n for n in names) and not any(n.endswith(".env") for n in names)
    # 4 Code uebernommen, gesperrte Pfade nicht
    p = os.path.join(str(tree), "Prototyp")
    assert open(os.path.join(p, "engine", "run_loop.py")).read() == "NEU run_loop"
    assert open(os.path.join(p, "engine", "exit_cplus.py")).read() == "NEU exit"
    assert open(os.path.join(p, ".env")).read() == "GEHEIM"                              # unangetastet
    assert not os.path.exists(os.path.join(p, "engine", "__pycache__"))
    assert not os.path.exists(os.path.join(p, "paper_runtime_neustart", "x.json"))        # kein Laufzeitordner kopiert
    assert os.path.exists(os.path.join(p, "paper_runtime_2monate", "trades.json"))
    assert open(os.path.join(p, "venv", "lib", "big.bin")).read() == "venv-inhalt"
    assert sim.tests_dir == p
    assert os.path.exists(os.path.join(p, "live_settings.json"))
    # 5 Listener: Stop-bat dann Start-bat; 6 neuer Lauf per bat
    assert sim.cmds == ["Bericht-Listener stoppen.bat", "Bericht-Listener starten.bat", "NEUSTART-LAUF starten.bat"]
    # 7 Autostart: neu angelegt, alt umbenannt (nicht geloescht), Listener-Eintrag bleibt
    st = os.path.join(str(tree), "Startup")
    assert os.path.exists(os.path.join(st, "TradingBot_Neustart.vbs"))
    assert not os.path.exists(os.path.join(st, "TradingBot_2Monate.vbs")) and os.path.exists(os.path.join(st, "TradingBot_2Monate.vbs.disabled"))
    assert os.path.exists(os.path.join(st, "TradingBot_BerichtListener.vbs"))
    # 8 genau EINE Schlussmeldung, exakter Text
    assert sim.sent == [U.FINAL_TEXT]
    assert "Bitte jetzt 1) die Telegram-Gruppen umbenennen und 2) den PC einmal neu starten" in sim.sent[0]
    assert "mit ‚bericht‘" in sim.sent[0]
    log = open(os.path.join(str(tree), "umstellung_log.txt"), encoding="utf-8").read()
    assert "Umstellung abgeschlossen" in log


def test_go_when_old_run_already_ended_does_not_touch_stop_file(tree):
    sim = Sim(tree, AFTER)
    sim.old_alive = False
    assert U.run(sim.cfg(), dry=False) == 0
    assert not os.path.exists(os.path.join(str(tree), "Prototyp", "paper_runtime_2monate", "STOP")) and sim.killed == []


def test_go_waits_for_busy_old_run_then_stops(tree):
    sim = Sim(tree, AFTER)
    sim.old_idle = False
    sim.age = 4000                                                       # Fenster, in dem der Zyklus laeuft/gleich startet
    calls = {"n": 0}
    orig = sim.alive

    def alive(pat):
        if "zwei-monate" in pat:
            calls["n"] += 1
            if calls["n"] > 3:
                sim.old_alive = False                                  # Zyklus fertig, Schleife beendet sich selbst
            return sim.old_alive
        return orig(pat)
    sim.alive = alive
    cfg = sim.cfg()
    assert U.run(cfg, dry=False) == 0 and sim.killed == []              # nicht gewaltsam beendet, nur gewartet


# ------------------------------------------------------------------ go: Fehlerpfade
def test_go_before_testend_refuses_and_leaves_old_run_alone(tree):
    sim = Sim(tree, BEFORE)
    rc = U.run(sim.cfg(), dry=False)
    assert rc == 3 and sim.old_alive and sim.killed == []
    assert not os.path.exists(os.path.join(str(tree), "Prototyp", "paper_runtime_2monate", "STOP"))
    assert not os.path.exists(os.path.join(str(tree), "Startup", "TradingBot_Neustart.vbs"))
    assert len(sim.sent) == 1 and sim.sent[0].startswith("Umstellung NICHT erfolgt – Eingriff nötig")


def test_go_red_tests_rolls_back_code_and_starts_nothing(tree):
    sim = Sim(tree, AFTER)
    sim.tests_ok = False
    rc = U.run(sim.cfg(), dry=False)
    assert rc == 3
    p = os.path.join(str(tree), "Prototyp")
    assert open(os.path.join(p, "engine", "run_loop.py")).read() == "ALT run_loop"       # aus der ZIP zurueckgespielt
    assert open(os.path.join(p, "notify", "live.py")).read() == "ALT live"
    assert sim.cmds == []                                                                  # nichts gestartet (kein Listener, kein Lauf)
    assert not os.path.exists(os.path.join(str(tree), "Startup", "TradingBot_Neustart.vbs"))
    assert os.path.exists(os.path.join(str(tree), "Startup", "TradingBot_2Monate.vbs"))   # alter Autostart bleibt
    assert len(sim.sent) == 1 and sim.sent[0].startswith("Umstellung NICHT erfolgt – Eingriff nötig") and len(sim.docs) == 1


def test_go_report_failure_stops_before_anything_changes(tree):
    sim = Sim(tree, AFTER)
    sim.report_ok = False
    assert U.run(sim.cfg(), dry=False) == 3
    p = os.path.join(str(tree), "Prototyp")
    assert open(os.path.join(p, "engine", "run_loop.py")).read() == "ALT run_loop"
    assert not os.path.exists(os.path.join(str(tree), "Sicherungen", "Prototyp_vor_Neustart_2026-10-17.zip"))
    assert sim.cmds == [] and len(sim.sent) == 1 and sim.sent[0].startswith("Umstellung NICHT erfolgt")


def test_go_new_run_does_not_start_reports_failure_but_keeps_old_autostart(tree):
    sim = Sim(tree, AFTER)
    sim.new_run_ok = False
    cfg = sim.cfg()
    cfg.new_run_wait_s = 30
    rc = U.run(cfg, dry=False)
    assert rc == 3 and len(sim.sent) == 1 and sim.sent[0].startswith("Umstellung NICHT erfolgt")
    assert os.path.exists(os.path.join(str(tree), "Startup", "TradingBot_2Monate.vbs"))
    assert not os.path.exists(os.path.join(str(tree), "Startup", "TradingBot_Neustart.vbs"))


def test_go_aborts_if_new_run_already_exists(tree):
    w(os.path.join(str(tree), "Prototyp", "paper_runtime_neustart", "START_MANIFEST.json"), "{}")
    sim = Sim(tree, AFTER)
    assert U.run(sim.cfg(), dry=False) == 3
    assert sim.killed == [] and not os.path.exists(os.path.join(str(tree), "Sicherungen"))


def test_alert_failure_does_not_crash(tree):
    sim = Sim(tree, AFTER)
    sim.tests_ok = False
    sim.send_fails = True
    assert U.run(sim.cfg(), dry=False) == 3


def test_copy_guard_blocks_secret_and_runtime_paths(tree):
    cfg = Sim(tree, AFTER).cfg()
    with pytest.raises(U.StepError):
        U.guard_copy_set(cfg, [("a", "b", ".env")])
    with pytest.raises(U.StepError):
        U.guard_copy_set(cfg, [("a", "b", "paper_runtime_2monate/trades.json")])
    with pytest.raises(U.StepError):
        U.guard_copy_set(cfg, [("a", "b", "venv/Scripts/python.exe")])
    files = [rel for _, _, rel in U.iter_copy_files(cfg)]
    assert ".env" not in files and not any(f.startswith("paper_runtime") or "__pycache__" in f for f in files)


def test_final_text_is_exactly_the_agreed_wording():
    assert U.FINAL_TEXT == ("Neustart erfolgreich: aktiv Pro.1 Baseline, Pro.3 Volumen, C+ (ehemals Pro.2-Gruppe), D (ehemals Pro.6-Gruppe). "
                            "Bitte jetzt 1) die Telegram-Gruppen umbenennen und 2) den PC einmal neu starten, damit der Autostart "
                            "geprüft wird. Nach dem Neustart kommt keine Meldung – mit ‚bericht‘ kannst du prüfen, ob alles läuft.")


# ------------------------------------------------------------------ Wartebot (simulierte Uhr)
class WSim:
    def __init__(self, tmp, start, dry_rc=0, go_rc=0):
        self.clock = Clock(start)
        self.sent, self.runs = [], []
        self.dry_rc, self.go_rc = dry_rc, go_rc
        self.sent_at, self.run_at = [], []

    def hooks(self, tmp):
        def run_umstellung(mode):
            self.runs.append(mode); self.run_at.append(self.clock.now())
            return self.dry_rc if mode == "--dry-run" else self.go_rc

        def send(t):
            self.sent.append(t); self.sent_at.append(self.clock.now())
        return W.Hooks(now=self.clock.now, sleep=self.clock.sleep, send_text=send, run_umstellung=run_umstellung,
                       log_path=str(tmp / "log.txt"), state_path=str(tmp / "state.json"))


D = lambda h, m, s=0: datetime(2026, 10, 17, h, m, s, tzinfo=TZ)


def test_wait_sends_notice_at_0900_then_umstellung_at_1215(tmp_path):
    s = WSim(tmp_path, datetime(2026, 10, 16, 21, 0, tzinfo=TZ))
    assert W.run(s.hooks(tmp_path)) == 0
    assert len(s.sent) == 1 and s.sent[0] == W.NOTICE_TEXT
    assert D(9, 0) <= s.sent_at[0] < D(9, 0, 40)                       # genau um 09:00
    assert s.runs == ["--dry-run", "--go"] and D(12, 15) <= s.run_at[0] < D(12, 16)
    assert "Heute um 12:00 endet der Zwei-Monats-Test" in s.sent[0] and "NICHT neu starten" in s.sent[0]


def test_started_after_0900_skips_notice(tmp_path):
    s = WSim(tmp_path, D(10, 30))
    assert W.run(s.hooks(tmp_path)) == 0
    assert s.sent == [] and s.runs == ["--dry-run", "--go"] and s.run_at[0] >= D(12, 15)


def test_started_after_1215_runs_immediately(tmp_path):
    s = WSim(tmp_path, D(13, 0))
    assert W.run(s.hooks(tmp_path)) == 0
    assert s.sent == [] and s.runs == ["--dry-run", "--go"] and s.run_at[0] == D(13, 0)


def test_failed_dry_run_sends_failure_message_and_never_goes(tmp_path):
    s = WSim(tmp_path, D(10, 0), dry_rc=1)
    assert W.run(s.hooks(tmp_path)) == W.RC_FAIL
    assert s.runs == ["--dry-run"] and s.sent == [W.FAIL_TEXT]
    assert W.FAIL_TEXT == "Umstellung NICHT erfolgt – Eingriff nötig"


def test_failed_go_does_not_send_second_message(tmp_path):
    s = WSim(tmp_path, D(10, 0), go_rc=3)
    assert W.run(s.hooks(tmp_path)) == W.RC_FAIL
    assert s.runs == ["--dry-run", "--go"] and s.sent == []             # --go meldet den Fehler selbst


def test_restart_after_completion_does_nothing_twice(tmp_path):
    s = WSim(tmp_path, D(10, 0))
    W.run(s.hooks(tmp_path))
    s2 = WSim(tmp_path, D(12, 40))
    assert W.run(s2.hooks(tmp_path)) == 0 and s2.runs == [] and s2.sent == []


def test_notice_not_repeated_after_restart_before_noon(tmp_path):
    s = WSim(tmp_path, datetime(2026, 10, 16, 20, 0, tzinfo=TZ), go_rc=0)
    h = s.hooks(tmp_path)
    # Prozess "stirbt" nach der Nachricht: Zustand schreiben, neu starten um 09:30 -> keine zweite Nachricht
    W._save(h, {"notice_sent": "x"})
    s2 = WSim(tmp_path, datetime(2026, 10, 16, 20, 0, tzinfo=TZ))
    W.run(s2.hooks(tmp_path))
    assert s2.sent == []


def test_after_the_day_refuses(tmp_path):
    s = WSim(tmp_path, datetime(2026, 10, 18, 8, 0, tzinfo=TZ))
    assert W.run(s.hooks(tmp_path)) == W.RC_FAIL and s.runs == [] and s.sent == []


def test_telegram_failure_of_notice_does_not_stop_the_switch(tmp_path):
    s = WSim(tmp_path, D(8, 0))
    h = s.hooks(tmp_path)

    def bad(t):
        raise RuntimeError("down")
    h.send_text = bad
    assert W.run(h) == 0 and s.runs == ["--dry-run", "--go"]
