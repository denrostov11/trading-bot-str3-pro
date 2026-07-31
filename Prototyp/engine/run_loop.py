# -*- coding: utf-8 -*-
"""Dauer-Loop fuer den gestuften Probebetrieb (STUFE 1) und spaeter den Zwei-Monats-Test.

- Wartet bis zum offiziellen Startzeitpunkt (Europe/Berlin), schreibt dann ein UNVERAENDERLICHES
  Startmanifest (Stufe, Start/Ende, code_version, config_hash, Universum, Sicherheitsbestaetigungen),
  sendet eine Paper-Trading-Startmeldung an System- + Vergleichsgruppe.
- Danach: alle CYCLE_SECONDS ein Zyklus (run_paper.run_once telegram=True). Trade-Alerts gehen live;
  System-Monitor nur bei Aktivitaet/Fehlern. Heartbeat alle 12 h.
- Robust: ein Zyklusfehler stoppt den Loop nie (Log + System-Alert). Neustart-fest (Zustaende auf Platte).
- Kontrollierter Stopp ohne Datenverlust: Datei `STOP` im Runtime-Ordner anlegen -> Loop beendet sauber.
- KEINE echten Orders. Telegram nur Ausgabe. Die lokale DB ist die verbindliche Quelle.
"""
import os, sys, io, json, time, hashlib, traceback
from datetime import datetime, timedelta
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
CYCLE_SECONDS = 3600          # ein Zyklus je Stunde (4h-Kerzen schliessen alle 4 h)
HEARTBEAT_SECONDS = 12 * 3600
CODE_VERSION = "engine-1.2"

# STUFE-1-Universum (~24 repraesentative Symbole)
STUFE1_SYMS = [
    ("Bitcoin","BTC-USD"),("Ethereum","ETH-USD"),("Solana","SOL-USD"),("XRP","XRP-USD"),
    ("Dogecoin","DOGE-USD"),("Cardano","ADA-USD"),("Chainlink","LINK-USD"),("Litecoin","LTC-USD"),
    ("Gold","GC=F"),("Silber","SI=F"),("Platin","PL=F"),("WTI","CL=F"),("Brent","BZ=F"),
    ("Erdgas","NG=F"),("Kupfer","HG=F"),("Mais","ZC=F"),("Weizen","ZW=F"),("Kaffee","KC=F"),
    ("EUR/USD","EURUSD=X"),("USD/JPY","JPY=X"),("GBP/USD","GBPUSD=X"),
    ("DAX","^GDAXI"),("Apple","AAPL"),("Nvidia","NVDA"),
]
ACTIVE_VARIANTS = [f"Str.3 Pro.{i}" for i in range(1, 9)]


def _universe():
    return [dict(name=n, symbol=s, **classify(s)) for n, s in STUFE1_SYMS]


def _config_hash(cfg):
    raw = json.dumps(cfg, sort_keys=True, default=str)
    return "C" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:15]


def run(stage="STUFE 1", official_start=None, stage_days=3, base_dir=None):
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
    if os.path.exists(manifest_path):
        # Neustart-Wiederaufnahme: Fenster aus dem unveraenderlichen Manifest lesen (nicht verschieben!)
        try:
            man = json.load(open(manifest_path, encoding="utf-8"))
            official_start = datetime.fromisoformat(man["start_local"])
            stage = man.get("stage", stage)
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
    stage_end = official_start + timedelta(days=stage_days)
    cfg = {"stage": stage, "start_local": official_start.isoformat(),
           "start_utc": official_start.astimezone(ZoneInfo("UTC")).isoformat(),
           "stage_end_local": stage_end.isoformat(), "code_version": CODE_VERSION,
           "universe": [s for _, s in STUFE1_SYMS], "active_variants": ACTIVE_VARIANTS,
           "cycle_seconds": CYCLE_SECONDS, "report_timezone": "Europe/Berlin",
           "real_orders": False, "telegram": "nur Ausgabe", "percent_only": True}
    cfg["config_hash"] = _config_hash(cfg)
    if not os.path.exists(manifest_path):        # bei Wiederaufnahme NICHT ueberschreiben
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=1, ensure_ascii=False)
    print(f"[{start_ts}] {stage} {'WIEDERAUFGENOMMEN' if resume else 'OFFIZIELL GESTARTET'}. Manifest: {manifest_path}")

    # Startmeldung an System + Vergleich (nur beim ersten Start, nicht bei Wiederaufnahme)
    try:
        svc = TelegramService(ACTIVE_VARIANTS)
        if svc.enabled and not resume:
            msg = (f"🟢 {stage} GESTARTET (Paper-Trading, keine echte Order)\n"
                   f"Start: {official_start.strftime('%d.%m.%Y %H:%M')} Europe/Berlin\n"
                   f"Stufe-Ende geplant: {stage_end.strftime('%d.%m.%Y %H:%M')}\n"
                   f"Instrumente: {len(STUFE1_SYMS)} · Varianten: Pro.1–8\n"
                   f"code_version {CODE_VERSION} · config_hash {cfg['config_hash']}\n"
                   f"Telegram nur Ausgabe. Lokale DB ist verbindliche Quelle.")
            svc.system(msg)
            from notify import messages as M
            svc.send(M.Message("Str.3 Pro.1", "v1", M.STRATEGY_STATUS, is_comparison=True, body=msg),
                     period=f"start:{stage}")
    except Exception:
        print("Startmeldung-Fehler:\n" + traceback.format_exc())

    last_heartbeat = time.time()
    cycle_n = 0
    while True:
        if os.path.exists(stop_file):
            print(f"[{datetime.now(TZ)}] STOP erkannt - beende {stage} kontrolliert.")
            _try_system(f"🔴 {stage} kontrolliert gestoppt um "
                        f"{datetime.now(TZ).strftime('%d.%m.%Y %H:%M')}. Zustaende gesichert.")
            return
        if datetime.now(TZ) >= stage_end:
            print(f"[{datetime.now(TZ)}] Stufen-Endzeit erreicht - {stage} abgeschlossen.")
            _try_system(f"✅ {stage} abgeschlossen ({stage_days} Tage). Bereit fuer Auswertung/nächste Stufe.")
            return
        cycle_n += 1
        try:
            mon = run_paper.run_once(universe=_universe(), base_dir=base, telegram=True,
                                     config_params={"code_version": CODE_VERSION,
                                                    "config_hash": cfg["config_hash"]})
            print(f"[{datetime.now(TZ)}] Zyklus {cycle_n}: "
                  f"trig={mon.get('accepted')} open={mon.get('opened')} close={mon.get('closed')} "
                  f"err={mon.get('errors')} tg={mon.get('telegram')}")
        except Exception:
            print(f"[{datetime.now(TZ)}] ZYKLUSFEHLER:\n" + traceback.format_exc())
            _try_system(f"⚠️ {stage}: Zyklusfehler abgefangen (Loop laeuft weiter).")
        if time.time() - last_heartbeat >= HEARTBEAT_SECONDS:
            _try_system(f"💓 {stage} laeuft. {datetime.now(TZ).strftime('%d.%m %H:%M')}. Keine echten Orders.")
            last_heartbeat = time.time()
        time.sleep(CYCLE_SECONDS)


def _try_system(text):
    try:
        svc = TelegramService(ACTIVE_VARIANTS)
        if svc.enabled:
            svc.system(text)
    except Exception:
        print("System-Meldung-Fehler:\n" + traceback.format_exc())


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true", help="nur ein Zyklus testen, kein Warten/Loop")
    ap.add_argument("--stage-days", type=int, default=3)
    ap.add_argument("--start-now", action="store_true",
                    help="offizieller Start = jetzt (kein Warten auf 21:00; nur beim Erststart wirksam)")
    args = ap.parse_args()
    if args.once:
        base = os.path.join(_PROTO, "paper_runtime_stufe1")
        os.makedirs(base, exist_ok=True)
        m = run_paper.run_once(universe=_universe(), base_dir=base, telegram=True)
        print("TEST-ZYKLUS:", json.dumps({k: m[k] for k in ("instruments","no_trigger","opened",
              "closed","errors","telegram")}, ensure_ascii=False))
    else:
        start = datetime.now(TZ) if args.start_now else None
        run(stage="STUFE 1", official_start=start, stage_days=args.stage_days)
