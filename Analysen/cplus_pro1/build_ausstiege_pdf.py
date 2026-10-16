# -*- coding: utf-8 -*-
"""Erzeugt "Ausstiege_im_Vergleich.pdf": laienverstaendliche Erklaerung der vier Ausstiegsregeln
(IST, B, C+, D) mit den Ergebnissen der Pro.1-Nachrechnung. Alle Zahlen werden aus
einzeltrades_pro1.csv berechnet (keine Handeingabe).

Technik: System-Python 3.12 mit reportlab (sieht besser aus als matplotlib-Text); Schrift Arial (C:\\Windows\\Fonts).
Aufruf: python build_ausstiege_pdf.py
Weitergabe-Sicherheit: Das PDF enthaelt keine IDs, Tokens, Namen, Pfade; keine internen Codenamen ausser
IST/B/C+/D/Pro.1 (im Text erklaert). Die Metadaten sind neutral.
"""
import os, csv
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
                                KeepTogether, PageBreak, CondPageBreak)
from reportlab.graphics.shapes import Drawing, Line, Rect, String

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "einzeltrades_pro1.csv")
OUT = os.path.join(HERE, "Ausstiege_im_Vergleich.pdf")

FD = r"C:\Windows\Fonts"
for n, f in (("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"), ("Arial-Italic", "ariali.ttf"),
             ("Arial-BoldItalic", "arialbi.ttf")):
    pdfmetrics.registerFont(TTFont(n, os.path.join(FD, f)))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-BoldItalic")

NAVY, TEAL, GREY, LIGHT, LINEC = (colors.HexColor(x) for x in ("#1f2d4d", "#0f766e", "#5b6477", "#f3f5f9", "#c9d0de"))
GREEN, RED, AMBER, BLUE, PURPLE = (colors.HexColor(x) for x in ("#1a9e5c", "#c0392b", "#d98e04", "#2f6fb5", "#6d3fc0"))
BG = {"blue": colors.HexColor("#e8f1fb"), "green": colors.HexColor("#e8f5ee"), "amber": colors.HexColor("#fff4d6"),
      "purple": colors.HexColor("#efe9fb"), "grey": LIGHT}
BD = {"blue": BLUE, "green": GREEN, "amber": AMBER, "purple": PURPLE, "grey": GREY}
VCOL = {"IST": BLUE, "B": TEAL, "C+": PURPLE, "D": AMBER}

S = {
    "body": ParagraphStyle("body", fontName="Arial", fontSize=9.6, leading=13.4, spaceAfter=4),
    "small": ParagraphStyle("small", fontName="Arial", fontSize=8.2, leading=10.8, textColor=GREY, spaceAfter=3),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=8.6, leading=11.2),
    "cellh": ParagraphStyle("cellh", fontName="Arial-Bold", fontSize=8.6, leading=11.2, textColor=colors.white),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=17, leading=21, textColor=NAVY, spaceBefore=4, spaceAfter=6, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12.5, leading=16, textColor=TEAL, spaceBefore=8, spaceAfter=3, keepWithNext=1),
    "h3": ParagraphStyle("h3", fontName="Arial-Bold", fontSize=10.2, leading=13, textColor=NAVY, spaceBefore=5, spaceAfter=2, keepWithNext=1),
    "title": ParagraphStyle("title", fontName="Arial-Bold", fontSize=25, leading=29, textColor=NAVY, spaceAfter=4),
    "sub": ParagraphStyle("sub", fontName="Arial", fontSize=11.5, leading=15, textColor=GREY, spaceAfter=8),
    "bul": ParagraphStyle("bul", fontName="Arial", fontSize=9.6, leading=13.2, leftIndent=12, bulletIndent=2, spaceAfter=2.5),
    "boxt": ParagraphStyle("boxt", fontName="Arial-Bold", fontSize=10, leading=13, spaceAfter=2),
    "boxb": ParagraphStyle("boxb", fontName="Arial", fontSize=9.2, leading=12.4, spaceAfter=2),
}
W = A4[0] - 36 * mm


def P(t, st="body"):
    return Paragraph(t, S[st])


def BUL(items):
    return [Paragraph(i, S["bul"], bulletText="\u2022") for i in items]


def BOX(kind, title, paras, width=None):
    inner = [Paragraph(title, S["boxt"])] + [Paragraph(p, S["boxb"]) if isinstance(p, str) else p for p in paras]
    t = Table([[inner]], colWidths=[width or W])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BG[kind]), ("LINEBEFORE", (0, 0), (0, -1), 3.2, BD[kind]),
                           ("BOX", (0, 0), (-1, -1), 0.5, BD[kind]), ("LEFTPADDING", (0, 0), (-1, -1), 8),
                           ("RIGHTPADDING", (0, 0), (-1, -1), 6), ("TOPPADDING", (0, 0), (-1, -1), 5),
                           ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return KeepTogether([t, Spacer(1, 5)])


def TBL(rows, widths, header=True, zebra=True, first_bold=False, repeat=True):
    data = []
    for ri, r in enumerate(rows):
        line = []
        for ci, c in enumerate(r):
            if isinstance(c, str):
                st = "cellh" if (header and ri == 0) else "cell"
                line.append(Paragraph(f"<b>{c}</b>" if (first_bold and ci == 0 and not (header and ri == 0)) else c, S[st]))
            else:
                line.append(c)
        data.append(line)
    t = Table(data, colWidths=widths, repeatRows=1 if (header and repeat) else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINEC),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra:
        for i in range(1 if header else 0, len(data)):
            if i % 2 == 0:
                st.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t.setStyle(TableStyle(st))
    return t


# ----------------------------------------------------------------- Daten aus der CSV
def num(x):
    return float(x.replace(",", ".")) if x not in ("", None) else None


def load():
    rows = list(csv.DictReader(open(CSV, encoding="utf-8-sig"), delimiter=";"))
    return rows


def stats(rows, v):
    cl = [r for r in rows if r[f"{v}_status"] == "closed"]
    op = [r for r in rows if r[f"{v}_status"] == "open"]
    nr = [num(r[f"{v}_netto_r"]) for r in cl]
    pc = [num(r[f"{v}_netto_pct"]) for r in cl]
    w = sum(1 for x in nr if x > 0)
    b = max(cl, key=lambda r: num(r[f"{v}_netto_r"]))
    s = min(cl, key=lambda r: num(r[f"{v}_netto_r"]))
    return {"closed": len(cl), "open": len(op), "win": w, "loss": len(cl) - w, "hit": w / len(cl) * 100,
            "sum_r": sum(nr), "sum_pct": sum(pc), "best": (b["symbol"], num(b[f"{v}_netto_r"])),
            "worst": (s["symbol"], num(s[f"{v}_netto_r"])), "avg_r": sum(nr) / len(cl),
            "unreal": sum(num(r["unrealisiert_netto_r_letzter_kurs"]) for r in op if r["unrealisiert_netto_r_letzter_kurs"])}


def f(v, d=1, sign=False):
    s = (f"{v:+.{d}f}" if sign else f"{v:.{d}f}").replace(".", ",").replace("-", "−")
    return s


def sym(s):
    """Lesbarer Instrumentname fuer Laien."""
    usd_base = {"JPY=X": "USD/JPY", "CAD=X": "USD/CAD", "CHF=X": "USD/CHF"}
    if s in usd_base:
        return usd_base[s]
    if s.endswith("=X") and len(s) == 8:
        return s[:3] + "/" + s[3:6]
    return {"SOL-USD": "SOL (Kryptowährung Solana)", "ETH-USD": "ETH (Ethereum)", "BTC-USD": "BTC (Bitcoin)",
            "GBPJPY=X": "GBP/JPY (Pfund/Yen)", "EURJPY=X": "EUR/JPY (Euro/Yen)"}.get(s, s.replace("=X", "").replace("-USD", ""))


def d8(iso):
    return f"{iso[8:10]}.{iso[5:7]}.{iso[0:4]}"


# ----------------------------------------------------------------- Grafiken
def drawing_ladder(levels, title, width=150 * mm * 0.58, height=150):
    """Preisleiter: levels = [(preis, text, farbe, fett)]; Preise 1970..2070 (Gold-Beispiel)."""
    d = Drawing(width, height)
    lo, hi = 1965.0, 2075.0
    sy = lambda p: 8 + (p - lo) * (height - 24) / (hi - lo)
    ax = 14
    d.add(Line(ax, sy(lo + 5), ax, sy(hi - 5), strokeColor=GREY, strokeWidth=0.8))
    d.add(String(0, height - 8, title, fontName="Arial-Bold", fontSize=7.8, fillColor=NAVY))
    last_y = -99.0
    for p, t, col, bold in sorted(levels, key=lambda x: x[0]):
        d.add(Line(ax - 5, sy(p), ax + 9, sy(p), strokeColor=col, strokeWidth=1.7))
        ty = max(sy(p) - 3, last_y + 9.5)                  # Beschriftungen nicht uebereinander
        last_y = ty
        if abs(ty - (sy(p) - 3)) > 0.5:
            d.add(Line(ax + 9, sy(p), ax + 12, ty + 3, strokeColor=col, strokeWidth=0.5))
        d.add(String(ax + 14, ty, t, fontName="Arial-Bold" if bold else "Arial", fontSize=7.6, fillColor=col))
    return d


def drawing_bars(vals, width=W * 0.92, height=150):
    """Waagerechtes Balkendiagramm Gesamt-% je Variante (gruen/rot, Nulllinie)."""
    d = Drawing(width, height)
    names = list(vals.keys())
    lo, hi = min(0, min(vals.values())), max(0, max(vals.values()))
    span = (hi - lo) or 1
    left, right = 78, width - 62
    zx = left + (0 - lo) / span * (right - left)
    rh = 28
    for i, n in enumerate(names):
        y = height - 22 - i * (rh + 6) - rh
        v = vals[n]
        bw = max(abs(v) / span * (right - left), 1)
        bx = zx if v >= 0 else zx - bw
        d.add(String(0, y + rh / 2 - 4, {"IST": "IST", "B": "B", "C+": "C+", "D": "D"}[n], fontName="Arial-Bold", fontSize=11, fillColor=VCOL[n]))
        d.add(Rect(bx, y + 3, bw, rh - 6, fillColor=GREEN if v > 0 else RED, strokeColor=None))
        tx = zx + bw + 4 if v >= 0 else zx - bw - 4
        d.add(String(tx, y + rh / 2 - 4, f"{f(v, 1, True)} %", fontName="Arial-Bold", fontSize=10,
                     fillColor=GREEN if v > 0 else RED, textAnchor="start" if v >= 0 else "end"))
    d.add(Line(zx, 4, zx, height - 14, strokeColor=colors.black, strokeWidth=0.8))
    d.add(String(0, height - 10, "Gesamtergebnis in Prozent (Summe aller abgeschlossenen Trades, nach Kosten)", fontName="Arial", fontSize=7.8, fillColor=GREY))
    return d


# ----------------------------------------------------------------- Seiten
def on_page(c, doc):
    c.saveState()
    w, h = A4
    c.setStrokeColor(LINEC); c.setLineWidth(0.5)
    c.line(18 * mm, h - 12 * mm, w - 18 * mm, h - 12 * mm)
    c.setFillColor(GREY); c.setFont("Arial", 7.8)
    c.drawString(18 * mm, h - 10 * mm, "Wann steigt man aus? Vier Ausstiegsregeln im Vergleich")
    c.line(18 * mm, 13 * mm, w - 18 * mm, 13 * mm)
    c.drawString(18 * mm, 8.5 * mm, "Paper-Trading – keine Anlageberatung. Es wurde kein echtes Geld eingesetzt.")
    c.drawRightString(w - 18 * mm, 8.5 * mm, f"Seite {doc.page}")
    c.restoreState()


def variant_header(code, name):
    t = Table([[Paragraph(f"<font color='white'><b>{code}</b></font>", ParagraphStyle("vh", fontName="Arial-Bold", fontSize=15, leading=18)),
                Paragraph(f"<b>{name}</b>", ParagraphStyle("vn", fontName="Arial-Bold", fontSize=12, leading=15, textColor=NAVY))]],
              colWidths=[22 * mm, W - 22 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (0, 0), VCOL[code]), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                           ("ALIGN", (0, 0), (0, 0), "CENTER"), ("BACKGROUND", (1, 0), (1, 0), LIGHT),
                           ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                           ("LEFTPADDING", (1, 0), (1, 0), 8)]))
    return t


def variant_block(code, name, idea, steps, example, ladder, pros, cons):
    left = [P(f"<b>Die Idee:</b> {idea}"), P("<b>So funktioniert’s</b>", "h3")] + BUL(steps)
    right = [ladder]
    top = Table([[left, right]], colWidths=[W * 0.60, W * 0.40])
    top.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0),
                             ("RIGHTPADDING", (0, 0), (0, 0), 8)]))
    pc = Table([[[Paragraph("<b>Vorteile</b>", S["boxt"])] + BUL(pros), [Paragraph("<b>Nachteile</b>", S["boxt"])] + BUL(cons)]],
               colWidths=[W / 2, W / 2])
    pc.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("BACKGROUND", (0, 0), (0, 0), BG["green"]),
                            ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fdecea")), ("BOX", (0, 0), (-1, -1), 0.4, LINEC),
                            ("LEFTPADDING", (0, 0), (-1, -1), 7), ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return [variant_header(code, name), Spacer(1, 5), top, BOX("blue", "Rechenbeispiel Gold", example), pc, Spacer(1, 6)]


def build():
    rows = load()
    ST = {v: stats(rows, v) for v in ("IST", "B", "C+", "D")}
    story = []

    # ===== Seite 1
    story += [Spacer(1, 4), Paragraph("Wann steigt man aus?", S["title"]),
              Paragraph("Vier Ausstiegsregeln im Vergleich &ndash; Nachrechnung aus einem Zwei-Monats-Papiertest", S["sub"])]
    story.append(BOX("grey", "Worum geht es?", [
        "Ein automatischer Handelsbot hat zwei Monate lang <b>nur auf dem Papier</b> gehandelt (Paper-Trading) &ndash; es wurde "
        "<b>kein echtes Geld</b> eingesetzt. Ausgewertet wurde die Variante <b>Pro.1</b>, die ungefilterte Grundstrategie des Bots. "
        "Für diese Auswertung bleiben <b>alle Einstiege gleich</b>; es wird nur durchgerechnet, was passiert wäre, wenn man "
        "nach vier unterschiedlichen Regeln <b>ausgestiegen</b> wäre: <b>IST</b> (so lief der Test tatsächlich), <b>B</b>, <b>C+</b> und <b>D</b>.",
        "Das Ganze ist eine Rückrechnung an kurzen, wenigen Daten &ndash; kein Beweis und keine Empfehlung."]))
    story.append(P("Kurz erklärt", "h2"))
    story.append(P("Zum Mitrechnen nutzen wir ein <b>Gold-Beispiel</b>: Wir steigen bei <b>2.000 $</b> ein, die wichtige Linie unter dem Kurs liegt bei "
                   "<b>1.980 $</b>, eine typische Kerze ist etwa <b>10 $</b> lang."))
    story.append(TBL([
        ["Begriff", "Einfach gesagt", "Im Gold-Beispiel"],
        ["Kerze, Docht, Schlusskurs", "Eine Kerze zeigt, was der Kurs in einem Zeitabschnitt (hier 4 Stunden) gemacht hat: Start, Höchst-, Tiefst- und "
         "Schlusskurs. Der <b>Docht</b> ist der dünne Strich: ein kurzer Ausschlag nach oben oder unten. Der <b>Schlusskurs</b> ist der letzte Kurs der Kerze.",
         "Ein Docht kann kurz auf 1.975 $ fallen, die Kerze schließt aber bei 1.995 $."],
        ["Trendlinie und Safety Line", "Eine <b>Trendlinie</b> verbindet mehrere Hoch- oder Tiefpunkte. Die <b>Safety Line</b> (Sicherheitslinie) ist eine zweite "
         "Linie auf der anderen Seite; sie zeigt, wo die Einstiegsidee nicht mehr stimmt.", "Die Safety Line liegt bei 1.980 $."],
        ["Stop-Loss", "Der Preis, bei dem man aussteigt, wenn es schiefgeht, um den Verlust zu begrenzen.", "Stop bei 1.980 $."],
        ["R (das geplante Risiko)", "Der Abstand vom Einstieg zum Stop. Gewinne und Verluste werden als Vielfache davon gemessen: +2R heißt, man hat das "
         "Doppelte des Risikos gewonnen, −1R heißt, der Stop wurde getroffen.", "1R = 20 $ (2.000 − 1.980)."],
        ["ATR", "Die typische Kerzenlänge eines Instruments (Durchschnitt der letzten 14 Kerzen). Damit lassen sich Abstände für jedes Instrument "
                "gleich messen.", "1 ATR = 10 $."],
        ["Zwischentief (Swing)", "Ein Tiefpunkt, nach dem der Kurs wieder steigt und der von den Nachbarkerzen bestätigt wird &ndash; eine Art "
                                 "„Treppenstufe“ in einem Aufwärtstrend.", "Gold steigt auf 2.060 $, fällt auf 2.045 $ und steigt wieder: 2.045 $ ist ein Zwischentief."],
        ["Break-even", "Den Stop auf den Einstiegspreis nachziehen, damit aus einem Gewinner kein Verlierer mehr wird.", "Stop wandert von 1.980 $ auf ca. 2.000 $."],
        ["Gebühren/Slippage", "In allen Rechnungen sind Handelskosten und kleine Preisabweichungen abgezogen (netto).", "Etwa 0,1R pro Trade bei Gold."],
    ], [34 * mm, W - 34 * mm - 52 * mm, 52 * mm], first_bold=True))

    # ===== Varianten
    story.append(PageBreak())
    story.append(P("Die vier Ausstiegsregeln", "h1"))
    story += variant_block(
        "IST", "Der feste Stop mit festem Ziel (so lief der Test wirklich)",
        "Vorher festlegen, wo man aussteigt: ein fester Stop gegen Verlust und ein festes Ziel für den Gewinn.",
        ["Der <b>Stop</b> liegt auf der Safety Line &ndash; berechnet für den Zeitpunkt 4 Kerzen nach dem Signal &ndash; und wird dann <b>eingefroren</b>.",
         "<b>Jede Berührung</b> löst aus, auch ein kurzer Docht.",
         "Das <b>Ziel</b> liegt an der nächsten Unterstützungs-/Widerstandszone (Preisbereich, an dem der Kurs schon öfter gedreht hat).",
         "Pro.1 zieht den Stop <b>nicht</b> auf den Einstieg nach (kein Break-even)."],
        ["Einstieg 2.000 $, Stop 1.980 $ (1R = 20 $), nächste Zone bei 2.030 $ als Ziel. Erreicht Gold 2.030 $: Gewinn <b>+1,5R</b> (netto ca. +1,4R). "
         "Berührt der Kurs 1.980 $ &ndash; auch nur mit einem Docht &ndash;: Verlust <b>−1R</b> (netto ca. −1,1R)."],
        drawing_ladder([(2030, "Ziel 2.030 $ (+1,5R)", GREEN, True), (2000, "Einstieg 2.000 $", NAVY, True), (1980, "Stop 1.980 $ (fest)", RED, True)], "Gold-Beispiel IST"),
        ["Einfach und vorhersehbar: Man kennt Risiko und Ziel von Anfang an.", "Gewinne werden sicher mitgenommen."],
        ["Das Ziel kann einen laufenden Trend früh abschneiden.", "Ein Docht kann einen sonst guten Trade beenden.", "Der Stop bewegt sich nicht mit."])
    story += variant_block(
        "B", "Ausstieg nur bei Schlusskurs durch die Linie",
        "Nicht aussteigen, nur weil der Kurs kurz zuckt, sondern erst, wenn eine Kerze wirklich jenseits der Linie <b>schließt</b>.",
        ["Die Safety Line <b>wandert mit</b> (sie ist eine schräge Linie).",
         "Ausstieg erst, wenn eine 4h-Kerze <b>jenseits der Linie schließt</b>; ausgeführt wird zum Start der nächsten Kerze.",
         "Ein <b>Notfallnetz</b> 1 ATR hinter der Linie löst sofort aus, falls der Kurs abstürzt oder eine Lücke reißt.",
         "<b>Kein Ziel</b> und <b>kein Nachziehen</b>."],
        ["Die Linie ist von 1.980 $ auf 2.040 $ gestiegen. Eine Kerze schließt bei 2.035 $, die nächste startet bei 2.033 $ &ndash; dort steigen wir aus: "
         "Gewinn ca. <b>+1,6R</b> (33 $ ÷ 20 $). Ein Docht auf 2.030 $ mit Schluss über 2.040 $ hätte nichts ausgelöst. "
         "Das Netz stünde bei 2.030 $."],
        drawing_ladder([(2040, "Linie (gewandert) 2.040 $", TEAL, True), (2030, "Notfallnetz 2.030 $", RED, False), (2000, "Einstieg 2.000 $", NAVY, True), (1980, "Start-Linie 1.980 $", GREY, False)], "Gold-Beispiel B"),
        ["Dochte werfen einen guten Trade nicht raus.", "Gewinne können laufen, solange der Trend hält."],
        ["Gewinne werden nicht gesichert: Man kann sie auch wieder abgeben.", "Trades bleiben lange offen.", "Die Linie kann weit entfernt liegen &ndash; das Risiko ist dann größer."])
    story.append(PageBreak())
    story += variant_block(
        "C+", "Wie B, aber mit Gewinnschutz in Stufen",
        "Wie B, aber sobald ein Trade klar im Plus ist, wird eine zusätzliche Gewinnschwelle hochgezogen &ndash; so bleibt mehr vom Gewinn übrig.",
        ["<b>Stufe 1:</b> bis +1,5R passiert nichts außer den Regeln von B.",
         "<b>Stufe 2:</b> schließt eine Kerze bei mindestens +1,5R, gilt als Schwelle der <b>Einstand plus Kosten</b>.",
         "<b>Stufe 3:</b> nach jedem <b>bestätigten Zwischentief</b> (Rücksetzer von mindestens 1 ATR, danach wieder Anstieg) steigt die Schwelle auf "
         "<b>Zwischentief minus 0,5 ATR</b>. Sie wandert nur nach oben.",
         "Es zählt immer die günstigere von Safety Line und Gewinnschwelle. Alles gilt nur für den <b>Schlusskurs</b>; darunter liegt ein "
         "<b>Notfallnetz</b> 1 ATR tiefer. Kein festes Ziel."],
        ["Gold schließt bei 2.030 $ (+1,5R): Stufe 2, Schwelle ca. 2.002 $. Es steigt auf 2.060 $, fällt auf 2.045 $ (Rücksetzer 15 $ = mehr als 1 ATR) "
         "und steigt wieder: Stufe 3, Schwelle <b>2.040 $</b> (2.045 − 5). Schließt später eine Kerze unter 2.040 $ und die nächste startet bei 2.038 $, "
         "ist der Gewinn ca. <b>+1,9R</b>. Das Netz stünde bei 2.030 $."],
        drawing_ladder([(2045, "Zwischentief 2.045 $", GREY, False), (2040, "Schwelle Stufe 3: 2.040 $", PURPLE, True), (2030, "Netz 2.030 $ / +1,5R", RED, False),
                        (2002, "Schwelle Stufe 2: ca. 2.002 $", PURPLE, False), (2000, "Einstieg 2.000 $", NAVY, True), (1980, "Safety Line 1.980 $", GREY, False)], "Gold-Beispiel C+"),
        ["Gewinne werden gestaffelt gesichert, Trends können trotzdem laufen.", "Dochte lösen nichts aus, Abstürze fängt das Netz auf."],
        ["Komplexer, mehr Regeln.", "Zwischen Stufe 2 und dem ersten Zwischentief ist der Schutz noch dünn (Beispiel GBP/JPY unten).", "Trades bleiben länger offen."])
    story += variant_block(
        "D", "Normaler Stop an der Linie, am Zwischentief nachgezogen",
        "Ein klassischer Stop, der der Linie und den Zwischentiefs folgt &ndash; reagiert aber auf jede Berührung.",
        ["Der Stop liegt knapp (0,1 ATR) hinter der mitwandernden Safety Line.",
         "Nach jedem bestätigten Zwischentief wird er auf <b>Zwischentief minus 0,5 ATR</b> nachgezogen.",
         "<b>Jede Berührung</b> löst aus &ndash; auch ein Docht.",
         "<b>Kein Ziel.</b>"],
        ["Gold steigt auf 2.060 $, fällt auf 2.045 $ und steigt wieder: Der Stop wird auf <b>2.040 $</b> (2.045 − 5) nachgezogen. Sobald der Kurs "
         "&ndash; auch nur mit einem Docht &ndash; 2.040 $ berührt, ist man draußen: Gewinn ca. <b>+2,0R</b>."],
        drawing_ladder([(2045, "Zwischentief 2.045 $", GREY, False), (2040, "Stop nachgezogen: 2.040 $", AMBER, True), (2000, "Einstieg 2.000 $", NAVY, True), (1979, "Start-Stop 1.979 $", RED, False)], "Gold-Beispiel D"),
        ["Folgt dem Trend und sichert Gewinne Schritt für Schritt.", "Klar und eindeutig: Berührung = Ausstieg."],
        ["Ein kurzer Docht kann einen guten Trade beenden.", "Kein Schutz durch Schlusskurs-Regel.", "Auch hier kein Ziel."])

    # ===== Vergleichstabelle
    story.append(P("Die Unterschiede auf einen Blick", "h2"))
    story.append(TBL([
        ["Frage", "IST", "B", "C+", "D"],
        ["Wo liegt der Stop?", "An der Safety Line (4 Kerzen vorausberechnet)", "An der mitwandernden Safety Line", "Safety Line oder Gewinnschwelle, je nachdem was günstiger ist", "0,1 ATR hinter der Linie bzw. am Zwischentief"],
        ["Bewegt er sich mit?", "Nein, fest", "Ja, mit der Linie", "Ja, Linie plus Gewinnschwelle (nur nach oben)", "Ja, Linie plus Zwischentiefe"],
        ["Was löst aus?", "Jede Berührung (auch Docht)", "Nur ein Schlusskurs", "Nur ein Schlusskurs", "Jede Berührung (auch Docht)"],
        ["Schutz bei Sturz / Lücke", "Der Stop (Ausstieg zum Stop-Preis)", "Notfallnetz 1 ATR", "Notfallnetz 1 ATR unter der Schwelle", "Der Stop (bei Lücke zum Eröffnungskurs)"],
        ["Gewinn sichern", "Nur über das feste Ziel", "Nein", "Ja, in Stufen", "Ja, am Zwischentief"],
        ["Festes Ziel?", "Ja", "Nein", "Nein", "Nein"],
        ["Wie viel muss man selbst festlegen?", "Wenig (Stop und Ziel ergeben sich aus dem Chart)", "Wenig (Netz 1 ATR)", "Mehr (1,5R, 0,5 ATR, 1 ATR)", "Mittel (0,1 ATR, 0,5 ATR)"],
    ], [28 * mm, 32 * mm, 30 * mm, 38 * mm, W - 128 * mm], first_bold=True))

    # ===== Ergebnisse
    story.append(CondPageBreak(120 * mm))
    story.append(P("Die Ergebnisse", "h1"))
    story.append(P("Es wurden <b>80 Trades</b> der Variante Pro.1 nachgerechnet. <b>Gewertet werden nur abgeschlossene Trades</b>; Trades, die am Ende noch "
                   "offen sind, zählen nicht (Vorgabe des Tests). „Gesamt-%“ ist die Summe der Netto-Prozente aller abgeschlossenen Trades bei gleichem Einsatz "
                   "je Trade, „Netto-R“ die Summe in R (jeweils nach Kosten)."))
    hdr = ["Variante", "abgeschl. / offen", "Gewinner / Verlierer", "Treffer", "Gesamt-%", "Netto-R", "bester Trade (R)", "schlechtester (R)"]
    trs = [hdr]
    for v in ("IST", "B", "C+", "D"):
        s = ST[v]
        trs.append([f"<b>{v}</b>", f"{s['closed']} / {s['open']}", f"{s['win']} / {s['loss']}", f"{f(s['hit'], 1)} %",
                    f"<b>{f(s['sum_pct'], 1, True)} %</b>", f(s["sum_r"], 2, True),
                    f"{sym(s['best'][0]).split(' (')[0]} {f(s['best'][1], 2, True)}", f"{sym(s['worst'][0]).split(' (')[0]} {f(s['worst'][1], 2, True)}"])
    story.append(TBL(trs, [15 * mm, 22 * mm, 24 * mm, 15 * mm, 21 * mm, 17 * mm, 30 * mm, W - 144 * mm]))
    story.append(Spacer(1, 6))
    story.append(drawing_bars({v: ST[v]["sum_pct"] for v in ("IST", "B", "C+", "D")}))
    story.append(P("Was steckt dahinter?", "h2"))
    story.append(TBL([
        ["Variante", "Laien-Deutung"],
        ["IST", f"IST nimmt am festen Ziel oft nur einen kleinen Gewinn mit, auch wenn der Kurs danach weiterläuft. Dafür ist der Verlust je Trade meist auf etwa 1R "
                f"begrenzt (Ausnahmen bei Kurslücken). Ergebnis: {f(ST['IST']['sum_pct'], 1, True)} % bei {ST['IST']['closed']} abgeschlossenen Trades &ndash; solide, aber ohne die großen Ausreißer."],
        ["B", f"B wirkt auf dem Papier schlecht ({f(ST['B']['sum_pct'], 1, True)} %). Das liegt daran, dass nur {ST['B']['closed']} Trades abgeschlossen sind &ndash; "
              f"und das fast nur Verlierer, die schnell durch die Linie fielen. {ST['B']['open']} Trades laufen noch, viele davon im Plus (auf dem Papier zusammen rund "
              f"{f(ST['B']['unreal'], 0, True)} R). Weil offene Trades nicht gewertet werden, fehlt dieser Teil &ndash; B ist hier <b>unterbewertet</b>, kann aber ebenso wieder abgeben."],
        ["C+", f"C+ liegt mit {f(ST['C+']['sum_pct'], 1, True)} % vorn &ndash; der Vorsprung kommt vor allem aus <b>drei Krypto-Trends</b> (Solana, Ethereum, Bitcoin, alle am 17.08. gestartet), "
               f"die C+ weiterlaufen ließ. Schwachstelle: zwischen Stufe 2 und dem ersten bestätigten Zwischentief ist der Schutz dünn &ndash; im Beispiel GBP/JPY wurde ein großer Gewinn fast ganz zurückgegeben."],
        ["D", f"D hat in R das beste Ergebnis ({f(ST['D']['sum_r'], 1, True)} R, {f(ST['D']['sum_pct'], 1, True)} %), und fast alle Trades sind abgeschlossen (nur {ST['D']['open']} offen), "
              f"der Vergleich ist hier also am wenigsten durch offene Trades verzerrt. Der Stop folgt dem Trend eng und sichert Gewinne laufend."],
    ], [18 * mm, W - 18 * mm], first_bold=True))

    # Einzelbeispiele
    def case(symbol, dir_):
        r = next(x for x in rows if x["symbol"] == symbol and x["richtung"] == dir_ and x["IST_status"] == "closed" and x["C+_status"] == "closed"
                 and abs(num(x["C+_netto_r"]) - num(x["IST_netto_r"])) > 3)
        return r
    story.append(P("Vier anschauliche Einzelfälle", "h2"))
    cases = []
    for symbol, dir_, text in (
            ("SOL-USD", "LONG", "Ein starker Trend: IST nahm am Ziel Gewinn mit; C+ ließ laufen und sicherte schrittweise ab."),
            ("ETH-USD", "LONG", "Gleiches Bild: Der Trend ging weiter, ein festes Ziel hätte ihn früh beendet."),
            ("GBPJPY=X", "SHORT", "Die Gegenprobe: IST traf ein großes Ziel; C+ gab den Gewinn zurück, weil noch kein Zwischentief den Schutz nachgezogen hatte."),
            ("EURJPY=X", "SHORT", "Ein kleiner Gewinn bei IST, ein langer Trend bei C+.")):
        r = case(symbol, dir_)
        ri, rc, rd = num(r["IST_netto_r"]), num(r["C+_netto_r"]), num(r["D_netto_r"]) if r["D_status"] == "closed" else None
        col = "green" if rc > ri else "amber"
        cases.append(BOX(col, f"{sym(symbol)} &ndash; {'Kauf (Long)' if dir_ == 'LONG' else 'Verkauf (Short)'}, Signal {d8(r['signal_utc'])}",
                         [f"<b>vorher (IST): {f(ri, 2, True)} R</b> &nbsp;&rarr;&nbsp; <b>nachher (C+): {f(rc, 2, True)} R</b>"
                          + (f" &nbsp;&middot;&nbsp; D: {f(rd, 2, True)} R" if rd is not None else ""), text]))
    story += cases

    # ===== Belastbarkeit
    story.append(P("Wie belastbar ist das?", "h2"))
    top3 = sorted([num(r["C+_netto_r"]) for r in rows if r["C+_status"] == "closed"], reverse=True)[:3]
    share = sum(top3) / ST["C+"]["sum_r"] * 100
    story += BUL([
        "<b>Kleine Stichprobe:</b> 2 Monate, 80 Trades, im Wesentlichen eine Marktphase, nur die Variante Pro.1.",
        f"<b>Wenige Ausreißer:</b> rund {share:.0f} % des C+-Ergebnisses stammen aus nur 3 Trades. Bei Devisen gab es kaum einen Unterschied zwischen IST und C+.",
        "<b>Offene Trades werden nicht gewertet.</b> Regeln ohne Ziel (B, C+, D) lassen Trades länger laufen, dadurch sind mehr davon noch offen.",
        "<b>Der „faire“ Vergleich ist ebenfalls verzerrt:</b> Betrachtet man nur Trades, die in allen vier Varianten schon abgeschlossen sind (33 Stück), "
        "sind es fast nur schnelle Verlierer &ndash; dort schneidet C+ nicht besser ab als IST.",
        "<b>Parameter vorher festgelegt, nicht optimiert:</b> 1,5R, 0,5 ATR, 1 ATR und 0,1 ATR wurden nicht angepasst, um das Ergebnis zu verbessern.",
        "<b>Nächster Schritt:</b> ein Test über 18 Monate, um zu sehen, ob sich das Bild über mehrere Marktphasen bestätigt.",
    ])
    story.append(Spacer(1, 4))
    story.append(BOX("purple", "Fazit",
                     ["Auf diesen zwei Monaten haben Regeln, die Gewinne laufen lassen und nachziehen (C+ und D), besser abgeschnitten als der feste Ausstieg &ndash; "
                      "wie verlässlich das ist, zeigt erst ein längerer Test. Keine Anlageberatung."]))
    return story


def main():
    doc = BaseDocTemplate(OUT, pagesize=A4, title="Wann steigt man aus? Vier Ausstiegsregeln im Vergleich", author="", subject="Paper-Trading, keine Anlageberatung",
                          leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm)
    fr = Frame(18 * mm, 16 * mm, W, A4[1] - 32 * mm, id="f", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="p", frames=[fr], onPage=on_page)])
    doc.build(build())
    print("OK:", OUT)


if __name__ == "__main__":
    main()
