# -*- coding: utf-8 -*-
"""Informative Top-down-Auswertung (KEIN Filter): stuetzen die hoeheren Zeitrahmen die Trade-Richtung?

Regel v2 (Punkte, je Zeitrahmen Monat / Woche / Tag; 1h nur zur Verfeinerung, nicht mitgezaehlt):
  1. STRUKTUR der letzten Swings (je die letzten 3 bestaetigten Swing-Hochs und Swing-Tiefs, Fraktal-Pivots des Zeitrahmens):
       Hochs steigen / fallen / ohne klare Richtung  (Preise innerhalb 0,1 ATR gelten als gleich), ebenso die Tiefs.
       steigende Hochs UND Tiefs: +2 | nur eine Seite steigt, die andere ohne Richtung: +1 | fallend: -2 / -1 | sonst 0
       (gegenlaeufig = Ausweitung bzw. Verengung -> 0).
  2. LAGE des Kurses zu den Hauptlinien (naechste intakte A+-Linie je Seite; Kurs liegt per Definition ueber der Unterstuetzung
       und unter dem Widerstand):
       Kurs ueber einer steigenden oder waagerechten Unterstuetzung: +1
       Kurs unter einem fallenden oder waagerechten Widerstand:      -1   (beides zugleich: 0, Keil/Range)
       Eine fallende Unterstuetzung bzw. ein steigender Widerstand zaehlt nicht (Kanal mit Gegenneigung).
  3. BRUCH einer Linie (A+-Linie, Schlusskurs-Bruch in den letzten 6 Monats-/8 Wochen-/10 Tageskerzen, Kurs liegt noch jenseits):
       Widerstand nach oben gebrochen: +1 | Unterstuetzung nach unten gebrochen: -1.
  Summe >= +2: Aufwaertstrend | <= -2: Abwaertstrend | sonst neutral (kein klares Bild).
  Verdikt zur Trade-Richtung: LONG + Aufwaertstrend = "stützt", LONG + Abwaertstrend = "widerspricht", sonst "neutral"
  (SHORT gespiegelt). Fehlende Daten / zu wenig Swings ergeben neutral mit Hinweis.
Der 4h-Rahmen zaehlt per Definition als Stuetze (dort liegt das Signal). Gezaehlt werden Monat, Woche, Tag, 4h (= 4 Rahmen).
Rein informativ - beeinflusst weder Einstieg noch Stop noch Ziel.
"""
from .params import TF_LABEL

THRESHOLD = 2                                      # |Punkte| >= 2 -> Trend


def _minus(s):
    return s.replace("-", "−")


def _trend(vals, tol):
    """+1 steigend, -1 fallend, 0 ohne klare Richtung; None, wenn weniger als 2 Swings."""
    if len(vals) < 2:
        return None
    pairs = [(b > a + tol) - (b < a - tol) for a, b in zip(vals[:-1], vals[1:])]
    s = sum(pairs)
    return 1 if s > 0 else (-1 if s < 0 else 0)


def structure(highs, lows, tol):
    """(Punkte, Text) fuer die Swing-Struktur."""
    th, tl = _trend(highs, tol), _trend(lows, tol)
    if th is None or tl is None:
        return 0, "zu wenige Swings für die Struktur"
    if th > 0 and tl > 0:
        return 2, "höhere Hochs und höhere Tiefs"
    if th < 0 and tl < 0:
        return -2, "tiefere Hochs und tiefere Tiefs"
    if th > 0 and tl == 0:
        return 1, "höhere Hochs, Tiefs ohne klare Richtung"
    if tl > 0 and th == 0:
        return 1, "höhere Tiefs, Hochs ohne klare Richtung"
    if th < 0 and tl == 0:
        return -1, "tiefere Hochs, Tiefs ohne klare Richtung"
    if tl < 0 and th == 0:
        return -1, "tiefere Tiefs, Hochs ohne klare Richtung"
    if th > 0 and tl < 0:
        return 0, "höhere Hochs bei tieferen Tiefs (Ausweitung)"
    if th < 0 and tl > 0:
        return 0, "tiefere Hochs bei höheren Tiefs (Verengung)"
    return 0, "Hochs und Tiefs ohne klare Richtung"


def position(sup, res):
    """(Punkte, Text) fuer die Lage des Kurses zu den Hauptlinien (sup/res: dict mit 'bias' oder None)."""
    pts, parts = 0, []
    if sup and sup["bias"] in ("up", "flat"):
        pts += 1
        parts.append("Kurs über " + ("steigender" if sup["bias"] == "up" else "waagerechter") + " Unterstützung")
    if res and res["bias"] in ("down", "flat"):
        pts -= 1
        parts.append("Kurs unter " + ("fallendem" if res["bias"] == "down" else "waagerechtem") + " Widerstand")
    if sup and res and pts == 0 and len(parts) == 2:
        return 0, "Kurs zwischen Unterstützung und Widerstand (Keil/Range)"
    return pts, " und ".join(parts)


def line_break(brk, tf):
    """(Punkte, Text) fuer den juengsten Linienbruch."""
    if not brk:
        return 0, ""
    ago = brk["bars_ago"]
    when = "in der letzten Kerze" if ago == 0 else (f"vor {ago} Kerze" if ago == 1 else f"vor {ago} Kerzen")
    if brk["kind"] == "resistance":
        return 1, f"Widerstand nach oben gebrochen ({when})"
    return -1, f"Unterstützung nach unten gebrochen ({when})"


def assess(inputs, tf):
    """Reine Bewertungsfunktion (testbar): inputs = ctx.extra['bias_in']. Rueckgabe dict mit score, bias, parts, text."""
    tol = inputs.get("tol", 0.0)
    ps, ts = structure(inputs.get("highs", []), inputs.get("lows", []), tol)
    pp, tp = position(inputs.get("support"), inputs.get("resistance"))
    pb, tb = line_break(inputs.get("break"), tf)
    score = ps + pp + pb
    bias = "up" if score >= THRESHOLD else ("down" if score <= -THRESHOLD else "neutral")
    parts = [("Struktur", ps, ts), ("Lage", pp, tp), ("Bruch", pb, tb)]
    text = " · ".join(t for _, _, t in parts if t)
    return {"score": score, "bias": bias, "parts": parts, "text": text}


def _verdict(bias, long):
    if bias == "neutral":
        return None
    return (bias == "up") == long


def _legacy(ctx, long, lab):
    """Rueckfall fuer Kontexte ohne Eingaben (alte Steigungsregel)."""
    if ctx.action is None or ctx.bias in ("", "flat"):
        return None, f"{lab}: neutral – keine Richtungsaussage."
    sup = (ctx.bias == "up") == long
    return sup, f"{lab}: {'stützt' if sup else 'widerspricht'} (Steigung der Hauptlinie)."


def evaluate_tf(direction, ctx, tf):
    """Ein Zeitrahmen: dict(supports True/False/None, verdict, score, text)."""
    long = direction == "LONG"
    lab = TF_LABEL[tf]
    if getattr(ctx, "no_data", False):
        return {"supports": None, "verdict": "neutral", "score": None, "text": f"{lab}: keine Daten → neutral (keine Aussage)."}
    inputs = ctx.extra.get("bias_in") if getattr(ctx, "extra", None) else None
    if inputs is None:
        if getattr(ctx, "timeout", False):
            return {"supports": None, "verdict": "neutral", "score": None, "text": f"{lab}: Zeitbudget überschritten → neutral (keine Aussage)."}
        if ctx.action is not None:                       # alte Kontexte (nur Steigung)
            sup, text = _legacy(ctx, long, lab)
            return {"supports": sup, "verdict": "neutral" if sup is None else ("stützt" if sup else "widerspricht"), "score": None, "text": text}
        return {"supports": None, "verdict": "neutral", "score": None, "text": f"{lab}: {ctx.reason or 'keine Daten'} → neutral (keine Aussage)."}
    r = assess(inputs, tf)
    sup = _verdict(r["bias"], long)
    word = {None: "neutral", True: "stützt", False: "widerspricht"}[sup]
    trend = {"up": "Aufwärtstrend", "down": "Abwärtstrend", "neutral": "kein klares Bild"}[r["bias"]]
    why = r["text"] or "keine Hinweise"
    sc = _minus(f"{r['score']:+d}")
    if sup is None:
        text = f"{lab}: neutral ({sc}) – {trend}: {why}."
    else:
        text = f"{lab}: {word} die {direction}-Richtung ({sc}) – {trend}: {why}."
    return {"supports": sup, "verdict": word, "score": r["score"], "text": text, "parts": r["parts"]}


def evaluate(direction, ctxs, signal_line_kind=None, signal_taps=0):
    """ctxs = {tf: Ctx} fuer M, W, D, 1h. Rueckgabe: {"items": {tf: dict}, "count": int, "total": 4, "neutral": n, "against": n}."""
    items, count, neutral, against = {}, 0, 0, 0
    for tf in ("M", "W", "D"):
        it = items[tf] = evaluate_tf(direction, ctxs[tf], tf)
        if it["supports"] is True:
            count += 1
        elif it["supports"] is False:
            against += 1
        else:
            neutral += 1
    kind = "Widerstandslinie" if direction == "LONG" else "Unterstützungslinie"
    items["4h"] = {"supports": True, "verdict": "stützt", "score": None,
                   "text": f"4h: Signal – Schlusskurs bricht die {kind} ({signal_taps} Taps) → {direction} ausgelöst."}
    count += 1
    it = evaluate_tf(direction, ctxs["1h"], "1h")
    it["text"] = it["text"][:-1] + "; zur Verfeinerung des Einstiegs, nicht mitgezählt."
    it["supports"] = None
    items["1h"] = it
    return {"items": items, "count": count, "total": 4, "neutral": neutral, "against": against}


def headline(result):
    extra = []
    if result.get("neutral"):
        extra.append(f"{result['neutral']} neutral")
    if result.get("against"):
        extra.append(f"{result['against']} widersprechen")
    tail = f" ({', '.join(extra)})" if extra else ""
    return f"Top-down-Ergebnis: {result['count']} von {result['total']} Zeitrahmen (Monat, Woche, Tag, 4h) stützen die Richtung{tail}."
