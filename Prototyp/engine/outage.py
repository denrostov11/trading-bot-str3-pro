# -*- coding: utf-8 -*-
"""Ausfall-Meldungen fuer die Gruppe "STR3 System" (A3a) - kurz, nur wenn ein Eingriff noetig ist.

Ausloeser:
- "errors"  : 3 Zyklen in Folge ohne Erfolg (Ausnahme oder keine Daten fuer alle Instrumente)
- "no_data" : in zwei Zyklen in Folge keine Daten fuer ALLE Instrumente
- "stall"   : kein erfolgreicher Zyklus seit mehr als 2 Stunden (Prozess haengt) - Wecker-/Standby-sicher
- "process_missing": Prozess ganz weg (vom Bericht-Listener erkannt, siehe listener_check)

Pro Ausfall genau EINE Meldung (Zustand `outage_state.json` im Laufzeitordner); nach der Erholung genau
eine Meldung "laeuft wieder". Telegram-Fehler aendern nie etwas am Bot-Zustand (send wird abgesichert).
"""
import json, os, time
from datetime import datetime, timezone

STALL_SECONDS = 2 * 3600
ERRORS_IN_ROW = 3
WAKE_GAP_SECONDS = 300          # groessere Luecke zwischen zwei Watchdog-Ticks = PC war im Standby


def _atomic(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def load_state(path):
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f)
        d.setdefault("active", {})
        return d
    except (OSError, ValueError):
        return {"active": {}}


def _fmt(ts):
    try:
        from zoneinfo import ZoneInfo
        return datetime.fromtimestamp(ts, ZoneInfo("Europe/Berlin")).strftime("%d.%m. %H:%M")
    except Exception:
        return str(ts)


REASON = {
    "errors": "3 Zyklen in Folge fehlgeschlagen",
    "no_data": "keine Kursdaten für alle Instrumente",
    "stall": "seit über 2 Stunden kein erfolgreicher Zyklus (Prozess hängt?)",
    "process_missing": "Bot-Prozess läuft nicht mehr",
}


class OutageMonitor:
    def __init__(self, state_path, send, clock=None, stall_seconds=STALL_SECONDS):
        """send(kind, text, period) -> beliebig; wird in try/except aufgerufen."""
        self.path, self.send = state_path, send
        self.clock = clock or time.time
        self.stall = stall_seconds
        self.fail_streak = 0
        self.nodata_streak = 0
        self.last_success = self.clock()
        self._last_tick = self.clock()
        self.state = load_state(state_path)

    # ---- intern ----
    def _save(self):
        try:
            _atomic(self.path, self.state)
        except Exception:
            pass

    def _raise(self, kind):
        if self.state["active"]:
            return False                              # pro Ausfall nur EINE Meldung
        now = self.clock()
        self.state["active"] = {kind: now}
        self.state["since"] = now
        self._save()
        text = f"⚠ Bot-Ausfall seit {_fmt(now)}: {REASON.get(kind, kind)}. Eingriff nötig (PC/Netz/Bot prüfen)."
        try:
            self.send(kind, text, f"outage:{int(now)}")
        except Exception:
            pass
        return True

    def _recover(self):
        if not self.state["active"]:
            return False
        since = self.state.get("since", self.clock())
        self.state = {"active": {}}
        self._save()
        text = f"✅ Bot läuft wieder ({_fmt(self.clock())}). Ausfall seit {_fmt(since)}."
        try:
            self.send("recovered", text, f"recover:{int(self.clock())}")
        except Exception:
            pass
        return True

    # ---- Ereignisse aus dem Lauf ----
    def cycle_result(self, mon=None, exception=None):
        """Nach jedem Zyklus aufrufen. mon = Monitoring-dict von run_once, exception = abgefangene Ausnahme."""
        if exception is not None:
            self.fail_streak += 1
            self.nodata_streak = 0
        else:
            m = mon or {}
            n = m.get("instruments", 0) or 0
            nd = (m.get("no_data", 0) or 0) + (m.get("fetch_failed", 0) or 0)
            bad = nd + (m.get("errors", 0) or 0)           # Instrumente ohne verwertbaren Abruf/mit Fehler
            if n == 0 or (n < 5 and bad >= n):
                # leere/ganz kleine Verfolgungsrunde: der Prozess lebt (Stall-Frist), liefert aber KEINEN Beleg dafuer, dass
                # Daten wieder fliessen -> weder Ausfall noch Erholung
                self.last_success = self.clock()
                return
            if bad >= n:                                    # alle Instrumente fehlgeschlagen (Daten/Fehler)
                self.fail_streak += 1
                self.nodata_streak = self.nodata_streak + 1 if nd >= n else 0
            else:
                self.fail_streak = 0
                self.nodata_streak = 0
                self.last_success = self.clock()
                self._recover()
                return
        if self.nodata_streak >= 2:
            self._raise("no_data")
        elif self.fail_streak >= ERRORS_IN_ROW:
            self._raise("errors")

    def tick(self):
        """Watchdog (alle ~30 s aus einem Thread). Erkennt Haenger (>2 h ohne Erfolg); ein Standby des PCs
        (grosse Luecke zwischen zwei Ticks) setzt die Frist neu, damit das Aufholen nach dem Aufwachen
        keinen Fehlalarm ausloest."""
        now = self.clock()
        if now - self._last_tick > WAKE_GAP_SECONDS:
            self.last_success = now
        self._last_tick = now
        if now - self.last_success > self.stall:
            self._raise("stall")


# ---------------------------------------------------------------- Bericht-Listener: Prozess ganz weg
class ProcessWatch:
    """Wird vom Bericht-Listener regelmaessig aufgerufen. Meldet genau einmal, wenn der Lauf-Prozess ueber
    mehrere Pruefungen hinweg fehlt UND last_cycle_monitor.json des neuen Laufs veraltet ist. Nach einem
    Standby/Neustart des PCs gilt eine Karenzzeit (der Autostart braucht einen Moment)."""
    def __init__(self, runtime_dir, alive_fn, send, clock=None, checks_needed=3, check_interval=180,
                 grace_seconds=600, stale_seconds=1800):
        self.rt, self.alive, self.send = runtime_dir, alive_fn, send
        self.clock = clock or time.time
        self.need, self.interval, self.grace, self.stale = checks_needed, check_interval, grace_seconds, stale_seconds
        self.start = self.clock()
        self._last_check = 0.0
        self._last_call = self.clock()
        self.missing = 0
        self.reported = False
        self.path = os.path.join(runtime_dir, "outage_state.json")

    def _monitor_age(self):
        try:
            with open(os.path.join(self.rt, "last_cycle_monitor.json"), encoding="utf-8") as f:
                end = json.load(f)["end"]
            return self.clock() - datetime.fromisoformat(end).timestamp()
        except Exception:
            return None

    def poll(self):
        now = self.clock()
        if now - self._last_call > WAKE_GAP_SECONDS:      # PC war im Standby -> Karenzzeit neu starten
            self.start = now
            self.missing = 0
        self._last_call = now
        if now - self.start < self.grace or now - self._last_check < self.interval:
            return None
        self._last_check = now
        alive = self.alive()
        age = self._monitor_age()
        if alive is None or alive is True:
            self.missing = 0
            self.reported = False
            return None
        if os.path.exists(os.path.join(self.rt, "STOP")):
            return None                                   # bewusst gestoppt (STOP-Datei) -> kein Ausfall
        if age is not None and age < self.stale:
            self.missing = 0                              # Zyklus war gerade erst -> evtl. Neustart laeuft
            return None
        self.missing += 1
        if self.missing < self.need:
            return None
        st = load_state(self.path)
        if st["active"] or self.reported:
            return None                                   # bereits gemeldet
        st["active"] = {"process_missing": now}
        st["since"] = now
        self.reported = True
        try:
            _atomic(self.path, st)
        except Exception:
            pass
        try:
            self.send("process_missing", f"⚠ Bot-Ausfall seit {_fmt(now)}: {REASON['process_missing']}. "
                                         f"Eingriff nötig (PC/Netz/Bot prüfen).", f"outage:{int(now)}")
        except Exception:
            pass
        return "process_missing"
