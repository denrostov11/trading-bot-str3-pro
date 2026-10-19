# -*- coding: utf-8 -*-
"""Textbausteine: Kurzbeschreibung (PDF S.3) und Telegram-Text unter der PDF (kompakt), im Format der bestehenden
Trade-Meldung (notify.messages.Message TRADE_OPENED) + Top-down-Zeile + PDF-Hinweis.

description(A)        Kurzbeschreibung fuer S.3 (mehrzeilig, Monospace)
telegram_draft(A)     Nachricht unter der PDF (< 1024 Zeichen, passt als Telegram-Caption) - nur Text, KEIN Versand
telegram_text         Alias von telegram_draft

Beide enthalten: Variante, Symbol, Richtung, Schlusszeit der Signal-Kerze und Einstiegszeit (deutsche Zeit), gebuchten
Einstiegskurs, Stop, Ziel (bzw. "kein festes Ziel - Ausstieg nach C+/D"), 1R, ATR, Top-down-Ergebnis, Grund und - wenn vom
Aufrufer geliefert - live_info (aktueller Kurs, Stand in R, Abstaende). Paper-Trading-Hinweis ist immer enthalten.

Seit 19.10.2026 traegt die Kurzbeschreibung (PDF S.3) ALLE Angaben, die aus der kurzen Telegram-Eroeffnungsmeldung entfernt
wurden: Status (gebucht / wartet), aktueller Kurs beim Versand samt Uhrzeit, Abstaende zu Einstieg/Stop/Ziel (bzw. Schwelle/
Stop bei C+/D) in Preis und R, Datenverzoegerung, realistischer Einstieg, Ausstiegsregel C+/D, parent_signal_id."""
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


def _mode(A):
    """Ausstiegsmodus des Trades: '' (Ziel/Stop), 'CPLUS' oder 'D'."""
    m = (A.get("trade") or {}).get("exit_mode") or ""
    return "CPLUS" if (m == "CPLUS" or (not m and A.get("c_plus"))) else m


def _flags(A):
    it = A["td"]["items"]
    return f"Monat {MARK[it['M']['supports']]} · Woche {MARK[it['W']['supports']]} · Tag {MARK[it['D']['supports']]} · 4h {MARK[it['4h']['supports']]}"


def _goal(A, short=False):
    """Ziel-Text: fester Zielpreis oder 'kein festes Ziel - Ausstieg nach C+' (+1,5R-Marke)."""
    if A["target"] is not None:
        rr = abs(A["target"] - A["E"]) / A["risk"] if A["risk"] else 0.0
        return f"{fprice(A['target'])}" + ("" if short else f" (nächste Unterstützungs-/Widerstandszone) → Ziel = {fnum(rr, 2)} R")
    if _mode(A) == "D":
        if short:
            return "kein festes Ziel – Ausstieg nach D"
        return ("kein festes Ziel – Ausstieg nach D (Stop 0,1 ATR jenseits der mitwandernden Safety Line, am bestätigten "
                f"Zwischen{'tief' if A['direction'] == 'LONG' else 'hoch'} nachgezogen; jede Berührung, auch ein Docht, löst aus)")
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
        part = ((A.get("trade") or {}).get("booked_entry") or {}).get("partial")
        lab = "gebucht, Open der Folgekerze" + (" – Kerze läuft noch" if part else "")
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


LABEL_W = 18                                    # Spaltenbreite der Beschriftung (muss zum Einzug in trade_pdf.make_trade_pdf passen)
STRONG_DEVIATION_R = 0.5                         # ab dieser Abweichung vom Einstieg (in R) wird ausdruecklich gewarnt
DELAY_NOTE_S = 120                               # ab dieser Verzoegerung wird sie als Minutenwert genannt


def _row(label, text):
    return f"{label:<{LABEL_W}}: {text}"


def _hm(ts):
    """'14:03 MESZ' (deutsche Zeit, nur Uhrzeit)."""
    return fde_de(ts)[11:]


def _dist(diff, risk):
    """Preisabstand mit Vorzeichen und in R: '+1,3288 (+1,06 R)'."""
    sg = "+" if diff >= 0 else "−"
    r = f" ({fnum(diff / risk, 2, True)} R)" if risk else ""
    return f"{sg}{fprice(abs(diff))}{r}"


def _live_rows(A):
    """Zeilen zum Zeitpunkt des Versands: aktueller Kurs (mit Uhrzeit), Abstaende in Preis und R, Datenverzoegerung,
    realistischer Einstieg. Ohne Kurs: 'nicht verfuegbar' (nichts erfinden)."""
    li = A.get("live_info")
    t = A.get("trade") or {}
    mode = _mode(A)
    long = A["direction"] == "LONG"
    sg = 1.0 if long else -1.0
    risk, E = A["risk"], A["E"]
    if not li:
        return [_row("Aktueller Kurs", "nicht verfügbar"), _row("Realist. Einstieg", "nicht verfügbar")]
    cur = li["price"]
    bits = [f"Kursbalken {_hm(li['time'])}"] if li.get("time") is not None else []
    if li.get("sent_at"):
        bits.append(f"Versand {_hm(li['sent_at'])}")
    if li.get("interval"):
        bits.append(f"{li['interval']}-Daten")
    rows = [_row("Aktueller Kurs", fprice(cur) + (f" ({', '.join(bits)})" if bits else ""))]
    rows.append(_row("Abstand Einstieg", _dist(sg * (cur - E), risk)))
    rows.append(_row("Abstand Stop", _dist(sg * (cur - A["stop0"]), risk)))
    lv = t.get("exit_level") or {}
    if mode in ("CPLUS", "D") and lv.get("threshold") is not None:
        rows.append(_row("Abstand akt. Stop" if mode == "D" else "Abstand Schwelle", _dist(sg * (cur - lv["threshold"]), risk)))
    elif A["target"] is not None:
        rows.append(_row("Abstand Ziel", _dist(sg * (A["target"] - cur), risk)))
    ds = li.get("delay_s")
    if ds is not None:
        rows.append(_row("Datenverzögerung", f"ca. {int(round(float(ds) / 60))} Min. (letzter Kursbalken {_hm(li['time'])})"
                         if float(ds) >= DELAY_NOTE_S and li.get("time") is not None else "keine messbare"))
    rows.append(_row("Realist. Einstieg", f"{fprice(cur)} (Kurs beim Versand{', ' + _hm(li['sent_at']) if li.get('sent_at') else ''}) – "
                     "zusätzlich gespeichert; gewertet wird der theoretische Einstieg (Open der Folgekerze)"))
    if risk and abs(cur - E) / risk >= STRONG_DEVIATION_R:
        worse = sg * (cur - E) > 0                # Kurs schon in Gewinnrichtung gelaufen -> spaeterer Einstieg ungünstiger
        rows.append(_row("Abweichung", f"Kurs weicht bereits {fnum(abs(cur - E) / risk, 2)} R vom Einstieg ab "
                         f"({'ungünstig' if worse else 'günstig'} für einen späteren Einstieg)"))
    rows.append(_row("Vorzeichen", "Einstieg + = Kurs in Gewinnrichtung; Stop/Ziel/Schwelle + = noch nicht erreicht"))
    return rows


def description(A):
    """Kurzbeschreibung des Trades (S.3 der PDF) - traegt ALLE Angaben der frueheren, ausfuehrlichen Telegram-Meldung."""
    t = A["trade"]
    long = A["direction"] == "LONG"
    mode = _mode(A)
    te, px, lab = _entry_line(A)
    status = ("Einstieg gebucht" if A.get("entry_booked")
              else "wartet auf Einstieg (Folgekerze noch nicht eröffnet, z. B. Markt geschlossen)")
    lines = [
        _row("Symbol / Richtung", f"{t['symbol']} · {A['direction']} ({'Kauf' if long else 'Verkauf'}) · Variante {_variant(A)}"),
        _row("Status", status),
        _row("Signal-Kerze", f"Schluss {fde_de(A['cutoff'])} (4h-Kerze {pd.Timestamp(A['sig_start']).strftime('%H:%M')}–{pd.Timestamp(A['cutoff']).strftime('%H:%M')} UTC)"),
        _row("Grund", _reason(A)),
        _row("Einstieg", f"{te} · Kurs {px} ({lab})"),
        _row("Stop", f"{fprice(A['stop0'])} (Safety Line bei Kerze Bruch+4, fest) → 1R = {fprice(A['risk'])} ({fnum(A['risk'] / A['E'] * 100, 2)} % vom Einstieg)"),
        _row("Ziel", _goal(A)),
    ]
    lv = t.get("exit_level") or {}
    if mode in ("CPLUS", "D") and lv.get("threshold") is not None:
        if mode == "D":
            lines.append(_row("Aktueller Stop", f"≈ {fprice(lv['threshold'])} (bei Einstieg)"))
        else:
            lines.append(_row("Aktuelle Schwelle", f"≈ {fprice(lv['threshold'])} (bei Einstieg) · Notfallnetz ≈ {fprice(lv['net'])}"))
    lines += [
        _row("ATR (14, 4h)", f"{fprice(A['a'])} (= {fnum(A['a'] / A['risk'], 2) if A['risk'] else '–'} R)"),
        _row("Top-down", f"{A['td']['count']} von {A['td']['total']} Zeitrahmen stützen die Richtung ({_flags(A)})"),
    ]
    lines += _live_rows(A)
    if t.get("parent_signal_id"):
        lines.append(_row("parent_signal_id", t["parent_signal_id"]))
    if A.get("ist") is not None and A["ist"].get("netto_r") is not None:
        ist = A["ist"]
        lines.append(_row("Ausgang IST", f"{OUTCOME_DE.get(ist['outcome'], ist['outcome'])} am {fde(ist['exit_time'], False)}, "
                     f"{fnum(ist['netto_r'], 2, True)} R netto ({fnum(ist['net_pct'], 2, True)} %)"))
        if A.get("cplus_r") is not None:
            lines.append(_row("Ausgang C+ Muster", f"{OUTCOME_DE.get(A['cplus']['exit']['outcome'])} am {fde(A['cplus_exit_time'], False)}, "
                         f"{fnum(A['cplus_r'], 2, True)} R netto ({fnum(A['cplus_pct'], 2, True)} %)"
                         f"; Stufe 2 {'erreicht' if A['cplus']['stage2_idx'] is not None else 'nicht erreicht'}, "
                         f"{len(A['cplus']['swings'])} Swing-Schwelle(n)"))
        else:
            lines.append(_row("Ausgang C+ Muster", "bis zum letzten verfügbaren Kurs noch offen (nicht gewertet)"))
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
