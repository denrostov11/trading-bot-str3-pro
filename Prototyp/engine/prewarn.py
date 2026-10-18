# -*- coding: utf-8 -*-
"""Vorwarnungen 30 und 15 Minuten vor dem 4h-Schluss (B1) - REIN INFORMATIV, kein Einstieg, kein Trade-Zustand.

Pruefung: dieselbe Erkennung wie beim echten Trigger, aber auf den abgeschlossenen 4h-Kerzen PLUS der noch
laufenden Kerze (Schlusskurs = aktueller Kurs). Liegt der Kurs gerade jenseits der Action Line (und existiert eine
gueltige Safety Line), kommt die Meldung "Moeglicher Bruch, Kerze schliesst um ..., aktuell ... ueber/unter der
Linie" in die jeweilige Varianten-Gruppe (Pro.1, Pro.3, C+; per Einstellung aenderbar). Nach dem Schluss folgt
IMMER eine Aufloesung: "bestaetigt" oder "nicht bestaetigt".

Einstellungen (live_settings.json, bei jedem Durchlauf neu gelesen): an/aus, Zeitpunkte, Nachtruhe 23:00-07:00
(keine Vorwarnungen, auch keine Aufloesungen dazu), Gruppen. Vorwarnungen veraendern NIE die Strategiebewertung:
sie schreiben weder ins Ledger noch in die Trades, nur in prewarn_state.json (und die Telegram-Queue).
"""
import json, os
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pandas as pd

from . import aggregate_4h, orchestrate, fastscan
from .varstate import StateRegistry

TZ = ZoneInfo("Europe/Berlin")
COLS = ["Time", "Open", "High", "Low", "Close", "Volume"]
RESOLVE_DEADLINE = timedelta(minutes=45)       # spaeteste Aufloesung nach dem Schluss


# ------------------------------------------------------------------ Hilfen
def _utc(ts):
    t = pd.Timestamp(ts)
    return t.tz_localize("UTC") if t.tzinfo is None else t.tz_convert("UTC")


def in_quiet(now, quiet_cfg):
    """True, wenn `now` in der Nachtruhe liegt (lokale Zeit Europe/Berlin; Fenster darf ueber Mitternacht gehen)."""
    if not quiet_cfg or not quiet_cfg.get("enabled", True):
        return False
    loc = _utc(now).tz_convert(TZ)
    cur = loc.hour * 60 + loc.minute

    def mins(s):
        h, m = str(s).split(":")
        return int(h) * 60 + int(m)
    try:
        a, b = mins(quiet_cfg.get("from", "23:00")), mins(quiet_cfg.get("to", "07:00"))
    except Exception:
        a, b = 23 * 60, 7 * 60
    return (cur >= a or cur < b) if a > b else (a <= cur < b)


def upcoming_boundary(now):
    """Naechster 4h-Schluss (UTC) nach `now`."""
    n = _utc(now)
    return n.floor("4h") + pd.Timedelta(hours=4)


def partial_compat(df1h, anchor_hour, session_hours, now, boundary):
    """Abgeschlossene 4h-Kerzen + die laufende Kerze (endet am `boundary`) als letzte Zeile. None, wenn die laufende
    Kerze keine Daten hat (z. B. Markt zu) oder nicht zum erwarteten Schluss gehoert."""
    agg = aggregate_4h.aggregate(df1h, anchor_hour=anchor_hour, session_hours=session_hours, data_cutoff=now)
    if agg.empty:
        return None
    fin = agg[agg["is_final"]]
    run = agg[~agg["is_final"]]
    if run.empty:
        return None
    last = run.iloc[-1]
    if pd.Timestamp(last["end_utc"]) != pd.Timestamp(boundary):
        return None
    comp = pd.concat([fin[COLS], run.tail(1)[COLS]], ignore_index=True)
    if len(fin) < orchestrate.MIN_FINAL_BARS:
        return None
    return comp.reset_index(drop=True)


def action_sig_of(action):
    return f"{action.kind}:{round(action.p0, 6)}:{round((action.p1 - action.p0) / (action.i1 - action.i0), 8)}"


def warn_text(symbol, direction, boundary, price, line_value, atr, minute, sid):
    from notify.trade_text import fde, fprice
    above = price > line_value
    dist = abs(price - line_value)
    extra = ""
    if sid == "Str.3 Pro.3":
        extra = "\nHinweis: Der Volumenfilter dieser Variante wird erst zum Kerzenschluss geprüft."
    return (f"Möglicher Bruch ({minute} Min. vor Schluss) – nur Vorwarnung, kein Einstieg\n"
            f"{symbol}: Richtung {'LONG' if direction == 'LONG' else 'SHORT'} möglich\n"
            f"Kerze schließt um {fde(boundary, False)} (deutsche Zeit)\n"
            f"Aktuell {fprice(price)} – {fprice(dist)} ({dist / atr:.2f} ATR) {'über' if above else 'unter'} der Linie "
            f"({fprice(line_value)})." + extra)


def merge_in_memory(cache, sym, df):
    """Wie BarCache.merge, aber OHNE Schreiben: Die Vorwarnung sieht die noch laufende Stunde, der Cache darf sie nicht
    erhalten (sonst koennte eine unfertige 1h-Kerze spaeter als abgeschlossen gelten)."""
    new = cache._normalize(df)
    old = cache.load(sym, "1h")
    comb = pd.concat([old, new], ignore_index=True) if old is not None and len(old) else new
    return (comb.dropna(subset=["Time"]).drop_duplicates(subset=["Time"], keep="last")
            .sort_values("Time").reset_index(drop=True))


# ------------------------------------------------------------------ Zustand
def _load(path):
    try:
        return json.load(open(path, encoding="utf-8"))
    except Exception:
        return {}


def _save(path, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, indent=1)
    os.replace(tmp, path)


def state_path(base):
    return os.path.join(base, "prewarn_state.json")


def done_minutes(base, boundary):
    st = _load(state_path(base))
    if st.get("boundary") == pd.Timestamp(boundary).isoformat():
        return set(st.get("done_minutes", []))
    return set()


# ------------------------------------------------------------------ Lauf
SENT_OK_NOT = ("DISABLED", "WARNING")        # Rueckgabewerte von TelegramService.send, die KEINE Zustellung bedeuten
EXPIRE_AFTER = timedelta(hours=24)           # unaufloesbare Eintraege werden nach 24 h ohne Aufloesung verworfen


def _delivered(r):
    return r not in SENT_OK_NOT and r is not None


def _fresh_state(b_iso, old):
    """Neuer Zustand fuer einen neuen 4h-Schluss; noch nicht aufgeloeste Vorwarnungen frueherer Schluesse BLEIBEN erhalten."""
    keep = [w for w in (old or {}).get("warnings", []) if not w.get("done")]
    return {"boundary": b_iso, "done_minutes": [], "warnings": keep}


def _norm_state(st):
    """Altes Format ('flagged'/'resolved') -> neues Format ('warnings')."""
    if "warnings" in st:
        return st
    ws = []
    for f in st.get("flagged", []):
        key = f"{f.get('symbol')}:{f.get('direction')}"
        w = {**f, "boundary": st.get("boundary"), "resolved_groups": [], "done": key in set(st.get("resolved", []))}
        ws.append(w)
    return {"boundary": st.get("boundary"), "done_minutes": st.get("done_minutes", []), "warnings": ws}


def current_flagged(base):
    """Warnungen des aktuellen/zuletzt geprueften 4h-Schlusses (fuer die Reihenfolge im vollen Zyklus)."""
    st = _norm_state(_load(state_path(base)))
    return [w for w in st.get("warnings", []) if w.get("boundary") == st.get("boundary")]


def run_prewarn(universe, base_dir, now, minute, settings, svc=None, downloader=None, throttle=None, pool=None,
                workers=4, log=None, detect_fn=None):
    """Ein Vorwarnungs-Durchgang `minute` Minuten vor dem naechsten 4h-Schluss. Gibt dict mit Zaehlern zurueck.
    Ein Fehler hier darf nie den Lauf stoeren (der Aufrufer faengt Ausnahmen ab)."""
    log = log if log is not None else []
    now = _utc(now)
    boundary = upcoming_boundary(now)
    pcfg = settings["prewarn"]
    sp = state_path(base_dir)
    st = _norm_state(_load(sp))
    b_iso = boundary.isoformat()
    if st.get("boundary") != b_iso:
        st = _fresh_state(b_iso, st)
    out = {"boundary": b_iso, "minute": minute, "checked": 0, "flagged": 0, "sent": 0, "quiet": False}
    if minute in st["done_minutes"]:
        return out
    quiet = in_quiet(now, pcfg.get("night_quiet"))
    out["quiet"] = quiet

    from .cache import BarCache
    cache = BarCache(os.path.join(base_dir, "data_cache"))
    reg = StateRegistry(os.path.join(base_dir, "state.json"))
    throttle = throttle or fastscan.Throttle()
    period_for = lambda s: fastscan.period_days_for(cache, s, now)
    dl = downloader or fastscan.default_downloader_factory(period_for)
    by_sym = {i["symbol"]: i for i in universe}
    frames, jobs = {}, {}
    for sym, df, err in fastscan.fetch_many([i["symbol"] for i in universe], dl, throttle, workers=workers):
        if df is None:
            continue
        inst = by_sym[sym]
        try:
            m = merge_in_memory(cache, sym, df)          # Zwischenabrufe mit unfertigen Kerzen NIE in den Cache schreiben
            comp = partial_compat(m, inst["anchor_hour"], inst["session_hours"], now.to_pydatetime(), boundary)
            if comp is None:
                continue
            lb = int(pcfg.get("lookback_bars", 0) or 0)
            if lb and len(comp) > lb:
                comp = comp.tail(lb).reset_index(drop=True)
            frames[sym] = comp
            out["checked"] += 1
            jobs[sym] = pool.submit(comp) if pool is not None else None
        except Exception as e:
            log.append(f"Vorwarnung {sym}: {type(e).__name__}")
    detect = detect_fn or orchestrate.default_detector
    flagged = []
    for sym, comp in frames.items():
        try:
            det = None
            fut = jobs.get(sym)
            if fut is not None:
                try:
                    det = fut.result(timeout=600)
                except Exception:
                    det = detect(comp)
            else:
                det = detect(comp)
            if not det or det.get("no_safety"):
                continue
            n = det["n"]
            if det["action"].breaking_bar != n - 1:
                continue
            price = float(comp["Close"].iloc[-1])
            line_v = float(det["action"].value_at(n - 1))
            flagged.append({"symbol": sym, "direction": det["direction"], "price": price, "line": line_v,
                            "atr": float(det["atr_last"]), "action_sig": action_sig_of(det["action"]),
                            "candle_start": pd.Timestamp(comp["Time"].iloc[-1]).isoformat()})
        except Exception as e:
            log.append(f"Vorwarnung {sym}: {type(e).__name__}")
    out["flagged"] = len(flagged)

    by_key = {(w["boundary"], w["symbol"], w["direction"]): w for w in st["warnings"]}
    for f in flagged:
        k = (b_iso, f["symbol"], f["direction"])
        if k not in by_key:
            w = {**f, "boundary": b_iso, "minutes": [], "sent_groups": [], "resolved_groups": [], "done": False}
            st["warnings"].append(w)
            by_key[k] = w
        else:
            by_key[k].update({kk: f[kk] for kk in ("price", "line", "atr", "action_sig")})
    if svc is not None and getattr(svc, "enabled", False) and pcfg.get("enabled", True) and not quiet:
        from notify import messages as M
        for f in flagged:
            rec = by_key[(b_iso, f["symbol"], f["direction"])]
            for sid in pcfg.get("groups", []):
                ok, _ = reg.get(sid).can_open(f["symbol"], f["action_sig"], now.timestamp())
                if not ok:
                    continue                              # diese Variante koennte gar nicht einsteigen
                body = warn_text(f["symbol"], f["direction"], boundary, f["price"], f["line"], f["atr"], minute, sid)
                m = M.Message(sid, "v1", M.PREWARN, symbol=f["symbol"], signal_id=f"PW:{b_iso}:{f['symbol']}:{f['direction']}",
                              body=body, title=f"{sid} – Vorwarnung")
                try:
                    r = svc.send(m, period=f"pw{minute}")
                    if _delivered(r):
                        out["sent"] += 1
                        if sid not in rec["sent_groups"]:
                            rec["sent_groups"].append(sid)
                except Exception as e:
                    log.append(f"Vorwarnung senden {f['symbol']}: {type(e).__name__}")
            if minute not in rec["minutes"]:
                rec["minutes"].append(minute)
    st["done_minutes"] = sorted(set(st["done_minutes"]) | {minute}, reverse=True)
    _save(sp, st)
    return out


def resolve(base_dir, now, svc=None, settings=None, log=None, ledger=None, watermark=None):
    """Aufloesung der Vorwarnungen ALLER bereits abgelaufenen 4h-Schluesse: 'bestaetigt' / 'nicht bestaetigt'.
    Nur fuer Vorwarnungen, die tatsaechlich gesendet wurden. Wartet auf die Bewertung der Kerze (Wasserstand);
    spaetestens 45 min nach dem Schluss wird als 'nicht bestaetigt' aufgeloest. Ein Eintrag gilt erst als erledigt, wenn
    die Aufloesung JE Gruppe erfolgreich eingereiht wurde (sonst Wiederholung beim naechsten Aufruf, bis 24 h nach Schluss)."""
    log = log if log is not None else []
    sp = state_path(base_dir)
    st = _norm_state(_load(sp))
    if not st.get("warnings"):
        return 0
    now = _utc(now)
    from .ledger import Ledger
    ledger = ledger or Ledger(os.path.join(base_dir, "ledger.json"))
    if watermark is None:
        watermark = _load(os.path.join(base_dir, "processed.json"))
    cand_by = {}
    for c in ledger.candidates:
        cand_by[(c["symbol"], pd.Timestamp(c["signal_time"]).isoformat())] = c
    n_sent = 0
    changed = False
    for f in st["warnings"]:
        if f.get("done"):
            continue
        boundary = _utc(f["boundary"])
        if now < boundary:
            continue
        if not f.get("sent_groups"):
            f["done"] = True                                  # nie gesendet (z. B. Nachtruhe) -> keine Aufloesung noetig
            changed = True
            continue
        if now - boundary >= EXPIRE_AFTER:
            f["done"] = True; f["expired"] = True; changed = True
            continue
        cs = _utc(f["candle_start"])
        wm = watermark.get(f["symbol"])
        evaluated = bool(wm) and _utc(wm) >= cs
        overdue = now - boundary >= RESOLVE_DEADLINE
        if not evaluated and not overdue:
            continue
        c = cand_by.get((f["symbol"], pd.Timestamp(cs).isoformat()))
        confirmed = bool(c) and c.get("direction") == f["direction"]
        if confirmed:
            if c["status"] == "ACCEPTED_PROVISIONAL":
                txt = "bestätigt – die Kerze hat die Linie durchbrochen, Signal erkannt (Trade wird gemeldet)."
            else:
                txt = f"bestätigt, aber abgelehnt ({c.get('rejection_reason') or c['status']})."
        else:
            txt = ("nicht bestätigt – die Kerze hat nicht jenseits der Linie geschlossen." if evaluated
                   else "nicht bestätigt – keine Bestätigung bis 45 Minuten nach Schluss (Daten verspätet).")
        if svc is None or not getattr(svc, "enabled", False):
            continue                                          # Telegram aus -> spaeter erneut versuchen (nicht als erledigt markieren)
        from notify import messages as M
        key = f"{f['symbol']}:{f['direction']}"
        for sid in f["sent_groups"]:
            if sid in f.setdefault("resolved_groups", []):
                continue
            body = f"{f['symbol']} ({f['direction']}): Vorwarnung von {boundary.tz_convert(TZ).strftime('%H:%M')} Uhr {txt}"
            m = M.Message(sid, "v1", M.PREWARN_RESOLVED, symbol=f["symbol"],
                          signal_id=f"PWR:{f['boundary']}:{key}", body=body, title=f"{sid} – Auflösung Vorwarnung")
            try:
                r = svc.send(m, period="resolve")
                if _delivered(r):
                    f["resolved_groups"].append(sid)
                    n_sent += 1
                    changed = True
            except Exception as e:
                log.append(f"Aufloesung senden {f['symbol']}: {type(e).__name__}")
        if all(g in f["resolved_groups"] for g in f["sent_groups"]):
            f["done"] = True
            changed = True
    if changed:
        _save(sp, st)
    return n_sent


def mark_done(base_dir, now, minute):
    """Markiert einen Durchgang als erledigt (auch nach Fehler), damit er nicht in Dauerschleife wiederholt wird."""
    sp = state_path(base_dir)
    b_iso = upcoming_boundary(now).isoformat()
    st = _norm_state(_load(sp))
    if st.get("boundary") != b_iso:
        st = _fresh_state(b_iso, st)
    st["done_minutes"] = sorted(set(st.get("done_minutes", [])) | {int(minute)}, reverse=True)
    _save(sp, st)
