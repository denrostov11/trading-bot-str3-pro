# -*- coding: utf-8 -*-
"""Berichtskennzahlen (R UND Prozent) je Variante + Variantenvergleich.

EINE zentrale Berechnungsschicht fuer ALLE Varianten (keine variantenspezifischen Formeln).
Aus Ledger (Signalzahlen) + PaperTradeStore (Trades). Prozent- und R-Werte stammen aus denselben
gespeicherten entry_open/exit_price/Kosten (keine zweite Ergebnisquelle).

Vier strikt getrennte, unterschiedlich benannte Prozent-Kennzahlen:
  1. Summe der Einzeltrade-% (sum_positive/sum_negative)
  2. Netto-Gewinnprozent bei gleichem Einsatz je Trade (net_profit_pct)
  3. tatsaechliche Kontoaenderung / Portfoliorendite (portfolio_return_pct) - nur wenn Kontosim aktiv
  4. kumulierte Rendite mit Wiederanlage (compounded_return_pct)

Drawdown wird aus einer ZEITLICH GEORDNETEN Equity-Kurve (nach closed_ts) berechnet (Fix P2).
Offene Trades werden als unrealisiert GETRENNT ausgewiesen.
"""
from statistics import median

MIN_CLOSED_TRADES_FOR_RANKING = 30
# Positionsgroessenmodell (ANNAHME-Defaults aus Spec-Beispiel; NUTZERENTSCHEIDUNG vor Teststart):
PAPER_CAPITAL = 100000
FIXED_NOTIONAL_PER_TRADE = 1000
RISK_PER_TRADE_PCT = 0.50
SIZING_NOTE = ("Summe der Einzeltrade-% = gleicher Einsatz je Trade (FIXED_NOTIONAL). "
               "Portfoliorendite/compounded nur bei aktiver Kontosimulation.")


def _closed(trades):
    return [t for t in trades if getattr(t, "status", None) == "closed"
            and t.result.get("status") == "closed"]


def _ordered(cl):
    """Nach Exit-Zeit sortiert (Fix P2) - Basis fuer Equity/Drawdown."""
    return sorted(cl, key=lambda t: t.result.get("closed_ts", 0))


def _drawdown(seq):
    peak = 0.0; equity = 0.0; mdd = 0.0
    for x in seq:
        equity += x
        peak = max(peak, equity)
        mdd = min(mdd, equity - peak)
    return round(mdd, 4)


def _compounded_pct(seq):
    eq = 1.0
    for x in seq:
        eq *= (1 + x / 100.0)
    return round((eq - 1) * 100, 4)


def variant_report(ledger, trades, strategy_id, account_sim=False):
    my = [t for t in trades if t.strategy_id == strategy_id]
    cl = _ordered(_closed(my))
    open_unrealized = [t for t in my if getattr(t, "status", None) in ("open", "pending_fill")]
    rep = {
        "strategy_id": strategy_id,
        "signal_counts": ledger.counts_by_status(strategy_id),
        "closed_trades": len(cl),
        "open_trades_unrealized": len(open_unrealized),
        "sizing_note": SIZING_NOTE,
    }
    if not cl:
        rep["note"] = "keine abgeschlossenen Trades"
        rep["sample_flag"] = "UNZUREICHENDE_STICHPROBE"
        return rep

    net_r = [t.result.get("netto_r", 0.0) for t in cl]
    gross_r = [t.result.get("brutto_r", 0.0) for t in cl]
    net_pct = [t.result.get("net_return_pct", 0.0) for t in cl]
    gross_pct = [t.result.get("gross_return_pct", 0.0) for t in cl]
    wins_r = [r for r in net_r if r > 0]; losses_r = [r for r in net_r if r < 0]
    wins_pct = [p for p in net_pct if p > 0]; losses_pct = [p for p in net_pct if p < 0]
    posR = sum(wins_r); negR = sum(losses_r)
    sum_pos_pct = sum(wins_pct)
    sum_neg_pct = abs(sum(losses_pct))                      # ABSOLUT (positiver Verlustbetrag)
    net_profit_pct = sum_pos_pct - sum_neg_pct

    rep.update({
        # --- R (feste Reihenfolge 1-5,11,12) ---
        "n_trades": len(cl),
        "hit_rate": round(len(wins_r) / len(cl), 4),
        "total_r_netto": round(sum(net_r), 3), "total_r_brutto": round(sum(gross_r), 3),
        "avg_r": round(sum(net_r) / len(cl), 3), "median_r": round(median(net_r), 3),
        "expectancy_r": round(sum(net_r) / len(cl), 3),
        "profit_factor": round(posR / abs(negR), 3) if negR != 0 else None,
        "max_drawdown_r": _drawdown(net_r),
        # --- Prozent (6-9,13) ---
        "sum_positive_return_pct": round(sum_pos_pct, 4),
        "sum_negative_return_pct": round(sum_neg_pct, 4),          # positiver Verlustbetrag
        "net_profit_pct": round(net_profit_pct, 4),
        "average_return_pct": round(sum(net_pct) / len(cl), 4),
        "median_return_pct": round(median(net_pct), 4),
        "average_winner_pct": round(sum(wins_pct) / len(wins_pct), 4) if wins_pct else 0.0,
        "average_loser_pct": round(sum(losses_pct) / len(losses_pct), 4) if losses_pct else 0.0,
        "best_trade_pct": round(max(net_pct), 4), "worst_trade_pct": round(min(net_pct), 4),
        "gross_profit_pct": round(sum(gross_pct), 4),
        "max_drawdown_pct": _drawdown(net_pct),
        "compounded_return_pct": _compounded_pct(net_pct),
        # --- Verteilung ---
        "winners": len(wins_r), "losers": len(losses_r),
        "break_even_exits": sum(1 for t in cl if t.result.get("outcome") == "BREAK_EVEN"),
        "avg_duration_days": round(sum(t.result.get("duration_days", 0) for t in cl) / len(cl), 2),
        "avg_mfe_r": round(sum(t.result.get("mfe_r", 0) for t in cl) / len(cl), 3),
        "avg_mae_r": round(sum(t.result.get("mae_r", 0) for t in cl) / len(cl), 3),
        "long_net_r": round(sum(t.result.get("netto_r", 0) for t in cl if t.direction == "LONG"), 3),
        "short_net_r": round(sum(t.result.get("netto_r", 0) for t in cl if t.direction == "SHORT"), 3),
        "ambiguous_intrabar": sum(1 for t in cl if t.result.get("ambiguous_intrabar")),
        "sample_flag": "OK" if len(cl) >= MIN_CLOSED_TRADES_FOR_RANKING else "UNZUREICHENDE_STICHPROBE",
    })
    # Portfoliorendite (tatsaechliche Kontoaenderung) nur bei aktiver, definierter Kontosimulation
    rep["portfolio_return_pct"] = (rep["compounded_return_pct"] if account_sim
                                   else "NICHT_SIMULIERT (Kontosim inaktiv)")
    return rep


def comparison(ledger, trades, strategy_ids, account_sim=False):
    reps = [variant_report(ledger, trades, sid, account_sim) for sid in strategy_ids]

    def rank_by(key, reverse=True):
        elig = [r for r in reps if r.get("sample_flag") == "OK" and isinstance(r.get(key), (int, float))]
        return [r["strategy_id"] for r in sorted(elig, key=lambda r: r[key], reverse=reverse)]

    rankings = {
        "by_total_r": rank_by("total_r_netto"),
        "by_expectancy_r": rank_by("expectancy_r"),
        "by_profit_factor": rank_by("profit_factor"),
        "by_lowest_drawdown_r": rank_by("max_drawdown_r", reverse=True),   # nahe 0 = besser
        "by_net_profit_pct": rank_by("net_profit_pct"),
        "by_avg_net_pct": rank_by("average_return_pct"),
        "by_median_net_pct": rank_by("median_return_pct"),
        "by_lowest_drawdown_pct": rank_by("max_drawdown_pct", reverse=True),
    }
    return {
        "variants": reps, "rankings": rankings,
        "eligible_for_ranking": sum(1 for r in reps if r.get("sample_flag") == "OK"),
        "note": ("Keine automatische Gewinnerbehauptung: Drawdown, Stichprobe, Kosten, Parallelitaet, "
                 "Datenqualitaet und Konzentrationsrisiken beachten. Prozent- und R-Kennzahlen getrennt."),
    }


def pairwise_by_parent(ledger, parent_signal_id):
    cand, evals = ledger.by_parent(parent_signal_id)
    return {
        "parent_signal_id": parent_signal_id,
        "candidate_status": cand["status"] if cand else None,
        "by_variant": {e["strategy_id"]: {"status": e["status"], "reason": e["rejection_reason"],
                                          "filters": e["filter_values"]} for e in evals},
    }
