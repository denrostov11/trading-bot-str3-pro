# -*- coding: utf-8 -*-
"""Einstellungen des laufenden Bots in EINER JSON-Datei (live_settings.json im Prototyp-Ordner).

Die Datei wird bei JEDEM Durchlauf neu gelesen -> Aenderungen wirken ohne Neustart (auch waehrend des
Tests). Fehlende/kaputte Datei oder Werte -> sichere Standardwerte. Es sind ausschliesslich
Ausgabe-Einstellungen (Vorwarnungen, Anhang-Format); Strategie-Parameter stehen NICHT hier.

Beispiel / Standard:
{
 "trade_pdf":  {"enabled": true, "timeout_s": 90, "png_dpi": 220},
 "prewarn":    {"enabled": true, "minutes_before": [30, 15],
                "night_quiet": {"enabled": true, "from": "23:00", "to": "07:00"},
                "groups": ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]},
 "cycle":      {"close_delay_s": 90}
}
"""
import json, os, copy

PROTO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(PROTO, "live_settings.json")

DEFAULTS = {
    "trade_pdf": {"enabled": True, "timeout_s": 90, "png_dpi": 220},
    "prewarn": {"enabled": True, "minutes_before": [30, 15],
                "night_quiet": {"enabled": True, "from": "23:00", "to": "07:00"},
                "groups": ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]},
    "cycle": {"close_delay_s": 90},
}


def _merge(base, over):
    out = copy.deepcopy(base)
    if not isinstance(over, dict):
        return out
    for k, v in over.items():
        if k not in out:
            continue                                   # unbekannte Schluessel werden ignoriert
        if isinstance(out[k], dict):
            out[k] = _merge(out[k], v)
        elif isinstance(out[k], bool):
            if isinstance(v, bool):
                out[k] = v
        elif isinstance(out[k], (int, float)):
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                out[k] = v
        elif isinstance(v, type(out[k])):
            out[k] = v
    return out


def load(path=None):
    """Liest die Datei jedes Mal neu. Gibt IMMER ein vollstaendiges dict zurueck."""
    path = path or PATH
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    s = _merge(DEFAULTS, data)
    # Plausibilisierung
    try:
        s["trade_pdf"]["timeout_s"] = max(10, min(600, int(s["trade_pdf"]["timeout_s"])))
        s["trade_pdf"]["png_dpi"] = max(72, min(400, int(s["trade_pdf"]["png_dpi"])))
        s["prewarn"]["minutes_before"] = sorted({int(m) for m in s["prewarn"]["minutes_before"] if 1 <= int(m) <= 120},
                                               reverse=True)
        s["cycle"]["close_delay_s"] = max(30, min(600, int(s["cycle"]["close_delay_s"])))
    except Exception:
        s = copy.deepcopy(DEFAULTS)
    return s


def write_default(path=None):
    """Legt die Datei mit Standardwerten an, falls sie fehlt (ueberschreibt nie)."""
    path = path or PATH
    if os.path.exists(path):
        return False
    with open(path, "w", encoding="utf-8") as f:
        json.dump(DEFAULTS, f, indent=1, ensure_ascii=False)
    return True
