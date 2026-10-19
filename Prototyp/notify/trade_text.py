# -*- coding: utf-8 -*-
"""Texte der Trade-Meldungen. Reine Formatierung vorhandener, lokal gespeicherter Werte - keine
Strategieberechnung. ALLE Zeiten in deutscher Zeit (Europe/Berlin, MEZ/MESZ).

KURZFORM (Standard, ab 19.10.2026 - Telegram-Meldungen sind bewusst kurz, alle Details stehen in der Trade-PDF):
- Eroeffnung: Kopfzeile "<Variante> · <Symbol> · <Richtung>", Einstieg (Uhrzeit + Kurs), Stop, Ziel (bzw. "Ausstieg
  nach C+" / "Ausstieg nach D"), "Details in der PDF" (+ Paper-Trading-Hinweis aus messages.render_text)
- Ereignisse (C+/D: Stufe 2, Schwelle/Stop nachgezogen, Ausstieg; Pro.1/Pro.3: Ergebnis): 1-2 Zeilen mit der Kernzahl

DETAILTEXT (trade_details_text): der fruehere ausfuehrliche Eroeffnungstext (Signal-Schluss, Status, aktueller Kurs,
Abstaende in Preis und R, Datenverzoegerung, realistischer Einstieg, parent_signal_id ...). Er geht NUR als zweite,
getrennte Nachricht raus, wenn die Trade-PDF nicht erstellt werden konnte (Rueckfall PNG/kein Anhang).
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import pandas as pd

TZ = ZoneInfo("Europe/Berlin")
STRONG_DEVIATION_R = 0.5          # ab dieser Abweichung vom Einstieg (in R) wird ausdruecklich gewarnt
DELAY_NOTE_S = 120                # ab dieser Verzoegerung wird sie in der Meldung genannt


def to_de(ts):
    """ISO/Timestamp (UTC oder mit Offset) -> aware datetime in Europe/Berlin; None bei Fehler."""
    if ts in (None, ""):
        return None
    try:
        t = pd.Timestamp(ts)
        t = t.tz_localize("UTC") if t.tzinfo is None else t
        return t.tz_convert(TZ).to_pydatetime()
    except Exception:
        return None


def fde(ts, with_date=True):
    """'16.10.2026 14:00 Uhr (MESZ)' (bzw. nur Uhrzeit)."""
    d = to_de(ts)
    if d is None:
        return "–"
    zone = {"CEST": "MESZ", "CET": "MEZ"}.get(d.tzname(), d.tzname() or "")
    if with_date:
        return f"{d.strftime('%d.%m.%Y %H:%M')} Uhr ({zone})"
    return f"{d.strftime('%H:%M')} Uhr"


def fprice(x):
    if x is None:
        return "–"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "–"
    s = f"{v:.6g}" if abs(v) < 1e5 else f"{v:.2f}"
    if "e" in s:
        s = f"{v:.8f}".rstrip("0").rstrip(".")
    return s.replace(".", ",")


def fsign(x, d=2):
    return (f"{x:+.{d}f}").replace(".", ",").replace("-", "−")


def fdist(price_diff, risk, d_price=None):
    """'+12,5 (+0,40 R)' - Preisabstand mit Vorzeichen und in R."""
    if price_diff is None:
        return "–"
    p = fprice(abs(price_diff))
    sg = "+" if price_diff >= 0 else "−"
    r = "" if not risk else f" ({fsign(price_diff / risk)} R)"
    return f"{sg}{p}{r}"


def strategy_short(sid):
    return sid.replace("Str.3 ", "")


def initial_cplus_levels(t):
    """Schwelle (Schlusskurs-Ausstieg) und Notfallnetz fuer die Einstiegskerze eines C+-Trades, aus der
    gespeicherten Safety Line (relativ zur Signalkerze). None, wenn nicht ableitbar."""
    try:
        from engine import exit_cplus as XC, exit_d as XD
        sl = t.safety_line
        if not sl:
            return None
        line = XC.make_line_fn(sl, 0)
        X = XD if t.exit_mode == "D" else XC
        thr, net, who = X.current_levels(X.new_state(), t.direction, line, 1, float(t.atr))
        return {"threshold": thr, "net": net, "source": who}
    except Exception:
        return None


def trade_details_text(t, quote=None, booked=None):
    """AUSFUEHRLICHER Eroeffnungstext (Rueckfall, wenn keine PDF entsteht). quote = livequote.fetch_quote-Ergebnis
    (oder None), booked = entry_booking.book_entry-Ergebnis (oder None = wartet auf Einstieg)."""
    long = t.direction == "LONG"
    sgn = 1.0 if long else -1.0
    sig_close = (t.booked_entry or {}).get("signal_close")
    entry = booked["price"] if booked else None
    ref_entry = entry if entry is not None else sig_close
    risk = abs(ref_entry - t.stop_initial) if ref_entry is not None else None
    lines = []
    lines.append(f"{'LONG (Kauf)' if long else 'SHORT (Verkauf)'} · {strategy_short(t.strategy_id)}")
    lines.append(f"Signal-Kerze geschlossen: {fde(t.signal_end_time or t.signal_time)}")
    if booked:
        lines.append("Status: Einstieg gebucht")
        lines.append(f"Einstieg: {fde(booked['time'])} · gebuchter Kurs {fprice(entry)}"
                     + (" (Open der Folgekerze, noch laufend)" if booked.get("partial") else ""))
    else:
        lines.append("Status: wartet auf Einstieg")
        lines.append("Einstieg: Open der nächsten 4h-Kerze (noch nicht eröffnet, z. B. Markt geschlossen)")

    cur = quote["price"] if quote else None
    if quote:
        lines.append(f"Aktueller Kurs: {fprice(cur)} (Stand {fde(quote['bar_time'], False)}, "
                     f"Versand {fde(quote.get('fetched_at') or datetime.now(timezone.utc), False)}, {quote['interval']}-Daten)")
    else:
        lines.append("Aktueller Kurs: nicht verfügbar")

    if cur is not None and ref_entry is not None and risk:
        lines.append(f"Abstand Kurs zu Einstieg: {fdist(sgn * (cur - ref_entry), risk)}")
        dev = abs(cur - ref_entry) / risk
        if dev >= STRONG_DEVIATION_R:
            # Ein SPAETERER Einstieg zum aktuellen Kurs ist ungünstig, wenn der Kurs schon in Gewinnrichtung gelaufen ist
            # (Long: höher, Short: tiefer als der gebuchte Einstieg) - günstig, wenn er dagegen gelaufen ist.
            worse = (sgn * (cur - ref_entry)) > 0
            lines.append(f"⚠ Kurs weicht bereits {fsign(dev, 2).lstrip('+')} R vom Einstieg ab "
                         f"({'ungünstig' if worse else 'günstig'} für einen späteren Einstieg).")
    lines.append(f"Stop: {fprice(t.stop_initial)} (1R = {fprice(risk)})" if risk else f"Stop: {fprice(t.stop_initial)}")
    if cur is not None and risk:
        lines.append(f"Abstand Kurs zu Stop: {fdist(sgn * (cur - t.stop_initial), risk)}")
    if t.exit_mode == "D":
        lv = initial_cplus_levels(t)
        lines.append("Ausstieg nach D (nachgezogener Stop, kein festes Ziel): Stop 0,1 ATR jenseits der mitwandernden "
                     "Safety Line, am bestätigten Zwischen" + ("tief" if long else "hoch") + " nachgezogen; "
                     "jede Berührung (auch ein Docht) löst aus.")
        if lv:
            lines.append(f"Aktueller Stop ≈ {fprice(lv['threshold'])}")
            if cur is not None and risk:
                lines.append(f"Abstand Kurs zum aktuellen Stop: {fdist(sgn * (cur - lv['threshold']), risk)}")
    elif t.exit_mode == "CPLUS":
        lv = initial_cplus_levels(t)
        lines.append("Ausstieg nach C+ (kein festes Ziel): Schlusskurs jenseits der mitwandernden Safety Line")
        if lv:
            lines.append(f"Aktuelle Schwelle ≈ {fprice(lv['threshold'])} · Notfallnetz ≈ {fprice(lv['net'])}")
            if cur is not None and risk:
                lines.append(f"Abstand Kurs zur Schwelle: {fdist(sgn * (cur - lv['threshold']), risk)}")
    else:
        lines.append(f"Ziel: {fprice(t.target)}")
        if cur is not None and risk and t.target:
            lines.append(f"Abstand Kurs zu Ziel: {fdist(sgn * (t.target - cur), risk)}")

    if quote:
        ds = quote.get("delay_s") or 0
        if ds >= DELAY_NOTE_S:
            lines.append(f"Datenverzögerung: ca. {int(round(ds / 60))} Min. (letzter Kursbalken {fde(quote['bar_time'], False)})")
        else:
            lines.append("Datenverzögerung: keine messbare")
    lines.append("Vorzeichen: Einstieg + = Kurs in Gewinnrichtung; Stop/Ziel/Schwelle + = noch nicht erreicht.")
    lines.append("Bewertet wird der theoretische Einstieg (Open der Folgekerze); der Kurs beim Versand wird "
                 "zusätzlich als realistischer Einstieg gespeichert.")
    lines.append(f"parent_signal_id: {t.parent_signal_id}")
    return "\n".join(lines)


# ------------------------------------------------------------------ KURZFORM (Telegram)
def fshort(ts):
    """'17.08. 14:00 Uhr' (deutsche Zeit, ohne Jahr/Zone - die Meldung ist ohnehin aktuell)."""
    d = to_de(ts)
    return "–" if d is None else f"{d.strftime('%d.%m. %H:%M')} Uhr"


def trade_head(t, suffix=""):
    """Kopfzeile: '<Variante> · <Symbol> · <Richtung>[ · Zusatz]' (z. B. 'Pro.1 · SOL-USD · LONG')."""
    return f"{strategy_short(t.strategy_id)} · {t.symbol} · {t.direction}" + (f" · {suffix}" if suffix else "")


def trade_opened_title(t):
    return trade_head(t)


def trade_opened_text(t, quote=None, booked=None):
    """KURZE Eroeffnungsmeldung (ohne Kopfzeile und Paper-Hinweis, die kommen aus trade_opened_title bzw.
    messages.render_text): Einstieg (Uhrzeit + Kurs), Stop, Ziel bzw. Ausstiegsregel, Hinweis auf die PDF.
    `quote` wird fuer die Kurzform nicht gebraucht (aktueller Kurs steht in der PDF)."""
    if booked and booked.get("price") is not None:
        entry = f"Einstieg: {fshort(booked['time'])} · Kurs {fprice(booked['price'])}"
    else:                                           # Folgekerze noch nicht eroeffnet (z. B. Markt zu)
        entry = f"Einstieg: ab {fshort(t.signal_end_time or t.signal_time)} · Kurs folgt"
    if t.exit_mode == "D":
        goal = "Ausstieg nach D"
    elif t.exit_mode == "CPLUS":
        goal = "Ausstieg nach C+"
    else:
        goal = f"Ziel: {fprice(t.target)}"
    return "\n".join([entry,f"Stop: {fprice(t.stop_initial)}", goal, "Details in der PDF"])


def trade_details_title(t):
    return trade_head(t, "Details (PDF nicht verfügbar)")


# ------------------------------------------------------------------ Ereignisse (C+/D und Ergebnis)
_SHORT_REASON = {"NOTFALLNETZ": "Notfallnetz", "SAFETY_CLOSE": "Safety Line", "GEWINNSCHWELLE_CLOSE": "Gewinnschwelle",
                 "STOP_INTRABAR": "Stop berührt", "TARGET": "Ziel erreicht", "STOP": "Stop getroffen",
                 "BREAK_EVEN": "Break-even"}


def reason_short(outcome):
    return _SHORT_REASON.get(outcome, str(outcome))


def _result_line(t, ev_time=None, ev_price=None):
    """'20.08. 14:00 Uhr · Kurs 77,02 · +0,98 R netto (+1,62 %)' - alle Teile nur, wenn vorhanden."""
    r = t.result or {}
    parts = []
    if ev_time or r.get("exit_time"):
        parts.append(f"{fshort(ev_time or r.get('exit_time'))}")
    px = ev_price if ev_price is not None else r.get("exit_price")
    if px is not None:
        parts.append(f"Kurs {fprice(px)}")
    parts.append(f"{fsign(r.get('netto_r', 0.0))} R netto ({fsign(r.get('net_return_pct', 0.0))} %)")
    return " · ".join(parts)


def cplus_event_title(t, ev):
    from engine import exit_cplus as XC
    k = ev["kind"]
    if k == XC.EV_STAGE2:
        return trade_head(t, "Stufe 2 erreicht")
    if k == XC.EV_TRAIL:
        return trade_head(t, "Stop nachgezogen" if t.exit_mode == "D" else "Schwelle nachgezogen")
    return trade_head(t, f"Ausstieg ({reason_short(ev.get('outcome'))})")


def cplus_event_text(t, ev):
    """Kurztext (Koerper ohne Kopfzeile) zu einem C+/D-Ereignis: die Kernzahl in 1 Zeile."""
    from engine import exit_cplus as XC
    k = ev["kind"]
    if k == XC.EV_STAGE2:
        return f"Neue Schwelle: {fprice(ev.get('level'))} (Einstand + Kosten)"
    if k == XC.EV_TRAIL:
        return f"Neuer Stop: {fprice(ev.get('level'))}" if t.exit_mode == "D" else f"Neue Schwelle: {fprice(ev.get('level'))}"
    return _result_line(t, ev.get("time"), ev.get("price"))


def closed_title(t):
    r = t.result or {}
    return trade_head(t, reason_short(r.get("outcome")))


def closed_text(t):
    """Kurztext zu einem geschlossenen Pro.1/Pro.3-Trade (Ziel / Stop / Break-even)."""
    return _result_line(t)


def realistic_vs_theoretical(t):
    """Vergleich theoretischer gegen realistischen Einstieg eines GESCHLOSSENEN Trades (nur Zusatzangabe).
    -> dict(e_theo, e_real, adverse_r, adverse_pct, r_theo, r_real, pct_theo, pct_real) oder None."""
    real = (t.realistic or {}).get("price")
    r = t.result or {}
    if real is None or r.get("status") != "closed" or not r.get("entry_open"):
        return None
    e = float(r["entry_open"])
    risk = abs(e - t.stop_initial)
    if risk <= 0:
        return None
    sgn = 1.0 if t.direction == "LONG" else -1.0
    adverse = sgn * (float(real) - e)                 # >0: realistischer Einstieg war SCHLECHTER
    adverse_pct = adverse / e * 100
    return {"e_theo": e, "e_real": float(real), "adverse_r": adverse / risk, "adverse_pct": adverse_pct,
            "r_theo": r.get("netto_r", 0.0), "r_real": r.get("netto_r", 0.0) - adverse / risk,
            "pct_theo": r.get("net_return_pct", 0.0), "pct_real": r.get("net_return_pct", 0.0) - adverse_pct}
