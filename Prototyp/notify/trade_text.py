# -*- coding: utf-8 -*-
"""Texte der Trade-Meldungen (A4). Reine Formatierung vorhandener, lokal gespeicherter Werte - keine
Strategieberechnung. ALLE Zeiten in deutscher Zeit (Europe/Berlin, MEZ/MESZ).

Inhalt der Eroeffnungsmeldung:
- Schlusszeit der Signal-Kerze, Einstiegszeit, gebuchter Einstiegskurs ("Einstieg gebucht") bzw.
  "wartet auf Einstieg"
- aktueller Kurs beim Versand mit Uhrzeit, Datenverzoegerung (falls messbar)
- Abstand des aktuellen Kurses zu Einstieg, Stop und Ziel - jeweils in Preis und in R
  (bei C+ statt Ziel: "Ausstieg nach C+" mit aktueller Schwelle und Notfallnetz)
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


def trade_opened_text(t, quote=None, booked=None):
    """Text der Eroeffnungsmeldung. quote = livequote.fetch_quote-Ergebnis (oder None), booked =
    entry_booking.book_entry-Ergebnis (oder None = wartet auf Einstieg)."""
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
                     f"Versand {fde(datetime.now(timezone.utc), False)}, {quote['interval']}-Daten)")
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


def cplus_event_text(t, ev):
    """Text zu einem C+-Ereignis (Stufe 2 / Schwelle nachgezogen / Ausstieg)."""
    from engine import exit_cplus as XC
    long = t.direction == "LONG"
    kind = ev["kind"]
    when = fde(ev.get("time"))
    if t.exit_mode == "D":
        return _d_event_text(t, ev, long, when)
    if kind == XC.EV_STAGE2:
        return ("\n".join([
            f"{t.direction} · Stufe 2 erreicht (Schluss ≥ +1,5 R)",
            f"Kerze: {when}",
            f"Gewinnschwelle jetzt: Einstand + Kosten = {fprice(ev.get('level'))}",
            "Ausstieg, sobald eine 4h-Kerze jenseits der günstigeren Schwelle (Safety Line oder Gewinnschwelle) schließt.",
            f"parent_signal_id: {t.parent_signal_id}"]))
    if kind == XC.EV_TRAIL:
        return ("\n".join([
            f"{t.direction} · Schwelle nachgezogen auf {fprice(ev.get('level'))}",
            f"Bestätigtes Zwischen{'tief' if long else 'hoch'} {fprice(ev.get('swing_price'))} "
            f"(Kerze {fde(ev.get('swing_time'))}), Bestätigung {when}",
            f"Schwelle = Swing {'−' if long else '+'}0,5 ATR (nur in Gewinnrichtung).",
            f"parent_signal_id: {t.parent_signal_id}"]))
    # Ausstieg
    r = t.result or {}
    reason = XC.EXIT_REASON_DE.get(ev.get("outcome"), ev.get("outcome"))
    return ("\n".join([
        f"{t.direction} · Ausstieg ({reason})",
        f"Ausstieg: {when} · Kurs {fprice(ev.get('price'))}",
        f"Ergebnis: {fsign(r.get('netto_r', 0.0))} R netto · {fsign(r.get('net_return_pct', 0.0))} % netto "
        f"(Einstieg {fprice(r.get('entry_open'))})",
        f"Dauer: {r.get('duration_days')} Tage · Stufe 2: {'ja' if r.get('cplus_stage2') else 'nein'} · "
        f"Swing-Nachziehen: {'ja' if r.get('cplus_stage3') else 'nein'}",
        f"parent_signal_id: {t.parent_signal_id}"]))


def _d_event_text(t, ev, long, when):
    """Variante D: 'Stop nachgezogen auf ...' bzw. 'Ausstieg (Grund)'."""
    from engine import exit_cplus as XC, exit_d as XD
    if ev["kind"] == XC.EV_TRAIL:
        return "\n".join([
            f"{t.direction} · Stop nachgezogen auf {fprice(ev.get('level'))}",
            f"Bestätigtes Zwischen{'tief' if long else 'hoch'} {fprice(ev.get('swing_price'))} "
            f"(Kerze {fde(ev.get('swing_time'))}), Bestätigung {when}",
            f"Stop = Swing {'−' if long else '+'}0,5 ATR (nur in Gewinnrichtung); es gilt der günstigere von Linien-Stop und Swing-Stop.",
            f"parent_signal_id: {t.parent_signal_id}"])
    r = t.result or {}
    reason = XD.EXIT_REASON_DE.get(ev.get("outcome"), ev.get("outcome"))
    return "\n".join([
        f"{t.direction} · Ausstieg ({reason})",
        f"Ausstieg: {when} · Kurs {fprice(ev.get('price'))}",
        f"Ergebnis: {fsign(r.get('netto_r', 0.0))} R netto · {fsign(r.get('net_return_pct', 0.0))} % netto "
        f"(Einstieg {fprice(r.get('entry_open'))})",
        f"Dauer: {r.get('duration_days')} Tage · Stop am Zwischen{'tief' if long else 'hoch'} nachgezogen: "
        f"{'ja' if r.get('d_swing') else 'nein'}",
        f"parent_signal_id: {t.parent_signal_id}"])


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
