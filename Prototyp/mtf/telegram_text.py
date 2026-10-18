# -*- coding: utf-8 -*-
"""Textbausteine: Kurzbeschreibung (PDF S.3) und Telegram-Text unter der PDF (kompakt), im Format der bestehenden
Trade-Meldung (notify.messages.Message TRADE_OPENED) + Top-down-Zeile + PDF-Hinweis.

description(A)        Kurzbeschreibung fuer S.3 (mehrzeilig, Monospace)
telegram_draft(A)     Nachricht unter der PDF (< 1024 Zeichen, passt als Telegram-Caption) - nur Text, KEIN Versand
telegram_text         Alias von telegram_draft

Beide enthalten: Variante, Symbol, Richtung, Schlusszeit der Signal-Kerze und Einstiegszeit (deutsche Zeit), gebuchten
Einstiegskurs, Stop, Ziel (bzw. "kein festes Ziel - Ausstieg nach C+"), 1R, ATR, Top-down-Ergebnis, Grund und - wenn vom
Aufrufer geliefert - live_info (aktueller Kurs, Stand in R, Abstaende). Paper-Trading-Hinweis ist immer enthalten."""
import pandas as pd
from .trade_pdf import fde, fde_de, fnum, fprice

OUTCOME_DE = {"TARGET": "Ziel erreicht", "STOP": "Stop getroffen", "BREAK_EVEN": "Break-even", "NOTFALLNETZ": "Notfallnetz",
              "SAFETY_CLOSE": "Schlusskurs durch Safety Line", "GEWINNSCHWELLE_CLOSE": "Schlusskurs unter Gewinnschwelle"}
MARK = {True: "✓", False: "✗", None: "–"}
PAPER = "Paper-Trading - keine echte Order."
TG_LIMIT = 1024


def _variant(A):
    t = A["trade"]
    return t.get("strategy_id") or t.get("variant") or "Str.3 Pro.1"


def _reason(A):
    long = A["direction"] == "LONG"
    kind = "Widerstandslinie" if long else "Unterstützungslinie"
    if A.get("action") is None:
        return f"Schlusskurs der 4h-Kerze bricht die {kind} (Action Line; Linien-Details nicht verfügbar)"
    s = A.get("safety")
    return (f"Schlusskurs der 4h-Kerze bricht die {kind} (Action Line, {len(A['action'].taps)} Taps, "
            f"{A['action'].angle_deg:.0f}° Neigung)" + (f"; Safety Line mit {len(s.taps)} Taps" if s is not None else ""))


def _reason_short(A):
    long = A["direction"] == "LONG"
    kind = "Widerstandslinie" if long else "Unterstützungslinie"
    if A.get("action") is None:
        return f"4h-Schluss bricht {kind}"
    s = A.get("safety")
    return f"4h-Schluss bricht {kind} ({len(A['action'].taps)} Taps)" + (f", Safety Line {len(s.taps)} Taps" if s is not None else "")


def _flags(A):
    it = A["td"]["items"]
    return f"Monat {MARK[it['M']['supports']]} · Woche {MARK[it['W']['supports']]} · Tag {MARK[it['D']['supports']]} · 4h {MARK[it['4h']['supports']]}"


def _goal(A, short=False):
    """Ziel-Text: fester Zielpreis oder 'kein festes Ziel - Ausstieg nach C+' (+1,5R-Marke)."""
    if A["target"] is not None:
        rr = abs(A["target"] - A["E"]) / A["risk"] if A["risk"] else 0.0
        return f"{fprice(A['target'])}" + ("" if short else f" (nächste Unterstützungs-/Widerstandszone) → Ziel = {fnum(rr, 2)} R")
    if A.get("c_plus"):
        r2 = fnum(A["c_plus"]["stage2_r"], 1)
        if short:
            return f"kein festes Ziel – Ausstieg nach C+ (+{r2}R bei {fprice(A['stage2_price'])})"
        return (f"kein festes Ziel – Ausstieg nach C+ (ab +{r2} R bei {fprice(A['stage2_price'])} Stop auf Einstand + Kosten, "
                f"danach unter bestätigten Swings; Notfallnetz {fnum(A['c_plus']['net_atr'], 1)} ATR)")
    return "kein Ziel angegeben"


def _entry_line(A, short=False):
    t = fde_de(A["entry_time"])
    if A.get("entry_booked"):
        px = fprice(A["booked_price"])
        lab = "gebucht"
    else:
        px = fprice(A["E"])
        lab = "erwartet, Eröffnung der nächsten 4h-Kerze"
    return t, px, lab


def _live_line(A, short=False):
    li = A.get("live_info")
    if not li:
        return None
    when = f" ({fde_de(li['time'])})" if li.get("time") is not None else ""
    parts = [f"Kurs {fprice(li['price'])}{when}"]
    if li.get("r_now") is not None:
        parts.append(f"{fnum(li['r_now'], 2, True)} R")
    if li.get("dist_stop") is not None:
        parts.append(f"Abstand Stop {fprice(li['dist_stop'])}" + (f" ({fnum(li['dist_stop_r'], 2)} R)" if li.get("dist_stop_r") is not None and not short else ""))
    if li.get("dist_target") is not None:
        parts.append(f"Abstand Ziel {fprice(li['dist_target'])}")
    return " · ".join(parts)


def description(A):
    """Kurzbeschreibung des Trades (S.3 der PDF)."""
    t = A["trade"]
    long = A["direction"] == "LONG"
    te, px, lab = _entry_line(A)
    lines = [
        f"Symbol / Richtung : {t['symbol']} · {A['direction']} ({'Kauf' if long else 'Verkauf'}) · Variante {_variant(A)}",
        f"Signal-Kerze      : Schluss {fde_de(A['cutoff'])} (4h-Kerze {pd.Timestamp(A['sig_start']).strftime('%H:%M')}–{pd.Timestamp(A['cutoff']).strftime('%H:%M')} UTC)",
        f"Grund             : {_reason(A)}",
        f"Einstieg          : {te} · Kurs {px} ({lab})",
        f"Stop              : {fprice(A['stop0'])} (Safety Line bei Kerze Bruch+4, fest) → 1R = {fprice(A['risk'])} ({fnum(A['risk'] / A['E'] * 100, 2)} % vom Einstieg)",
        f"Ziel              : {_goal(A)}",
        f"ATR (14, 4h)      : {fprice(A['a'])} (= {fnum(A['a'] / A['risk'], 2) if A['risk'] else '–'} R)",
        f"Top-down          : {A['td']['count']} von {A['td']['total']} Zeitrahmen stützen die Richtung ({_flags(A)})",
    ]
    live = _live_line(A)
    if live:
        lines.append(f"Aktuell           : {live}")
    if A.get("ist") is not None and A["ist"].get("netto_r") is not None:
        ist = A["ist"]
        lines.append(f"Ausgang IST       : {OUTCOME_DE.get(ist['outcome'], ist['outcome'])} am {fde(ist['exit_time'], False)}, "
                     f"{fnum(ist['netto_r'], 2, True)} R netto ({fnum(ist['net_pct'], 2, True)} %)")
        if A.get("cplus_r") is not None:
            lines.append(f"Ausgang C+ (Muster): {OUTCOME_DE.get(A['cplus']['exit']['outcome'])} am {fde(A['cplus_exit_time'], False)}, "
                         f"{fnum(A['cplus_r'], 2, True)} R netto ({fnum(A['cplus_pct'], 2, True)} %)"
                         f"; Stufe 2 {'erreicht' if A['cplus']['stage2_idx'] is not None else 'nicht erreicht'}, "
                         f"{len(A['cplus']['swings'])} Swing-Schwelle(n)")
        else:
            lines.append("Ausgang C+ (Muster): bis zum letzten verfügbaren Kurs noch offen (nicht gewertet)")
    lines.append("")
    if A.get("muster"):
        lines.append("MUSTER – fiktiver Trade aus dem Paper-Test. Paper-Trading – keine echte Order, keine Anlageberatung.")
    else:
        lines.append("Paper-Trading – keine echte Order, keine Anlageberatung.")
    return "\n".join(lines)


def telegram_draft(A):
    """Nachricht unter der PDF (kompakt, < 1024 Zeichen). Kein Versand - nur Text."""
    t = A["trade"]
    te, px, lab = _entry_line(A)
    rr_pct = A["risk"] / A["E"] * 100
    live = _live_line(A, short=True)
    rows = [
        f"{_variant(A)} - TRADE_OPENED",
        f"{t['symbol']} · {A['direction']} · Variante {_variant(A)}",
        f"Signal-Kerze (4h) Schluss: {fde_de(A['cutoff'])}",
        f"Einstieg: {te} · Kurs {px} ({'gebucht' if A.get('entry_booked') else 'erwartet'})",
        f"Stop: {fprice(A['stop0'])} · Ziel: {_goal(A, short=True)}",
        f"1R = {fprice(A['risk'])} ({fnum(rr_pct, 1)} %) · ATR {fprice(A['a'])}",
        f"Grund: {_reason_short(A)}",
        f"Top-down: {A['td']['count']} von {A['td']['total']} Zeitrahmen stützen die Richtung ({_flags(A)})",
    ]
    if live:
        rows.append(f"Aktuell: {live}")
    if t.get("parent_signal_id"):
        rows.append(f"parent_signal_id: {t['parent_signal_id']}")
    rows += ["PDF mit 5 Charts (Monat bis 1h) im Anhang.", PAPER]
    text = "\n".join(rows)
    if len(text) > TG_LIMIT:                                 # Notbremse: optionale Zeilen zuerst weglassen
        rows = [r for r in rows if not r.startswith("parent_signal_id") and not r.startswith("PDF mit")]
        text = "\n".join(rows)
    if len(text) > TG_LIMIT:
        rows = [r for r in rows if not r.startswith("Aktuell")]
        text = "\n".join(rows)
    return text


telegram_text = telegram_draft
