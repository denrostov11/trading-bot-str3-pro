# -*- coding: utf-8 -*-
"""Bericht-Abruf per Telegram: Schreibt der Nutzer in der Gruppe "STR3 System" das Wort "bericht"
(oder /bericht, /bericht@<botname>), sendet der Bot dort eine PDF mit dem aktuellen Stand des
laufenden Zwei-Monats-Paper-Tests.

Eigener, separater Prozess (aendert nichts am Paper-Lauf):
- Long-Polling per getUpdates (Update-Offset atomar persistent -> nach Neustart nichts doppelt).
- Reagiert NUR auf den Chat STR3_SYSTEM_CHAT_ID (und, falls gesetzt, nur auf Nutzer aus
  TELEGRAM_AUTHORIZED_USER_IDS); alle anderen Chats/Nutzer werden ignoriert.
- Rate-Limit: hoechstens 1 Bericht je 60 s.
- Nur lesende Funktion: keine Handels-/Steuerbefehle, kein eval/exec/Shell, keine Pfade aus Telegram.
- Secrets (Token, Chat-IDs) kommen zur Laufzeit aus Prototyp/.env, erscheinen nie in Log/Ausgabe
  (redact). Fehler werden knapp (ohne Pfade/Geheimnisse) in die Gruppe gemeldet.

Aufruf: pythonw notify/report_listener.py            (Dauerbetrieb)
        python  notify/report_listener.py --check    (Privatsphaere-/Webhook-Diagnose, kein Versand)
        python  notify/report_listener.py --announce (einmalige Hinweisnachricht in die Gruppe)
        python  notify/report_listener.py --send-now (einmal Bericht bauen und senden, wie der Listener)
"""
import os, sys

# WICHTIG: Wird die Datei direkt gestartet, steht ihr Ordner (notify/) vorn in sys.path. Dort liegt eine
# queue.py, die das Standardmodul "queue" verdecken wuerde (urllib3/logging.handlers brechen dann ab).
_HERE = os.path.dirname(os.path.abspath(__file__))
PROTO = os.path.dirname(_HERE)
sys.path[:] = [p for p in sys.path if os.path.abspath(p or os.getcwd()) != _HERE]
if PROTO not in sys.path:
    sys.path.insert(0, PROTO)

import re, json, time, logging, traceback    # noqa: E402
from logging.handlers import RotatingFileHandler    # noqa: E402

from notify.redact import redact, safe_error          # noqa: E402

RUNTIME = os.path.join(PROTO, "report_listener_runtime")
STATE_PATH = os.path.join(RUNTIME, "state.json")
LOG_PATH = os.path.join(RUNTIME, "listener.log")
LOCK_PATH = os.path.join(RUNTIME, "listener.lock")
STOP_PATH = os.path.join(RUNTIME, "STOP")
REPORT_DIR = os.path.join(RUNTIME, "reports")
PAPER_RT = os.path.join(PROTO, "paper_runtime_2monate")
PAPER_LOG = os.path.join(PROTO, "run_loop_log.txt")

MIN_INTERVAL_S = 60
POLL_TIMEOUT_S = 50
KEEP_REPORTS = 10

log = logging.getLogger("report_listener")


# ------------------------------------------------------------------ Parsen / Filter / Rate-Limit
def normalize_text(text):
    """Kleinschreibung, Whitespace (auch geschuetzte/Zero-Width-Leerzeichen) vereinheitlicht."""
    if not text:
        return ""
    t = re.sub(r"[​‌‍﻿]", "", str(text))
    return re.sub(r"\s+", " ", t).strip().casefold()


def is_report_trigger(text, bot_username=None):
    """True fuer 'bericht' (egal ob gross/klein, mit beliebigen Leerzeichen drumherum) sowie
    '/bericht' und '/bericht@<botname>'. Ein '/bericht@anderer_bot' loest NICHT aus.
    Bei /-Befehlen zaehlt nur das erste Wort (Telegram erlaubt Argumente)."""
    t = normalize_text(text)
    if not t:
        return False
    if t == "bericht":
        return True
    if t.startswith("/"):
        first = t.split(" ", 1)[0]
        m = re.fullmatch(r"/bericht(?:@([a-z0-9_]+))?", first)
        if not m:
            return False
        target = m.group(1)
        if target is None:
            return True
        return bool(bot_username) and target == str(bot_username).lstrip("@").casefold()
    return False


def extract_message(update):
    """update-dict -> dict(update_id, chat_id, user_id, is_bot, text) oder None (keine Textnachricht)."""
    if not isinstance(update, dict) or "update_id" not in update:
        return None
    msg = update.get("message")
    if not isinstance(msg, dict):
        return {"update_id": update["update_id"], "chat_id": None, "user_id": None, "is_bot": False, "text": ""}
    chat = msg.get("chat") or {}
    frm = msg.get("from") or {}
    return {"update_id": update["update_id"],
            "chat_id": None if chat.get("id") is None else str(chat.get("id")),
            "user_id": None if frm.get("id") is None else str(frm.get("id")),
            "is_bot": bool(frm.get("is_bot")),
            "text": msg.get("text") or ""}


def chat_allowed(chat_id, system_chat_id):
    return bool(system_chat_id) and chat_id is not None and str(chat_id) == str(system_chat_id)


def user_allowed(user_id, allowed_users):
    """Leere Allowlist = kein zusaetzlicher Nutzerfilter (Chat-Filter gilt immer)."""
    if not allowed_users:
        return True
    return user_id is not None and str(user_id) in {str(u) for u in allowed_users}


def rate_check(last_ts, now, min_interval=MIN_INTERVAL_S):
    """(ok, wartesekunden). last_ts None/0 = noch nie."""
    if not last_ts:
        return True, 0
    wait = min_interval - (now - last_ts)
    return (wait <= 0), max(0, int(wait + 0.999))


# ------------------------------------------------------------------ Persistenter Zustand
class StateStore:
    """Update-Offset + Zeitpunkt des letzten Berichts, atomar gespeichert (tmp + os.replace)."""
    def __init__(self, path):
        self.path = path
        self.offset = 0
        self.last_report_ts = 0.0
        self.initialized = False
        self._load()

    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            self.offset = int(d.get("offset", 0))
            self.last_report_ts = float(d.get("last_report_ts", 0.0))
            self.initialized = bool(d.get("initialized", False))
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            log.warning("Zustandsdatei unlesbar - starte mit leerem Zustand (Backlog wird uebersprungen).")

    def save(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"offset": self.offset, "last_report_ts": self.last_report_ts,
                       "initialized": self.initialized}, f)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def advance(self, update_id):
        """Offset VOR der Bearbeitung setzen und speichern: lieber einmal nicht antworten als doppelt."""
        nxt = int(update_id) + 1
        if nxt > self.offset:
            self.offset = nxt
            self.save()


# ------------------------------------------------------------------ Listener-Logik
class Listener:
    """Kernlogik ohne Netz: Sender (send_text/send_document), Berichtserzeuger und Uhr sind injizierbar."""
    def __init__(self, state, sender, build_report, system_chat_id, allowed_users=(), bot_username=None,
                 clock=time.time, min_interval=MIN_INTERVAL_S):
        self.state, self.sender, self.build_report = state, sender, build_report
        self.system_chat_id, self.allowed_users = str(system_chat_id), set(allowed_users or ())
        self.bot_username, self.clock, self.min_interval = bot_username, clock, min_interval

    def _say(self, text):
        try:
            self.sender.send_text(self.system_chat_id, text)
        except Exception as e:                       # Telegram-Fehler darf nie den Listener stoppen
            log.warning("Antwort nicht zustellbar: %s", safe_error(e))

    def handle_update(self, update):
        """Gibt eine Statusmarke zurueck (fuer Tests/Log): ignored/not_trigger/rate_limited/sent/error."""
        m = extract_message(update)
        if m is None:
            return "ignored"
        self.state.advance(m["update_id"])
        if m["chat_id"] is None or not chat_allowed(m["chat_id"], self.system_chat_id):
            return "ignored"
        if m["is_bot"] or not user_allowed(m["user_id"], self.allowed_users):
            return "ignored"
        if not is_report_trigger(m["text"], self.bot_username):
            return "not_trigger"

        now = self.clock()
        ok, wait = rate_check(self.state.last_report_ts, now, self.min_interval)
        if not ok:
            log.info("Bericht angefordert - Rate-Limit (noch %s s)", wait)
            self._say(f"Bericht kommt gleich / bitte warten: Der letzte Bericht wurde gerade erst erstellt. "
                      f"Nächster Abruf in ca. {wait} s möglich.")
            return "rate_limited"
        self.state.last_report_ts = now
        self.state.save()
        log.info("Bericht angefordert - erstelle PDF")
        self._say("Erstelle Bericht …")
        try:
            path, caption = self.build_report()
            self.sender.send_document(self.system_chat_id, path, caption)
            log.info("Bericht gesendet (%s)", os.path.basename(path))
            return "sent"
        except Exception as e:
            log.error("Bericht fehlgeschlagen: %s\n%s", safe_error(e), redact(traceback.format_exc()))
            self._say(f"Der Bericht konnte nicht erstellt oder gesendet werden (Fehler: {type(e).__name__}). "
                      f"Details stehen im Log des Listeners. Bitte später erneut versuchen.")
            return "error"

    def process_updates(self, updates):
        results = []
        for u in sorted(updates or [], key=lambda x: x.get("update_id", 0)):
            try:
                results.append(self.handle_update(u))
            except Exception as e:
                log.error("Update-Verarbeitung fehlgeschlagen: %s", safe_error(e))
                results.append("error")
        return results


# ------------------------------------------------------------------ Telegram-API (nur lesend: getUpdates/getMe/...)
class ApiError(Exception):
    def __init__(self, msg, code=None):
        super().__init__(msg)
        self.code = code


class BotApi:
    def __init__(self, token):
        self._base = f"https://api.telegram.org/bot{token}"

    def _call(self, method, params=None, timeout=15):
        import requests
        try:
            r = requests.post(f"{self._base}/{method}", json=params or {}, timeout=timeout)
            j = r.json()
        except Exception as e:
            raise ApiError(safe_error(e))
        if not j.get("ok"):
            raise ApiError(redact(str(j.get("description"))), code=j.get("error_code"))
        return j.get("result")

    def get_me(self):
        return self._call("getMe")

    def get_updates(self, offset, timeout=POLL_TIMEOUT_S):
        return self._call("getUpdates", {"offset": offset, "timeout": timeout,
                                         "allowed_updates": ["message"]}, timeout=timeout + 15)

    def get_webhook_info(self):
        return self._call("getWebhookInfo")

    def get_chat_member(self, chat_id, user_id):
        return self._call("getChatMember", {"chat_id": chat_id, "user_id": user_id})


# ------------------------------------------------------------------ Hilfen fuer den Betrieb
def read_settings():
    """Token/System-Chat/Allowlist aus Prototyp/.env (zur Laufzeit, wie die notify-Schicht). Nie ausgeben."""
    from notify.live import read_env
    env = read_env()
    users = [u.strip() for u in (env.get("TELEGRAM_AUTHORIZED_USER_IDS") or "").split(",") if u.strip()]
    return {"token": (env.get("TELEGRAM_BOT_TOKEN") or "").strip(),
            "system_chat": (env.get("STR3_SYSTEM_CHAT_ID") or "").strip(), "users": users}


def make_report_builder(now_fn=None):
    def build():
        from notify import status_report as SR
        from datetime import datetime
        d = SR.collect(PAPER_RT, PAPER_LOG, now=now_fn() if now_fn else None)
        stamp = d["now"].strftime("%Y-%m-%d_%H%M")
        path = SR.build_pdf(d, os.path.join(REPORT_DIR, f"STR3_Zwischenstand_{stamp}.pdf"))
        _cleanup_reports()
        return path, SR.caption(d)
    return build


def _cleanup_reports(keep=KEEP_REPORTS):
    """Raeumt nur die EIGENEN Listener-PDFs auf (STR3_Zwischenstand_*.pdf)."""
    try:
        files = sorted(f for f in os.listdir(REPORT_DIR) if f.startswith("STR3_Zwischenstand_") and f.endswith(".pdf"))
        for f in files[:-keep]:
            os.remove(os.path.join(REPORT_DIR, f))
    except OSError:
        pass


class _RedactFormatter(logging.Formatter):
    def format(self, record):
        return redact(super().format(record))


def setup_logging():
    os.makedirs(RUNTIME, exist_ok=True)
    h = RotatingFileHandler(LOG_PATH, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
    h.setFormatter(_RedactFormatter("%(asctime)s %(levelname)s %(message)s"))
    log.setLevel(logging.INFO)
    log.handlers[:] = [h]


def diagnose(settings):
    """Privatsphaere-/Webhook-Diagnose (ohne Versand). Gibt dict mit Booleans/Status zurueck."""
    api = BotApi(settings["token"])
    out = {}
    me = api.get_me()
    out["bot_username"] = me.get("username")
    out["can_read_all_group_messages"] = bool(me.get("can_read_all_group_messages"))
    try:
        wh = api.get_webhook_info()
        out["webhook_gesetzt"] = bool(wh.get("url"))
        out["pending_updates"] = wh.get("pending_update_count")
    except ApiError as e:
        out["webhook_gesetzt"] = f"Fehler: {e}"
    try:
        cm = api.get_chat_member(settings["system_chat"], me.get("id"))
        out["bot_status_in_gruppe"] = cm.get("status")
    except ApiError as e:
        out["bot_status_in_gruppe"] = f"Fehler: {e}"
    return out


def run_forever(settings):
    api = BotApi(settings["token"])
    from notify.transport import RealTelegramTransport
    sender = RealTelegramTransport(settings["token"])
    state = StateStore(STATE_PATH)

    username, can_read = None, None
    try:
        me = api.get_me()
        username, can_read = me.get("username"), bool(me.get("can_read_all_group_messages"))
    except ApiError as e:
        log.warning("getMe fehlgeschlagen: %s", e)
    log.info("Listener gestartet (Bot @%s, Gruppen-Nachrichten lesbar ohne Befehl: %s)", username, can_read)
    if can_read is False:
        log.warning("Privacy-Modus aktiv: normale Texte wie 'bericht' kommen in Gruppen evtl. nicht an; "
                    "/bericht@%s funktioniert immer.", username)

    if not state.initialized:                       # Backlog beim ersten Start ueberspringen
        try:
            ups = api._call("getUpdates", {"offset": -1, "timeout": 0, "allowed_updates": ["message"]})
            if ups:
                state.offset = max(state.offset, int(ups[-1]["update_id"]) + 1)
            state.initialized = True
            state.save()
            log.info("Erststart: Backlog uebersprungen")
        except ApiError as e:
            log.warning("Initialisierung fehlgeschlagen: %s", e)

    listener = Listener(state, sender, make_report_builder(), settings["system_chat"], settings["users"], username)
    backoff = 5
    while True:
        if os.path.exists(STOP_PATH):
            log.info("STOP-Datei erkannt - beende.")
            return 0
        try:
            ups = api.get_updates(state.offset)
            backoff = 5
            if ups:
                listener.process_updates(ups)
        except ApiError as e:
            if e.code == 409:
                log.error("HTTP 409 Konflikt: ein anderer Prozess nutzt getUpdates/Webhook fuer diesen Bot. "
                          "Warte %s s.", 60)
                time.sleep(60)
            else:
                log.warning("Polling-Fehler: %s (warte %s s)", e, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, 120)
        except Exception as e:
            log.error("Unerwarteter Fehler: %s\n%s", safe_error(e), redact(traceback.format_exc()))
            time.sleep(backoff)
            backoff = min(backoff * 2, 120)


def acquire_lock():
    """Einzelinstanz (OS-Lock; wird beim Prozessende automatisch frei). None = andere Instanz laeuft."""
    os.makedirs(RUNTIME, exist_ok=True)
    f = open(LOCK_PATH, "w")
    try:
        import msvcrt
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except ImportError:
        pass
    except OSError:
        f.close()
        return None
    return f


def main(argv=None):
    argv = argv if argv is not None else sys.argv[1:]
    if sys.stdout is None or not hasattr(sys.stdout, "buffer"):    # pythonw: kein stdout
        os.makedirs(RUNTIME, exist_ok=True)
        sys.stdout = sys.stderr = open(os.path.join(RUNTIME, "stdout.txt"), "a", encoding="utf-8", buffering=1)
    setup_logging()
    try:
        settings = read_settings()
    except OSError:
        log.error("Konfiguration nicht lesbar (.env fehlt?).")
        return 2
    if not settings["token"] or not settings["system_chat"]:
        log.error("Token oder System-Chat-ID fehlt - Listener nicht startbar.")
        return 2

    if "--check" in argv:
        try:
            print(json.dumps(diagnose(settings), ensure_ascii=False, indent=1))
            return 0
        except ApiError as e:
            print("Diagnose fehlgeschlagen:", e)
            return 1
    if "--announce" in argv:
        from notify.transport import RealTelegramTransport
        RealTelegramTransport(settings["token"]).send_text(
            settings["system_chat"],
            "Bericht-Abruf ist eingerichtet – schreibe ‚bericht‘ (oder /bericht), um den aktuellen Stand als PDF zu erhalten.")
        print("Hinweisnachricht gesendet.")
        return 0

    if "--send-now" in argv:
        # Einmaliger Versand ueber denselben Pfad wie der Listener (Bericht bauen -> sendDocument).
        from notify.transport import RealTelegramTransport
        tr = RealTelegramTransport(settings["token"])
        try:
            path, cap = make_report_builder()()
            res = tr.send_document(settings["system_chat"], path, cap)
            log.info("Einmal-Bericht gesendet (%s)", os.path.basename(path))
            print(f"OK: ok={res.ok} message_id={res.message_id} datei={os.path.basename(path)}")
            return 0
        except Exception as e:
            log.error("Einmal-Bericht fehlgeschlagen: %s", safe_error(e))
            print("FEHLER:", safe_error(e))
            return 1

    lock = acquire_lock()
    if lock is None:
        log.info("Listener laeuft bereits (Sperre aktiv) - zweite Instanz beendet sich.")
        return 3
    try:
        return run_forever(settings)
    except Exception as e:
        log.error("Listener abgestuerzt: %s\n%s", safe_error(e), redact(traceback.format_exc()))
        return 1


if __name__ == "__main__":
    sys.exit(main())
