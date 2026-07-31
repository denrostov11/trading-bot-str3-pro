# -*- coding: utf-8 -*-
"""Berichtserzeugung im Lauf: erzeugt je Variante + Vergleich einen PDF-Bericht und den
Telegram-Kurztext fuer einen Zeitraum (7 oder 30 volle Kalendertage). LOKAL-zuerst (Modus B):
PDFs landen im Runtime-Reports-Ordner; die Telegram-Zustellung wird spaeter (nach Chat-ID-Setup)
angebunden - die Kurztexte/PDFs sind dafuer bereits fertig.

Reine Prozent-Auswertung (kein Kapitalkonto) + R. Rollierend-30 wird NIE als Kalendermonat bezeichnet.
"""
import os, time

from . import reporting as REP, reporting_pdf as RP
from .ledger import Ledger
from .tracker import PaperTradeStore

ALL_VARIANTS = [f"Str.3 Pro.{i}" for i in range(1, 9)]


def _period_trades(trades, days, now):
    """Geschlossene Trades der letzten `days` Kalendertage + aktuell offene (unrealisiert)."""
    lo = now - days * 86400
    out = []
    for t in trades:
        st = getattr(t, "status", None)
        if st == "closed" and lo <= t.result.get("closed_ts", 0) <= now:
            out.append(t)
        elif st in ("open", "pending_fill"):
            out.append(t)
    return out


def generate_reports(base_dir, days, label, strategy_ids=None, now=None):
    """Erzeugt PDF je Variante + Vergleich + Kurztexte. Gibt {short_texts, variant_pdfs, comparison_pdf}."""
    strategy_ids = strategy_ids or ALL_VARIANTS
    now = now or time.time()
    rt = base_dir
    ledger = Ledger(os.path.join(rt, "ledger.json"))
    trades_store = PaperTradeStore(os.path.join(rt, "trades.json"))
    reports_dir = os.path.join(rt, "reports")
    os.makedirs(reports_dir, exist_ok=True)
    period = _period_trades(trades_store.trades, days, now)
    datestr = time.strftime("%Y-%m-%d", time.localtime(now))

    short_texts, variant_pdfs = {}, {}
    for sid in strategy_ids:
        rep = REP.variant_report(ledger, period, sid)
        short_texts[sid] = RP.short_text(rep, label)
        fn = f"STR3_{sid.split('.')[-1].strip()}_{'WEEKLY' if days == 7 else 'ROLLING_30D'}_{datestr}.pdf"
        variant_pdfs[sid] = RP.build_variant_pdf(rep, os.path.join(reports_dir, fn), label)

    comp = REP.comparison(ledger, period, strategy_ids)
    comp_pdf = RP.build_comparison_pdf(comp, os.path.join(reports_dir, f"STR3_COMPARISON_{datestr}.pdf"))
    return {"short_texts": short_texts, "variant_pdfs": variant_pdfs, "comparison_pdf": comp_pdf,
            "reports_dir": reports_dir}


def deliver_via_telegram(reports, telegram_config, dispatcher=None):
    """Optionaler Zustell-Hook: sendet Kurztext + PDF je Variante an die zugehoerige Gruppe.
    Wird erst aktiv, wenn Telegram konfiguriert ist (Chat-IDs vorhanden). Ohne Konfiguration:
    No-Op (lokale PDFs bleiben die verbindliche Ausgabe)."""
    if not telegram_config or not getattr(telegram_config, "enabled", False):
        return {"delivered": 0, "note": "Telegram inaktiv (keine Chat-IDs) - nur lokale PDFs."}
    # Verdrahtung an notify.dispatcher/queue erfolgt beim Live-Setup (nach Chat-ID-Eingabe).
    return {"delivered": 0, "note": "Live-Zustellung wird beim Telegram-Setup angebunden."}
