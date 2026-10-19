# -*- coding: utf-8 -*-
"""Umstellung Zwei-Monats-Test -> Neustart-Lauf (Pro.1 Baseline, Pro.3 Volumen, C+), Sa 17.10.2026 nach 12:00.

  python umstellung_17-10.py --dry-run   prueft ALLES (Zeitfenster, alter Lauf, Bericht, ZIP, Codekopie, Tests,
                                         Listener, Startdateien, Autostart), veraendert nichts, sendet nichts.
  python umstellung_17-10.py --go        fuehrt die Umstellung aus (Ablauf unten).

Manuell starten (oder ueber warte_und_umstellen.py). KEINE Windows-Aufgabe, KEIN git, KEIN pip.

Ablauf (--go), jeder Schritt wird protokolliert (umstellung_log.txt):
 1. Alter Lauf beendet? Erst NACH dem Testende (12:00, aus dem Manifest). Endet er nicht von selbst: STOP-Datei
    setzen; schlaeft die Schleife (zwischen zwei Zyklen), wird der Prozess danach beendet - der Zustand liegt
    nach jedem Zyklus atomar auf Platte.
 2. Abschlussbericht des Zwei-Monats-Tests als PDF (nur geschlossene Trades, offene = "offen, nicht gewertet",
    alle 8 Varianten, Gesamt-% gross oben) -> STR3 System.
 3. Lokale ZIP-Sicherung von Prototyp (ohne venv, ohne .env) -> Sicherungen\\Prototyp_vor_Neustart_2026-10-17.zip
 4. Code aus Prototyp_v2 nach Prototyp uebernehmen (unangetastet: .env, venv, alle Laufzeit-/Datenordner), dann
    Tests in Prototyp. ROT -> ueberschriebene Dateien aus der ZIP zurueckspielen, Ausfall-Meldung, nichts starten.
 5. Bericht-Listener neu starten (Stop-/Start-bat).
 6. Neuen Lauf starten (TradingBot_Neustart.vbs) und pruefen, dass der erste Zyklus laeuft.
 7. Autostart: TradingBot_Neustart.vbs in den Autostart-Ordner legen, alten Eintrag TradingBot_2Monate.vbs auf
    .disabled umbenennen (nichts wird geloescht).
 8. EINE Schlussmeldung an STR3 System.
Bei einem Fehler: eine kurze Meldung "Umstellung NICHT erfolgt - Eingriff noetig" an STR3 System, nichts weiter starten.

Rueckgabecodes: 0 ok | 1 Pruefung(en) fehlgeschlagen (dry-run) | 3 Umstellung fehlgeschlagen (Meldung gesendet)
"""
import os, sys, io, json, time, shutil, hashlib, zipfile, subprocess, argparse, tempfile, traceback, re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
HERE = os.path.dirname(os.path.abspath(__file__))
DATE_TAG = "2026-10-17"

EXPECTED_VARIANTS = ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]
FINAL_TEXT = ("Neustart erfolgreich: aktiv Pro.1 Baseline, Pro.3 Volumen, C+ (ehemals Pro.2-Gruppe), D (ehemals Pro.6-Gruppe). "
              "Bitte jetzt 1) die Telegram-Gruppen umbenennen und 2) den PC einmal neu starten, damit der Autostart "
              "geprüft wird. Nach dem Neustart kommt keine Meldung – mit ‚bericht‘ kannst du prüfen, ob alles läuft.")
FAIL_TEXT = "Umstellung NICHT erfolgt – Eingriff nötig"

# Code, der von Prototyp_v2 nach Prototyp uebernommen wird (alles andere bleibt unangetastet)
COPY_DIRS = ["engine", "notify", "mtf", "viewer", "tests"]
COPY_ROOT_PATTERNS = (".py",)            # Python-Dateien im Wurzelordner
COPY_ROOT_EXTRA = ["requirements.txt", ".env.example"]
EXCLUDE_DIR_NAMES = {"__pycache__", ".pytest_cache", "venv", ".git"}
EXCLUDE_FILE_NAMES = {".env"}
BACKUP_EXCLUDE_TOP = {"venv", ".pytest_cache"}


# ------------------------------------------------------------------ Konfiguration (alles injizierbar fuer Tests)
@dataclass
class Cfg:
    root: str = HERE
    startup_dir: str = os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs", "Startup")
    stage_wait_s: int = 1500
    new_run_wait_s: int = 900
    # Hooks (Standard = echte Implementierung, in Tests ersetzt)
    now: callable = None
    sleep: callable = time.sleep
    send_text: callable = None
    send_doc: callable = None
    proc_alive: callable = None          # (pattern) -> bool|None
    proc_idle: callable = None           # (pattern) -> bool
    proc_kill: callable = None           # (pattern) -> int
    variant_check: callable = None       # () -> [(name, ok, detail)]  Pruefung der aktiven Varianten inkl. D
    cycle_age: callable = None           # () -> Sekunden seit Ende des letzten Zyklus des alten Laufs (None = unbekannt)
    run_tests: callable = None           # (dir) -> (ok, tail)
    run_cmd: callable = None             # (argv) -> rc
    build_report: callable = None        # (old_rt, out_path, now) -> caption
    log_path: str = None
    dry: bool = True
    log_lines: list = field(default_factory=list)
    overwritten: list = field(default_factory=list)       # ersetzte Code-Dateien (fuer den Rollback)
    progress: dict = field(default_factory=dict)          # was bereits veraendert/gestartet wurde (fuer den Rueckbau)

    def __post_init__(self):
        self.proto = os.path.join(self.root, "Prototyp")
        self.v2 = os.path.join(self.root, "Prototyp_v2")
        self.old_rt = os.path.join(self.proto, "paper_runtime_2monate")
        self.new_rt = os.path.join(self.proto, "paper_runtime_neustart")
        self.backups = os.path.join(self.root, "Sicherungen")
        self.zip_path = os.path.join(self.backups, f"Prototyp_vor_Neustart_{DATE_TAG}.zip")
        self.report_path = os.path.join(self.backups, f"Abschlussbericht_Zwei-Monats-Test_{DATE_TAG}.pdf")
        self.venv_py = os.path.join(self.proto, "venv", "Scripts", "python.exe")
        self.new_vbs = os.path.join(self.root, "TradingBot_Neustart.vbs")
        self.start_bat = os.path.join(self.root, "NEUSTART-LAUF starten.bat")
        self.lst_start = os.path.join(self.root, "Bericht-Listener starten.bat")
        self.lst_stop = os.path.join(self.root, "Bericht-Listener stoppen.bat")
        self.lst_rt = os.path.join(self.proto, "report_listener_runtime")
        self.log_path = self.log_path or os.path.join(self.root, "umstellung_log.txt")
        self.now = self.now or (lambda: datetime.now(TZ))
        self.proc_alive = self.proc_alive or default_alive
        self.proc_idle = self.proc_idle or default_idle
        self.proc_kill = self.proc_kill or default_kill
        self.variant_check = self.variant_check or (lambda: default_variant_check(self))
        self.cycle_age = self.cycle_age or (lambda: default_cycle_age(self))
        self.run_tests = self.run_tests or (lambda d: default_run_tests(self, d))
        self.run_cmd = self.run_cmd or default_run_cmd
        self.send_text = self.send_text or (lambda t: default_send_text(self, t))
        self.send_doc = self.send_doc or (lambda p, c: default_send_doc(self, p, c))
        self.build_report = self.build_report or (lambda rt, out, now: default_build_report(self, rt, out, now))


class StepError(Exception):
    pass


# ------------------------------------------------------------------ Protokoll
_SECRET_PATTERNS = [re.compile(r"bot\d{6,}:[A-Za-z0-9_-]{20,}"), re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}"),
                    re.compile(r"(?<![\w.])-\d{9,}(?![\w.])")]


def redact(text):
    """Entfernt Bot-Token-/Chat-ID-Muster aus JEDER Protokollzeile (auch aus verketteten Ausnahmen)."""
    t = str(text)
    for p in _SECRET_PATTERNS:
        t = p.sub("[REDACTED]", t)
    return t


def log(cfg, msg, level="INFO"):
    line = redact(f"[{cfg.now().strftime('%Y-%m-%d %H:%M:%S')}] {level:5} {msg}")
    cfg.log_lines.append(line)
    try:
        print(line)
    except Exception:
        pass
    if not cfg.dry:
        try:
            with open(cfg.log_path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError:
            pass


class Checks:
    """Sammelt Pruefergebnisse (dry-run)."""
    def __init__(self, cfg):
        self.cfg, self.fails, self.warns = cfg, [], []

    def ok(self, name, detail=""):
        log(self.cfg, f"OK    {name}" + (f": {detail}" if detail else ""))

    def warn(self, name, detail=""):
        self.warns.append(name)
        log(self.cfg, f"WARN  {name}: {detail}", "WARN")

    def fail(self, name, detail=""):
        self.fails.append(name)
        log(self.cfg, f"FAIL  {name}: {detail}", "FAIL")


# ------------------------------------------------------------------ echte Hooks
def _ps(cmd, timeout=30):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd], capture_output=True, text=True,
                       timeout=timeout, creationflags=flags)
    return r.stdout or ""


def _pattern_ok(pattern):
    return bool(re.fullmatch(r"[A-Za-z0-9_.\-]+(\|[A-Za-z0-9_.\-]+)*", pattern))


def _where(pattern):
    """'run_loop.py|zwei-monate' -> PowerShell-Bedingung (alle Teile muessen in der Kommandozeile vorkommen).
    Nur Python-Prozesse und NIE der abfragende PowerShell-Prozess selbst (dessen Kommandozeile enthaelt ja die Suchbegriffe)."""
    parts = " -and ".join(f"$_.CommandLine -like '*{p}*'" for p in pattern.split("|"))
    name = "wscript*" if pattern.endswith(".vbs") else "python*"
    return f"$_.Name -like '{name}' -and $_.ProcessId -ne $PID -and {parts}"


def default_alive(pattern):
    if not _pattern_ok(pattern):
        return None
    try:
        out = _ps(f"(Get-CimInstance Win32_Process | Where-Object {{ {_where(pattern)} }} | Measure-Object).Count")
        return int((out or "0").strip() or 0) > 0
    except Exception:
        return None


def _cpu_seconds(pattern):
    out = _ps("$p = Get-CimInstance Win32_Process | Where-Object { " + _where(pattern) + " }; "
              "$t = 0; foreach ($x in $p) { $t += ($x.KernelModeTime + $x.UserModeTime) }; $t / 10000000")
    return float((out or "0").strip().replace(",", ".") or 0)


def default_idle(pattern):
    """Prozess 'schlaeft' (Schleife zwischen zwei Zyklen): CPU-Zeit waechst in 20 s um < 1 s."""
    try:
        a = _cpu_seconds(pattern); time.sleep(20); b = _cpu_seconds(pattern)
        return (b - a) < 1.0
    except Exception:
        return False


OLD_SLEEP_S = 3600           # der alte Lauf schlaeft nach jedem Zyklus genau CYCLE_SECONDS = 3600 s
OLD_IDLE_MARGIN_S = 180


def default_cycle_age(cfg):
    """Sekunden seit dem Ende des letzten Zyklus des alten Laufs (last_cycle_monitor.json 'end'); None = unbekannt."""
    try:
        d = read_json(os.path.join(cfg.old_rt, "last_cycle_monitor.json"))
        return (cfg.now() - datetime.fromisoformat(d["end"])).total_seconds()
    except Exception:
        return None


def old_run_is_sleeping(cfg):
    """Sicher zwischen zwei Zyklen? Nur wenn der letzte Zyklus VOR kurzem endete (Schleife schlaeft dann 3600 s) UND der
    Prozess keine CPU nutzt. Niedrige CPU allein genuegt NICHT (ein Zyklus kann auf Yahoo/Telegram warten)."""
    age = cfg.cycle_age()
    if age is None or not (30 <= age <= OLD_SLEEP_S - OLD_IDLE_MARGIN_S):
        return False
    return bool(cfg.proc_idle("run_loop.py|zwei-monate"))


def default_kill(pattern):
    if not _pattern_ok(pattern):
        return 0
    out = _ps("$p = Get-CimInstance Win32_Process | Where-Object { " + _where(pattern) + " }; "
              "$n = 0; foreach ($x in $p) { Stop-Process -Id $x.ProcessId -Force -ErrorAction SilentlyContinue; $n++ }; $n")
    try:
        return int((out or "0").strip() or 0)
    except ValueError:
        return 0


def default_run_cmd(argv):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.run(argv, creationflags=flags, timeout=120).returncode


def default_run_tests(cfg, directory):
    py = cfg.venv_py
    env = dict(os.environ)
    env["PYTHONDONTWRITEBYTECODE"] = "1"                       # --dry-run schreibt keine __pycache__ in Prototyp_v2
    r = subprocess.run([py, "-m", "pytest", "-p", "no:cacheprovider", "-q", "-x"], cwd=directory, capture_output=True,
                       text=True, timeout=1800, env=env)
    tail = (r.stdout or "").strip().splitlines()[-3:]
    return r.returncode == 0, " | ".join(tail)


def _telegram(cfg):
    """(transport, system_chat) aus Prototyp\\.env zur Laufzeit - Werte werden NIE ausgegeben."""
    if cfg.v2 not in sys.path:
        sys.path.insert(0, cfg.v2)
    from notify.live import read_env
    from notify.config import load_and_validate
    from notify.transport import RealTelegramTransport
    c, _ = load_and_validate(read_env(os.path.join(cfg.proto, ".env")), EXPECTED_VARIANTS)
    if not c.enabled or not c.system_target():
        raise StepError("Telegram nicht konfiguriert (Token/System-Chat)")
    return RealTelegramTransport(c.token), c.system_target()


def default_send_text(cfg, text):
    tr, chat = _telegram(cfg)
    tr.send_text(chat, text)


def default_send_doc(cfg, path, caption):
    tr, chat = _telegram(cfg)
    tr.send_document(chat, path, caption)


def default_build_report(cfg, old_rt, out_path, now):
    """Abschlussbericht des Zwei-Monats-Tests (alle 8 Varianten, nur geschlossene Trades). -> Bildunterschrift."""
    if cfg.v2 not in sys.path:
        sys.path.insert(0, cfg.v2)
    from notify import status_report as SR
    d = SR.collect(old_rt, None, now=now, check_process=False, variants=SR.ALL_VARIANTS)
    SR.build_pdf(d, out_path, title="Abschlussbericht Zwei-Monats-Test", final=True)
    return SR.caption(d, final=True)


# ------------------------------------------------------------------ Hilfen
def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def old_end(cfg):
    m = read_json(os.path.join(cfg.old_rt, "START_MANIFEST.json"))
    return datetime.fromisoformat(m["stage_end_local"]), m


def iter_copy_files(cfg):
    """(quelle, ziel, relativ) aller zu uebernehmenden Code-Dateien."""
    out = []
    for d in COPY_DIRS:
        base = os.path.join(cfg.v2, d)
        if not os.path.isdir(base):
            continue
        for dp, dns, fns in os.walk(base):
            dns[:] = [x for x in dns if x not in EXCLUDE_DIR_NAMES]
            for fn in fns:
                if fn in EXCLUDE_FILE_NAMES or fn.endswith((".pyc", ".log", ".tmp", ".part")):
                    continue
                src = os.path.join(dp, fn)
                rel = os.path.relpath(src, cfg.v2)
                out.append((src, os.path.join(cfg.proto, rel), rel))
    for fn in sorted(os.listdir(cfg.v2)):
        p = os.path.join(cfg.v2, fn)
        if os.path.isfile(p) and (fn.endswith(COPY_ROOT_PATTERNS) or fn in COPY_ROOT_EXTRA) and fn not in EXCLUDE_FILE_NAMES:
            out.append((p, os.path.join(cfg.proto, fn), fn))
    return out


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for ch in iter(lambda: f.read(1 << 20), b""):
            h.update(ch)
    return h.hexdigest()


def plan_copy(cfg):
    """-> (neu, geaendert, gleich) als Listen von (src, dst, rel)."""
    new, changed, same = [], [], []
    for src, dst, rel in iter_copy_files(cfg):
        if not os.path.exists(dst):
            new.append((src, dst, rel))
        elif sha(src) == sha(dst):
            same.append((src, dst, rel))
        else:
            changed.append((src, dst, rel))
    return new, changed, same


def guard_copy_set(cfg, files):
    """Sicherheitsnetz: nie .env, venv oder Laufzeit-/Datenordner im Kopiersatz."""
    for src, dst, rel in files:
        parts = rel.replace("\\", "/").split("/")
        if parts[0] in ("venv",) or parts[-1] == ".env" or any(p.startswith("paper_runtime") or p in (
                "backtest_runtime", "data_cache", "report_listener_runtime", "mtf_cache") for p in parts):
            raise StepError(f"Kopiersatz enthaelt gesperrten Pfad: {rel}")


def estimate_backup(cfg):
    n = size = 0
    for dp, dns, fns in os.walk(cfg.proto):
        if dp == cfg.proto:
            dns[:] = [d for d in dns if d not in BACKUP_EXCLUDE_TOP]
        dns[:] = [d for d in dns if d != "__pycache__"]
        for fn in fns:
            if fn in EXCLUDE_FILE_NAMES:
                continue
            try:
                size += os.path.getsize(os.path.join(dp, fn)); n += 1
            except OSError:
                pass
    return n, size


# ------------------------------------------------------------------ Schritte
def default_variant_check(cfg):
    """Prueft im NEUEN Code (Prototyp_v2): aktive Varianten = Pro.1, Pro.3, C+, D; jede hat Code, Routing und eine
    Chat-ID in Prototyp/.env (nur Ja/Nein, nie die Werte); D schreibt in die Pro.6-Gruppe, C+ in die Pro.2-Gruppe."""
    if cfg.v2 not in sys.path:
        sys.path.insert(0, cfg.v2)
    from engine import run_paper, variants as V, exit_d
    from notify.config import load_and_validate, VARIANT_ENV
    from notify.live import read_env
    out = []
    out.append(("aktive Varianten im neuen Code", run_paper.ACTIVE_VARIANTS == EXPECTED_VARIANTS, ", ".join(run_paper.ACTIVE_VARIANTS)))
    out.append(("Variante D: Bewertung + Ausstiegsmodul", "Str.3 D" in V.REGISTRY and hasattr(exit_d, "advance"), "engine/exit_d.py"))
    out.append(("Routing C+ -> Pro.2-Gruppe, D -> Pro.6-Gruppe",
                VARIANT_ENV.get("Str.3 C+") == "STR3_PRO2_CHAT_ID" and VARIANT_ENV.get("Str.3 D") == "STR3_PRO6_CHAT_ID", ""))
    env = read_env(os.path.join(cfg.proto, ".env"))
    c, _ = load_and_validate(env, EXPECTED_VARIANTS)
    for sid in EXPECTED_VARIANTS:
        out.append((f"Chat-ID vorhanden: {sid} ({VARIANT_ENV[sid]})", bool(c.chat_for_variant(sid)), "nur Ja/Nein"))
    out.append(("Chat-ID vorhanden: STR3_SYSTEM_CHAT_ID", bool(c.system_chat), "nur Ja/Nein"))
    return out


def step_variants(cfg, ck):
    try:
        for name, ok, detail in cfg.variant_check():
            (ck.ok if ok else ck.fail)(name, detail if ok else (detail or "fehlt"))
    except Exception as e:
        ck.fail("Pruefung der Varianten (inkl. D)", f"{type(e).__name__}")


def step_preflight(cfg, ck):
    step_variants(cfg, ck)
    for name, p in [("Prototyp", cfg.proto), ("Prototyp_v2", cfg.v2), ("venv-Python", cfg.venv_py),
                    ("Neu-VBS", cfg.new_vbs), ("Neu-Start-bat", cfg.start_bat), ("Listener-Start-bat", cfg.lst_start),
                    ("Listener-Stop-bat", cfg.lst_stop)]:
        (ck.ok if os.path.exists(p) else ck.fail)(f"vorhanden: {name}", "" if os.path.exists(p) else p)
    # .env nur auf Existenz pruefen (nie oeffnen/ausgeben)
    (ck.ok if os.path.exists(os.path.join(cfg.proto, ".env")) else ck.fail)("vorhanden: Prototyp\\.env (nur Existenz geprueft)")
    if not os.path.isdir(cfg.startup_dir):
        ck.fail("Autostart-Ordner", cfg.startup_dir)
    else:
        ck.ok("Autostart-Ordner", cfg.startup_dir)
    if os.path.exists(os.path.join(cfg.new_rt, "START_MANIFEST.json")):
        ck.fail("neuer Lauf noch nicht vorhanden", "paper_runtime_neustart\\START_MANIFEST.json existiert bereits")
    else:
        ck.ok("neuer Lauf noch nicht vorhanden")
    if os.path.exists(cfg.zip_path):
        ck.warn("ZIP existiert bereits", f"neue Sicherung erhaelt Zusatz im Namen: {os.path.basename(cfg.zip_path)}")
    try:
        end, man = old_end(cfg)
        ck.ok("Manifest des alten Laufs", f"Ende {end.strftime('%d.%m.%Y %H:%M')} Europe/Berlin, Stufe {man.get('stage')}")
    except Exception as e:
        ck.fail("Manifest des alten Laufs", type(e).__name__)
    st = os.path.join(cfg.v2, "BAU_STAND.md")
    ck.ok("BAU_STAND.md vorhanden") if os.path.exists(st) else ck.warn("BAU_STAND.md fehlt")
    try:
        free = shutil.disk_usage(cfg.root).free
        n, size = estimate_backup(cfg)
        (ck.ok if free > size * 3 else ck.fail)("Speicherplatz fuer ZIP", f"{size / 1e6:.0f} MB zu sichern, frei {free / 1e9:.0f} GB")
        ck.ok("ZIP-Umfang (ohne venv/.env)", f"{n} Dateien")
    except Exception as e:
        ck.fail("Speicherplatz/ZIP-Umfang", type(e).__name__)


def step_old_run(cfg, ck):
    """Schritt 1."""
    end, man = old_end(cfg)
    now = cfg.now()
    alive = cfg.proc_alive("run_loop.py|zwei-monate")
    state = {True: "laeuft", False: "beendet", None: "nicht feststellbar"}[alive]
    if cfg.dry:
        ck.ok("alter Lauf", f"{state}; Testende {end.strftime('%d.%m.%Y %H:%M')} "
                            + ("(noch nicht erreicht - im --go wuerde abgebrochen)" if now < end else "(erreicht)"))
        if alive:
            ck.ok("Plan alter Lauf", "STOP-Datei setzen; schlaeft die Schleife -> Prozess beenden (nur NACH Testende)")
        return
    if now < end:
        raise StepError(f"Testende {end.strftime('%d.%m.%Y %H:%M')} noch nicht erreicht - alter Lauf bleibt unangetastet")
    if alive is False:
        log(cfg, "alter Lauf bereits beendet")
        return
    stop_file = os.path.join(cfg.old_rt, "STOP")
    with open(stop_file, "w", encoding="utf-8") as f:
        f.write("STOP\n")
    log(cfg, "alter Lauf: STOP-Datei gesetzt")
    t0 = cfg.now()
    while True:
        alive = cfg.proc_alive("run_loop.py|zwei-monate")
        if alive is False:
            log(cfg, "alter Lauf beendet sich selbst"); return
        if alive and old_run_is_sleeping(cfg):
            n = cfg.proc_kill("run_loop.py|zwei-monate")
            log(cfg, f"alter Lauf schlief zwischen zwei Zyklen (letzter Zyklus vor {int(cfg.cycle_age() or 0)} s beendet) - "
                     f"{n} Prozess(e) beendet (Zustand liegt atomar auf Platte)")
            cfg.sleep(3)
            if cfg.proc_alive("run_loop.py|zwei-monate"):
                raise StepError("alter Lauf liess sich nicht beenden")
            return
        if (cfg.now() - t0).total_seconds() > cfg.stage_wait_s:
            raise StepError("alter Lauf rechnet noch nach der Wartezeit - nicht beendet")
        cfg.sleep(20)


def step_report(cfg, ck):
    """Schritt 2."""
    now = cfg.now()
    if cfg.dry:
        tmp = tempfile.mkdtemp(prefix="umstellung_dry_")
        try:
            out = os.path.join(tmp, "Abschlussbericht.pdf")
            cap = cfg.build_report(cfg.old_rt, out, now)
            size = os.path.getsize(out)
            (ck.ok if size > 5000 else ck.fail)("Abschlussbericht (Probelauf, nur temporaer)", f"{size // 1024} KB; Kurztext: {cap.splitlines()[2] if len(cap.splitlines()) > 2 else cap[:80]}")
        finally:
            shutil.rmtree(tmp, ignore_errors=True)
        return
    os.makedirs(cfg.backups, exist_ok=True)
    cap = cfg.build_report(cfg.old_rt, cfg.report_path, now)
    if not os.path.exists(cfg.report_path) or os.path.getsize(cfg.report_path) < 5000:
        raise StepError("Abschlussbericht wurde nicht erzeugt")
    cfg.send_doc(cfg.report_path, cap)
    log(cfg, f"Abschlussbericht gesendet ({os.path.getsize(cfg.report_path) // 1024} KB): {cfg.report_path}")


def step_zip(cfg, ck):
    """Schritt 3."""
    n, size = estimate_backup(cfg)
    if cfg.dry:
        ck.ok("ZIP-Sicherung (Plan)", f"{n} Dateien, {size / 1e6:.0f} MB unkomprimiert -> {cfg.zip_path}")
        return
    os.makedirs(cfg.backups, exist_ok=True)
    path = cfg.zip_path
    k = 2
    while os.path.exists(path):
        path = cfg.zip_path.replace(".zip", f"_{k}.zip"); k += 1
    part = path + ".part"
    skipped = 0
    count = 0
    with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED, compresslevel=6) as z:
        for dp, dns, fns in os.walk(cfg.proto):
            if dp == cfg.proto:
                dns[:] = [d for d in dns if d not in BACKUP_EXCLUDE_TOP]
            dns[:] = [d for d in dns if d != "__pycache__"]
            for fn in fns:
                if fn in EXCLUDE_FILE_NAMES:
                    continue
                full = os.path.join(dp, fn)
                arc = os.path.join("Prototyp", os.path.relpath(full, cfg.proto))
                try:
                    z.write(full, arc); count += 1
                except OSError:
                    skipped += 1
    with zipfile.ZipFile(part) as z:
        bad = z.testzip()
        if bad:
            raise StepError(f"ZIP defekt: {bad}")
    os.replace(part, path)
    cfg.zip_path = path
    log(cfg, f"ZIP-Sicherung: {path} ({count} Dateien, {os.path.getsize(path) / 1e6:.0f} MB, uebersprungen {skipped})")


def step_code(cfg, ck):
    """Schritt 4."""
    new, changed, same = plan_copy(cfg)
    guard_copy_set(cfg, new + changed + same)
    if cfg.dry:
        ck.ok("Codekopie (Plan)", f"{len(new)} neu, {len(changed)} geaendert, {len(same)} gleich; "
                                  ".env, venv und alle Laufzeit-/Datenordner bleiben unangetastet")
        ok, tail = cfg.run_tests(cfg.v2)
        (ck.ok if ok else ck.fail)("Tests in Prototyp_v2", tail)
        return
    # Transaktion: JEDE Ausnahme (Kopieren, Pruefen, Tests, Zeitueberschreitung) stellt die ersetzten Dateien aus der ZIP wieder her
    cfg.overwritten = []
    try:
        for src, dst, rel in changed + new:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            if (src, dst, rel) in changed:
                cfg.overwritten.append(rel)              # VOR dem Ersetzen vormerken -> auch Teilstaende werden zurueckgespielt
            tmp = dst + ".umstellung_tmp"
            shutil.copyfile(src, tmp)
            os.replace(tmp, dst)
        cfg.progress["code"] = True
        for src, dst, rel in changed + new:
            if sha(src) != sha(dst):
                raise StepError(f"Kopie fehlerhaft: {rel}")
        log(cfg, f"Code uebernommen: {len(new)} neu, {len(changed)} ersetzt, {len(same)} unveraendert")
        created = os.path.join(cfg.proto, "live_settings.json")
        if not os.path.exists(created):
            with open(created, "w", encoding="utf-8") as f:
                json.dump({"trade_pdf": {"enabled": True, "timeout_s": 90, "png_dpi": 220},
                           "prewarn": {"enabled": True, "minutes_before": [30, 15],
                                       "night_quiet": {"enabled": True, "from": "23:00", "to": "07:00"},
                                       "groups": ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]},
                           "cycle": {"close_delay_s": 90}}, f, indent=1, ensure_ascii=False)
            log(cfg, "live_settings.json mit Standardwerten angelegt")
        ok, tail = cfg.run_tests(cfg.proto)
        if not ok:
            raise StepError(f"Tests in Prototyp ROT ({tail})")
        log(cfg, f"Tests in Prototyp gruen: {tail}")
    except BaseException:
        _rollback(cfg, cfg.overwritten)
        cfg.progress["code"] = False
        raise


def _rollback(cfg, rels):
    """Spielt ueberschriebene Dateien aus der ZIP zurueck (nichts wird geloescht)."""
    try:
        with zipfile.ZipFile(cfg.zip_path) as z:
            names = set(z.namelist())
            n = 0
            for rel in rels:
                arc = ("Prototyp/" + rel.replace("\\", "/"))
                if arc in names:
                    dst = os.path.join(cfg.proto, rel)
                    with open(dst, "wb") as f:
                        f.write(z.read(arc))
                    n += 1
        log(cfg, f"Rollback: {n} Dateien aus der ZIP zurueckgespielt", "WARN")
    except Exception as e:
        log(cfg, f"Rollback fehlgeschlagen: {type(e).__name__}", "FAIL")


def _unwind(cfg):
    """Rueckbau nach einem Fehler in/nach Schritt 4, damit der Zustand 'vor der Umstellung' bleibt:
    Autostart zuruecknehmen, neuen Lauf stoppen (Laufzeitordner wird UMBENANNT, damit ein neuer Versuch moeglich ist),
    Code aus der ZIP zurueckspielen, Bericht-Listener mit dem alten Code neu starten. Nichts wird geloescht."""
    pr = cfg.progress
    stamp = cfg.now().strftime("%Y%m%d_%H%M%S")
    try:
        if pr.get("autostart_new"):
            new = os.path.join(cfg.startup_dir, "TradingBot_Neustart.vbs")
            if os.path.exists(new):
                os.replace(new, new + f".fehlgeschlagen_{stamp}")
            log(cfg, "Rueckbau: neuer Autostart-Eintrag umbenannt", "WARN")
        if pr.get("autostart_old_renamed"):
            old = os.path.join(cfg.startup_dir, "TradingBot_2Monate.vbs")
            dis = pr["autostart_old_renamed"]
            if os.path.exists(dis) and not os.path.exists(old):
                os.replace(dis, old)
            log(cfg, "Rueckbau: alter Autostart-Eintrag wiederhergestellt", "WARN")
    except Exception as e:
        log(cfg, f"Rueckbau Autostart fehlgeschlagen: {type(e).__name__}", "FAIL")
    try:
        if pr.get("new_run"):
            os.makedirs(cfg.new_rt, exist_ok=True)
            with open(os.path.join(cfg.new_rt, "STOP"), "w", encoding="utf-8") as f:
                f.write("STOP\n")
            cfg.proc_kill("TradingBot_Neustart.vbs")          # Watchdog zuerst, damit nichts neu startet
            cfg.proc_kill("run_loop.py|neustart")
            cfg.sleep(3)
            if os.path.isdir(cfg.new_rt):
                os.replace(cfg.new_rt, cfg.new_rt + f"_abgebrochen_{stamp}")
            log(cfg, "Rueckbau: neuer Lauf gestoppt, Laufzeitordner umbenannt", "WARN")
    except Exception as e:
        log(cfg, f"Rueckbau neuer Lauf fehlgeschlagen: {type(e).__name__}", "FAIL")
    try:
        if cfg.overwritten and (pr.get("code") or pr.get("listener") or pr.get("new_run")):
            _rollback(cfg, cfg.overwritten)
            pr["code"] = False
    except Exception as e:
        log(cfg, f"Rueckbau Code fehlgeschlagen: {type(e).__name__}", "FAIL")
    try:
        if pr.get("listener"):
            cfg.run_cmd(["cmd", "/c", cfg.lst_stop])
            t0 = cfg.now()
            while cfg.proc_alive("report_listener.py") and (cfg.now() - t0).total_seconds() < 150:
                cfg.sleep(5)
            if cfg.proc_alive("report_listener.py"):
                cfg.proc_kill("report_listener.py"); cfg.sleep(3)
            cfg.run_cmd(["cmd", "/c", cfg.lst_start])
            log(cfg, "Rueckbau: Bericht-Listener mit dem alten Code neu gestartet", "WARN")
    except Exception as e:
        log(cfg, f"Rueckbau Listener fehlgeschlagen: {type(e).__name__}", "FAIL")


def step_listener(cfg, ck):
    """Schritt 5."""
    if cfg.dry:
        alive = cfg.proc_alive("report_listener.py")
        ck.ok("Bericht-Listener (Plan)", f"derzeit {'laeuft' if alive else 'nicht aktiv' if alive is False else 'unbekannt'}; "
                                          "Stop-bat, warten bis beendet, Start-bat")
        return
    cfg.progress["listener"] = True                       # ab hier ist der Listener veraendert (Rueckbau noetig)
    cfg.run_cmd(["cmd", "/c", cfg.lst_stop])
    t0 = cfg.now()
    while cfg.proc_alive("report_listener.py") and (cfg.now() - t0).total_seconds() < 150:
        cfg.sleep(5)
    if cfg.proc_alive("report_listener.py"):
        log(cfg, "Listener beendet sich nicht rechtzeitig - wird beendet", "WARN")
        cfg.proc_kill("report_listener.py")
        cfg.sleep(3)
    cfg.run_cmd(["cmd", "/c", cfg.lst_start])
    t0 = cfg.now()
    while not cfg.proc_alive("report_listener.py") and (cfg.now() - t0).total_seconds() < 60:
        cfg.sleep(3)
    if not cfg.proc_alive("report_listener.py"):
        raise StepError("Bericht-Listener laeuft nach dem Neustart nicht")
    log(cfg, "Bericht-Listener neu gestartet (neuer Code)")


def step_new_run(cfg, ck):
    """Schritt 6."""
    if cfg.dry:
        ck.ok("Neuer Lauf (Plan)", f"{os.path.basename(cfg.start_bat)} -> wscript TradingBot_Neustart.vbs; Pruefung: Manifest, Prozess, erster Zyklus")
        return
    cfg.progress["new_run"] = True                        # ab hier kann der neue Lauf existieren (Rueckbau noetig)
    cfg.run_cmd(["cmd", "/c", cfg.start_bat])
    manifest = os.path.join(cfg.new_rt, "START_MANIFEST.json")
    t0 = cfg.now()
    while (cfg.now() - t0).total_seconds() < 180 and not (os.path.exists(manifest) and cfg.proc_alive("run_loop.py|neustart")):
        cfg.sleep(5)
    if not os.path.exists(manifest) or not cfg.proc_alive("run_loop.py|neustart"):
        raise StepError("neuer Lauf startet nicht (kein Manifest/Prozess)")
    log(cfg, "neuer Lauf gestartet (Manifest vorhanden, Prozess aktiv)")
    mon = os.path.join(cfg.new_rt, "last_cycle_monitor.json")
    t0 = cfg.now()
    while (cfg.now() - t0).total_seconds() < cfg.new_run_wait_s:
        if os.path.exists(mon):
            try:
                m = read_json(mon)
                if m.get("instruments", 0) > 0:
                    bad = (m.get("no_data", 0) or 0) + (m.get("fetch_failed", 0) or 0) + (m.get("errors", 0) or 0)
                    if bad >= m["instruments"]:
                        raise StepError("erster Zyklus ohne verwertbare Daten (Abruf-/Verarbeitungsfehler bei allen Instrumenten)")
                    log(cfg, f"erster Zyklus ok: {m['instruments']} Instrumente, Fehler {m.get('errors')}, "
                             f"Dauer {m.get('duration_s')} s")
                    return
            except StepError:
                raise
            except Exception:
                pass
        if not cfg.proc_alive("run_loop.py|neustart"):
            raise StepError("neuer Lauf beendete sich waehrend des ersten Zyklus")
        cfg.sleep(10)
    raise StepError("erster Zyklus des neuen Laufs nicht rechtzeitig fertig")


def step_autostart(cfg, ck):
    """Schritt 7 (Nutzer-Freigabe: Autostart ja; keine Windows-Aufgabenplanung)."""
    dst = os.path.join(cfg.startup_dir, "TradingBot_Neustart.vbs")
    old = os.path.join(cfg.startup_dir, "TradingBot_2Monate.vbs")
    old_dis = old + ".disabled"
    if cfg.dry:
        ck.ok("Autostart (Plan)", f"kopieren: TradingBot_Neustart.vbs -> {cfg.startup_dir}")
        if os.path.exists(old):
            ck.ok("Autostart (Plan)", "umbenennen: TradingBot_2Monate.vbs -> TradingBot_2Monate.vbs.disabled (nichts wird geloescht)")
        else:
            ck.warn("alter Autostart-Eintrag", "TradingBot_2Monate.vbs nicht im Autostart-Ordner gefunden")
        if os.path.exists(os.path.join(cfg.startup_dir, "TradingBot_BerichtListener.vbs")):
            ck.ok("Autostart Bericht-Listener bleibt", "TradingBot_BerichtListener.vbs")
        return
    shutil.copyfile(cfg.new_vbs, dst)
    cfg.progress["autostart_new"] = True
    log(cfg, f"Autostart: {dst} angelegt")
    if os.path.exists(old):
        target = old_dis
        k = 2
        while os.path.exists(target):
            target = f"{old_dis}.{k}"; k += 1
        os.replace(old, target)
        cfg.progress["autostart_old_renamed"] = target
        log(cfg, f"Autostart: alter Eintrag umbenannt -> {os.path.basename(target)}")
    else:
        log(cfg, "Autostart: alter Eintrag TradingBot_2Monate.vbs nicht gefunden (bereits deaktiviert?)", "WARN")


# ------------------------------------------------------------------ Gesamtablauf
def run(cfg, dry):
    cfg.dry = dry
    ck = Checks(cfg)
    log(cfg, f"=== Umstellung 17.10.2026 - {'DRY-RUN (veraendert nichts, sendet nichts)' if dry else 'GO'} ===")
    alert_sent = {"v": False}

    def alert(detail):
        if dry or alert_sent["v"]:
            return
        alert_sent["v"] = True
        try:
            cfg.send_text(f"{FAIL_TEXT} ({detail})")
        except Exception as e:
            log(cfg, f"Ausfall-Meldung nicht zustellbar: {type(e).__name__}", "FAIL")

    steps = [("Vorpruefung", step_preflight), ("1 alter Lauf", step_old_run), ("2 Abschlussbericht", step_report),
             ("3 ZIP-Sicherung", step_zip), ("4 Code + Tests", step_code), ("5 Bericht-Listener", step_listener),
             ("6 neuer Lauf", step_new_run), ("7 Autostart", step_autostart)]
    for name, fn in steps:
        log(cfg, f"--- {name}")
        try:
            fn(cfg, ck)
            if not dry and name == "Vorpruefung" and ck.fails:
                raise StepError("Vorpruefung: " + ", ".join(ck.fails))
        except StepError as e:
            if dry:
                ck.fail(name, str(e))
            else:
                log(cfg, f"FEHLER in {name}: {e}", "FAIL")
                _unwind(cfg)
                alert(name)
                return 3
        except Exception as e:
            tb = traceback.format_exc()
            if dry:
                ck.fail(name, f"{type(e).__name__}: {e}")
            else:
                log(cfg, f"FEHLER in {name}: {type(e).__name__}\n{tb}", "FAIL")
                _unwind(cfg)
                alert(name)
                return 3
    if dry:
        log(cfg, f"=== Ergebnis dry-run: {len(ck.fails)} FAIL, {len(ck.warns)} WARN ===")
        return 1 if ck.fails else 0
    try:
        cfg.send_text(FINAL_TEXT)
        log(cfg, "Schlussmeldung gesendet")
    except Exception as e:
        log(cfg, f"Schlussmeldung nicht zustellbar: {type(e).__name__}", "FAIL")
    log(cfg, "=== Umstellung abgeschlossen ===")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description="Umstellung auf den Neustart-Lauf (17.10.2026)")
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", help="alles pruefen, nichts aendern, nichts senden")
    g.add_argument("--go", action="store_true", help="Umstellung durchfuehren")
    a = ap.parse_args(argv)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    return run(Cfg(), dry=a.dry_run)


if __name__ == "__main__":
    sys.exit(main())
