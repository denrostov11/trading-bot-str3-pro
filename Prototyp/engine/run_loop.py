# -*- coding: utf-8 -*-
"""Dauer-Loop des Paper-Laufs (Neustart-Lauf ab 17.10.2026; fruehere Stufen/Zwei-Monats-Test nutzen dieselbe Datei).

- Zeitplan (A5): ein voller Zyklus 90 s nach JEDEM 4h-Schluss (00/04/08/12/16/20 UTC), dazwischen stuendlich
  die Trade-Verfolgung. Nach Standby/Ausfall wird sofort aufgeholt (Kerze fuer Kerze, ohne Look-ahead).
- Unveraenderliches START_MANIFEST (Start, code_version, config_hash, Universum, Varianten); unbefristet
  mit --neustart. Wiederaufnahme aus dem Manifest nach jedem Neustart.
- Gruppe "STR3 System": KEINE Zyklus-, Start-, Herzschlag- oder Stopp-Meldungen mehr. Nur Ausfall- und
  Erholungsmeldungen (engine/outage.py: 3 Zyklusfehler in Folge, keine Daten fuer alle Instrumente,
  >2 h ohne erfolgreichen Zyklus).
- Kontrollierter Stopp ohne Datenverlust: Datei `STOP` im Runtime-Ordner anlegen.
- KEINE echten Orders. Telegram nur Ausgabe. Die lokale DB ist die verbindliche Quelle.
"""
import os, sys, io, json, time, hashlib, traceback, threading
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROTO = os.path.dirname(_HERE)
# pythonw (unsichtbar) hat kein stdout -> in Logdatei schreiben
if sys.stdout is None or not hasattr(sys.stdout, "buffer"):
    _log = open(os.path.join(_PROTO, "run_loop_log.txt"), "a", encoding="utf-8", buffering=1)
    sys.stdout = _log; sys.stderr = _log
sys.path.insert(0, _PROTO)

from engine import run_paper, run_reports
from engine.instruments import classify
from notify.live import TelegramService

TZ = ZoneInfo("Europe/Berlin")
DETECT_WORKERS = 6            # Prozesse fuer die parallele Linien-Erkennung (A5)
CODE_VERSION = "engine-2.0"   # Neustart 17.10.2026: Pro.1/Pro.3/C+, schnelle Zyklen, ruhige System-Gruppe

# STUFE-1-Universum (~24 repraesentative Symbole)
STUFE1_SYMS = [
    ("Bitcoin","BTC-USD"),("Ethereum","ETH-USD"),("Solana","SOL-USD"),("XRP","XRP-USD"),
    ("Dogecoin","DOGE-USD"),("Cardano","ADA-USD"),("Chainlink","LINK-USD"),("Litecoin","LTC-USD"),
    ("Gold","GC=F"),("Silber","SI=F"),("Platin","PL=F"),("WTI","CL=F"),("Brent","BZ=F"),
    ("Erdgas","NG=F"),("Kupfer","HG=F"),("Mais","ZC=F"),("Weizen","ZW=F"),("Kaffee","KC=F"),
    ("EUR/USD","EURUSD=X"),("USD/JPY","JPY=X"),("GBP/USD","GBPUSD=X"),
    ("DAX","^GDAXI"),("Apple","AAPL"),("Nvidia","NVDA"),
]
ACTIVE_VARIANTS = list(run_paper.ACTIVE_VARIANTS)

# Wird von run() je Stufe gesetzt (STUFE 1 = 24 Symbole; sonst volles Universum ~94).
ACTIVE_SYMS = list(STUFE1_SYMS)


def _stufe2_syms():
    from engine.instruments import load_universe
    return [(x["name"], x["symbol"]) for x in load_universe()]


def _add_months(dt, months):
    """Kalendergenaues Monatsaddieren (2 Kalendermonate = z. B. 17.08.->17.10.). Bei kuerzerem
    Zielmonat wird auf den letzten gueltigen Tag geklemmt (z. B. 31.12.+2M -> 28./29.02.)."""
    import calendar
    m = dt.month - 1 + months
    y = dt.year + m // 12
    m = m % 12 + 1
    d = min(dt.day, calendar.monthrange(y, m)[1])
    return dt.replace(year=y, month=m, day=d)


def _universe():
    return [dict(name=n, symbol=s, **classify(s)) for n, s in ACTIVE_SYMS]


def _config_hash(cfg):
    raw = json.dumps(cfg, sort_keys=True, default=str)
    return "C" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:15]


def _read_last_boundary(base):
    try:
        d = json.load(open(os.path.join(base, "cycle_state.json"), encoding="utf-8"))
        return datetime.fromisoformat(d["last_full_boundary"])
    except Exception:
        return None


def _read_passes(base):
    try:
        return int(json.load(open(os.path.join(base, "cycle_state.json"), encoding="utf-8")).get("passes", 1))
    except Exception:
        return 1


def _next_event(base):
    """Naechster Zyklus bzw. naechste Vorwarnung. Die Einstellungen werden bei JEDEM Aufruf neu gelesen."""
    from engine import scheduler as SCH, live_settings, prewarn
    st = live_settings.load()
    pw = st["prewarn"]
    minutes, done = (), ()
    if pw.get("enabled", True):
        minutes = pw["minutes_before"]
        done = prewarn.done_minutes(base, prewarn.upcoming_boundary(datetime.now(timezone.utc)))
    return SCH.next_run(datetime.now(timezone.utc), _read_last_boundary(base), st["cycle"]["close_delay_s"],
                        _read_passes(base), minutes, done)


def _run_prewarn(base, minute, pool):
    from engine import prewarn, live_settings, fastscan
    st = live_settings.load()
    svc = TelegramService(ACTIVE_VARIANTS)
    t0 = time.time()
    out = prewarn.run_prewarn(_universe(), base, datetime.now(timezone.utc), minute, st, svc=svc, pool=pool)
    print(f"[{datetime.now(TZ)}] Vorwarnung {minute} min: geprueft={out['checked']} moeglicher_bruch={out['flagged']} "
          f"gesendet={out['sent']} nachtruhe={out['quiet']} dauer={round(time.time() - t0, 1)}s")


def _resolve_prewarn(base):
    from engine import prewarn, live_settings
    svc = TelegramService(ACTIVE_VARIANTS)
    n = prewarn.resolve(base, datetime.now(timezone.utc), svc=svc, settings=live_settings.load())
    if n:
        print(f"[{datetime.now(TZ)}] Vorwarnungs-Aufloesungen gesendet: {n}")


def _priority_symbols(base):
    """Instrumente mit moeglichem Signal (Vorwarnung 'Moeglicher Bruch') zuerst pruefen."""
    try:
        from engine import prewarn
        return [x["symbol"] for x in prewarn.current_flagged(base)]
    except Exception:
        return []


_OUTAGE_LOCK = threading.Lock()


def _outage_sender(base):
    """Ausfall-/Erholungsmeldung an die Gruppe STR3 System (kurz, einmalig je Ausfall).
    Sendet DIREKT (ohne die gemeinsame Zustell-Queue-Datei): Watchdog-Thread und Zyklus teilen sich sonst dieselbe
    notify_queue.json mit je eigenem Speicherabbild (verlorene/doppelte Eintraege). Idempotenz sichert der Zustand in
    outage_state.json (eine Meldung je Ausfall). Nicht zustellbare Meldungen bleiben in `outage_outbox.json` und werden vom
    Watchdog (send.flush, alle 30 s) wiederholt, bis sie zugestellt sind - Reihenfolge bleibt erhalten."""
    outbox_path = os.path.join(base, "outage_outbox.json")

    def _load():
        try:
            return list(json.load(open(outbox_path, encoding="utf-8")))
        except Exception:
            return []

    def _save(items):
        try:
            tmp = outbox_path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(items, f)
            os.replace(tmp, outbox_path)
        except Exception:
            pass

    def _deliver(text, attempts):
        """True = zugestellt (oder Telegram bewusst aus). TransportError ist bereits redigiert."""
        try:
            from notify.live import read_env
            from notify.config import load_and_validate
            from notify.transport import RealTelegramTransport
            cfg, _ = load_and_validate(read_env(), ACTIVE_VARIANTS)
            target = cfg.system_target()
            if not cfg.enabled or not target:
                return True
            tr = RealTelegramTransport(cfg.token)
            for attempt in range(attempts):
                try:
                    tr.send_text(target, "STR3 System – Bot-Status\n" + text)
                    return True
                except Exception:
                    if attempt + 1 < attempts:
                        time.sleep(5 * (attempt + 1))
            return False
        except Exception as e:
            print("Ausfall-Meldung-Fehler:", type(e).__name__)
            return False

    def send(kind, text, period):
        with _OUTAGE_LOCK:
            items = _load()
            if items or not _deliver(text, 3):               # ältere offene Meldungen zuerst (Reihenfolge)
                items.append({"text": text, "period": period})
                _save(items)

    def flush():
        with _OUTAGE_LOCK:
            items = _load()
            if not items:
                return 0
            sent = 0
            while items and _deliver(items[0]["text"], 1):
                items.pop(0)
                sent += 1
            _save(items)
            return sent
    send.flush = flush
    return send


def run(stage="STUFE 1", official_start=None, stage_days=3, base_dir=None, syms=None, unlimited=False,
        fast=True):
    global ACTIVE_SYMS
    if syms is not None:
        ACTIVE_SYMS = list(syms)
    base = base_dir or os.path.join(_PROTO, "paper_runtime_stufe1")
    os.makedirs(base, exist_ok=True)
    stop_file = os.path.join(base, "STOP")
    manifest_path = os.path.join(base, "START_MANIFEST.json")
    now = datetime.now(TZ)

    # Einzelinstanz-Sperre: verhindert, dass Autostart + manuelles Starten zwei Loops auf denselben
    # Dateien laufen lassen (Race/Doppel-Telegram). OS-Lock -> beim Prozessende automatisch frei.
    try:
        import msvcrt
        _lock = open(os.path.join(base, "run_loop.lock"), "w")
        try:
            msvcrt.locking(_lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print(f"[{now}] run_loop laeuft bereits (Sperre aktiv) - zweite Instanz beendet sich.")
            return
    except ImportError:
        _lock = None                     # Nicht-Windows: keine Sperre

    resume = False
    man_stage_end = None
    if os.path.exists(manifest_path):
        # Neustart-Wiederaufnahme: Fenster aus dem unveraenderlichen Manifest lesen (nicht verschieben!)
        try:
            man = json.load(open(manifest_path, encoding="utf-8"))
            official_start = datetime.fromisoformat(man["start_local"])
            stage = man.get("stage", stage)
            man_stage_end = man.get("stage_end_local")   # festes Ende aus dem Manifest (kein Drift bei Resume)
            unlimited = bool(man.get("unlimited", unlimited))
            resume = True
            print(f"[{now}] Wiederaufnahme aus Manifest: Start {official_start}, Stufe {stage}.")
        except Exception:
            print("Manifest unlesbar - Neuberechnung."); resume = False
    if official_start is None:
        official_start = now.replace(hour=21, minute=0, second=0, microsecond=0)
    print(f"[{now}] run_loop bereit. Offizieller Start: {official_start} ({stage}).")

    # Bis zum offiziellen Start warten (Vorlauf)
    while datetime.now(TZ) < official_start:
        if os.path.exists(stop_file):
            print("STOP vor Start erkannt - beende."); return
        time.sleep(min(60, (official_start - datetime.now(TZ)).total_seconds()))

    start_ts = datetime.now(TZ)
    stage_end = None
    if not unlimited:
        stage_end = datetime.fromisoformat(man_stage_end) if (resume and man_stage_end) \
            else official_start + timedelta(days=stage_days)
    cfg = {"stage": stage, "start_local": official_start.isoformat(),
           "start_utc": official_start.astimezone(ZoneInfo("UTC")).isoformat(),
           "stage_end_local": stage_end.isoformat() if stage_end else None, "unlimited": bool(unlimited),
           "code_version": CODE_VERSION,
           "universe": [s for _, s in ACTIVE_SYMS], "active_variants": ACTIVE_VARIANTS,
           "cycle": "4h-Schluss + 90 s (voll), stuendlich Trade-Verfolgung", "report_timezone": "Europe/Berlin",
           "real_orders": False, "telegram": "nur Ausgabe", "percent_only": True}
    cfg["config_hash"] = _config_hash(cfg)
    if not os.path.exists(manifest_path):        # bei Wiederaufnahme NICHT ueberschreiben
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1, ensure_ascii=False)
    print(f"[{start_ts}] {stage} {'WIEDERAUFGENOMMEN' if resume else 'OFFIZIELL GESTARTET'}. Manifest: {manifest_path}")

    from engine import scheduler as SCH, outage as OUT, live_settings, fastscan
    outage_send = _outage_sender(base)
    outage = OUT.OutageMonitor(os.path.join(base, "outage_state.json"), outage_send)
    stop_wd = threading.Event()

    def watchdog():
        while not stop_wd.wait(30):
            try:
                outage.tick()
                outage_send.flush()                   # nicht zugestellte Ausfall-/Erholungsmeldungen erneut versuchen
            except Exception:
                pass
    threading.Thread(target=watchdog, daemon=True, name="outage-watchdog").start()

    pool = fastscan.DetectPool(max_workers=DETECT_WORKERS) if fast else None
    cycle_n = 0
    try:
        while True:
            if os.path.exists(stop_file):
                print(f"[{datetime.now(TZ)}] STOP erkannt - beende {stage} kontrolliert.")
                return
            if stage_end is not None and datetime.now(TZ) >= stage_end:
                print(f"[{datetime.now(TZ)}] Stufen-Endzeit erreicht - {stage} abgeschlossen.")
                return
            when, kind = _next_event(base)
            # in kurzen Schritten warten: STOP bleibt reaktionsfaehig, Aufwachen aus Standby faellt sofort auf
            while datetime.now(timezone.utc) < when and not os.path.exists(stop_file):
                time.sleep(min(15.0, max(0.5, (when - datetime.now(timezone.utc)).total_seconds())))
                w2, k2 = _next_event(base)                   # Einstellungen/Zeitplan bei jedem Schritt neu bewerten
                if w2 < when or (k2 == SCH.FULL and kind != SCH.FULL):
                    when, kind = w2, k2
            if os.path.exists(stop_file):
                continue
            if kind.startswith(SCH.PREWARN):                 # Vorwarnung (nur Information, B1)
                try:
                    _run_prewarn(base, int(kind.split(":")[1]), pool)
                except Exception:
                    print(f"[{datetime.now(TZ)}] VORWARNUNG-FEHLER:\n" + traceback.format_exc())
                    try:
                        from engine import prewarn as _pw
                        _pw.mark_done(base, datetime.now(timezone.utc), int(kind.split(":")[1]))
                    except Exception:
                        time.sleep(30)
                continue
            cycle_n += 1
            try:
                mon = run_paper.run_once(universe=_universe(), base_dir=base, telegram=True, mode=kind,
                                         priority_symbols=_priority_symbols(base), fast=fast, pool=pool,
                                         config_params={"code_version": CODE_VERSION,
                                                        "config_hash": cfg["config_hash"]})
                outage.cycle_result(mon=mon)
                try:
                    _resolve_prewarn(base)                 # Aufloesung nach JEDEM Zyklus (Fristen unabhaengig vom vollen Zyklus)
                except Exception:
                    print(f"[{datetime.now(TZ)}] VORWARNUNG-AUFLOESUNG-FEHLER:\n" + traceback.format_exc())
                print(f"[{datetime.now(TZ)}] Zyklus {cycle_n} ({kind}): "
                      f"trig={mon.get('accepted')} open={mon.get('opened')} close={mon.get('closed')} "
                      f"err={mon.get('errors')} nodata={mon.get('no_data')} tg={mon.get('telegram')} "
                      f"dauer={mon.get('duration_s')}s erste_meldung_nach={mon.get('first_alert_latency_s')}s")
            except Exception:
                print(f"[{datetime.now(TZ)}] ZYKLUSFEHLER:\n" + traceback.format_exc())
                outage.cycle_result(exception=True)
                time.sleep(60)
    finally:
        stop_wd.set()
        if pool is not None:
            pool.shutdown()


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="nur ein Zyklus testen, kein Warten/Loop")
    ap.add_argument("--stage-days", type=int, default=3)
    ap.add_argument("--start-now", action="store_true",
                    help="offizieller Start = jetzt (kein Warten auf 21:00; nur beim Erststart wirksam)")
    ap.add_argument("--stage2", action="store_true",
                    help="STUFE 2: volles Universum (~94), eigenes Runtime-Verzeichnis, 7 Tage default")
    ap.add_argument("--zwei-monate", action="store_true", dest="zwei_monate",
                    help="ZWEI-MONATS-TEST (alter Lauf, paper_runtime_2monate): Wiederaufnahme aus dem Manifest")
    ap.add_argument("--neustart", action="store_true",
                    help="NEUSTART-LAUF ab 17.10.2026: Pro.1/Pro.3/C+, volles Universum (94), UNBEFRISTET, "
                         "Runtime paper_runtime_neustart, neustart-fest (Manifest)")
    ap.add_argument("--no-fast", action="store_true", help="sequentieller Abruf/Erkennung (wie frueher)")
    args = ap.parse_args()
    fast = not args.no_fast
    if args.neustart:
        base = os.path.join(_PROTO, "paper_runtime_neustart")
        ACTIVE_SYMS = _stufe2_syms()
        start = datetime.now(TZ) if args.start_now or not os.path.exists(os.path.join(base, "START_MANIFEST.json")) \
            else None
        run(stage="NEUSTART", official_start=start, stage_days=0, base_dir=base, syms=ACTIVE_SYMS,
            unlimited=True, fast=fast)
    elif args.zwei_monate:
        base = os.path.join(_PROTO, "paper_runtime_2monate")
        ACTIVE_SYMS = _stufe2_syms()
        now0 = datetime.now(TZ)
        start = now0.replace(hour=12, minute=0, second=0, microsecond=0)   # nur relevant ohne Manifest
        end = _add_months(start, 2)                                        # 2 Kalendermonate
        days = (end - start).days
        run(stage="ZWEI-MONATS-TEST", official_start=start, stage_days=days, base_dir=base,
            syms=ACTIVE_SYMS, fast=False)
    elif args.stage2:
        base = os.path.join(_PROTO, "paper_runtime_stufe2")
        ACTIVE_SYMS = _stufe2_syms()
        if args.once:
            os.makedirs(base, exist_ok=True)
            m = run_paper.run_once(universe=_universe(), base_dir=base, telegram=True)
            print("STUFE2 TEST-ZYKLUS:", json.dumps({k: m[k] for k in ("instruments","no_trigger",
                  "opened","closed","errors","telegram")}, ensure_ascii=False))
        else:
            start = datetime.now(TZ) if args.start_now else None
            days = args.stage_days if args.stage_days != 3 else 7
            run(stage="STUFE 2", official_start=start, stage_days=days, base_dir=base, syms=ACTIVE_SYMS,
                fast=fast)
    elif args.once:
        base = os.path.join(_PROTO, "paper_runtime_stufe1")
        os.makedirs(base, exist_ok=True)
        m = run_paper.run_once(universe=_universe(), base_dir=base, telegram=True)
        print("TEST-ZYKLUS:", json.dumps({k: m[k] for k in ("instruments","no_trigger","opened",
              "closed","errors","telegram")}, ensure_ascii=False))
    else:
        start = datetime.now(TZ) if args.start_now else None
        run(stage="STUFE 1", official_start=start, stage_days=args.stage_days, fast=fast)
