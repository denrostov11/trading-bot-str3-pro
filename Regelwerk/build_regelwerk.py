# -*- coding: utf-8 -*-
"""Erzeugt das Regelwerk-PDF "Strategie 3 Pro" (Einsteiger-Niveau, Deutsch, mit Umlauten).

Aufruf (System-Python 3.12 mit reportlab; die venv des Bots enthaelt nur matplotlib und wird
bewusst NICHT veraendert, weil dort der Zwei-Monats-Test laeuft):

    python build_regelwerk.py

Ausgabe: Regelwerk_Strategie3Pro.pdf (neben diesem Skript).
Schrift: Arial aus C:\\Windows\\Fonts (Unicode: ae/oe/ue/ss als echte Umlaute).

Alle Zahlen stammen aus Spezifikation UND Code (Stand 11.10.2026):
  Prototyp/scan_100.py (Linienerkennung), Prototyp/engine/*.py, SPEC_CLEANED.md, DECISIONS.md,
  VARIANT_MATRIX.csv sowie den Laufdaten in Prototyp/paper_runtime_2monate (nur gelesen).
Dieses Skript liest KEINE Geheimnisse (.env) und veraendert nichts ausser der PDF-Ausgabe.
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table,
                                TableStyle, KeepTogether, NextPageTemplate, PageBreak, CondPageBreak)
from reportlab.graphics.shapes import Drawing, Line, Rect, String, Circle, Polygon
from reportlab.graphics import renderPDF

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Regelwerk_Strategie3Pro.pdf")
STAND = "11.10.2026"

# ---------------------------------------------------------------- Schriften
FD = r"C:\Windows\Fonts"
pdfmetrics.registerFont(TTFont("Arial", os.path.join(FD, "arial.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Bold", os.path.join(FD, "arialbd.ttf")))
pdfmetrics.registerFont(TTFont("Arial-Italic", os.path.join(FD, "ariali.ttf")))
pdfmetrics.registerFont(TTFont("Arial-BoldItalic", os.path.join(FD, "arialbi.ttf")))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold",
                              italic="Arial-Italic", boldItalic="Arial-BoldItalic")

# ---------------------------------------------------------------- Farben
NAVY = colors.HexColor("#1f2d4d")
TEAL = colors.HexColor("#0f766e")
GREY = colors.HexColor("#5b6477")
LIGHT = colors.HexColor("#f3f5f9")
LINE = colors.HexColor("#c9d0de")
GREEN, GREEN_BG = colors.HexColor("#1a9e5c"), colors.HexColor("#e8f5ee")
BLUE, BLUE_BG = colors.HexColor("#2f6fb5"), colors.HexColor("#e8f1fb")
AMBER, AMBER_BG = colors.HexColor("#d98e04"), colors.HexColor("#fff4d6")
PURPLE, PURPLE_BG = colors.HexColor("#6d3fc0"), colors.HexColor("#efe9fb")
RED = colors.HexColor("#c0392b")

# ---------------------------------------------------------------- Stile
S = {}
S["body"] = ParagraphStyle("body", fontName="Arial", fontSize=9.3, leading=12.6, textColor=colors.black,
                           spaceAfter=3.5)
S["small"] = ParagraphStyle("small", parent=S["body"], fontSize=8.2, leading=10.6, textColor=GREY)
S["cell"] = ParagraphStyle("cell", parent=S["body"], fontSize=8.5, leading=11, spaceAfter=0)
S["cellb"] = ParagraphStyle("cellb", parent=S["cell"], fontName="Arial-Bold")
S["cellh"] = ParagraphStyle("cellh", parent=S["cell"], fontName="Arial-Bold", textColor=colors.white)
S["h1"] = ParagraphStyle("h1", fontName="Arial-Bold", fontSize=17, leading=21, textColor=NAVY,
                         spaceBefore=4, spaceAfter=6, keepWithNext=1)
S["h2"] = ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12, leading=15, textColor=TEAL,
                         spaceBefore=8, spaceAfter=3, keepWithNext=1)
S["h3"] = ParagraphStyle("h3", fontName="Arial-Bold", fontSize=10, leading=13, textColor=NAVY,
                         spaceBefore=5, spaceAfter=2, keepWithNext=1)
S["title"] = ParagraphStyle("title", fontName="Arial-Bold", fontSize=26, leading=30, textColor=NAVY,
                            spaceAfter=4)
S["sub"] = ParagraphStyle("sub", fontName="Arial", fontSize=11.5, leading=15, textColor=GREY, spaceAfter=6)
S["bul"] = ParagraphStyle("bul", parent=S["body"], leftIndent=11, bulletIndent=2, spaceAfter=2)
S["boxt"] = ParagraphStyle("boxt", parent=S["body"], fontName="Arial-Bold", fontSize=9.6, spaceAfter=2)
S["boxb"] = ParagraphStyle("boxb", parent=S["body"], fontSize=9, leading=12, spaceAfter=2)

W = A4[0] - 36 * mm  # nutzbare Breite


def P(t, st="body"):
    return Paragraph(t, S[st])


def H1(t):
    return Paragraph(t, S["h1"])


def H2(t):
    return Paragraph(t, S["h2"])


def H3(t):
    return Paragraph(t, S["h3"])


def BUL(items, st="bul"):
    return [Paragraph(i, S[st], bulletText="\u2022") for i in items]


def TBL(rows, widths, header=True, zebra=True, head_bg=NAVY, fs=None):
    """Tabelle mit Zeilenumbruch in Zellen. rows: Liste von Listen (Text oder Flowable)."""
    data = []
    for ri, r in enumerate(rows):
        line = []
        for c in r:
            if isinstance(c, str):
                line.append(Paragraph(c, S["cellh"] if (header and ri == 0) else S["cell"]))
            else:
                line.append(c)
        data.append(line)
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("GRID", (0, 0), (-1, -1), 0.4, LINE),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), head_bg))
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if (i % 2) == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(st))
    return t


def BOX(kind, title, paras, width=None):
    """Farbiger Kasten. kind: beispiel (blau) / aktiv (gruen) / unklar (gelb) / geplant (violett)."""
    bg, bd = {"beispiel": (BLUE_BG, BLUE), "aktiv": (GREEN_BG, GREEN), "unklar": (AMBER_BG, AMBER),
              "geplant": (PURPLE_BG, PURPLE)}[kind]
    inner = [Paragraph(title, S["boxt"])]
    for p in paras:
        inner.append(Paragraph(p, S["boxb"]) if isinstance(p, str) else p)
    t = Table([[inner]], colWidths=[width or W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg),
                           ("LINEBEFORE", (0, 0), (0, -1), 3.2, bd),
                           ("BOX", (0, 0), (-1, -1), 0.5, bd),
                           ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return KeepTogether([t, Spacer(1, 5)])


def TAG(kind):
    """Kleines Etikett fuer Tabellenzellen."""
    col, txt = {"aktiv": ("#1a9e5c", "AKTIV"), "unklar": ("#d98e04", "UNKLAR / PRÜFEN"),
                "diag": ("#2f6fb5", "NUR DIAGNOSE"), "geplant": ("#6d3fc0", "GEPLANT")}[kind]
    return f'<font color="{col}"><b>{txt}</b></font>'


# ---------------------------------------------------------------- Seitenvorlagen
def _footer(c, doc, band_color, band_text=None):
    c.saveState()
    w, h = A4
    if band_text:
        c.setFillColor(band_color)
        c.rect(0, h - 11 * mm, w, 11 * mm, stroke=0, fill=1)
        c.setFillColor(colors.white)
        c.setFont("Arial-Bold", 9.5)
        c.drawString(18 * mm, h - 7.6 * mm, band_text)
    else:
        c.setStrokeColor(LINE)
        c.setLineWidth(0.5)
        c.line(18 * mm, h - 12 * mm, w - 18 * mm, h - 12 * mm)
        c.setFillColor(GREY)
        c.setFont("Arial", 7.8)
        c.drawString(18 * mm, h - 10 * mm, "Regelwerk Strategie 3 Pro  \u00b7  Einsteiger-Fassung")
        c.drawRightString(w - 18 * mm, h - 10 * mm, f"Stand {STAND}")
    c.setStrokeColor(band_color if band_text else LINE)
    c.line(18 * mm, 13 * mm, w - 18 * mm, 13 * mm)
    c.setFillColor(GREY)
    c.setFont("Arial", 7.8)
    c.drawString(18 * mm, 8.5 * mm, "Paper-Trading \u2013 keine echte Order. Keine Anlageberatung.")
    c.drawRightString(w - 18 * mm, 8.5 * mm, f"Seite {doc.page}")
    c.restoreState()


def on_normal(c, doc):
    _footer(c, doc, LINE)


def on_planned(c, doc):
    _footer(c, doc, PURPLE, "GEPLANT / BESCHLOSSEN \u2013 NOCH NICHT IM BOT  (diese Regeln gelten heute NICHT)")


def on_cover(c, doc):
    c.saveState()
    c.setFillColor(NAVY)
    c.rect(0, A4[1] - 8 * mm, A4[0], 8 * mm, stroke=0, fill=1)
    c.restoreState()
    _footer(c, doc, LINE)


# ---------------------------------------------------------------- Grafiken
def _lab(d, x, y, text, col, size=7.2, bg=colors.HexColor("#101624")):
    """Beschriftung mit dunklem Hintergrund, damit Linien den Text nicht durchstreichen."""
    wdt = pdfmetrics.stringWidth(text, "Arial", size)
    d.add(Rect(x - 1.5, y - 2, wdt + 3, size + 2.5, fillColor=bg, strokeColor=None))
    d.add(String(x, y, text, fontName="Arial", fontSize=size, fillColor=col))


def drawing_wedge():
    """Schema: Keil aus Action Line (steigende Unterstuetzung) und Safety Line (fallender Widerstand),
    Bruch nach unten -> SHORT. Kein echter Kurs."""
    w, h = W, 215
    d = Drawing(w, h)
    d.add(Rect(0, 0, w, h, fillColor=colors.HexColor("#101624"), strokeColor=None))
    sx = lambda x: 12 + x * (w - 24) / 230.0
    sy = lambda y: 10 + y * (h - 20) / 120.0
    cy, ca = colors.HexColor("#3fd0e0"), colors.HexColor("#e0a526")
    # Linien (verlaengert bis x=222)
    d.add(Line(sx(8), sy(26), sx(222), sy(26 + 0.185 * 214), strokeColor=cy, strokeWidth=1.7))
    d.add(Line(sx(14), sy(100), sx(222), sy(100 - 0.19 * 208), strokeColor=ca, strokeWidth=1.7,
               strokeDashArray=[5, 3]))
    # Kerzen: (x, open, close, high, low)
    cand = [(20, 62, 55, 66, 50), (34, 55, 33, 58, 30), (48, 36, 48, 52, 33), (62, 48, 70, 91, 45),
            (76, 70, 52, 73, 45), (90, 52, 45, 56, 38), (104, 47, 62, 66, 38), (118, 62, 56, 80.3, 53),
            (132, 56, 62, 66, 50), (146, 58, 38, 62, 36), (160, 37, 33, 41, 30)]
    for x, o, c_, hi, lo in cand:
        col = colors.HexColor("#16c784") if c_ >= o else colors.HexColor("#ea3943")
        d.add(Line(sx(x), sy(lo), sx(x), sy(hi), strokeColor=col, strokeWidth=0.8))
        d.add(Rect(sx(x) - 3.2, sy(min(o, c_)), 6.4, max(sy(max(o, c_)) - sy(min(o, c_)), 1),
                   fillColor=col, strokeColor=col))
    # Taps (Action Line y = 26 + 0.185*(x-8)); Safety: y = 100 - 0.19*(x-14)
    for x in (34, 90, 132):
        d.add(Circle(sx(x), sy(26 + 0.185 * (x - 8) - 0.5), 6, strokeColor=cy, fillColor=None, strokeWidth=1.2))
    for x in (62, 118):
        d.add(Circle(sx(x), sy(100 - 0.19 * (x - 14)), 6, strokeColor=ca, fillColor=None, strokeWidth=1.2))
    # Bruchkerze bei x=146 (Schluss klar unter der Action Line)
    d.add(Line(sx(146), sy(0), sx(146), sy(125), strokeColor=colors.HexColor("#ffffff"), strokeWidth=0.5,
               strokeDashArray=[2, 3]))
    # Einstieg = Open der naechsten Kerze, Stop = Safety bei Bruchkerze + 4 (4 Kerzen = 56 Einheiten)
    stop_y = 100 - 0.19 * (146 + 4 * 14 - 14)
    d.add(Line(sx(153), sy(37), sx(222), sy(37), strokeColor=colors.white, strokeWidth=0.9))
    d.add(Line(sx(153), sy(stop_y), sx(222), sy(stop_y), strokeColor=colors.HexColor("#ea3943"),
               strokeWidth=1.1, strokeDashArray=[4, 2]))
    d.add(Line(sx(153), sy(12), sx(222), sy(12), strokeColor=colors.HexColor("#16c784"), strokeWidth=1.1,
               strokeDashArray=[4, 2]))
    # Beschriftungen (mit Hintergrund)
    wh = colors.white
    _lab(d, sx(8), sy(20), "Action Line (steigend, 3 Taps)", cy, 7.6)
    _lab(d, sx(14), sy(108), "Safety Line (fallend, 2 Taps) – muss intakt sein", ca, 7.6)
    _lab(d, sx(104), sy(118), "Keil: die Linien laufen aufeinander zu (Apex rechts)", colors.HexColor("#9aa3b5"), 7.6)
    _lab(d, sx(84), sy(26), "Bruchkerze: Schluss unter", wh)
    _lab(d, sx(84), sy(22), "der Action Line = Signal", wh)
    _lab(d, sx(155), sy(39.5), "Einstieg (SHORT): Open nächste Kerze", wh)
    _lab(d, sx(150), sy(stop_y + 2.5), "Stop = Safety bei Bruch+4 (fest)", colors.HexColor("#ff7b72"))
    _lab(d, sx(155), sy(14), "Ziel = nächste S/R-Zone", colors.HexColor("#16c784"))
    _lab(d, sx(8), sy(2), "Schema, keine echten Kurse. Bruch nach OBEN (fallende Action Line) = alles gespiegelt = LONG.",
         colors.HexColor("#9aa3b5"), 6.8)
    return d


def drawing_ladder():
    """Gold-Beispiel: Preisleiter mit Stop, Einstieg, +1R, +2R und ATR-Klammer."""
    w, h = W * 0.60, 150
    d = Drawing(w, h)
    sy = lambda p: 12 + (p - 1970) * (h - 26) / 80.0
    ax = 46
    d.add(Line(ax, sy(1970), ax, sy(2050), strokeColor=GREY, strokeWidth=1))
    levels = [(2040, "Ziel +2R  2.040 $", colors.HexColor("#16a34a")),
              (2020, "+1R  2.020 $", colors.HexColor("#16a34a")),
              (2000, "Einstieg  2.000 $", NAVY),
              (1980, "Stop (Safety Line)  1.980 $  = −1R", RED)]
    for p, t, col in levels:
        d.add(Line(ax - 5, sy(p), ax + 8, sy(p), strokeColor=col, strokeWidth=1.6))
        d.add(String(ax + 14, sy(p) - 3, t, fontName="Arial-Bold" if p in (2000,) else "Arial",
                     fontSize=8.2, fillColor=col))
    # 1R-Klammer
    bx = ax - 14
    d.add(Line(bx, sy(2000), bx, sy(1980), strokeColor=RED, strokeWidth=1))
    d.add(Line(bx - 3, sy(2000), bx + 3, sy(2000), strokeColor=RED, strokeWidth=1))
    d.add(Line(bx - 3, sy(1980), bx + 3, sy(1980), strokeColor=RED, strokeWidth=1))
    d.add(String(bx - 12, (sy(2000) + sy(1980)) / 2 - 3, "1R", fontName="Arial-Bold", fontSize=8.5,
                 fillColor=RED))
    # ATR-Klammer rechts
    rx = w - 70
    d.add(Line(rx, sy(2010), rx, sy(2000), strokeColor=TEAL, strokeWidth=1))
    d.add(Line(rx - 3, sy(2010), rx + 3, sy(2010), strokeColor=TEAL, strokeWidth=1))
    d.add(Line(rx - 3, sy(2000), rx + 3, sy(2000), strokeColor=TEAL, strokeWidth=1))
    d.add(String(rx + 6, (sy(2010) + sy(2000)) / 2 - 3, "1 ATR = 10 $", fontName="Arial", fontSize=8,
                 fillColor=TEAL))
    return d


# ---------------------------------------------------------------- Inhalt
story = []

# ===== SEITE 1: Titel + 10 Saetze
story += [Spacer(1, 6),
          Paragraph("Regelwerk Strategie 3 Pro", S["title"]),
          Paragraph("Der Paper-Trading-Bot in einfachen Worten: Begriffe, alle aktiven Regeln, die Varianten "
                    "Pro.1 bis Pro.8 &ndash; und was erst geplant ist.", S["sub"])]
story.append(TBL([
    ["Stand", f"{STAND}. Geprüft gegen Code (<i>Prototyp\\scan_100.py</i>, <i>Prototyp\\engine\\*.py</i>) und "
              "Spezifikation (<i>SPEC_CLEANED.md</i>, <i>DECISIONS.md</i>, <i>VARIANT_MATRIX.csv</i>) sowie die "
              "Laufdaten des Zwei-Monats-Tests (nur gelesen)."],
    ["Laufender Test", "Zwei-Monats-Paper-Test, 17.08.2026 12:00 bis <b>17.10.2026 12:00</b> (Europe/Berlin), "
                       "94 Instrumente, Pro.1&ndash;Pro.8, ein Prüfzyklus pro Stunde."],
    ["Zielgruppe", "Einsteiger. Jeder Fachbegriff wird erklärt (Teil 1, Glossar am Ende)."],
], [28 * mm, W - 28 * mm], header=False, zebra=False))
story.append(Spacer(1, 5))
story.append(TBL([
    [P("<b>So liest du dieses Dokument</b>", "cell"),
     P(TAG("aktiv") + " = gilt heute im Bot (im Code geprüft)", "cell"),
     P(TAG("unklar") + " = Spezifikation und Code passen nicht zusammen oder es ist nicht eindeutig", "cell"),
     P(TAG("geplant") + " = beschlossen/geplant, <b>noch NICHT im Bot</b> (violette Seiten, Teil 3)", "cell")],
], [30 * mm, 42 * mm, 56 * mm, W - 128 * mm], header=False, zebra=False))
story.append(H2("Der Bot in 10 Sätzen"))
ten = [
    ["1", "Der Bot ist ein <b>reiner Simulator (Paper-Trading)</b>: Er „handelt“ nur auf dem Papier, hat keine "
          "Verbindung zu einem Broker und kann keine echte Order auslösen."],
    ["2", "Er holt Kursdaten von <b>Yahoo Finance</b> (1-Stunden-Kerzen) und baut daraus <b>4-Stunden-Kerzen</b>. "
          "Nur vollständig abgeschlossene Kerzen zählen."],
    ["3", "Er beobachtet <b>94 Instrumente</b> (Krypto, Devisen, Futures, Indizes, ein paar Aktien/ETFs) und prüft "
          "jede Stunde, ob eine neue 4h-Kerze fertig ist."],
    ["4", "Er sucht eine <b>Action Line</b> (Trendlinie mit mindestens 3 Berührungen) und eine gegenläufige "
          "<b>Safety Line</b>; zusammen bilden sie einen <b>Keil</b>, der sich zuspitzt."],
    ["5", "<b>Signal</b> = eine 4h-Kerze <b>schließt</b> deutlich jenseits der Action Line (Break) und es gibt eine "
          "passende Safety Line. Bruch nach unten = Short, nach oben = Long. Abpraller (Bounce) handelt der Bot nicht."],
    ["6", "<b>Einstieg</b> zum Eröffnungskurs der <b>nächsten</b> Kerze &ndash; nie rückwirkend."],
    ["7", "<b>Stop</b> fest an der Safety Line (Stand: 4 Kerzen nach dem Bruch). <b>Ziel</b> = nächste "
          "Unterstützungs-/Widerstandszone. Ein 2R-Mindestabstand wird heute nur <i>protokolliert</i>, nicht "
          "erzwungen."],
    ["8", "Ergebnisse werden in <b>R</b> (Vielfache des Risikos) und in <b>Prozent</b> gemessen, jeweils brutto und "
          "netto (nach Gebühren und Slippage). Es gibt kein Kapitalkonto."],
    ["9", "<b>Acht Varianten</b> (Pro.1&ndash;Pro.8) bewerten dasselbe Signal mit verschiedenen Zusatzfiltern; "
          "Pro.1 ist die ungefilterte Basis, Pro.8 ist noch nicht konfiguriert."],
    ["10", "Telegram ist <b>nur Ausgabe</b> (Trade-Meldungen mit Chart, Systemmeldungen). Die lokalen Dateien sind die "
           "verbindliche Quelle; ein Telegram-Fehler ändert nie einen Trade."],
]
story.append(TBL(ten, [8 * mm, W - 8 * mm], header=False))
story.append(Spacer(1, 6))
story.append(BOX("unklar", "Wichtig vorab: zwei Dinge, die man leicht falsch versteht",
                 ["<b>1.</b> In der alten Spezifikation steht „Ziel mindestens 2R, sonst kein Trade“. Im Code ist das heute "
                  "<b>nur eine Diagnose</b> (<i>would_reject_rr_DIAGNOSTIC</i>) &ndash; im laufenden Test haben 237 von 332 "
                  "Trades ein R:R unter 2 (Details in Teil 2.3).",
                  "<b>2.</b> Berichte (Wochen-/30-Tage-PDF) und Telegram-Lesebefehle sind gebaut, aber im Dauerlauf "
                  "<b>nicht angeschlossen</b>: Es werden heute keine Berichte automatisch erzeugt oder versandt "
                  "(Teil 2.9 / 2.11)."]))

# ===== TEIL 1: Grundbegriffe
story.append(PageBreak())
story.append(H1("Teil 1 &ndash; Grundbegriffe einfach erklärt"))
story.append(H2("1.1 R &ndash; das Maß für Gewinn und Verlust"))
story.append(P("<b>R ist das Risiko, das du bei einem Trade von vornherein eingeplant hast:</b> der Abstand vom "
               "Einstiegspreis bis zum Stop. Gewinne und Verluste werden als Vielfache davon gemessen. "
               "<b>+2R</b> heißt: doppelt so viel gewonnen, wie man maximal verlieren wollte. "
               "<b>&minus;1R</b> heißt: der Stop wurde getroffen. Der Vorteil: Ein Trade in Gold und ein Trade in "
               "Bitcoin sind sofort vergleichbar, obwohl die Preise völlig verschieden sind."))
story.append(P("<b>Beispiel Gold</b> (nur zum Verstehen, keine echten Kurse): Einstieg 2.000 $, Safety Line / Stop "
               "1.980 $. Das Risiko beträgt <b>1R = 20 $</b>. Ein Ziel bei 2.040 $ wäre +2R. "
               "Fällt Gold auf 1.980 $, sind es &minus;1R."))
story.append(TBL([
    [drawing_ladder(),
     P("<b>Und die Kosten?</b> Der Bot rechnet immer auch <b>netto</b>. Gold ist im Bot ein Future: Gebühr 0,03 % pro "
       "Seite (je 0,6 $ bei 2.000 $) plus 0,05 ATR Slippage pro Seite (je 0,5 $). Zusammen ca. 2,2 $ = <b>0,11R</b>. "
       "Ein Treffer bei +2R bringt also netto etwa <b>+1,89R</b>, ein Stop-Verlust kostet netto etwa "
       "<b>&minus;1,11R</b>.", "boxb")],
], [W * 0.60 + 4, W - W * 0.60 - 4], header=False, zebra=False))
story.append(H2("1.2 ATR &ndash; die typische Kerzenlänge"))
story.append(P("<b>ATR</b> (Average True Range) sagt, wie weit sich ein Instrument in einer Kerze <i>typischerweise</i> "
               "bewegt. Im Bot (<i>scan_100.atr</i>): <b>14 Kerzen, Zeitrahmen 4h</b>. Pro Kerze wird die "
               "„True Range“ bestimmt, das ist der größte der drei Werte: Hoch&minus;Tief, |Hoch&minus;Vortagesschluss|, "
               "|Tief&minus;Vortagesschluss| (Lücken zählen also mit). Daraus wird der <b>einfache Durchschnitt der letzten "
               "14 Werte</b> gebildet (kein Wilder-Glätten). Beispiel: <b>1 ATR = 10 $</b> bei Gold heißt: eine "
               "4h-Kerze ist typischerweise etwa 10 $ lang. Dein Stop-Abstand von 20 $ wäre dann <b>2 ATR</b>."))
story.append(P("Der Bot misst damit seine Toleranzen in ATR statt in Euro/Dollar: Eine Berührung zählt zum Beispiel, "
               "wenn der Kurs höchstens 0,25 ATR an der Linie liegt. So passt dieselbe Regel für Bitcoin, Gold und "
               "Euro/Dollar."))
story.append(H2("1.3 Kerzen und Linien"))
story.append(TBL([
    ["Begriff", "So einfach erklärt"],
    ["Kerze", "Ein Zeitabschnitt (hier 4 Stunden) als Balken: <b>Open</b> (Start), <b>High</b> (Höchstkurs), "
              "<b>Low</b> (Tiefstkurs), <b>Close</b> (Schlusskurs). Grün = Schluss über Start, rot = darunter."],
    ["Docht (Wick)", "Der dünne Strich über/unter dem Körper: ein kurzer Ausschlag. Dochte zählen für <b>Berührungen</b> "
                     "(Taps), aber <b>nicht</b> für den Bruch."],
    ["Schlusskurs", "Der letzte Kurs einer Kerze. Er allein entscheidet beim Break: Ein Docht, der die Linie durchsticht, "
                    "ist noch kein Signal."],
    ["Zeitrahmen 4h aus 1h", "Yahoo liefert 1-Stunden-Kerzen. Der Bot fasst je 4 zu einer 4h-Kerze zusammen (Beginn "
                             "00, 04, 08, 12, 16, 20 Uhr UTC; im Sommer +2 Std. = deutsche Zeit). Eine 4h-Kerze zählt "
                             "erst, wenn ihre Zeit abgelaufen ist <b>und</b> alle ihre Stunden da sind."],
    ["Long / Short", "Long = auf steigende Kurse setzen, Short = auf fallende. Im Paper-Trading rein rechnerisch."],
    ["Action Line", "Die Trendlinie, die gebrochen werden muss, damit ein Signal entsteht. Steigende Linie unter dem "
                    "Kurs (Unterstützung) → Bruch nach unten = <b>Short</b>. Fallende Linie über dem Kurs (Widerstand) → "
                    "Bruch nach oben = <b>Long</b>."],
    ["Tap (Berührung)", "Ein Moment, in dem der Kurs die Linie berührt (Docht genügt). Zwischen zwei Taps müssen "
                        "mindestens 6 Kerzen liegen."],
    ["Safety Line", "Eine zweite Trendlinie auf der <b>Gegenseite</b> (bei Short: fallender Widerstand darüber). Sie "
                    "bestimmt den <b>Stop</b>. Sie muss <i>intakt</i> sein, also darf keine Kerze sie per Schlusskurs "
                    "durchbrochen haben."],
    ["Keil (Wedge) / Apex", "Action und Safety Line laufen aufeinander zu wie ein Keil. Ihr gedachter Schnittpunkt heißt "
                            "<b>Apex</b>. Parallele oder auseinanderlaufende Linien sind <b>ungültig</b>."],
    ["Break / Bounce", "<b>Break</b> = Kerze schließt jenseits der Action Line, die Linie ist gebrochen. <b>Bounce</b> = "
                       "Abprall an der Linie. Der heutige Bot kennt <b>nur Break</b>; Bounce ist Teil der geplanten "
                       "Tori-Linie (Teil 3)."],
    ["Break-even", "Wenn ein Trade genug im Plus ist, wird der Stop auf den Einstiegspreis nachgezogen, damit aus "
                   "einem Gewinner kein Verlierer mehr wird (Regel BE-1, Teil 2.4)."],
    ["Paper-Trading", "Handeln mit Spielgeld auf dem Papier: Alles wird simuliert und gespeichert, aber nichts "
                      "wird gekauft."],
    ["Backtest", "Die Strategie wird auf <b>vergangenen</b> Daten durchgespielt (hier 01.01.2025&ndash;30.06.2026), "
                 "Kerze für Kerze, ohne in die Zukunft zu schauen."],
    ["Universum", "Die Liste der überwachten Instrumente (Teil 2.1)."],
], [34 * mm, W - 34 * mm]))
story.append(Spacer(1, 4))
story.append(drawing_wedge())
story.append(P("<b>Abbildung:</b> So sieht ein SHORT-Signal schematisch aus. Die türkise Linie (Action) wird durch den "
               "Schlusskurs gebrochen; die gelbe, gestrichelte Linie (Safety) gibt den Stop vor.", "small"))

# ===== TEIL 2: aktive Regeln
story.append(CondPageBreak(75 * mm))
story.append(Spacer(1, 8))
story.append(H1("Teil 2 &ndash; Alle Regeln, die der Bot heute anwendet " + TAG("aktiv")))
story.append(P("Jede Regel wurde im Code nachgelesen. Wo Spezifikation und Code auseinandergehen, steht das "
               "ausdrücklich dabei und ist in Teil 2.12 gesammelt."))
story.append(H2("2.1 Datenbasis, Universen, Handelszeitrahmen"))
story.append(TBL([
    ["Punkt", "Regel (heute)", "Quelle"],
    ["Datenquelle", "<b>Yahoo Finance</b> über <i>yfinance</i>, 1-Stunden-Kerzen (live: letzte 240 Tage). Keine zweite "
                    "Datenquelle. Ein lokaler Cache sammelt die Daten additiv und wird nie gekürzt; Abrufe mit bis zu 3 Wiederholungen "
                    "bei Fehlern.", "dataaccess.py, cache.py"],
    ["4h-Bau", "Je 4 Stunden-Kerzen = eine 4h-Kerze, Raster ab <b>00:00 UTC</b> (00/04/08/12/16/20 UTC) für <b>alle</b> "
               "Instrumente. Nur <b>abgeschlossene</b> Kerzen (<i>is_final</i>): Zeit vorbei <b>und</b> alle 4 "
               "Stunden-Kerzen vorhanden. Unvollständige Kerzen erzeugen nie ein Signal.", "aggregate_4h.py"],
    ["Mindest-Historie", "Mindestens 90 abgeschlossene 4h-Kerzen, sonst wird das Instrument übersprungen "
                         "(INSUFFICIENT_HISTORY).", "orchestrate.py"],
    ["Handelszeitrahmen", "Ausschließlich <b>4h</b>. Geprüft wird stündlich, bewertet wird jede neu abgeschlossene "
                          "4h-Kerze. War der PC aus, werden verpasste Kerzen beim nächsten Start der Reihe nach "
                          "nachgeholt (ohne Blick in die Zukunft).", "run_loop.py, orchestrate.py"],
    ["Universum 94", "<b>94 Instrumente</b> mit Datenquelle: 15 Krypto, 20 Devisen, 31 Futures (Metalle, Energie, "
                     "Agrar, Aktienindex-Futures), 10 Indizes, 18 Aktien/ETFs. Sechs Wunschwerte ohne Yahoo-Quelle sind "
                     "deaktiviert (Nickel, Zink, Blei, Eisenerz, Propan, LNG). <i>Namensfalle:</i> „DAX Futures“, „FTSE100 Fut“ "
                     "usw. sind in Wahrheit Kassa-Indizes.", "scan_100.py (Liste), instruments.py"],
    ["Universum 94plus_Aktien", "94 + 83 weitere Aktien aus dem Nasdaq-100 = <b>177</b> Symbole. Nur im Backtest.",
     "backtest_config.json"],
    ["Universum Maximum", "Geplant: <b>652</b> Symbole (518 Aktien, 55 Krypto, 38 Devisen, 31 Futures, 10 Indizes). "
                          "Tatsächlich haben nur ca. <b>195</b> davon Daten (Yahoo-Sperre am 09.08.2026) &ndash; "
                          "ergo " + TAG("unklar") + ": kein echter 652er-Test.", "Backtest-Ordner, frozen/"],
], [32 * mm, W - 32 * mm - 40 * mm, 40 * mm]))

story.append(H2("2.2 Linienkonstruktion (Action Line, Safety Line, Keil)"))
story.append(P("Alle Werte stammen aus <i>scan_100.py</i> und gelten für Action- <b>und</b> Safety-Kandidaten, soweit "
               "nicht anders vermerkt."))
story.append(TBL([
    ["Kriterium", "Wert im Code", "Erklärung"],
    ["Eckpunkte (Pivots)", "Fraktal mit K = 3", "Ein Tief/Hoch zählt, wenn es das niedrigste/höchste von je 3 Kerzen links und "
                           "rechts ist. Erst nach 3 abgeschlossenen Kerzen bestätigt."],
    ["Linie", "durch 2 Pivots", "Unterstützung durch zwei Tiefs, Widerstand durch zwei Hochs; mindestens 6 Kerzen Abstand "
                                 "zwischen den beiden."],
    ["Berührung (Tap)", "Docht höchstens 0,25 ATR von der Linie (auch leicht durchstochen)",
     "Taps brauchen mindestens 6 Kerzen Abstand; liegen sie näher, wird nur der extremere gezählt."],
    ["Bruch", "Schlusskurs mehr als 0,15 ATR jenseits der Linie", "Die Bruchkerze zählt nicht mehr als Tap. Die erste "
                                                                   "solche Kerze ist die Bruchkerze."],
    ["Action Line „A+“", "mindestens <b>3 Taps</b>, Dauer mindestens <b>90 Kerzen</b>, Winkel unter <b>45°</b>",
     "Dauer = von der ersten Verankerung bis zum Bruch. Winkel wird auf ein Fenster von 390 Kerzen und 25 % des Kurses "
     "normiert (flach bis mäßig steil)."],
    ["Safety Line", "mindestens <b>2 Taps</b>, Dauer ≥ 90 Kerzen, Winkel ≤ 45°, <b>intakt</b>, richtige Seite",
     "Bei Short muss sie über der Action Line liegen, bei Long darunter. Intakt = kein Schlusskurs hat sie durchbrochen."],
    ["Alter der Safety-Taps", "ältester Tap höchstens <b>4 Monate</b> alt", "Kalenderzeit, nicht Kerzenzahl (Nutzer-Regel "
                                                                              "17.08.2026)."],
    ["Keil / Apex", "Abstand schrumpft nach rechts; Apex höchstens <b>180 Kerzen</b> voraus",
     "Gemessen an der Bruchkerze. 180 Kerzen sind bei durchgehend gehandelten Märkten etwa 30 Tage. Eine zusätzliche "
     "Kalendergrenze (45 Tage) wurde zurückgenommen."],
    ["Auswahl der Safety", "die <b>nächstgelegene</b> gültige Gegenlinie", "Bewertet wird der Abstand zur Action Line in ATR "
                                                                           "plus 0,02 pro Kerze seit dem letzten Tap."],
    ["Mehrere Brüche", "höchste Bewertung gewinnt", "Bewertung = Taps × 100 + Dauer × 0,1 − Winkel × 0,5."],
    ["Keine Safety Line", "<b>kein Signal</b>", "Status NO_CONVERGING_SAFETY &ndash; wird nicht im Ledger protokolliert."],
], [31 * mm, 52 * mm, W - 83 * mm]))
story.append(Spacer(1, 3))
story.append(BOX("unklar", "Unklar / prüfen: Mindestdauer und Erkennungsfenster",
                 ["<b>Mindestdauer.</b> Entschieden wurde „21 Kalendertage statt starrer 90 Kerzen“ (DECISIONS #6). Im Code steht aber "
                  "weiterhin die <b>90-Kerzen-Grenze</b> (<i>MIN_DURATION = 90</i>), eine 21-Tage-Prüfung existiert nicht. "
                  "Folge: Bei Krypto sind 90 Kerzen etwa 15 Tage, bei Aktien/Indizes (nur 1&ndash;2 vollständige 4h-Kerzen pro Handelstag, "
                  "siehe 2.11) deutlich mehr.",
                  "<b>Erkennungsfenster.</b> Der Live-Lauf sucht Linien in der <b>gesamten</b> gespeicherten 4h-Historie "
                  "(wächst täglich). Der Backtest nutzte ein festes Fenster von <b>540 Kerzen</b> (ca. 4 Monate). Ob das die "
                  "Ergebnisse spürbar verschiebt, ist nicht geprüft."]))

story.append(H2("2.3 Einstieg, Stop, Ziel"))
story.append(TBL([
    ["Baustein", "Regel (heute)"],
    ["Signal", "Die <b>gerade abgeschlossene</b> 4h-Kerze ist die Bruchkerze (kein Rückwärts-Suchen). Bruch von unten nach "
               "oben = LONG, von oben nach unten = SHORT. Danach wird alles in einem unveränderlichen <b>Snapshot</b> "
               "(mit eindeutiger <i>parent_signal_id</i>) festgehalten: Linien, Taps, ATR, Stop, Ziel, Datenqualität."],
    ["Einstieg", "Zum <b>Eröffnungskurs der nächsten Kerze</b>. Das ist der Bezugspunkt für R und Prozent. Zusätzlich "
                 "wird als Slippage 0,05 ATR gerechnet (nur über die Kosten, kein Doppelabzug)."],
    ["Stop", "Der Wert der <b>Safety Line, 4 Kerzen nach der Bruchkerze</b> (Linie nach vorn verlängert), "
             "<b>fest eingefroren</b>. Er wandert nie nach (außer durch Break-even). Ist der Stop auf der falschen Seite "
             "des Einstiegs oder gleich null Abstand: <b>REJECTED_STOP</b>, kein Trade. Eine Stop-Weite in ATR wird "
             "berechnet, aber nur diagnostisch (Vorschlag 0,5&ndash;6 ATR, <i>nicht</i> filternd)."],
    ["Ziel", "Die <b>nächste S/R-Zone</b> in Handelsrichtung, mindestens 0,5R vom Einstieg entfernt. Zone = "
             "Häufung von mindestens <b>2 Pivot-Punkten</b> (K=3, alle Hochs und Tiefs der Historie), die höchstens "
             "<b>0,6 ATR</b> auseinanderliegen; Zonenpreis = Mittelwert. <b>Gibt es keine Zone, wird kein Trade eröffnet.</b>"],
], [26 * mm, W - 26 * mm]))
story.append(Spacer(1, 3))
story.append(BOX("unklar", "Die 2R-Prüfung &ndash; ehrlich dargestellt",
                 ["Die Spezifikation (SPEC_CLEANED §5, DECISIONS #2/#3) sagt: Wird die nächste Zone nicht mit ≥ 2,0R "
                  "erreicht, dann <b>REJECTED_RR</b> und kein Trade. <b>Im Code ist das nicht aktiv.</b> "
                  "<i>baseline.py</i> berechnet nur das Flag <i>would_reject_rr_DIAGNOSTIC</i> (R:R &lt; 2 oder keine Zone) und "
                  "speichert es. Grund: Die S/R-Definition ist als „Nutzerentscheidung offen“ eingestuft (Prompt 2, Präzisierung 8).",
                  "<b>Folge im Live-Test (Stand 11.10.2026):</b> 318 akzeptierte Signale, davon wären 239 an der 2R-Regel "
                  "gescheitert. 46 hatten gar keine Zone (kein Trade). Von den 332 eröffneten Trades hatten <b>237 ein "
                  "R:R unter 2</b> (Median 1,35; kleinster Wert 0,51). Die S/R-Zonen bestimmen also de facto das Ziel, "
                  "obwohl die Spezifikation sie noch als „diagnostisch“ führt."]))

story.append(H2("2.4 Trade-Verwaltung nach dem Einstieg"))
story.append(TBL([
    ["Baustein", "Regel (heute)"],
    ["Prüfung", "Kerze für Kerze (4h) ab der Einstiegskerze. Trifft das Tief (Long) bzw. Hoch (Short) den Stop → "
                "<b>STOP</b>, Ausstieg zum Stop-Preis. Trifft die Kerze das Ziel → <b>TARGET</b>, Ausstieg zum Ziel-Preis. "
                "Berührt eine Kerze <b>beides</b>, gilt konservativ der <b>Stop zuerst</b> (markiert als AMBIGUOUS_INTRABAR)."],
    ["Break-even BE-1", "Erreicht die Kerze einen Gewinn von <b>0,3 %</b> (Devisen, Indizes) bzw. <b>1,0 %</b> (alle anderen: Krypto, "
                        "Aktien/ETFs, Futures) ab Einstieg, wird der Stop auf <b>Einstieg ± 0,02 ATR</b> gezogen "
                        "(nur nachziehen, nie verschlechtern). Die Bewegung gilt erst ab der <b>nächsten</b> Kerze. Ein späterer Treffer heißt "
                        "<b>BREAK_EVEN</b>. Wirkt nur bei Pro.2&ndash;Pro.8."],
    ["Break-even BE-0", "Kein Nachziehen: der Stop bleibt bis zum Ende. Gilt für <b>Pro.1</b> (reine Basis)."],
    ["Weitere BE-Modi", "BE-2 (+0,75R), BE-3 (+1,0R), BE-4 (+1,0 ATR) sind im Code vorhanden, werden aber von keiner "
                        "aktiven Variante genutzt."],
    ["Kosten", "Immer <b>brutto und netto</b> parallel. Gebühr je Seite: Devisen 0,02 %, Indizes 0,03 %, Futures 0,03 %, "
               "Aktien 0,02 %, Krypto 0,10 %. Dazu Slippage 0,05 ATR je Seite. Netto-R = Brutto-R − (2 × Slippage + "
               "Gebühr × (Einstieg + Ausstieg)) / Risiko."],
    ["Messgrößen", "R-Werte und Prozent (Summe der Einzeltrade-Prozent, „gleicher Einsatz je Trade“), dazu MFE/MAE "
                   "(bester/schlechtester Verlauf in R), Dauer, Trefferquote, Profit-Faktor, Drawdown."],
    ["Positionsgröße / Risiko", "<b>Keine.</b> Es gibt kein Kapitalkonto, keine Positionsgrößen, keine Wiederanlage. Jeder "
                                "Trade zählt gleich. Die Konstanten 100.000 / 1.000 / 0,5 % in <i>reporting.py</i> sind nur Platzhalter "
                                "(Kontosimulation aus)."],
    ["Sperren je Variante", "Pro Instrument <b>nur ein offener Trade</b>, nach Schließung <b>24 Stunden Pause</b>, und "
                            "<b>jede Linie nur einmal</b> (gleiche Art, Ankerpreis ±0,1 %, Steigung ±5 %). Jede Variante führt "
                            "das <b>getrennt</b>: Ein Trade in Pro.2 blockiert Pro.3 nicht."],
    ["Datenqualität", "Doppelte/unsortierte Zeitstempel → TIMESERIES_ISSUE. Bei Futures gilt ein Tag als „Rollover-Verdacht“, "
                      "wenn Kerzenlänge oder Lücke das 5-Fache des Medians der letzten 20 Kerzen übersteigen; liegt das Signal "
                      "innerhalb ±2 Tagen davon → <b>REJECTED_DATA_QUALITY</b>."],
    ["TEST_END", "<b>Nur im Backtest:</b> am 30.06.2026 noch offene Trades werden zum letzten Schlusskurs bewertet "
                 "(Mark-to-Market, mit denselben Kosten) und als <b>TEST_END</b> getrennt ausgewiesen; nie gefüllte Aufträge "
                 "werden gestrichen. Im Live-Test gibt es dafür " + TAG("unklar") + " keine automatische Schlussbewertung "
                 "(Teil 2.12)."],
], [30 * mm, W - 30 * mm]))
story.append(Spacer(1, 3))
story.append(BOX("beispiel", "Beispiel Gold, Schritt für Schritt (SHORT-Spiegelung gilt analog)",
                 ["Gold bricht nach oben durch die fallende Action Line, die Kerze schließt bei 2.000 $ (Signal). "
                  "Die steigende Safety Line steht 4 Kerzen später bei 1.980 $ → <b>Stop 1.980 $</b>, 1R = 20 $. Nächste Zone "
                  "bei 2.030 $ → <b>Ziel 2.030 $</b> = nur 1,5R (der Bot würde den Trade heute trotzdem eröffnen). Die nächste "
                  "Kerze eröffnet bei 2.001 $ → <b>Einstieg 2.001 $</b>. Steigt Gold um 1,0 % (2.021 $), rutscht der Stop auf "
                  "2.001 $ + 0,02 ATR (0,2 $) = 2.001,2 $ (BE-1). Fällt der Kurs danach zurück, endet der Trade als "
                  "BREAK_EVEN mit kleinem Netto-Minus (Kosten)."]))

# ===== Varianten
story.append(H2("2.5 Die Varianten Pro.1 bis Pro.8"))
story.append(P("Alle Varianten bewerten <b>denselben Snapshot</b> (gleiche Linien, gleicher Stop, gleiches Ziel). Eine Variante "
               "darf nie Linien ändern, sie darf nur zusätzlich <b>filtern</b>. Mögliche Urteile: PASS (handeln), FAIL "
               "(abgelehnt), NOT_EVALUABLE (Daten fehlen, wird <i>nicht</i> als bestanden gewertet), DIAGNOSTIC (nur "
               "protokollieren), NOT_CONFIGURED. Die Zahlen unter „Live“ sind eine Momentaufnahme der Laufdaten vom "
               "11.10.2026 (318 akzeptierte Signale, 332 Trades)."))
var_rows = [
    ["Variante", "Was sie anders macht", "Live (11.10.)"],
    ["<b>Pro.1</b><br/>Baseline<br/>BE-0", "Keine Zusatzfilter: jedes gültige Signal wird gehandelt. Der Stop bleibt bis zum "
     "Schluss an der Safety Line (kein Break-even). Dient als Maßstab für alle anderen Varianten.",
     "80 Trades"],
    ["<b>Pro.2</b><br/>Daily-EMA200<br/>BE-1", "Richtungsfilter auf Tagesbasis: Long nur, wenn der letzte abgeschlossene Tagesschluss "
     "<b>über</b> dem 200-Tage-EMA liegt, Short nur darunter. Braucht mindestens 250 Tageskerzen. "
     "<b>Im Live-Lauf werden keine Tagesdaten geladen</b> → immer NOT_EVALUABLE („Daily-Daten fehlen“). Im Backtest "
     "funktioniert der Filter.", "318 von 318 NOT_EVALUABLE, <b>0 Trades</b>"],
    ["<b>Pro.3</b><br/>RVOL<br/>BE-1", "Volumenbestätigung: Das Volumen der Bruchkerze muss mindestens das <b>1,2-Fache</b> des "
     "Medians der 20 Kerzen davor sein. Braucht verwertbares Volumen; Devisen haben keines → NOT_EVALUABLE. "
     "Auch Indizes/Futures nur, wenn die Daten plausibel sind (mind. 95 % gültig, nicht durchgehend 0).",
     "263 NOT_EVALUABLE, 50 PASS, 5 FAIL; 21 Trades"],
    ["<b>Pro.4</b><br/>ATR-Regime<br/>BE-1", "Volatilitätsfilter: Die Schwankung (ATR in % vom Kurs) muss im mittleren Bereich liegen &ndash; "
     "zwischen dem <b>20. und 90. Perzentil</b> der letzten 100 Kerzen. Nicht zu ruhig, nicht extrem.",
     "220 PASS, 98 FAIL; 76 Trades"],
    ["<b>Pro.5</b><br/>Kombi<br/>BE-1", "Alle drei Filter gleichzeitig: Pro.2 <b>und</b> Pro.3 <b>und</b> Pro.4 müssen PASS sein. "
     "Ist einer nicht auswertbar, ist das Ergebnis NOT_EVALUABLE. Da Pro.2 live nie auswertbar ist, handelt Pro.5 live nie.",
     "318 von 318 NOT_EVALUABLE, <b>0 Trades</b>"],
    ["<b>Pro.6</b><br/>Breakout-Qualität<br/>BE-1", "Die Bruchkerze muss kräftig sein: Körper mindestens <b>50 %</b> der Kerzenlänge, "
     "Kerzenlänge <b>0,8 bis 2,5 ATR</b>, Schluss im äußeren Viertel in Handelsrichtung (Long: oberes 25 %, "
     "Short: unteres 25 %).", "119 PASS, 199 FAIL; 56 Trades"],
    ["<b>Pro.7</b><br/>Trendqualität<br/>BE-1", "Nur Diagnose: ADX(14), Choppiness(14) und R² (30 Kerzen) werden berechnet und "
     "gespeichert, aber <b>ohne Schwelle</b>. Praktisch handelt Pro.7 jedes Signal, ist also Pro.1 <i>mit</i> BE-1 &ndash; "
     "gut für den Vergleich, was Break-even allein bewirkt.", "318 DIAGNOSTIC; 99 Trades"],
    ["<b>Pro.8</b><br/>Daily-Struktur", "<b>Nicht konfiguriert</b> (PRO8_NOT_CONFIGURED). Die algorithmische Definition steht aus, "
     "also handelt die Variante nie.", "0 Trades"],
]
story.append(TBL(var_rows, [31 * mm, W - 31 * mm - 40 * mm, 40 * mm]))
story.append(Spacer(1, 3))
story.append(BOX("unklar", "Unklar / prüfen: Vergleichbarkeit der Varianten",
                 ["Pro.1 läuft mit <b>BE-0</b>, Pro.2&ndash;8 mit <b>BE-1</b>. Unterschiede zwischen Pro.1 und einer Filtervariante "
                  "stammen deshalb teils vom Break-even, nicht nur vom Filter. Der Vergleich Pro.1 ↔ Pro.7 zeigt den "
                  "reinen Break-even-Effekt. Die Spezifikation (VARIANT_MATRIX.csv, SPEC §9c) nennt zusätzlich "
                  "„Pro.1 + BE-1“ als aktive Kontrolle &ndash; im Lauf ist sie <b>nicht</b> aktiv."]))

# ===== laufender Test, Backtests
story.append(H2("2.6 Der laufende Zwei-Monats-Paper-Test"))
story.append(TBL([
    ["Eigenschaft", "Wert"],
    ["Fenster", "17.08.2026 12:00 bis <b>17.10.2026 12:00</b> Europe/Berlin (2 Kalendermonate = 61 Tage). Das Ende steht fest im "
                "Start-Manifest und verschiebt sich bei einem Neustart nicht."],
    ["Umfang", "94 Instrumente, Pro.1&ndash;Pro.8, ein Zyklus pro Stunde, keine echten Orders, Telegram nur Ausgabe."],
    ["Neustart-fest", "Autostart bei Anmeldung; nach PC-Pause werden verpasste Kerzen nachgeholt. Der PC muss aber ab und zu "
                      "laufen (sonst altern Daten; Lücken über 200 Kerzen = ca. 33 Tage werden nicht mehr vollständig aufgeholt)."],
    ["Stand der Laufdaten (11.10.2026, 15:50)", "411 geprüfte Kandidaten (318 akzeptiert, 93 wegen Datenqualität/Rollover abgelehnt, fast nur "
     "Futures). 332 Trades: 295 geschlossen, 37 offen. Nach Klasse: <b>Devisen 232, Krypto 94, Index 3, Futures 3, Aktien 0.</b> "
     "Summe Netto-R der geschlossenen Trades: Pro.1 +4,0 (65 Trades), Pro.3 +13,1 (20), Pro.4 +14,3 (69), Pro.6 +6,9 (52), "
     "Pro.7 +0,3 (89). Das ist eine Momentaufnahme mit kleinen Stichproben und <b>keine</b> Aussage über die Strategie."],
    ["Ende des Tests", "Der Loop beendet sich selbst, meldet „Stufen-Endzeit erreicht“ und lässt Zustände liegen. Offene Trades "
                       "bleiben offen und erscheinen als „unrealisiert“ (siehe 2.12)."],
], [38 * mm, W - 38 * mm]))
story.append(H2("2.7 Backtests (18 Monate, 01.01.2025&ndash;30.06.2026)"))
story.append(P("Deterministisch, mit eingefrorenen Rohdaten, Kerze für Kerze ohne Blick in die Zukunft (Tagesdaten für "
               "Pro.2/Pro.5 nur bis zum Entscheidungszeitpunkt). Gleiche Regeln wie live; Pro.1 = BE-0, Rest = BE-1; "
               "die 4h-Kerze wird konservativ ausgewertet (Stop vor Ziel). Ergebnis Universum 94 (netto, Berichte noch vom "
               "Code vor den Korrekturen vom 08.10.2026, daher nur zur Orientierung, <b>keine Empfehlung</b>):"))
story.append(TBL([
    ["Variante", "Trades", "Netto-R", "Summe Einzeltrade-%", "Profit-Faktor"],
    ["Pro.1 Baseline", "542", "−60,2", "+73,4", "0,80"],
    ["Pro.2 Daily-EMA200", "321", "−38,0", "−52,5", "0,62"],
    ["<b>Pro.3 RVOL</b>", "<b>184</b>", "<b>+8,3</b>", "<b>+100,5</b>", "<b>1,31</b>"],
    ["Pro.4 ATR-Regime", "620", "−49,4", "−19,7", "0,71"],
    ["Pro.5 Kombi", "52", "−7,4", "−45,4", "0,46"],
    ["Pro.6 Breakout-Qualität", "502", "−46,4", "−7,4", "0,68"],
    ["Pro.7 Trendqualität", "842", "−79,9", "+41,7", "0,66"],
    ["Pro.8", "0", "&ndash;", "&ndash;", "&ndash;"],
], [58 * mm, 22 * mm, 24 * mm, 40 * mm, W - 144 * mm]))
story.append(Spacer(1, 3))
story.append(P("<b>Wichtig beim Lesen:</b> R und Prozent können gegensätzlich aussehen (Pro.1: −60 R, aber +73 %), weil beide Maße die Trades "
               "unterschiedlich gewichten (R relativ zur Stop-Weite, Prozent relativ zum Kurs). Nur Pro.3 war in R und in Prozent im Plus. In den Universen 94plus_Aktien (177) "
               "und Maximum (nur ca. 195 mit Daten) zeigte sich dasselbe Bild.", "small"))

# ===== Sicherheit, Telegram
story.append(H2("2.8 Sicherheitsregeln"))
story += BUL([
    "<b>Nur Paper-Trading.</b> Es gibt im Code keine Broker-Anbindung und keine Orderfunktion. Jede Trade-Meldung trägt den Hinweis "
    "„Paper-Trading – keine echte Order“.",
    "<b>Telegram ist nur Ausgabe.</b> 10 Gruppen: eine je Variante (Pro.1&ndash;8), eine für den Vergleich, eine für „STR3 System“. "
    "Aktiv werden gesendet: Trade eröffnet (mit Chartbild), Trade beendet (Ziel/Stop/Break-even), Systemmeldungen (Start, "
    "Herzschlag alle 12 Stunden, Fehler, Zyklus-Zusammenfassung nur bei Aktivität).",
    "<b>Ein Telegram-Fehler verändert nie einen Trade.</b> Zuerst wird gerechnet und gespeichert, Telegram läuft danach in einem "
    "abgesicherten Block.",
    "<b>Geheimnisse</b> (Bot-Token, Chat-IDs) liegen nur in <i>Prototyp\\.env</i>, nicht in Code, Logs oder Dokumenten.",
    "<b>Lesende Befehle</b> (/status, /offene_trades, /bilanz, /vergleich …, insgesamt 18) sind mit Nutzer-Allowlist, ohne "
    "eval/Shell und ohne Konfigänderung gebaut &ndash; " + TAG("unklar") + ": im Dauerlauf <b>nicht angeschlossen</b> (kein Abruf "
    "eingehender Nachrichten), also derzeit nicht bedienbar.",
    "Nicht erlaubt und nicht gebaut: Läufe starten/stoppen, Parameter ändern, Backtests auslösen, Orders. Das braucht ein eigenes, "
    "streng abgesichertes Design und eine ausdrückliche Freigabe.",
])
story.append(H2("2.9 Berichte und Bilder"))
story += BUL([
    "<b>Berichte:</b> Erzeugung (<i>run_reports.generate_reports</i>: Wochen-PDF mit 7 Tagen, „rollierend 30 Tage“, Vergleichs-PDF) "
    "und Zustellung (<i>notify.live.deliver_reports</i>) sind gebaut und getestet. <b>Aufgerufen wird beides im Dauerlauf nie</b> "
    "(<i>run_reports</i> wird in <i>run_loop.py</i> importiert, aber nicht benutzt); im Laufordner existiert kein "
    "<i>reports</i>-Ordner. Berichte entstehen derzeit nur auf Handanstoß. „Rollierend 30 Tage“ ist <b>kein</b> Kalendermonat.",
    "<b>Trade-Bilder:</b> Zu jedem neuen Setup entsteht ein Chart (Kerzen, Action-/Safety-Linie, Taps, Bruchmarker, "
    "Einstieg/Stop/Ziel) und geht mit der Meldung an die Varianten-Gruppe. Auflösung nur <b>95 dpi</b> (<i>trade_chart.py</i>) &ndash; "
    "deshalb unscharf. Im Bild heißt „Einstieg“ der Schlusskurs der Bruchkerze, der simulierte Einstieg ist aber der Eröffnungskurs "
    "der Folgekerze.",
])
story.append(H2("2.10 Parameter auf einen Blick"))
story.append(TBL([
    ["Parameter", "Wert", "Parameter", "Wert"],
    ["Zeitrahmen", "4h (aus 1h)", "Zyklus", "stündlich"],
    ["Pivot-Fraktal", "K = 3", "Tap-Toleranz / Bruch-Toleranz", "0,25 ATR / 0,15 ATR"],
    ["Mindestabstand Taps", "6 Kerzen", "ATR", "14 Kerzen, einfacher Durchschnitt"],
    ["Taps Action / Safety", "≥ 3 / ≥ 2", "Maximaler Winkel", "45°"],
    ["Mindestdauer Linie", "90 Kerzen (Code)", "Apex", "≤ 180 Kerzen"],
    ["Safety-Tap-Alter", "≤ 4 Monate", "Stop", "Safety bei Bruch+4, fest"],
    ["Ziel", "nächste Zone, ≥ 0,5R", "S/R-Zone", "≥ 2 Pivots, ≤ 0,6 ATR"],
    ["2R-Mindestabstand", "nur Diagnose", "Slippage", "0,05 ATR je Seite"],
    ["Gebühr je Seite", "FX 0,02 · Index 0,03 · Futures 0,03 · Aktien 0,02 · Krypto 0,10 %", "Sperren",
     "1 Trade/Instrument, 24 h Pause, Linie nur 1×"],
], [34 * mm, 48 * mm, 40 * mm, W - 122 * mm]))

story.append(H2("2.11 Bekannte Einschränkungen"))
story.append(TBL([
    ["Einschränkung", "Was genau (aus Code/Laufdaten belegt)"],
    ["Pro.2 und Pro.5 handeln live nie", "Im Live-Lauf werden keine Tagesdaten übergeben → NOT_EVALUABLE bei allen 318 Signalen → "
                                         "0 Trades. Im Backtest funktionierten sie."],
    ["Pro.3 großteils nicht auswertbar", "263 von 318 Signalen NOT_EVALUABLE (hauptsächlich Devisen: kein zentrales Volumen). Nur "
                                         "55 Signale wurden tatsächlich geprüft."],
    ["Aktien und Indizes: dünne 4h-Kerzen", "Die Börsenzeiten werden nur genähert (alle Klassen Raster ab 00:00 UTC, kein Sitzungskalender). "
                                           "Belegt am Cache: Apple hat nur <b>1</b> vollständige 4h-Kerze pro Handelstag (16&ndash;20 UTC), der "
                                           "DAX 2. Im laufenden Test gab es bislang <b>0 Aktien-Trades</b>; ob das die Ursache ist, ist "
                                           + TAG("unklar") + "."],
    ["Futures oft abgelehnt", "93 Signale wurden wegen Rollover-Verdacht/Datenqualität abgelehnt, überwiegend Futures (z. B. RTY, YM, ES)."],
    ["Alle Ausstiege auf 4h-Basis", "Stop/Ziel werden pro 4h-Kerze geprüft; Ausstieg immer genau zum Stop- bzw. Zielpreis, auch wenn "
                                    "die Kerze mit einer Lücke jenseits davon eröffnet. Das ist leicht optimistisch."],
    ["Erkennung bis zu ca. 1 Stunde später", "Der Zyklus läuft stündlich, der Einstieg wird aber zum Eröffnungskurs der Kerze nach "
                                             "dem Signal gebucht. Echt handeln könnte man diesen Preis nur bei sofortiger Reaktion " + TAG("unklar") + "."],
    ["Trade-Bilder unscharf", "<i>trade_chart.py</i>: <i>dpi=95</i>."],
    ["Berichte nicht automatisch", "<i>run_reports</i> wird nie aufgerufen, kein <i>reports</i>-Ordner, kein Versand-Termin angeschlossen."],
    ["Lesebefehle nicht angeschlossen", "Befehle sind implementiert, aber nichts ruft Telegram-Nachrichten ab."],
    ["Zwei-Monats-Test ohne TEST_END", "Die Schlussbewertung offener Trades existiert nur im Backtest-Code."],
    ["Backtest Universum Maximum", "Nur ca. 195 von 652 Symbolen mit Daten; Neurechnung und Neuerzeugung der Berichte zurückgestellt."],
    ["Änderungen nur lokal", "Letzter Commit im Repository: 30.09.2026; 24 Dateien sind seitdem geändert/neu und nicht committet oder gepusht (Nutzerentscheidung 08.10.2026)."],
], [48 * mm, W - 48 * mm]))

# ===== Abweichungen
story.append(H2("2.12 Wo Spezifikation und Code auseinandergehen " + TAG("unklar")))
story.append(P("Maßgeblich dafür, was der Bot <b>wirklich tut</b>, ist der Code. Die Tabelle zeigt, was die Spezifikation "
               "sagt und wie du es einordnen solltest."))
story.append(TBL([
    ["Thema", "Spezifikation", "Code (gilt)", "Offen"],
    ["Mindestdauer", "21 Kalendertage, 90-Kerzen-Regel entfällt", "90 Kerzen, keine 21-Tage-Prüfung", "angleichen oder Spez. korrigieren"],
    ["2R-Prüfung", "unter 2R → REJECTED_RR, kein Trade", "nur Flag would_reject_rr_DIAGNOSTIC; Trades mit R:R &lt; 2 laufen", "Nutzerentscheidung"],
    ["S/R-Zone", "Definition offen, nur diagnostisch", "provisorische Zonen bestimmen das Ziel; ohne Zone kein Trade", "Nutzerentscheidung"],
    ["Break-even BE-1", "Puffer 10 % der Schwelle; alter Bot prüfte alle 15 Minuten", "Puffer 0,02 ATR, Prüfung auf 4h-Kerzen",
     "prüfen, ob gewollt"],
    ["Kontrolle Pro.1+BE-1", "aktive Kontrolle neben Pro.1+BE-0", "läuft nur Pro.1+BE-0", "prüfen"],
    ["4h-Anker / Session", "FX 22:00 UTC, Futures nach CME-Sitzung, Aktien nach Handelszeit", "überall 00:00 UTC, kein Sitzungsfilter",
     "als Näherung akzeptiert (25.07.), Wirkung auf Aktien offen"],
    ["Rollover", "Linie darf keinen Rollover überspannen", "nur Nähe ±2 Tage zum Signal geprüft", "prüfen"],
    ["Alter Safety-Taps (4 Monate)", "fehlt in SPEC_CLEANED", "aktiv seit 17.08.2026", "Spez. nachführen"],
    ["RVOL (Pro.3)", "„Median von 20 vergleichbaren 4h-Kerzen“", "Median der 20 vorherigen Kerzen (nicht tageszeit-gleich)", "Begriff „vergleichbar“ klären"],
    ["Pro.2/Pro.5 live", "EMA200 aus Tagesdaten", "Tagesdaten werden live nicht geladen", "Anbindung fehlt"],
    ["Berichte / Befehle", "Wochen-/30-Tage-Berichte und Lesebefehle per Telegram", "gebaut, aber nicht verdrahtet", "Anschluss geplant"],
    ["TEST_END live", "Bewertung zum Testende", "nur im Backtest-Code", "vor 17.10. klären"],
    ["Erkennungsfenster", "540 Kerzen (Designfenster)", "Live: gesamte Historie; Backtest: 540", "Wirkung ungeprüft"],
], [31 * mm, 46 * mm, 54 * mm, W - 131 * mm]))

# ===== TEIL 3: geplant (violette Seiten)
story.append(NextPageTemplate("planned"))
story.append(PageBreak())
story.append(Paragraph("Teil 3 &ndash; Beschlossen / geplant &ndash; <font color='#6d3fc0'>noch NICHT im Bot</font>", S["h1"]))
story.append(BOX("geplant", "Lies das bitte zuerst",
                 ["Alles in diesem Teil ist <b>Entwurf bzw. Beschluss</b>, aber <b>nicht gebaut</b>. Der laufende Zwei-Monats-Test "
                  "(bis 17.10.2026 12:00) bleibt unverändert, und für den Bot gelten ausschließlich die Regeln aus Teil 2. "
                  "<b>Umsetzung erst nach dem 17.10.2026.</b> Alle Schwellen unten sind Vorschläge und werden vor dem Einsatz mit "
                  "dem Testplan geprüft."]))
story.append(H2("3.1 Neue Linie „Tori.x“ auf Basis der Tori-Trades-Methode"))
story.append(P("Strategie 3 Pro stammt ursprünglich aus Toris Trendlinien-PDF. Vier ihrer Videos wurden ausgewertet. Daraus soll eine "
               "neue Linie <b>Tori.x</b> entstehen &ndash; zunächst als eigener Strang neben Pro.1&ndash;8."))
story.append(TBL([
    ["Baustein", "Geplante Tori.x-Regel", "Heute (Pro.1)"],
    ["Analyse", "<b>Top-down</b>: Monat → Woche → Tag → 4h → 1h. Gehandelt wird auf <b>4h oder 1h</b>.", "nur 4h, keine Mehr-Zeitrahmen-Analyse"],
    ["Setups", "<b>Break</b> und <b>Bounce</b> (Abprall an der Linie).", "nur Break"],
    ["Ziel", "<b>Kein festes Ziel, kein R:R-Filter.</b> Der Trade läuft, solange die Safety Line hält.", "festes S/R-Ziel, 2R nur Diagnose"],
    ["Ausstieg", "Bei <b>Kerzen-Schluss</b> durch die Safety Line.", "fester Stop an Safety bei Bruch+4, Ausstieg intrabar"],
], [24 * mm, W - 24 * mm - 52 * mm, 52 * mm]))
story.append(H2("3.2 Ausstieg „C+“ (vom Nutzer favorisiert)"))
story.append(P("Grundidee: Der Ausstieg wird nur durch den <b>Schlusskurs</b> ausgelöst, nicht durch einen kurzen Docht. Als "
               "Absicherung gegen Abstürze und Lücken gibt es ein <b>Notfallnetz</b>. Schwellen werden in <b>R und ATR</b> statt in "
               "Euro angegeben, damit eine Regel für alle Instrumente passt &ndash; es gibt <b>keine Einzeloptimierung je Instrument</b>."))
story.append(TBL([
    ["Baustein", "Regel (Entwurf)"],
    ["Schlusskurs-Ausstieg", "Schließt eine Kerze durch die Safety Line, wird zum <b>Eröffnungskurs der nächsten Kerze</b> ausgestiegen."],
    ["Notfallnetz", "<b>1 ATR</b> jenseits der Linie. Es löst <b>sofort</b> aus (auch mitten in der Kerze), gedacht nur für Absturz/Lücke."],
    ["Stufe 1", "Bis <b>+1,5R</b>: kein Nachziehen, nur die Safety Line zählt."],
    ["Stufe 2", "Ab <b>+1,5R</b>: Gewinn-Stop auf <b>Einstand + Kosten</b>."],
    ["Stufe 3", "Nach einem <b>bestätigten Zwischentief</b> (Rücksetzer von mindestens ca. 1 ATR, danach wieder Anstieg): Stop unter das "
                "Zwischentief minus <b>½ ATR</b> Puffer."],
    ["Gewinn-Stop", "Zählt ebenfalls nur beim <b>Schlusskurs</b>; darunter liegt wieder ein Notfallnetz, <b>1 ATR</b> tiefer."],
    ["Welcher Stop gilt?", "Immer der <b>schützendere</b> von Safety Line und Gewinn-Stop (bei Long der höhere, bei Short der tiefere)."],
], [38 * mm, W - 38 * mm]))
story.append(Spacer(1, 3))
story.append(BOX("geplant", "Beispiel Gold (Rechenbeispiel, kein Datensatz)",
                 ["Einstieg 2.000 $, Safety Line 1.980 $ (1R = 20 $), 1 ATR = 10 $. <b>Stufe 1:</b> bis 2.030 $ (+1,5R) bleibt es bei "
                  "der Safety Line; Notfallnetz bei 1.970 $ (1 ATR unter der Linie). <b>Stufe 2:</b> ab 2.030 $ wandert der Gewinn-Stop auf "
                  "Einstand + Kosten, also ca. 2.002 $ (Schlusskurs-Regel, Notfallnetz 1 ATR darunter). <b>Stufe 3:</b> Gold steigt auf "
                  "2.060 $, fällt auf 2.045 $ (Rücksetzer 15 $ = 1,5 ATR, mehr als 1 ATR) und steigt wieder → Zwischentief bestätigt. "
                  "Neuer Gewinn-Stop = 2.045 − ½ ATR (5 $) = <b>2.040 $</b> (Schlusskurs-Regel, Notfallnetz bei 2.030 $)."]))
story.append(H2("3.3 Testplan für C+"))
story += BUL([
    "<b>Vorab festgelegtes Raster</b> (nichts wird nachträglich nachgebessert): Einstand-Schwelle bei <b>1R / 1,5R / 2R</b> × "
    "Puffer <b>¼ / ½ / 1 ATR</b> = <b>9 Kombinationen</b>.",
    "<b>Walk-Forward:</b> die ersten <b>12 Monate</b> zur Auswahl der Kombination, die letzten <b>6 Monate</b> zur Prüfung auf "
    "ungesehenen Daten.",
    "<b>Vergleich</b> mit zwei Referenzen: <b>B</b> = Schlusskurs-Ausstieg plus Notfallnetz, aber ohne Nachziehen; "
    "<b>D</b> = der alte Intrabar-Stop-Stil (wie heute).",
    "<b>Optionale Zusatzvariante:</b> die Hälfte der Position bei <b>+2R</b> verkaufen &ndash; <b>noch nicht entschieden</b>.",
])
story.append(H2("3.4 Weitere geplante Bausteine"))
story += BUL([
    "<b>Zwischenberichte</b> an die Telegram-Gruppe <b>„STR3 System“</b> (heute werden keine Berichte automatisch versandt, siehe 2.9).",
    "<b>Schärfere Analysebilder</b> je möglichem Trade: Mehr-Zeitrahmen-Darstellung mit Trendlinien und Safety Lines (heute ein "
    "4h-Chart mit 95 dpi).",
    "<b>Zeitplan:</b> Umsetzung erst <b>nach dem 17.10.2026</b>, um den laufenden Test nicht zu stören.",
])
story.append(Spacer(1, 4))
story.append(BOX("geplant", "Abgrenzung", ["Bis zur Umsetzung ändern diese Pläne nichts an den aktiven Regeln. Änderungen an Strategie-Parametern, "
                                           "Filtern, Universen oder der Bewertung werden vorher vorgeschlagen und brauchen deine Freigabe."]))

# ===== Glossar
story.append(NextPageTemplate("normal"))
story.append(PageBreak())
story.append(H1("Glossar"))
gl = [
    ["Action Line", "Trendlinie, deren Bruch das Signal auslöst (mind. 3 Taps)."],
    ["Apex", "Gedachter Schnittpunkt der beiden Linien des Keils; höchstens 180 Kerzen voraus."],
    ["ATR", "Average True Range: typische Kerzenlänge (hier 14 Kerzen, 4h, einfacher Durchschnitt)."],
    ["Backtest", "Durchspielen der Regeln auf vergangenen Daten, ohne Blick in die Zukunft."],
    ["Bounce", "Abprall an einer Linie. Der heutige Bot handelt ihn nicht (nur geplant)."],
    ["Break", "Kerze schließt jenseits der Action Line (mehr als 0,15 ATR). Löst das Signal aus."],
    ["Break-even (BE)", "Stop auf den Einstiegspreis nachziehen. BE-0 = nie, BE-1 = ab 0,3 % bzw. 1,0 % Gewinn."],
    ["Brutto / Netto", "Ergebnis vor bzw. nach Gebühren und Slippage."],
    ["Close / Schlusskurs", "Letzter Kurs einer Kerze."],
    ["Cooldown", "24 Stunden Pause für ein Instrument nach einem beendeten Trade (je Variante)."],
    ["Diagnostic", "Wert wird berechnet und gespeichert, beeinflusst aber keine Entscheidung."],
    ["Docht (Wick)", "Dünner Strich über/unter dem Kerzenkörper (Hoch/Tief)."],
    ["Drawdown", "Größter Rückgang vom bisherigen Höchststand der Ergebniskurve."],
    ["EMA200", "Exponentieller Durchschnitt über 200 (hier Tages-)Kerzen; zeigt den Langfrist-Trend."],
    ["Futures", "Terminkontrakte (z. B. Gold, Öl, Mais, Index-Futures)."],
    ["Intakt", "Linie, die keine Kerze per Schlusskurs durchbrochen hat."],
    ["Keil (Wedge)", "Zwei aufeinander zulaufende Linien (Action + Safety)."],
    ["Kerze", "Open, High, Low, Close eines Zeitabschnitts (hier 4 Stunden)."],
    ["Ledger", "Lokales Protokoll aller Kandidaten und Varianten-Urteile (auch der abgelehnten)."],
    ["Long / Short", "Auf steigende / fallende Kurse setzen."],
    ["Look-ahead", "Unzulässiger Blick in die Zukunft; im Bot ausgeschlossen."],
    ["Mark-to-Market", "Bewertung eines offenen Trades zum aktuellen Kurs (TEST_END im Backtest)."],
    ["MFE / MAE", "Größter günstiger / ungünstiger Ausschlag während eines Trades, in R."],
    ["NOT_EVALUABLE", "Filter nicht prüfbar (Daten fehlen); zählt nie als bestanden."],
    ["Paper-Trading", "Simulation ohne echtes Geld und ohne Broker."],
    ["parent_signal_id", "Eindeutige Nummer eines Signals; alle Varianten bewerten denselben Snapshot."],
    ["Pivot", "Lokales Hoch/Tief (3 Kerzen links und rechts niedriger/höher)."],
    ["Profit-Faktor", "Summe der Gewinne geteilt durch Summe der Verluste (über 1 = im Plus)."],
    ["R", "Geplantes Risiko eines Trades (Einstieg bis Stop); Ergebnis in Vielfachen davon."],
    ["REJECTED_*", "Kandidat abgelehnt (z. B. REJECTED_STOP, REJECTED_DATA_QUALITY, REJECTED_RR)."],
    ["Safety Line", "Gegenläufige Linie, die den Stop festlegt; muss intakt sein."],
    ["Slippage", "Abweichung zwischen gedachtem und tatsächlichem Preis (hier 0,05 ATR je Seite)."],
    ["Snapshot", "Unveränderliche Momentaufnahme eines Signals (Linien, ATR, Stop, Ziel)."],
    ["S/R-Zone", "Unterstützungs-/Widerstandszone: Häufung von mind. 2 Pivots innerhalb 0,6 ATR."],
    ["Tap", "Berührung einer Trendlinie (Docht genügt); mind. 6 Kerzen Abstand."],
    ["TEST_END", "Bewertung eines am Testende noch offenen Trades zum letzten Schlusskurs (nur Backtest)."],
    ["Universum", "Liste der überwachten Instrumente (94 / 177 / 652)."],
    ["Walk-Forward", "Parameter auf älteren Daten wählen, auf neueren ungesehenen Daten prüfen."],
    ["Zeitrahmen", "Länge einer Kerze; hier 4h (aus 1h-Daten gebaut)."],
]
half = (len(gl) + 1) // 2
rows = []
for i in range(half):
    a = gl[i]
    b = gl[i + half] if i + half < len(gl) else ["", ""]
    rows.append([Paragraph(f"<b>{a[0]}</b>", S["cell"]), Paragraph(a[1], S["cell"]),
                 Paragraph(f"<b>{b[0]}</b>", S["cell"]), Paragraph(b[1], S["cell"])])
gt = Table(rows, colWidths=[31 * mm, W / 2 - 31 * mm, 31 * mm, W / 2 - 31 * mm])
gt.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, LINE),
                        ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
                        ("LINEAFTER", (1, 0), (1, -1), 0.6, LINE)]))
story.append(gt)

# ---------------------------------------------------------------- Dokument
frame_n = Frame(18 * mm, 16 * mm, W, A4[1] - 16 * mm - 16 * mm, id="fn", leftPadding=0, rightPadding=0,
                topPadding=0, bottomPadding=0)
doc = BaseDocTemplate(OUT, pagesize=A4, title="Regelwerk Strategie 3 Pro", author="Trading-Bot-Projekt",
                      subject="Regelwerk für Einsteiger (Paper-Trading)", leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm)
doc.addPageTemplates([
    PageTemplate(id="cover", frames=[frame_n], onPage=on_cover, autoNextPageTemplate="normal"),
    PageTemplate(id="normal", frames=[frame_n], onPage=on_normal),
    PageTemplate(id="planned", frames=[frame_n], onPage=on_planned),
])
doc.build(story)
print("OK:", OUT)
