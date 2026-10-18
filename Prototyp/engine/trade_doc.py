# -*- coding: utf-8 -*-
"""Anhang zur Trade-Meldung: Trade-PDF (top-down, B2) mit Rueckfall auf das PNG-Chartbild (dpi 220).

- PDF: mtf.trade_pdf (anderer Baustein, wird nur aufgerufen) in einem eigenen Prozess mit Zeitlimit
  (live_settings trade_pdf.timeout_s, Standard 90 s). Fehler oder Zeitueberschreitung -> PNG.
- Ein-/ausschaltbar in live_settings.json (trade_pdf.enabled, Standard an); wird bei jedem Aufruf neu gelesen.
- Ein Fehler hier darf nie eine Meldung verhindern: im schlimmsten Fall geht der Text ohne Anhang raus.
"""
import os
from . import live_settings


def make_png(rt, t, result, log, dpi):
    if result is None or result.get("action_obj") is None or result.get("compat") is None:
        return None
    from . import trade_chart as TC
    chart_dir = os.path.join(rt, "charts")
    os.makedirs(chart_dir, exist_ok=True)
    return TC.render_trade_chart(
        result["compat"], t.symbol, t.symbol, result.get("action_obj"), result.get("safety_obj"),
        t.direction, result.get("signal_close", t.stop_initial), t.stop_initial,
        (None if t.exit_mode in ("CPLUS", "D") else t.target),          # C+/D haben kein festes Ziel
        os.path.join(chart_dir, f"{t.parent_signal_id}_{t.exit_mode or 'BASE'}.png"),
        variant={"CPLUS": "Str.3 C+", "D": "Str.3 D"}.get(t.exit_mode, "Str.3 Pro"), dpi=dpi)


def make_attachment(rt, t, result, ledger, cache, log, settings=None, pdf_fn=None, png_fn=None):
    """-> Pfad (PDF oder PNG) oder None. pdf_fn/png_fn injizierbar (Tests)."""
    s = settings or live_settings.load()
    tp = s["trade_pdf"]
    if tp["enabled"]:
        try:
            fn = pdf_fn or _make_pdf
            path = fn(rt, t, ledger, cache, tp["timeout_s"], log)
            if path and os.path.exists(path):
                return path
            log.append(f"Trade-PDF {t.symbol}: nicht erzeugt - Rueckfall PNG")
        except Exception as e:
            log.append(f"Trade-PDF {t.symbol}: {type(e).__name__} - Rueckfall PNG")
    try:
        return (png_fn or make_png)(rt, t, result, log, tp["png_dpi"])
    except Exception as e:
        log.append(f"PNG {t.symbol}: {type(e).__name__}")
        return None


def _pdf_worker(args, q):
    """Laeuft im eigenen Prozess (hartes Zeitlimit durch den Aufrufer). Ruft NUR die oeffentliche Funktion des
    mtf-Bausteins auf (analyse + make_trade_pdf)."""
    try:
        from mtf import data as D, trade_pdf as TP, telegram_text as TT
        from engine import tracker as T
        t = dict(args["trade"])
        if t.get("exit_mode") == "D":
            t["target"] = 0.0                       # D hat kein festes Ziel (mtf: 0 -> "kein Ziel")
        h1 = D.load_1h(args["h1_path"])
        daily, _src = D.load_daily(t["symbol"], h1=h1)
        live = args.get("live")
        A = TP.analyse(t, args["snapshot"], h1, daily, T.cost_fraction(t["asset_class"]),
                       c_plus=({} if t.get("exit_mode") == "CPLUS" else None), live_info=live,
                       max_seconds=args["budget_s"])
        TP.make_trade_pdf(args["out"], A, TT.description(A), max_seconds=args["budget_s"])
        q.put(("ok", args["out"]))
    except BaseException as e:                       # auch MtfTimeout & Co.: nie hart abstuerzen
        q.put(("err", type(e).__name__))


def _make_pdf(rt, t, ledger, cache, timeout_s, log, worker=None):
    """Trade-PDF (top-down) ueber mtf.trade_pdf in einem eigenen Prozess mit Zeitlimit `timeout_s`.
    Rueckgabe: Pfad oder None (Fehler/Zeitueberschreitung -> Aufrufer nimmt das PNG)."""
    from dataclasses import asdict
    import multiprocessing as mp
    cand, _ = ledger.by_parent(t.parent_signal_id)
    snap = (cand or {}).get("snapshot")
    if not snap:
        log.append(f"Trade-PDF {t.symbol}: kein Snapshot im Ledger")
        return None
    h1_path = cache._path(t.symbol, "1h")
    if not os.path.exists(h1_path):
        log.append(f"Trade-PDF {t.symbol}: keine 1h-Daten im Cache")
        return None
    out_dir = os.path.join(rt, "trade_pdfs")
    os.makedirs(out_dir, exist_ok=True)
    out = os.path.join(out_dir, f"{t.parent_signal_id}_{t.exit_mode or 'BASE'}_{t.symbol.replace('/', '_').replace('=', '_')}.pdf")
    live = None
    rz = t.realistic or {}
    if rz.get("price"):
        live = {"price": rz["price"], "time": rz.get("quote_time")}
    args = {"trade": asdict(t), "snapshot": snap, "h1_path": h1_path, "out": out, "live": live,
            "budget_s": max(10.0, float(timeout_s) - 5.0)}
    ctx = mp.get_context("spawn")
    q = ctx.Queue()
    p = ctx.Process(target=worker or _pdf_worker, args=(args, q), daemon=True)
    p.start()
    p.join(timeout_s)
    if p.is_alive():
        p.terminate(); p.join(5)
        if p.is_alive():
            p.kill()
        log.append(f"Trade-PDF {t.symbol}: Zeitlimit {timeout_s}s ueberschritten")
        _cleanup(out)
        return None
    try:
        kind, val = q.get(timeout=2)
    except Exception:
        log.append(f"Trade-PDF {t.symbol}: Prozess ohne Ergebnis")
        _cleanup(out)
        return None
    if kind != "ok":
        log.append(f"Trade-PDF {t.symbol}: Fehler {val}")
        _cleanup(out)
        return None
    return val


def _cleanup(out):
    for f in (out, out + ".part"):
        try:
            if os.path.exists(f):
                os.remove(f)
        except OSError:
            pass
