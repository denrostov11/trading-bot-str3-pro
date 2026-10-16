# -*- coding: utf-8 -*-
"""Informative Top-down-Auswertung (KEIN Filter): stuetzen die hoeheren Zeitrahmen die Trade-Richtung?

Regel: Bias = Trendrichtung der Hauptlinie des Zeitrahmens (Kontextlinie aus lines.detect_context, intakt): steigende
Linie -> Aufwaertstrend (stuetzt LONG), fallende Linie -> Abwaertstrend (stuetzt SHORT), nahezu waagerecht -> seitwaerts
(keine Aussage). Keine gueltige Linie -> keine Aussage (zaehlt nicht als Stuetze). Der 4h-Rahmen zaehlt per Definition als
Stuetze (dort liegt das Signal). Gezaehlt werden Monat, Woche, Tag, 4h (= 4 Rahmen); 1h dient nur der Verfeinerung.
"""
from .params import TF_LABEL


def _side_text(ctx):
    n = len(ctx.action.taps)
    return f"{ctx.kind}, {n} Taps"


def _line_phrase(ctx):
    rising = ctx.bias == "up"
    kind = "Unterstützungslinie unter dem Kurs" if ctx.action.kind == "support" else "Widerstandslinie über dem Kurs"
    return ("steigende " if rising else "fallende ") + kind


def evaluate(direction, ctxs, signal_line_kind=None, signal_taps=0):
    """ctxs = {tf: Ctx} fuer M, W, D, 1h. Rueckgabe: {"items": {tf: dict}, "count": int, "total": 4}."""
    long = direction == "LONG"
    items, count = {}, 0
    for tf in ("M", "W", "D"):
        c = ctxs[tf]
        lab = TF_LABEL[tf]
        if c.action is None:
            items[tf] = {"supports": None, "text": f"{lab}: {c.reason} → keine Aussage."}
            continue
        if c.bias == "flat":
            items[tf] = {"supports": None, "text": f"{lab}: Seitwärts – nahezu waagerechte {'Unterstützung' if c.action.kind == 'support' else 'Widerstand'} "
                                                   f"({_side_text(c)}) → keine Richtungsaussage."}
            continue
        up = c.bias == "up"
        sup = (up and long) or ((not up) and (not long))
        base = f"{lab}: {'Aufwärtstrend' if up else 'Abwärtstrend'} – {_line_phrase(c)} ({_side_text(c)})"
        items[tf] = {"supports": sup,
                     "text": base + (f" → {direction}-Richtung bestätigt." if sup else f" → widerspricht der {direction}-Richtung: Vorsicht.")}
        count += 1 if sup else 0
    kind = "Widerstandslinie" if direction == "LONG" else "Unterstützungslinie"
    items["4h"] = {"supports": True, "text": f"4h: Signal – Schlusskurs bricht die {kind} ({signal_taps} Taps) → {direction} ausgelöst."}
    count += 1
    c = ctxs["1h"]
    if c.action is None:
        items["1h"] = {"supports": None, "text": f"1h: {c.reason} → Verfeinerung nur über die 4h-Levels."}
    else:
        word = {"up": "Aufwärtstrend", "down": "Abwärtstrend", "flat": "Seitwärts"}[c.bias]
        items["1h"] = {"supports": None, "text": f"1h: {word} im Detail – {_line_phrase(c) if c.bias != 'flat' else 'waagerechte Linie'} "
                                                 f"({_side_text(c)}); zur Verfeinerung des Einstiegs, nicht mitgezählt."}
    return {"items": items, "count": count, "total": 4}


def headline(result):
    return f"Top-down-Ergebnis: {result['count']} von {result['total']} Zeitrahmen (Monat, Woche, Tag, 4h) stützen die Trade-Richtung."
