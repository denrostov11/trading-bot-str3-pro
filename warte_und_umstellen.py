# -*- coding: utf-8 -*-
"""Einmaliger Wartebot fuer die Umstellung am Sa 17.10.2026. KEIN Autostart, KEINE Windows-Aufgabe.

Start (Fenster bleibt offen):  Prototyp\\venv\\Scripts\\python.exe warte_und_umstellen.py
Start unsichtbar:              "warte_und_umstellen starten.bat"
Der PC darf bis zur Erfolgsmeldung nicht neu gestartet werden und nicht in den Standby gehen.

Ablauf (alle Zeiten Europe/Berlin):
 a) 09:00  genau EINE Vorab-Nachricht an STR3 System. Ist es beim Start schon nach 09:00 -> uebersprungen.
 b) 12:15  zuerst umstellung_17-10.py --dry-run; ist er ok -> --go. Ist es beim Start schon nach 12:15 -> sofort.
           Fehler -> kurze Meldung "Umstellung NICHT erfolgt - Eingriff noetig", nichts weiter starten
           (der alte Code bleibt aktiv bzw. im Zustand vor der Umstellung).
 c) danach beendet sich der Prozess.
Protokoll: umstellung_log.txt (neben diesem Skript). Zustand (damit eine Meldung nie doppelt geht): warte_state.json.
"""
import os, sys, json, time, subprocess, argparse
from dataclasses import dataclass
from datetime import datetime, date, time as dtime
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Berlin")
HERE = os.path.dirname(os.path.abspath(__file__))
DAY = date(2026, 10, 17)
T_NOTICE = datetime.combine(DAY, dtime(9, 0), tzinfo=TZ)
T_GO = datetime.combine(DAY, dtime(12, 15), tzinfo=TZ)

NOTICE_TEXT = ("Heute um 12:00 endet der Zwei-Monats-Test. Gegen 12:15 stellt der Bot automatisch auf "
               "Pro.1 Baseline / Pro.3 Volumen / C+ / D um. Bitte den PC bis zur Erfolgsmeldung NICHT neu starten. "
               "Danach bitte neu starten, damit der Autostart greift.")
FAIL_TEXT = "Umstellung NICHT erfolgt – Eingriff nötig"

RC_OK, RC_FAIL = 0, 3


@dataclass
class Hooks:
    now: callable = None
    sleep: callable = time.sleep
    send_text: callable = None
    run_umstellung: callable = None       # (mode) -> rc ; mode "--dry-run" | "--go"
    log_path: str = os.path.join(HERE, "umstellung_log.txt")
    state_path: str = os.path.join(HERE, "warte_state.json")


def _log(h, msg):
    line = f"[{h.now().strftime('%Y-%m-%d %H:%M:%S')}] WARTE {msg}"
    try:
        print(line)
    except Exception:
        pass
    try:
        with open(h.log_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def _state(h):
    try:
        return json.load(open(h.state_path, encoding="utf-8"))
    except Exception:
        return {}


def _save(h, st):
    tmp = h.state_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(st, f, indent=1)
    os.replace(tmp, h.state_path)


def _wait_until(h, t):
    while True:
        n = h.now()
        if n >= t:
            return
        h.sleep(min(30.0, max(1.0, (t - n).total_seconds())))


def run(h):
    """-> Rueckgabecode. Reine Ablauflogik (Uhr, Sender und Umstellung injizierbar)."""
    st = _state(h)
    start = h.now()
    _log(h, f"gestartet ({start.strftime('%d.%m.%Y %H:%M')} Europe/Berlin)")
    if start.date() > DAY:
        _log(h, "Datum liegt nach dem 17.10.2026 - dieser Wartebot ist nur fuer den 17.10.2026 gedacht; nichts getan")
        return RC_FAIL
    # a) Vorab-Nachricht
    if start >= T_NOTICE:
        _log(h, "nach 09:00 - Vorab-Nachricht wird uebersprungen")
    elif st.get("notice_sent"):
        _log(h, "Vorab-Nachricht war bereits gesendet")
    else:
        _wait_until(h, T_NOTICE)
        try:
            h.send_text(NOTICE_TEXT)
            st["notice_sent"] = h.now().isoformat()
            _save(h, st)
            _log(h, "Vorab-Nachricht an STR3 System gesendet")
        except Exception as e:
            _log(h, f"Vorab-Nachricht nicht zustellbar: {type(e).__name__}")
    # b) 12:15
    if h.now() >= T_GO:
        _log(h, "nach 12:15 - Umstellung beginnt sofort")
    else:
        _wait_until(h, T_GO)
    if st.get("go_done"):
        _log(h, "Umstellung wurde bereits ausgefuehrt - beende")
        return RC_OK
    _log(h, "starte umstellung_17-10.py --dry-run")
    rc = h.run_umstellung("--dry-run")
    if rc != 0:
        _log(h, f"dry-run NICHT ok (rc={rc}) - Umstellung abgebrochen, nichts gestartet")
        try:
            h.send_text(FAIL_TEXT)
        except Exception as e:
            _log(h, f"Ausfall-Meldung nicht zustellbar: {type(e).__name__}")
        st["go_done"] = "abgebrochen_dry_run"
        _save(h, st)
        return RC_FAIL
    _log(h, "dry-run ok - starte umstellung_17-10.py --go")
    rc = h.run_umstellung("--go")
    st["go_done"] = f"rc={rc}"
    _save(h, st)
    if rc != 0:
        if rc == RC_FAIL:
            _log(h, "--go fehlgeschlagen (rc=3); die Fehlermeldung hat umstellung_17-10.py bereits gesendet")
        else:                                              # Start/Zeitueberschreitung/unbehandelter Absturz -> niemand hat gemeldet
            _log(h, f"--go endete unerwartet (rc={rc}) - sende Ausfall-Meldung")
            try:
                h.send_text(FAIL_TEXT)
            except Exception as e:
                _log(h, f"Ausfall-Meldung nicht zustellbar: {type(e).__name__}")
        return RC_FAIL
    _log(h, "Umstellung erfolgreich - beende")
    return RC_OK


def default_hooks():
    h = Hooks()
    h.now = lambda: datetime.now(TZ)
    py = os.path.join(HERE, "Prototyp", "venv", "Scripts", "python.exe")
    script = os.path.join(HERE, "umstellung_17-10.py")

    def run_umstellung(mode):
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        env = dict(os.environ); env["PYTHONIOENCODING"] = "utf-8"
        try:
            r = subprocess.run([py, script, mode], capture_output=True, text=True, encoding="utf-8", errors="replace",
                               timeout=3 * 3600, creationflags=flags, env=env)
        except Exception as e:
            _log(h, f"{mode}: Prozessfehler {type(e).__name__}")
            return 99
        if mode == "--dry-run":                       # --go schreibt sein eigenes Protokoll
            for ln in (r.stdout or "").splitlines():
                _log(h, "  dry-run | " + ln)
        return r.returncode
    h.run_umstellung = run_umstellung

    def send_text(text):
        import importlib.util
        spec = importlib.util.spec_from_file_location("umstellung_17_10", script)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        mod.default_send_text(mod.Cfg(), text)
    h.send_text = send_text
    return h


def main(argv=None):
    argparse.ArgumentParser(description=__doc__.split("\n")[0]).parse_args(argv)
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    return run(default_hooks())


if __name__ == "__main__":
    sys.exit(main())
