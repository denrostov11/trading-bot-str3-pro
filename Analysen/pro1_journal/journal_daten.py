# -*- coding: utf-8 -*-
"""Pro.1 Baseline - Trade-Journal: Daten, Pruefungen, CSV. (Bot-venv: python journal_daten.py)

Stichtag = Zeitpunkt des LETZTEN tatsaechlich gesendeten Zwischenberichts (Listener-Log: 12.10.2026 14:15
Europe/Berlin = 12:15 UTC). Gezaehlt werden nur Trades, deren Ausstiegskerze zum Stichtag abgeschlossen war
(Kerzenbeginn + 4 h <= Stichtag). Arbeitet NUR auf der Kopie in daten_kopie/ (kopie_erstellen.py).
Schreibt: Pro1_Baseline_Tradejournal.csv, journal_daten.json (Eingabe fuer build_journal_pdf.py).
"""
import os, sys, json, csv, random
from zoneinfo import ZoneInfo
import pandas as pd

PROTO = r"C:\Users\denro\Desktop\Claude Code\Trading_Bot\Prototyp"
sys.path.insert(0, PROTO)
from engine import aggregate_4h, tracker as T            # noqa: E402  (nur lesend genutzt)
from mtf.lines import calibrate_shift                    # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "daten_kopie")
BERLIN = ZoneInfo("Europe/Berlin")
STICHTAG_BERLIN = pd.Timestamp("2026-10-12 14:15", tz=BERLIN)
STICHTAG = STICHTAG_BERLIN.tz_convert("UTC")
REPORT_FILE = "STR3_Zwischenstand_2026-10-12_1415.pdf"       # zuletzt gesendeter Bericht (Listener-Log 14:15:33)
REPORT_EXPECT = {"closed": 65, "win": 31, "loss": 34, "open": 16, "pct": 81.9, "r": 4.01}
CLASS_DE = {"fx": "Devisen", "crypto": "Krypto", "futures": "Futures", "index": "Index", "stock": "Aktie/ETF"}
KIND_DE = {"support": "Unterstützung", "resistance": "Widerstand"}


def safe(s):
    return "".join(ch if ch.isalnum() or ch in "-_" else "_" for ch in str(s))


_fin = {}


def fin_bars(sym):
    if sym not in _fin:
        df = pd.read_csv(os.path.join(DATA, "data_cache", safe(sym) + "__1h.csv"))
        _fin[sym] = aggregate_4h.final_only(aggregate_4h.aggregate(df)).reset_index(drop=True)
    return _fin[sym]


def iso(ts):
    return pd.Timestamp(ts).tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:%S+00:00")


def locate(df, idx, price, col, tol=40):
    lo, hi = max(0, idx - tol), min(len(df) - 1, idx + tol)
    vals = df[col].values[lo:hi + 1]
    j = int((abs(vals - price)).argmin())
    return (lo + j) if abs(vals[j] - price) <= 1e-6 * max(abs(price), 1.0) else None


def anchors(t, snap):
    """Action-/Safety-Anker mit Datum (4h-Kerzenbeginn, UTC) und Kurs. Datum ueber Preis-Treffer, sonst ueber den Index."""
    f = fin_bars(t["symbol"])
    times = pd.to_datetime(f["Time"], utc=True)
    k = int(times[times == pd.Timestamp(t["signal_time"])].index[0])
    shift = calibrate_shift(snap["safety_anchor"], float(t["stop_initial"]), k)
    out = {}
    for name in ("action_anchor", "safety_anchor"):
        i0, p0, i1, p1, kind, ntaps, ang = snap[name]
        col = "Low" if kind == "support" else "High"
        pts = []
        for i, p in ((i0, p0), (i1, p1)):
            j = locate(f, i + shift, p, col)
            exact = j is not None
            if j is None:
                j = min(max(i + shift, 0), len(f) - 1)
            pts.append({"time": iso(times.iloc[j]), "price": float(p), "exact": bool(exact)})
        out[name.split("_")[0]] = {"kind": kind, "kind_de": KIND_DE[kind], "taps": int(ntaps), "angle": float(ang), "p": pts}
    return out


def main():
    allt = json.load(open(os.path.join(DATA, "trades.json"), encoding="utf-8"))
    led = json.load(open(os.path.join(DATA, "ledger.json"), encoding="utf-8"))
    cand = {c["parent_signal_id"]: c for c in led["candidates"]}
    p1 = [t for t in allt if t["strategy_id"] == "Str.3 Pro.1"]
    inc = [t for t in p1 if t["status"] == "closed" and pd.Timestamp(t["result"]["exit_time"]) + pd.Timedelta(hours=4) <= STICHTAG]
    inc.sort(key=lambda t: (t["entry_time"], t["signal_time"], t["symbol"]))
    later_closed = [t for t in p1 if t["status"] == "closed" and t not in inc]
    open_st = [t for t in p1 if t not in inc and pd.Timestamp(t["signal_time"]) + pd.Timedelta(hours=4) <= STICHTAG]
    open_st.sort(key=lambda t: (t["signal_time"], t["symbol"]))

    rows, cum, problems = [], 0.0, []
    for n, t in enumerate(inc, 1):
        r, sn = t["result"], cand[t["parent_signal_id"]]["snapshot"]
        c = cand[t["parent_signal_id"]]
        # --- Abgleich Trade <-> Ledger/Snapshot
        if abs(float(t["stop_initial"]) - sn["baseline_stop"]) > 1e-5 * abs(sn["baseline_stop"]):
            problems.append((n, t["symbol"], "stop != snapshot"))
        if sn["baseline_target"] is None or abs(float(t["target"]) - sn["baseline_target"]) > 1e-5 * abs(sn["baseline_target"]):
            problems.append((n, t["symbol"], "ziel != snapshot"))
        if t["signal_time"] != c["signal_time"] or t["direction"] != c["direction"]:
            problems.append((n, t["symbol"], "signal/richtung != ledger"))
        E, X, S = r["entry_open"], r["exit_price"], r["stop_initial"]
        long = t["direction"] == "LONG"
        move = (X - E) if long else (E - X)
        risk = abs(E - S)
        # --- Nachrechnung der Kennzahlen
        gross = move / E * 100
        if abs(gross - r["gross_return_pct"]) > 0.002:
            problems.append((n, t["symbol"], f"brutto-% {gross:.4f} != {r['gross_return_pct']}"))
        if abs(r["gross_return_pct"] - r["fees_pct"] - r["slippage_pct"] - r["net_return_pct"]) > 0.0006:
            problems.append((n, t["symbol"], "netto != brutto - kosten"))
        brutto_r = move / risk
        if abs(brutto_r - r["brutto_r"]) > 0.002:
            problems.append((n, t["symbol"], f"brutto-R {brutto_r:.3f} != {r['brutto_r']}"))
        a = float(t["atr"])
        cost = 2 * 0.05 * a + T.cost_fraction(t["asset_class"]) * (abs(E) + abs(X))
        if abs((brutto_r - cost / risk) - r["netto_r"]) > 0.003:
            problems.append((n, t["symbol"], "netto-R Nachrechnung"))
        cum += r["net_return_pct"]
        rows.append({
            "nr": n, "symbol": t["symbol"], "klasse": CLASS_DE.get(t["asset_class"], t["asset_class"]), "richtung": t["direction"],
            "signal_utc": iso(t["signal_time"]), "einstieg_utc": iso(t["entry_time"]), "einstieg_kurs": E,
            "stop": S, "ziel": float(t["target"]), "risiko_preis": risk, "risiko_pct": risk / E * 100,
            "ausstieg_utc": iso(r["exit_time"]), "ausstieg_kurs": X, "ausgang": "Ziel" if r["outcome"] == "TARGET" else "Stop",
            "dauer_tage": r["duration_days"], "brutto_pct": r["gross_return_pct"], "netto_pct": r["net_return_pct"],
            "netto_r": r["netto_r"], "brutto_r": r["brutto_r"], "kosten_pct": r["fees_pct"] + r["slippage_pct"],
            "kum_pct": cum, "ambiguous": bool(r.get("ambiguous_intrabar")), "atr": a, "trade_id": t["trade_id"],
            "anker": anchors(t, sn), "ausstieg_buchung_utc": iso(pd.Timestamp(r["exit_time"]) + pd.Timedelta(hours=4)),
        })

    wins = sum(1 for x in rows if x["netto_r"] > 0)
    tot = {"closed": len(rows), "win": wins, "loss": len(rows) - wins, "hit": wins / len(rows) * 100,
           "pct": sum(x["netto_pct"] for x in rows), "brutto_pct": sum(x["brutto_pct"] for x in rows),
           "r": sum(x["netto_r"] for x in rows), "open": len(open_st),
           "sum_pos": sum(x["netto_pct"] for x in rows if x["netto_pct"] > 0), "sum_neg": sum(x["netto_pct"] for x in rows if x["netto_pct"] < 0),
           "ziel_n": sum(1 for x in rows if x["ausgang"] == "Ziel"), "ziel_pct": sum(x["netto_pct"] for x in rows if x["ausgang"] == "Ziel"),
           "stop_n": sum(1 for x in rows if x["ausgang"] == "Stop"), "stop_pct": sum(x["netto_pct"] for x in rows if x["ausgang"] == "Stop"),
           "ambiguous": sum(1 for x in rows if x["ambiguous"])}
    by_class = {}
    for x in rows:
        c = by_class.setdefault(x["klasse"], {"n": 0, "pct": 0.0, "r": 0.0, "win": 0})
        c["n"] += 1; c["pct"] += x["netto_pct"]; c["r"] += x["netto_r"]; c["win"] += 1 if x["netto_r"] > 0 else 0

    # --- Abgleich mit dem zuletzt gesendeten Bericht (aus dessen PDF-Text, read-only)
    rep_ok = {}
    rp = os.path.join(PROTO, "report_listener_runtime", "reports", REPORT_FILE)
    try:
        from pypdf import PdfReader
        txt = PdfReader(rp).pages[0].extract_text()
        i = txt.index("Pro.1\n")
        seg = txt[i:i + 120]
        rep_ok = {"text": " ".join(seg.split())[:90]}
    except Exception:
        rep_ok = {"text": "(Berichts-PDF nicht lesbar; Abgleich gegen REPORT_EXPECT)"}
    matches = (tot["closed"] == REPORT_EXPECT["closed"] and tot["win"] == REPORT_EXPECT["win"] and tot["loss"] == REPORT_EXPECT["loss"]
               and round(tot["pct"], 1) == REPORT_EXPECT["pct"] and round(tot["r"], 2) == REPORT_EXPECT["r"] and tot["open"] == REPORT_EXPECT["open"])

    # --- Stichprobe: 5 Trades mit tracker.simulate_trade auf den eigenen Kerzen nachsimulieren; zusaetzlich ALLE
    def resim(t):
        f = fin_bars(t["symbol"])
        times = pd.to_datetime(f["Time"], utc=True)
        e = int(times[times > pd.Timestamp(t["signal_time"])].index[0])
        bars = [{"High": float(f["High"].iloc[i]), "Low": float(f["Low"].iloc[i]), "Open": float(f["Open"].iloc[i]),
                 "Close": float(f["Close"].iloc[i])} for i in range(e, len(f))]
        rs = T.simulate_trade(t["direction"], t["asset_class"], float(t["atr"]), float(t["result"]["entry_open"]),
                              float(t["stop_initial"]), float(t["target"]), bars, be_mode="BE-0")
        if rs.get("status") != "closed":
            return None
        ex = times.iloc[e + int(rs["duration_bars"]) - 1]
        return {"exit_time": iso(ex), "exit_price": rs["exit_price"], "outcome": rs["outcome"], "netto_r": rs["netto_r"], "net_pct": rs["net_return_pct"]}
    rnd = random.Random(7)
    tg = [x for x in inc if x["result"]["outcome"] == "TARGET"]
    sp = [x for x in inc if x["result"]["outcome"] == "STOP"]
    sample = rnd.sample(tg, 2) + rnd.sample(sp, 2) + rnd.sample([x for x in inc if x not in tg[:0]], 1)
    sample_res = []
    for t in sample:
        rs = resim(t); r = t["result"]
        ok = rs is not None and rs["exit_time"] == iso(r["exit_time"]) and abs(rs["exit_price"] - r["exit_price"]) < 1e-6 * abs(r["exit_price"]) \
            and rs["outcome"] == r["outcome"] and abs(rs["net_pct"] - r["net_return_pct"]) < 0.002 and abs(rs["netto_r"] - r["netto_r"]) < 0.002
        sample_res.append({"nr": next(x["nr"] for x in rows if x["trade_id"] == t["trade_id"]), "symbol": t["symbol"], "ok": bool(ok),
                           "exit_time": iso(r["exit_time"]), "exit_price": r["exit_price"], "outcome": r["outcome"]})
    all_ok = sum(1 for t in inc if (lambda rs, r: rs is not None and rs["exit_time"] == iso(r["exit_time"]) and abs(rs["exit_price"] - r["exit_price"]) < 1e-6 * abs(r["exit_price"]))(resim(t), t["result"]))

    open_rows = []
    for i, t in enumerate(open_st, 1):
        r = t.get("result") or {}
        E = r.get("entry_open") if r.get("entry_open") is not None else (t["entry_price"] if t.get("entry_time") else None)
        open_rows.append({"nr": f"O{i}", "symbol": t["symbol"], "klasse": CLASS_DE.get(t["asset_class"], t["asset_class"]), "richtung": t["direction"],
                          "signal_utc": iso(t["signal_time"]), "einstieg_utc": iso(t["entry_time"]) if t.get("entry_time") else None,
                          "einstieg_kurs": E, "stop": float(t["stop_initial"]), "ziel": float(t["target"]),
                          "inzwischen_geschlossen": t in later_closed})

    meta = {"stichtag_berlin": STICHTAG_BERLIN.strftime("%d.%m.%Y %H:%M"), "stichtag_utc": STICHTAG.strftime("%d.%m.%Y %H:%M"),
            "start_berlin": "17.08.2026 12:00", "report_file_time": "12.10.2026 14:15", "report_txt": rep_ok["text"],
            "matches_report": bool(matches), "later_closed": [(t["symbol"], t["result"]["exit_time"]) for t in later_closed],
            "n_trades_after": len(p1) - len(inc) - len(open_st)}
    out = {"meta": meta, "tot": tot, "by_class": by_class, "rows": rows, "open": open_rows, "problems": problems,
           "sample": sample_res, "resim_all_ok": all_ok, "resim_all_n": len(inc)}
    json.dump(out, open(os.path.join(HERE, "journal_daten.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    cols = ["nr", "symbol", "klasse", "richtung", "signal_utc", "einstieg_utc", "einstieg_kurs", "stop", "ziel", "risiko_preis", "risiko_pct",
            "ausstieg_utc", "ausstieg_kurs", "ausgang", "dauer_tage", "brutto_pct", "netto_pct", "netto_r", "kum_pct"]
    with open(os.path.join(HERE, "Pro1_Baseline_Tradejournal.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(cols + ["action_typ", "action_anker1_utc", "action_anker1_kurs", "action_anker2_utc", "action_anker2_kurs", "action_taps",
                           "safety_typ", "safety_anker1_utc", "safety_anker1_kurs", "safety_anker2_utc", "safety_anker2_kurs", "safety_taps"])
        fmt = lambda v: str(v).replace(".", ",") if isinstance(v, float) else v
        for x in rows:
            a, s = x["anker"]["action"], x["anker"]["safety"]
            w.writerow([fmt(round(x[c], 6) if isinstance(x[c], float) else x[c]) for c in cols] +
                       [a["kind_de"], a["p"][0]["time"], fmt(a["p"][0]["price"]), a["p"][1]["time"], fmt(a["p"][1]["price"]), a["taps"],
                        s["kind_de"], s["p"][0]["time"], fmt(s["p"][0]["price"]), s["p"][1]["time"], fmt(s["p"][1]["price"]), s["taps"]])
        w.writerow(["Summe", "", "", "", "", "", "", "", "", "", "", "", "", "", "", fmt(round(tot["brutto_pct"], 4)), fmt(round(tot["pct"], 4)),
                    fmt(round(tot["r"], 3)), fmt(round(tot["pct"], 4))])
    print("Stichtag", meta["stichtag_berlin"], "Berlin;", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in tot.items()})
    print("Abgleich Bericht:", matches, "| Probleme:", problems, "| Stichprobe:", [(s["nr"], s["symbol"], s["ok"]) for s in sample_res],
          "| alle nachsimuliert:", all_ok, "/", len(inc), "| offen:", len(open_rows), "| spaeter geschlossen:", meta["later_closed"])


if __name__ == "__main__":
    main()
