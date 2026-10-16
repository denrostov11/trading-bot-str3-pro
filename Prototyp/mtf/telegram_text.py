# -*- coding: utf-8 -*-
"""Textbausteine: Kurzbeschreibung (PDF S.3) und Entwurf der Telegram-Nachricht (kompakt), im Format der
bestehenden Trade-Meldung (notify.messages.Message TRADE_OPENED) + Top-down-Zeile + PDF-Hinweis."""
import pandas as pd
from .trade_pdf import fde, fnum, fprice

OUTCOME_DE = {"TARGET": "Ziel erreicht", "STOP": "Stop getroffen", "BREAK_EVEN": "Break-even", "NOTFALLNETZ": "Notfallnetz",
              "SAFETY_CLOSE": "Schlusskurs durch Safety Line", "GEWINNSCHWELLE_CLOSE": "Schlusskurs unter Gewinnschwelle"}
MARK = {True: "✓", False: "✗", None: "–"}


def _reason(A):
    long = A["direction"] == "LONG"
    kind = "Widerstandslinie" if long else "Unterstützungslinie"
    return (f"Schlusskurs der 4h-Kerze bricht die {kind} (Action Line, {len(A['action'].taps)} Taps, "
            f"{A['action'].angle_deg:.0f}° Neigung); Safety Line mit {len(A['safety'].taps)} Taps")


def _flags(A):
    it = A["td"]["items"]
    return f"Monat {MARK[it['M']['supports']]} · Woche {MARK[it['W']['supports']]} · Tag {MARK[it['D']['supports']]} · 4h {MARK[it['4h']['supports']]}"


def description(A):
    t = A["trade"]
    long = A["direction"] == "LONG"
    rr = abs(A["target"] - A["E"]) / A["risk"]
    lines = [
        f"Symbol / Richtung : {t['symbol']} · {A['direction']} ({'Kauf' if long else 'Verkauf'}) · Variante Str.3 Pro.1",
        f"Signal            : {fde(A['cutoff'])} (Schluss der 4h-Kerze {pd.Timestamp(A['sig_start']).strftime('%H:%M')}–{pd.Timestamp(A['cutoff']).strftime('%H:%M')})",
        f"Grund             : {_reason(A)}",
        f"Einstieg          : {fprice(A['E'])} (Eröffnung der nächsten 4h-Kerze)",
        f"Stop              : {fprice(A['stop0'])} (Safety Line bei Kerze Bruch+4, fest) → 1R = {fprice(A['risk'])} ({fnum(A['risk'] / A['E'] * 100, 2)} % vom Einstieg)",
        f"Ziel              : {fprice(A['target'])} (nächste Unterstützungs-/Widerstandszone) → Ziel = {fnum(rr, 2)} R",
        f"ATR (14, 4h)      : {fprice(A['a'])} (= {fnum(A['a'] / A['risk'], 2)} R)",
        f"Top-down          : {A['td']['count']} von {A['td']['total']} Zeitrahmen stützen die Richtung ({_flags(A)})",
    ]
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
    lines.append("MUSTER – fiktiver Trade aus dem Paper-Test. Paper-Trading – keine echte Order, keine Anlageberatung.")
    return "\n".join(lines)


def telegram_draft(A):
    """Kompakter Nachrichtenentwurf (kein Versand!), der kuenftig zusammen mit der PDF gesendet wuerde."""
    t = A["trade"]
    long = A["direction"] == "LONG"
    kind = "Widerstandslinie" if long else "Unterstützungslinie"
    rr_pct = A["risk"] / A["E"] * 100
    return "\n".join([
        f"Str.3 Pro.1 (v1) - TRADE_OPENED",
        f"Instrument: {t['symbol']}",
        f"{A['direction']} · Einstieg geplant (Open nächste Kerze) · Signal {fde(A['cutoff'])}",
        f"Stop: {fprice(A['stop0'])} · Ziel: {fprice(A['target'])} · 1R = {fprice(A['risk'])} ({fnum(rr_pct, 1)} %) · ATR {fprice(A['a'])}",
        f"Grund: 4h-Schluss bricht {kind} ({len(A['action'].taps)} Taps), Safety Line {len(A['safety'].taps)} Taps",
        f"Top-down: {A['td']['count']} von {A['td']['total']} Zeitrahmen stützen die Richtung ({_flags(A)})",
        f"parent_signal_id: {t['parent_signal_id']}",
        "PDF mit 5 Charts (Monat bis 1h) im Anhang.",
        "Paper-Trading - keine echte Order.",
    ])
