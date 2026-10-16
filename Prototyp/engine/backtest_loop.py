# -*- coding: utf-8 -*-
"""Checkpoint-fester Backtest-Runner (Etappe E): rechnet eine Warteschlange von Universen
mehrtaegig im Hintergrund ab.

- Je Universum ein Lauf-Verzeichnis; je Symbol ISOLIERTE Ergebnisdateien (ledger/trades/state)
  -> ein abgestuerztes Symbol wird beim naechsten Start sauber neu gerechnet, ohne andere zu
  beeintraechtigen. Fertige Symbole werden per done.json uebersprungen (Neustart-/reboot-fest).
- PC muss zum Rechnen AN sein (Backtest = reine Rechenlast); bei Aus/Neustart macht der Runner
  automatisch dort weiter, wo er war. Einzelinstanz-Sperre gegen Doppelstart.
- Nach Abschluss eines Universums: Merge aller Symbol-Ergebnisse -> TEST_END + Berichte/Export
  (backtest_report.build_universe_reports) in den Ausgabe-Wurzelordner.
- Reine Simulation; keine echten Orders. Die Warteschlange (backtest_config.json) wird nach jedem
  Universum neu gelesen -> weitere Universen koennen waehrend des Laufs angehaengt werden.
"""
import os, sys, json, hashlib, traceback
from datetime import datetime, timezone
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_PROTO = os.path.dirname(_HERE)
if sys.stdout is None or not hasattr(sys.stdout, "buffer"):     # pythonw hat kein stdout
    _log = open(os.path.join(_PROTO, "backtest_loop_log.txt"), "a", encoding="utf-8", buffering=1)
    sys.stdout = _log; sys.stderr = _log
sys.path.insert(0, _PROTO)

from engine import backtest_data as BD, backtest_run as BR, backtest_report as BRP, aggregate_4h
from engine.instruments import classify
from engine.ledger import Ledger
from engine.tracker import PaperTradeStore, PaperTrade
from engine.varstate import StateRegistry

BASE = os.path.join(_PROTO, "backtest_runtime")


def _p(msg):
    print(f"[{datetime.now(timezone.utc).isoformat()}] {msg}", flush=True)


def _atomic_json(path, obj):
    """Schreibt JSON atomar (Temp-Datei + os.replace). Ein Abbruch waehrend des Schreibens kann
    den bestehenden Checkpoint dadurch nicht mehr zerstoeren."""
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def _load_json(path, default):
    if not os.path.exists(path):
        return default
    with open(path, encoding="utf-8") as f:
        return json.load(f)


# Ein voruebergehender Download-Fehler (z. B. Yahoo-Sperre wegen zu vieler Anfragen) darf ein Symbol
# NICHT endgueltig als "ohne Daten" abhaken. Am 09.08.2026 sind so 456 Symbole in 12 s verloren gegangen.
NO_DATA_MAX_DAYS = 3      # erst nach Fehlversuchen an so vielen VERSCHIEDENEN Tagen endgueltig quarantaenisiert
NO_DATA_BREAKER = 10      # so viele Symbole IN FOLGE ohne Daten -> Datenquelle gestoert, Lauf pausieren
NO_DATA_FILE = "no_data_attempts.json"


class _Paused:
    """Ergebnis "pausiert" (Datenquelle gestoert). Bewusst falsy, damit es nie als "fertig" gilt."""
    def __bool__(self):
        return False

    def __repr__(self):
        return "PAUSED"


PAUSED = _Paused()


def _today():
    return datetime.now(timezone.utc).date().isoformat()


def _register_no_data(attempts, symbol):
    """Merkt sich die Kalendertage mit Fehlversuch. True = endgueltig ohne Daten (Quarantaene)."""
    rec = attempts.get(symbol) or {"days": []}
    today = _today()
    if today not in rec["days"]:
        rec["days"].append(today)
    attempts[symbol] = rec
    return len(rec["days"]) >= NO_DATA_MAX_DAYS


IDENTITY_FILE = "run_identity.json"
_IDENTITY_KEYS = ("start", "end", "variants", "be_map", "code_version", "config_hash")


class RunIdentityMismatch(RuntimeError):
    """Checkpoints eines Lauf-Verzeichnisses passen nicht zur aktuellen Konfiguration."""


def _run_identity(cfg):
    # JSON-Rundreise normalisiert Typen (Tupel/Listen), damit der Vergleich stabil ist
    return json.loads(json.dumps({k: cfg.get(k) for k in _IDENTITY_KEYS}, sort_keys=True, default=str))


def _identity_matches(run_dir, cfg):
    p = os.path.join(run_dir, IDENTITY_FILE)
    return os.path.exists(p) and _load_json(p, {}) == _run_identity(cfg)


def _check_run_identity(run_dir, cfg):
    """Bindet die Checkpoints eines Lauf-Verzeichnisses an die Konfiguration, mit der sie entstanden.

    Ohne diese Pruefung wuerden nach einer Aenderung von Zeitraum, Varianten, BE-Modus oder
    code_version die bereits fertigen Symbole mit ALTEN Einstellungen weiterverwendet und mit neu
    gerechneten gemischt - der Bericht truege trotzdem den neuen config_hash."""
    want = _run_identity(cfg)
    p = os.path.join(run_dir, IDENTITY_FILE)
    if os.path.exists(p):
        have = _load_json(p, {})
        if have != want:
            diff = sorted(k for k in _IDENTITY_KEYS if have.get(k) != want.get(k))
            raise RunIdentityMismatch(
                f"{run_dir}: Checkpoints stammen aus einer anderen Konfiguration (abweichend: "
                f"{', '.join(diff)}). Fuer neue Einstellungen einen neuen Universums-Namen oder ein "
                f"neues Laufzeit-Verzeichnis verwenden.")
        return
    done = _load_json(os.path.join(run_dir, "done.json"), [])
    if done:
        raise RunIdentityMismatch(
            f"{run_dir}: {len(done)} fertige Symbole ohne Lauf-Identitaet - Herkunft unklar, "
            f"werden nicht wiederverwendet.")
    _atomic_json(p, want)


def _process_symbol(inst, cfg, sym_dir, frozen_dir, dl_1h=None, dl_1d=None, detect_fn=None):
    os.makedirs(sym_dir, exist_ok=True)
    for fn in ("ledger.json", "trades.json", "state.json"):     # Re-run = sauberer Neustart
        pth = os.path.join(sym_dir, fn)
        if os.path.exists(pth):
            os.remove(pth)
    lg = Ledger(os.path.join(sym_dir, "ledger.json"))
    store = PaperTradeStore(os.path.join(sym_dir, "trades.json"))
    state = StateRegistry(os.path.join(sym_dir, "state.json"))
    frozen = BD.fetch_and_freeze(inst["symbol"], frozen_dir, dl_1h=dl_1h, dl_1d=dl_1d)
    cp = {"code_version": cfg["code_version"], "config_hash": cfg["config_hash"]}
    return BR.run_symbol(inst["name"], inst["symbol"], inst["asset_class"], inst["is_futures"],
                         cfg["variants"], frozen.get("1h"), frozen.get("1d"), cfg["start"],
                         cfg["end"], lg, store, state, cfg["be_map"], inst["anchor_hour"],
                         inst["session_hours"], cp, None, detect_fn)


def _merge(run_dir, symbols):
    lg = Ledger(os.path.join(run_dir, "ledger_merged.json"))
    store = PaperTradeStore(os.path.join(run_dir, "trades_merged.json"))
    lg.candidates, lg.variant_evals, store.trades = [], [], []
    for sym in symbols:
        sd = os.path.join(run_dir, "symbols", BD.safe_name(sym))
        lp, tp = os.path.join(sd, "ledger.json"), os.path.join(sd, "trades.json")
        if os.path.exists(lp):
            d = json.load(open(lp, encoding="utf-8"))
            lg.candidates += d.get("candidates", []); lg.variant_evals += d.get("variant_evals", [])
        if os.path.exists(tp):
            for row in json.load(open(tp, encoding="utf-8")):
                store.trades.append(PaperTrade(**row))
    lg._save(); store._save()
    return lg, store


def _compat_by_symbol(symbols, frozen_dir, end):
    out = {}
    for sym in symbols:
        p = os.path.join(frozen_dir, BD.safe_name(sym) + "_1h.csv")
        if not os.path.exists(p):
            continue
        h1 = pd.read_csv(p); h1["Time"] = pd.to_datetime(h1["Time"], utc=True)
        agg = aggregate_4h.aggregate(h1, anchor_hour=0, session_hours=None,
                                     data_cutoff=pd.Timestamp(end, tz="UTC"))
        fin = aggregate_4h.final_only(agg).reset_index(drop=True)
        out[sym] = fin[["Time", "Open", "High", "Low", "Close", "Volume"]].reset_index(drop=True)
    return out


def process_universe(u, cfg, base_dir, frozen_dir, out_root, dl_1h=None, dl_1d=None, detect_fn=None):
    name = u["name"]
    symbols = [(x[0], x[1]) for x in u["symbols"]]
    insts = [dict(name=n, symbol=s, **classify(s)) for n, s in symbols]
    run_dir = os.path.join(base_dir, "run_" + name)
    os.makedirs(os.path.join(run_dir, "symbols"), exist_ok=True)
    _check_run_identity(run_dir, cfg)
    done_path = os.path.join(run_dir, "done.json")
    done = set(_load_json(done_path, []))
    attempts_path = os.path.join(run_dir, NO_DATA_FILE)
    attempts = _load_json(attempts_path, {})
    failed = []
    no_data_streak = 0
    for i, inst in enumerate(insts):
        if inst["symbol"] in done:
            continue
        try:
            sd = os.path.join(run_dir, "symbols", BD.safe_name(inst["symbol"]))
            s = _process_symbol(inst, cfg, sd, frozen_dir, dl_1h, dl_1d, detect_fn)
            _p(f"{name} {i + 1}/{len(insts)} {inst['symbol']}: {s.get('status')} "
               f"acc={s.get('accepted')} opened={s.get('opened')} bars={s.get('window_bars')}")
        except Exception:
            _p(f"{name} {inst['symbol']} FEHLER:\n" + traceback.format_exc())
            failed.append(inst["symbol"])
            continue
        if s.get("status") == "NO_DATA_QUARANTINE":
            # JEDES NO_DATA zaehlt zur Serie - auch eines am 3. Fehltag. Sonst wuerde eine mehrtaegige
            # Sperre am 3. Tag doch wieder hunderte Symbole endgueltig aufgeben (Ursprungsfehler, verzoegert).
            no_data_streak += 1
            final = _register_no_data(attempts, inst["symbol"])
            _atomic_json(attempts_path, attempts)
            if no_data_streak >= NO_DATA_BREAKER:
                _p(f"{name}: {no_data_streak} Symbole in Folge ohne Daten - Datenquelle vermutlich "
                   f"gesperrt/gestoert. Lauf pausiert.")
                return PAUSED
            if not final:
                failed.append(inst["symbol"])        # offen lassen -> an einem spaeteren Tag erneut
                continue
            _p(f"{name} {inst['symbol']}: an {NO_DATA_MAX_DAYS} Tagen ohne Daten - endgueltig quarantaenisiert.")
        else:
            no_data_streak = 0
        done.add(inst["symbol"])
        _atomic_json(done_path, sorted(done))
    if failed:
        # Ein gescheitertes Symbol darf weder (teilweise) in den Bericht einfliessen noch das
        # Universum als fertig markieren - sonst wuerde es nie wieder versucht.
        _p(f"{name}: {len(failed)} Symbol(e) fehlgeschlagen ({', '.join(failed[:10])}"
           f"{' ...' if len(failed) > 10 else ''}) - Universum bleibt OFFEN, kein Bericht.")
        return False
    allsyms = [s for _, s in symbols]
    lg, store = _merge(run_dir, allsyms)
    cbs = _compat_by_symbol(allsyms, frozen_dir, cfg["end"])
    manifest = {"run_id": f"{name}_{cfg['config_hash']}", "window": [cfg["start"], cfg["end"]],
                "universe": name, "n_symbols": len(allsyms), "code_version": cfg["code_version"],
                "config_hash": cfg["config_hash"], "timezone": "Europe/Berlin", "seed": 0,
                "generated": datetime.now(timezone.utc).isoformat(),
                "annahmen": "4h-Intrabar-Naeherung (Stop zuerst); Session genaehert; R:R diagnostisch; "
                            "reine R/%-Auswertung ohne Kapitalkonto"}
    BRP.build_universe_reports(out_root, name, lg, store, cfg["variants"], cfg["start"], cfg["end"],
                               manifest, compat_by_symbol=cbs)
    _p(f"BERICHT fertig: {name} -> {os.path.join(out_root, name)} "
       f"(Trades: {len(store.trades)}, Kandidaten: {len(lg.candidates)})")
    return True


def run(config_path=None):
    os.makedirs(BASE, exist_ok=True)
    try:                                                        # Einzelinstanz-Sperre
        import msvcrt
        _lk = open(os.path.join(BASE, "backtest.lock"), "w")
        try:
            msvcrt.locking(_lk.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            _p("Backtest-Runner laeuft bereits (Sperre) - zweite Instanz beendet sich."); return
    except ImportError:
        pass
    config_path = config_path or os.path.join(BASE, "backtest_config.json")
    ud_path = os.path.join(BASE, "universes_done.json")
    _p("Backtest-Runner gestartet.")
    while True:
        cfg = _load_json(config_path, None)
        frozen_dir = cfg.get("frozen_dir", os.path.join(BASE, "frozen"))
        out_root = cfg["out_root"]
        cfg["config_hash"] = cfg.get("config_hash") or _cfg_hash(cfg)
        ud = set(_load_json(ud_path, []))
        # fertig = abgeschlossen UND mit genau dieser Konfiguration gerechnet
        pending = [u for u in cfg["queue"]
                   if not (u["name"] in ud
                           and _identity_matches(os.path.join(BASE, "run_" + u["name"]), cfg))]
        if not pending:
            _p("Alle Universen der Warteschlange fertig. Runner beendet."); return
        u = pending[0]
        _p(f"Starte Universum {u['name']} ({len(u['symbols'])} Symbole).")
        try:
            ok = process_universe(u, cfg, BASE, frozen_dir, out_root)
            if ok is False:                 # gewoehnlicher Fehler: genau ein zweiter Versuch
                _p(f"{u['name']}: zweiter Versuch fuer gescheiterte Symbole.")
                ok = process_universe(u, cfg, BASE, frozen_dir, out_root)
        except RunIdentityMismatch as e:
            _p(f"ABBRUCH {u['name']}: {e}")
            return
        if ok is PAUSED:                    # Datenquelle gestoert: KEIN Sofort-Neuversuch
            _p(f"Runner pausiert: Datenquelle fuer {u['name']} gestoert - neuer Versuch beim naechsten Start.")
            return
        if not ok:
            _p(f"Runner beendet: {u['name']} unvollstaendig - neuer Versuch beim naechsten Start.")
            return
        ud.add(u["name"]); _atomic_json(ud_path, sorted(ud))


def _cfg_hash(cfg):
    core = {k: cfg[k] for k in ("start", "end", "variants", "be_map", "code_version") if k in cfg}
    return "C" + hashlib.sha1(json.dumps(core, sort_keys=True, default=str).encode()).hexdigest()[:15]


if __name__ == "__main__":
    run()
