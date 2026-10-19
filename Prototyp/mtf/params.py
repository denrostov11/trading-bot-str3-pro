# -*- coding: utf-8 -*-
"""Skalierung der bar-basierten Erkennungsparameter je Zeitrahmen.

Die kanonische Erkennung (scan_100) rechnet in 4h-KERZEN: MIN_DURATION = 90, MAX_APEX_BARS = 180,
THREE_MONTH_BARS = 390, MIN_SPACING = 6, PIVOT_K = 3, Safety-Tap-Alter 4 Monate, Fenster 540 Kerzen.
Auf Monatskerzen waeren 90 Kerzen = 7,5 Jahre - unsinnig. Darum wird je Zeitrahmen ein ANALYSEFENSTER
(in Kerzen) gewaehlt und alle fensterabhaengigen Werte proportional zur 4h-Referenz (540 Kerzen) skaliert.

  Fenster     : 1h 540 (~22 Tage) | 4h 540 (~90 Tage) | Tag 360 (~1 Jahr) | Woche 156 (~3 Jahre) | Monat 72 (6 Jahre)
  MIN_DURATION = round(90  * Fenster / 540)       MAX_APEX = round(APEX_FRAC * Fenster)   (siehe unten)
  Winkel-Normierung (THREE_MONTH_BARS) = round(390 * Fenster / 540)
  MIN_SPACING  = max(3, round(6 * sqrt(Fenster / 540)))   (Abstand zwischen Taps; Wurzel, damit er nicht zu stark schrumpft)
  PIVOT_K      = 3 bei Fenster >= 150, sonst 2 (nur Monat)
  Safety-Tap-Alter = round(Fenster-Dauer in Monaten * 4/3)   (4h: 90 Tage -> 4 Monate, wie im Original)

Anpassung v2 (Safety Line auf Tag/Woche/Monat, siehe Parameter_je_Zeitrahmen.md):
  MAX_APEX = APEX_FRAC * Fenster mit APEX_FRAC = 1/3 (1h, 4h: Originalwert 180 bleibt) bzw. 1/2 (Tag, Woche, Monat) -
  hoehere Zeitrahmen haben wenige Swings, ein Keil darf dort etwas weiter vor dem Apex stehen.
  Tag-Fenster in KALENDERtagen gerechnet (360 Handelstage ~ 504 Kalendertage bei Devisen/Aktien/Futures, nicht 360):
  Safety-Tap-Alter Tag 16 -> 22 Monate, sonst wuerden Taps am linken Rand des Fensters allein wegen Wochenenden verworfen.
Unveraendert fuer alle Zeitrahmen: Tap-Toleranz 0,25 ATR, Bruch-Toleranz 0,15 ATR, ATR(14), max. Winkel 45 Grad,
Action-Line A+ = mind. 3 Taps, Safety = mind. 2 Taps. Toris Minimum (2 Beruehrungspunkte) gilt als Rueckfall
fuer Kontextlinien hoeherer Zeitrahmen.
"""
import math
import threading
from contextlib import contextmanager
from dataclasses import dataclass

TIMEFRAMES = ["M", "W", "D", "4h", "1h"]            # Top-down-Reihenfolge
TF_LABEL = {"M": "Monat", "W": "Woche", "D": "Tag", "4h": "4h", "1h": "1h"}
WINDOW = {"1h": 540, "4h": 540, "D": 360, "W": 156, "M": 72}
WINDOW_DAYS = {"1h": 540 / 24.0, "4h": 540 * 4 / 24.0, "D": 360 * 7 / 5.0, "W": 156 * 7.0, "M": 72 * 30.4}   # Tag: Handelstage -> Kalendertage
APEX_FRAC = {"1h": 1 / 3.0, "4h": 1 / 3.0, "D": 0.5, "W": 0.5, "M": 0.5}      # MAX_APEX = APEX_FRAC * Fenster (4h: 180 wie im Original)
REF_WINDOW = 540                                   # 4h-Referenz

_LOCK = threading.RLock()
_NAMES = ("MIN_SPACING", "MIN_DURATION", "MAX_APEX_BARS", "THREE_MONTH_BARS", "MAX_SAFETY_TAP_AGE_MONTHS", "PIVOT_K")


@dataclass(frozen=True)
class TFParams:
    tf: str
    window: int
    min_duration: int
    max_apex: int
    angle_bars: int
    min_spacing: int
    k: int
    safety_age_months: int
    min_bars: int            # Mindestzahl abgeschlossener Kerzen fuer eine Analyse


def scaled(tf):
    w = WINDOW[tf]
    return TFParams(
        tf=tf, window=w,
        min_duration=round(90 * w / REF_WINDOW), max_apex=round(APEX_FRAC[tf] * w),
        angle_bars=round(390 * w / REF_WINDOW),
        min_spacing=max(3, round(6 * math.sqrt(w / REF_WINDOW))),
        k=3 if w >= 150 else 2,
        safety_age_months=max(1, round(WINDOW_DAYS[tf] * (4.0 / 3.0) / 30.4)),
        min_bars=max(30, round(90 * w / REF_WINDOW) + 12),
    )


def _s100():
    import scan_100                                 # kanonische Erkennung (Prototyp/ muss im sys.path sein)
    return scan_100


@contextmanager
def scan_params(tf):
    """Setzt die bar-basierten Konstanten von scan_100 fuer die Dauer des Blocks auf die Werte des Zeitrahmens
    und stellt sie danach wieder her (Prozess-lokal, Datei unveraendert, per Lock gegen Parallelzugriff gesichert)."""
    P = scaled(tf)
    s100 = _s100()
    with _LOCK:
        saved = {n: getattr(s100, n) for n in _NAMES}
        try:
            s100.MIN_SPACING, s100.MIN_DURATION, s100.MAX_APEX_BARS = P.min_spacing, P.min_duration, P.max_apex
            s100.THREE_MONTH_BARS, s100.MAX_SAFETY_TAP_AGE_MONTHS, s100.PIVOT_K = P.angle_bars, P.safety_age_months, P.k
            yield P
        finally:
            for n, v in saved.items():
                setattr(s100, n, v)


def param_rows():
    """Zeilen der Parametertabelle: Parameter, 4h-Original, Tag, Woche, Monat, 1h (+ Regel)."""
    s = _s100()
    orig = {"window": 540, "min_duration": s.MIN_DURATION, "max_apex": s.MAX_APEX_BARS, "angle_bars": s.THREE_MONTH_BARS,
            "min_spacing": s.MIN_SPACING, "k": s.PIVOT_K, "safety_age_months": s.MAX_SAFETY_TAP_AGE_MONTHS}
    P = {tf: scaled(tf) for tf in ("D", "W", "M", "1h")}
    rows = [
        ("Analysefenster (Kerzen)", "window", "gewählt: 1h 22 Tage, 4h 90 Tage, Tag 1 Jahr, Woche 3 Jahre, Monat 6 Jahre"),
        ("MIN_DURATION (Kerzen)", "min_duration", "90 · Fenster / 540"),
        ("MAX_APEX_BARS (Kerzen)", "max_apex", "Fenster / 3 (1h, 4h) bzw. Fenster / 2 (Tag, Woche, Monat)"),
        ("Winkel-Normierung (Kerzen)", "angle_bars", "390 · Fenster / 540"),
        ("MIN_SPACING zwischen Taps (Kerzen)", "min_spacing", "max(3, 6 · √(Fenster / 540))"),
        ("PIVOT_K (Fraktal)", "k", "3 bei Fenster ≥ 150, sonst 2"),
        ("Safety-Tap-Alter (Monate)", "safety_age_months", "Fensterdauer in Kalendertagen · 4/3 (Tag: 504 Kalendertage)"),
    ]
    out = []
    for name, key, rule in rows:
        out.append((name, orig[key], getattr(P["D"], key), getattr(P["W"], key), getattr(P["M"], key), getattr(P["1h"], key), rule))
    out += [
        ("Tap-/Bruch-Toleranz (ATR)", "0,25 / 0,15", "0,25 / 0,15", "0,25 / 0,15", "0,25 / 0,15", "0,25 / 0,15", "unverändert"),
        ("Min. Taps Action (A+) / Safety", "3 / 2", "3 / 2", "3 / 2", "3 / 2", "3 / 2", "unverändert; Rückfall Kontextlinie: 2 (Tori)"),
        ("Max. Winkel", "45°", "45°", "45°", "45°", "45°", "unverändert"),
        ("ATR-Periode", "14", "14", "14", "14", "14", "unverändert (einfacher Durchschnitt)"),
    ]
    return out


def param_table_md():
    head = "| Parameter | 4h-Original | Tag | Woche | Monat | 1h | Regel |\n|---|---|---|---|---|---|---|\n"
    return head + "\n".join("| " + " | ".join(str(c) for c in r) + " |" for r in param_rows()) + "\n"


def param_doc_md():
    """Inhalt von Parameter_je_Zeitrahmen.md: Tabelle + Begruendung der Anpassungen v2 (Safety Line auf Tag/Woche/Monat)."""
    return ("# Parameter je Zeitrahmen (Skalierung der bar-basierten Erkennung)\n\n" + param_table_md() + """
## Änderungen v2 (Safety Line auf Tag, Woche, Monat)

**Anlass.** Die Safety Line wurde auf den höheren Zeitrahmen kaum gefunden (in den ersten Mustern auf fast keinem). Geprüft wurde, ob
die Kriterien der Gegenlinie (`pick_safety`: mind. 2 Taps, intakt, richtige Seite, Safety-Tap-Alter, Konvergenz/Keil, Apex) dort zu
streng skaliert sind. Messung: 3 Symbole (SOL-USD, GBPJPY, AUDUSD) × 22 Stichtage (monatlich 01/2025–10/2026) × Tag/Woche/Monat,
jeweils nur Stichtage mit gültiger Action Line (Tag 62, Woche 60, Monat 55 Fälle).

**Ablehnungsgründe der Gegenlinien** (Summe über alle Fälle, Mehrfachnennung nicht möglich, Reihenfolge der Prüfung):

| Grund | Tag | Woche | Monat | Bewertung |
|---|---|---|---|---|
| bereits gebrochen (nicht intakt) | 835 | 337 | 157 | Regel des Nutzers, bleibt |
| divergent (Keil öffnet sich) | 278 | 112 | 17 | Keil-Regel des Nutzers, bleibt |
| Apex zu weit | 76 | 41 | 15 | **zu streng skaliert → gelockert** |
| Tap zu alt | 78 | 0 | 0 | **Skalierungsfehler (Handelstage statt Kalendertage) → korrigiert** |

**Anpassung 1 – Apex (`MAX_APEX_BARS`).** Original: Apex höchstens 180 4h-Kerzen voraus = ein Drittel des Analysefensters (540).
Bisherige Skalierung hielt das Drittel auch auf Tag/Woche/Monat (120 / 52 / 24 Kerzen). Höhere Zeitrahmen haben je Fenster viel
weniger Swings; ein Keil darf dort länger vor dem Apex stehen. Neu: **halbes Fenster** (Tag 180, Woche 78, Monat 36 Kerzen).
4h und 1h bleiben beim Originalwert 180 (Test sichert das).

**Anpassung 2 – Safety-Tap-Alter Tag.** Das Alter wird in Kalendermonaten geprüft, das Tagesfenster aber in Kerzen (360). Bei
Devisen/Aktien/Futures sind 360 Tageskerzen etwa 504 Kalendertage (Wochenenden fehlen). Mit 16 Monaten fielen Taps am linken
Fensterrand allein deshalb heraus. Neu: Fensterdauer des Tags = 504 Kalendertage → **22 Monate** (Woche 48, Monat 96 unverändert).

**Wirkung** (gleiche Stichproben, Safety Line gefunden / Fälle mit Action Line):

| | vorher | nachher |
|---|---|---|
| Tag | 19 / 62 (31 %) | 24 / 62 (39 %) |
| Woche | 14 / 60 (23 %) | 16 / 60 (27 %) |
| Monat | 3 / 55 (5 %) | 6 / 55 (11 %) |

(Anpassung 2 allein änderte in dieser Stichprobe nichts, ist aber systematisch richtig.) Geprüft und **nicht** geändert:
größere Fenster (Monat 96/120, Woche 208/260 Kerzen) — brachten keine zusätzlichen Safety Lines (Woche sogar weniger).
Ein Partner für irgendeine andere A+-Linie des Zeitrahmens existiert kaum öfter (Tag 26 / Woche 17 / Monat 6 von je ~60), eine
Umstellung der Auswahl der Hauptlinie lohnt also nicht.

**Rest.** Auf dem Monatsrahmen bleibt die Safety Line selten (rund jeder neunte Fall): 72 Kerzen ergeben nur ca. 10 Swings, die
meisten Gegenlinien sind schon gebrochen. Das ist das Ergebnis der Regeln, nicht ein Fehler. **Es wird nichts erfunden:** gibt es
keine gültige Linie, steht im Chart „keine gültige Linie nach unseren Regeln“ bzw. „keine gültige Safety Line nach unseren Regeln“.

**Technik (ohne Ergebnisänderung).** `fastlines.find_lines_fast` ersetzt die Python-Schleife von `scan_100.find_lines` durch eine
vektorisierte Variante (Ergebnisse identisch, per Test gegen scan_100 geprüft; ca. 15× schneller; flache Tagesdaten mit 400 Kerzen: Original 192 s allein für die Unterstützungsseite, jetzt 0,4 s für beide Seiten) und begrenzt die Suche hart:
höchstens 110 jüngste Pivots je Seite, höchstens 800 Kandidatenlinien vor der Duplikat-Bereinigung, Zeitbudget 6 s je Zeitrahmen
(danach „keine Linienaussage“). Normale Daten haben 10–70 Pivots je Seite, die Grenzen greifen dort nie. Die Zeitrahmen-Parameter werden als Argument übergeben; Konstanten von `scan_100` werden NICHT mehr verändert (sicher neben dem laufenden Engine-Code im selben Prozess).
""")
