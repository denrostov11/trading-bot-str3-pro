# -*- coding: utf-8 -*-
"""Backtest-Auswertung/Export (Etappe C): TEST_END-Bewertung, Monats-/Gesamtkennzahlen,
CSV-Audit-Set und beschriftete Ordnerstruktur je Universum.

- Kennzahlen kommen aus der EINEN zentralen Schicht (reporting.variant_report/comparison) -
  keine variantenspezifischen Formeln, keine zweite Ergebnisquelle.
- Am Testende offene Trades werden per Mark-to-Market (tracker.mark_to_market, outcome=TEST_END)
  bewertet und im Bericht GETRENNT von regulaeren Exits gefuehrt.
- Monatsberichte = variant_report auf die im jeweiligen Monat GESCHLOSSENEN Trades.
Die PDF-Erzeugung setzt auf diese Daten auf (separates Modul).
"""
import os, json, copy
import pandas as pd
from datetime import datetime, timezone

from . import reporting as REP
from . import tracker as T

VARIANT_LABELS = {
    "Str.3 Pro.1": "Pro.1_Baseline",
    "Str.3 Pro.2": "Pro.2_Daily-EMA200",
    "Str.3 Pro.3": "Pro.3_RVOL",
    "Str.3 Pro.4": "Pro.4_ATR-Regime",
    "Str.3 Pro.5": "Pro.5_Kombi-EMA+RVOL+ATR",
    "Str.3 Pro.6": "Pro.6_Breakout-Qualitaet",
    "Str.3 Pro.7": "Pro.7_Trendqualitaet-diagnostisch",
    "Str.3 Pro.8": "Pro.8_nicht-konfiguriert",
}


# ---------------- TEST_END: offene Trades zum letzten Schluss bewerten ----------------
def test_end_close(store, compat_by_symbol, end_iso):
    """Schliesst am 30.06.2026 (end_iso) noch offene Trades. Gefuellte Trades -> Mark-to-Market
    (outcome=TEST_END); nie gefuellte pending_fill -> status='cancelled' (NOT_FILLED, zaehlt nicht).
    Gibt (n_test_end, n_not_filled)."""
    end = pd.Timestamp(end_iso)
    if end.tzinfo is None:
        end = end.tz_localize("UTC")
    n_te = n_nf = 0
    for t in store.trades:
        if t.status not in ("open", "pending_fill"):
            continue
        if t.status == "pending_fill" or not t.entry_time:
            t.status = "cancelled"
            t.result = {"status": "cancelled", "outcome": "NOT_FILLED"}
            n_nf += 1
            continue
        compat = compat_by_symbol.get(t.symbol)
        if compat is None or len(compat) == 0:
            continue
        times = pd.to_datetime(compat["Time"], utc=True)
        m = times <= end
        if not m.any():
            continue
        li = m[m].index[-1]
        last_close = float(compat["Close"].iloc[li])
        prev = t.result or {}
        res = T.mark_to_market(t.direction, t.asset_class, t.atr, t.entry_price, t.stop_initial,
                               t.target, last_close, be_moved=prev.get("be_moved", False),
                               mfe=prev.get("mfe_r", 0.0), mae=prev.get("mae_r", 0.0),
                               dur=prev.get("duration_bars", 0),
                               stop_final=prev.get("stop_current"))
        if res.get("error"):
            continue
        exit_ts = pd.Timestamp(compat["Time"].iloc[li])
        res["exit_time"] = exit_ts.isoformat()
        res["closed_ts"] = float(exit_ts.timestamp())
        t.status = "closed"; t.result = res
        n_te += 1
    store._save()
    return n_te, n_nf


# ---------------- Monatsaufteilung ----------------
def month_list(start, end):
    """Liste (jahr, monat) von start bis end (inklusive)."""
    s = pd.Timestamp(start); e = pd.Timestamp(end)
    out, y, m = [], s.year, s.month
    while (y, m) <= (e.year, e.month):
        out.append((y, m))
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


def trades_in_month(trades, year, month):
    """Im (jahr, monat) GESCHLOSSENE Trades (nach closed_ts)."""
    out = []
    for t in trades:
        if getattr(t, "status", None) != "closed":
            continue
        ts = (t.result or {}).get("closed_ts")
        if ts is None:
            continue
        d = datetime.fromtimestamp(ts, tz=timezone.utc)
        if d.year == year and d.month == month:
            out.append(t)
    return out


# ---------------- CSV-Audit-Set (Abschnitt 12) ----------------
def _w(df, path):
    df.to_csv(path, index=False, encoding="utf-8")


def write_csv_audit(csv_dir, ledger, store, variants, run_manifest):
    os.makedirs(csv_dir, exist_ok=True)
    # trades.csv (je Trade/Variante)
    rows = []
    for t in store.trades:
        r = t.result or {}
        rows.append({"trade_id": t.trade_id, "parent_signal_id": t.parent_signal_id,
                     "strategy_id": t.strategy_id, "break_even": t.break_even, "symbol": t.symbol,
                     "asset_class": t.asset_class, "direction": t.direction,
                     "signal_time": t.signal_time, "entry_time": t.entry_time,
                     "status": t.status, "outcome": r.get("outcome"),
                     "entry_open": r.get("entry_open"), "exit_price": r.get("exit_price"),
                     "stop_initial": r.get("stop_initial"), "target": r.get("target"),
                     "brutto_r": r.get("brutto_r"), "netto_r": r.get("netto_r"),
                     "gross_return_pct": r.get("gross_return_pct"),
                     "net_return_pct": r.get("net_return_pct"),
                     "mfe_r": r.get("mfe_r"), "mae_r": r.get("mae_r"),
                     "duration_days": r.get("duration_days"),
                     "ambiguous_intrabar": r.get("ambiguous_intrabar"),
                     "exit_time": r.get("exit_time")})
    _w(pd.DataFrame(rows), os.path.join(csv_dir, "trades.csv"))
    # signals.csv (je Varianten-Bewertung) + rejected_signals.csv
    ev = pd.DataFrame(ledger.variant_evals)
    _w(ev, os.path.join(csv_dir, "signals.csv"))
    if len(ev):
        rej = ev[ev["status"].isin(["FAIL", "NOT_EVALUABLE", "NOT_CONFIGURED"])]
    else:
        rej = ev
    _w(rej, os.path.join(csv_dir, "rejected_signals.csv"))
    # snapshots.jsonl (je Kandidat, unveraenderlicher Entscheidungszustand)
    with open(os.path.join(csv_dir, "snapshots.jsonl"), "w", encoding="utf-8") as f:
        for c in ledger.candidates:
            f.write(json.dumps(c, ensure_ascii=False, default=str) + "\n")
    # summary_by_strategy.csv (Kernkennzahlen je Variante)
    srows = []
    for sid in variants:
        rep = REP.variant_report(ledger, store.trades, sid)
        rep = {**rep}
        rep.pop("signal_counts", None); rep.pop("sizing_note", None)
        srows.append({"strategy_id": sid, **rep})
    _w(pd.DataFrame(srows), os.path.join(csv_dir, "summary_by_strategy.csv"))
    # equity_curve.csv (je Variante zeitgeordnet, kumuliert netto-R + netto-%)
    erows = []
    for sid in variants:
        cl = sorted([t for t in store.trades if t.strategy_id == sid and t.status == "closed"],
                    key=lambda t: (t.result or {}).get("closed_ts", 0))
        cum_r = cum_p = 0.0
        for t in cl:
            r = t.result or {}
            cum_r += r.get("netto_r", 0.0); cum_p += r.get("net_return_pct", 0.0)
            erows.append({"strategy_id": sid, "closed_time": r.get("exit_time"),
                          "netto_r": r.get("netto_r"), "cum_netto_r": round(cum_r, 3),
                          "net_return_pct": r.get("net_return_pct"), "cum_net_pct": round(cum_p, 4)})
    _w(pd.DataFrame(erows), os.path.join(csv_dir, "equity_curve.csv"))
    # run_manifest.json
    with open(os.path.join(csv_dir, "run_manifest.json"), "w", encoding="utf-8") as f:
        json.dump(run_manifest, f, indent=2, ensure_ascii=False, default=str)


# ---------------- Monatssicht des Ledgers + TEST_END-Aufschluesselung ----------------
TEST_END_HINWEIS = ("Die Kennzahlen dieses Berichts (Trefferquote, Erwartungswert, Ranking usw.) enthalten "
                    "auch TEST_END-Bewertungen: Positionen, die am Testende noch offen waren und zum letzten "
                    "Schlusskurs bewertet wurden. Das sind keine regulaeren Ausstiege - siehe "
                    "abschluss_aufschluesselung.")


def ledgers_by_month(ledger, months):
    """Je (jahr, monat) eine nur lesende Ledger-SICHT mit den Kandidaten, deren signal_time in diesem
    Monat liegt (UTC), und genau deren Varianten-Bewertungen. Ohne das zeigte jeder Monatsbericht die
    Signalzahlen des GESAMTEN Testzeitraums."""
    wanted = set(months)
    cand_by_m = {m: [] for m in months}
    month_of_cand = {}
    for c in ledger.candidates:
        st = c.get("signal_time")
        if not st:
            continue
        ts = pd.Timestamp(st)
        ts = ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
        key = (ts.year, ts.month)
        if key in wanted:
            cand_by_m[key].append(c)
            month_of_cand[c.get("candidate_id")] = key
    evals_by_m = {m: [] for m in months}
    for v in ledger.variant_evals:
        key = month_of_cand.get(v.get("candidate_id"))
        if key is not None:
            evals_by_m[key].append(v)
    out = {}
    for m in months:
        view = copy.copy(ledger)
        view.path = None              # nur lesend: ein versehentliches _save() scheitert laut
        view.candidates = cand_by_m[m]
        view.variant_evals = evals_by_m[m]
        out[m] = view
    return out


def abschluss_aufschluesselung(trades, strategy_id):
    """Trennt regulaere Ausstiege von TEST_END-Bewertungen. variant_report zaehlt beide als
    abgeschlossene Trades; hier werden sie getrennt ausgewiesen, damit nichts verdeckt bleibt."""
    cl = [t for t in trades if t.strategy_id == strategy_id and getattr(t, "status", None) == "closed"]

    def agg(ts):
        return {"n": len(ts),
                "netto_r": round(sum((t.result or {}).get("netto_r", 0.0) for t in ts), 3),
                "net_return_pct": round(sum((t.result or {}).get("net_return_pct", 0.0) for t in ts), 4)}

    te = [t for t in cl if (t.result or {}).get("outcome") == "TEST_END"]
    reg = [t for t in cl if (t.result or {}).get("outcome") != "TEST_END"]
    return {"regulaere_ausstiege": agg(reg), "test_end_bewertungen": agg(te), "hinweis": TEST_END_HINWEIS}


def _with_breakdown(comp, trades):
    for rep in comp.get("variants", []):
        rep["abschluss_aufschluesselung"] = abschluss_aufschluesselung(trades, rep["strategy_id"])
    comp["test_end_hinweis"] = TEST_END_HINWEIS
    return comp


# ---------------- Ordnerstruktur + Metriken je Variante ----------------
def build_universe_reports(root, universe_name, ledger, store, variants, start, end,
                           run_manifest, compat_by_symbol=None):
    """Erzeugt <root>/<universe_name>/ mit je Variante Ordner (Gesamt + Monatskennzahlen als JSON),
    _GESAMT_Vergleich/ und _CSV_Audit/. TEST_END-Bewertung vorab. Gibt das Zielverzeichnis.
    (PDF-Erzeugung baut separat auf diese JSON-/CSV-Daten auf.)"""
    if compat_by_symbol:
        te, nf = test_end_close(store, compat_by_symbol, end)
        run_manifest = {**run_manifest, "test_end_closed": te, "not_filled": nf}
    base = os.path.join(root, universe_name)
    os.makedirs(base, exist_ok=True)
    months = month_list(start, end)
    month_ledgers = ledgers_by_month(ledger, months)

    for sid in variants:
        folder = os.path.join(base, VARIANT_LABELS.get(sid, sid.replace(" ", "_")))
        os.makedirs(folder, exist_ok=True)
        overall = REP.variant_report(ledger, store.trades, sid)
        overall["abschluss_aufschluesselung"] = abschluss_aufschluesselung(store.trades, sid)
        with open(os.path.join(folder, f"{VARIANT_LABELS.get(sid, sid)}_GESAMT.json"),
                  "w", encoding="utf-8") as f:
            json.dump(overall, f, indent=2, ensure_ascii=False, default=str)
        my = [t for t in store.trades if t.strategy_id == sid]
        for (y, m) in months:
            mt = trades_in_month(my, y, m)
            rep = REP.variant_report(month_ledgers[(y, m)], mt, sid)
            rep["monat"] = f"{y}-{m:02d}"
            rep["abschluss_aufschluesselung"] = abschluss_aufschluesselung(mt, sid)
            with open(os.path.join(folder, f"Monat_{y}-{m:02d}.json"), "w", encoding="utf-8") as f:
                json.dump(rep, f, indent=2, ensure_ascii=False, default=str)

    comp_dir = os.path.join(base, "_GESAMT_Vergleich")
    os.makedirs(comp_dir, exist_ok=True)
    with open(os.path.join(comp_dir, "GESAMT_alle-Varianten.json"), "w", encoding="utf-8") as f:
        json.dump(_with_breakdown(REP.comparison(ledger, store.trades, variants), store.trades), f,
                  indent=2, ensure_ascii=False, default=str)
    for (y, m) in months:
        mt = trades_in_month(store.trades, y, m)
        with open(os.path.join(comp_dir, f"Vergleich_Monat_{y}-{m:02d}.json"),
                  "w", encoding="utf-8") as f:
            json.dump(_with_breakdown(REP.comparison(month_ledgers[(y, m)], mt, variants), mt), f,
                      indent=2, ensure_ascii=False, default=str)

    write_csv_audit(os.path.join(base, "_CSV_Audit"), ledger, store, variants, run_manifest)
    return base
