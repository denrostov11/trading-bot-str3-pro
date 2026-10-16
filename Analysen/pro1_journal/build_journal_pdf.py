# -*- coding: utf-8 -*-
"""Baut Pro1_Baseline_Tradejournal.pdf aus journal_daten.json (erzeugt von journal_daten.py).
System-Python 3.12 mit reportlab, Schrift Arial. Aufruf: python build_journal_pdf.py"""
import os, json
from datetime import datetime, timedelta
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, PageTemplate, Frame, Paragraph, Spacer, Table, TableStyle,
                                KeepTogether, NextPageTemplate, PageBreak)
from reportlab.graphics.shapes import Drawing, Line, Circle, String, Rect

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "Pro1_Baseline_Tradejournal.pdf")
J = json.load(open(os.path.join(HERE, "journal_daten.json"), encoding="utf-8"))
M, TOT, ROWS, OPEN = J["meta"], J["tot"], J["rows"], J["open"]

FD = r"C:\Windows\Fonts"
for n, f in (("Arial", "arial.ttf"), ("Arial-Bold", "arialbd.ttf"), ("Arial-Italic", "ariali.ttf"), ("Arial-BoldItalic", "arialbi.ttf")):
    pdfmetrics.registerFont(TTFont(n, os.path.join(FD, f)))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic", boldItalic="Arial-BoldItalic")

NAVY, TEAL, GREY, LIGHT, LINEC = (colors.HexColor(x) for x in ("#1f2d4d", "#0f766e", "#5b6477", "#f3f5f9", "#c9d0de"))
GREEN, RED, AMBER, BLUE = (colors.HexColor(x) for x in ("#1a9e5c", "#c0392b", "#d98e04", "#2f6fb5"))
GBG, RBG = colors.HexColor("#eef8f2"), colors.HexColor("#fdf0ee")
BGB = {"blue": colors.HexColor("#e8f1fb"), "amber": colors.HexColor("#fff4d6"), "green": colors.HexColor("#e8f5ee"), "grey": LIGHT}
BDB = {"blue": BLUE, "amber": AMBER, "green": GREEN, "grey": GREY}

S = {
    "body": ParagraphStyle("body", fontName="Arial", fontSize=9.4, leading=13, spaceAfter=3.5),
    "small": ParagraphStyle("small", fontName="Arial", fontSize=7.8, leading=10, textColor=GREY, spaceAfter=2),
    "h1": ParagraphStyle("h1", fontName="Arial-Bold", fontSize=18, leading=22, textColor=NAVY, spaceAfter=4, keepWithNext=1),
    "h2": ParagraphStyle("h2", fontName="Arial-Bold", fontSize=12, leading=15, textColor=TEAL, spaceBefore=7, spaceAfter=3, keepWithNext=1),
    "sub": ParagraphStyle("sub", fontName="Arial", fontSize=10.5, leading=14, textColor=GREY, spaceAfter=6),
    "bul": ParagraphStyle("bul", fontName="Arial", fontSize=9.2, leading=12.6, leftIndent=12, bulletIndent=2, spaceAfter=2.2),
    "cell": ParagraphStyle("cell", fontName="Arial", fontSize=8.3, leading=10.4),
    "cellh": ParagraphStyle("cellh", fontName="Arial-Bold", fontSize=8.3, leading=10.4, textColor=colors.white),
    "t": ParagraphStyle("t", fontName="Arial", fontSize=6.3, leading=7.5),
    "th": ParagraphStyle("th", fontName="Arial-Bold", fontSize=6.1, leading=7.2, textColor=colors.white),
    "tr": ParagraphStyle("tr", fontName="Arial", fontSize=6.3, leading=7.5, alignment=2),
    "boxt": ParagraphStyle("boxt", fontName="Arial-Bold", fontSize=10, leading=13, spaceAfter=2),
    "boxb": ParagraphStyle("boxb", fontName="Arial", fontSize=9.2, leading=12.4, spaceAfter=2),
}
PW, PH = A4
LW, LH = landscape(A4)
WP = PW - 36 * mm
WL = LW - 20 * mm


def f(v, d=2, sign=False):
    return (f"{v:+.{d}f}" if sign else f"{v:.{d}f}").replace(".", ",").replace("-", "−")


def price(x):
    return f"{float(x):.6g}".replace(".", ",")


def dt(iso):
    return datetime.strptime(iso[:19], "%Y-%m-%dT%H:%M:%S")


def tcell(iso, style="t"):
    """UTC-Zeit (Datum + Uhr) und darunter Berlin-Zeit (MESZ = UTC+2; alle Daten vor der Zeitumstellung am 25.10.2026)."""
    if not iso:
        return Paragraph("–", S[style])
    u = dt(iso)
    b = u + timedelta(hours=2)
    assert u < datetime(2026, 10, 25, 1, 0), "Sommerzeit-Annahme verletzt"
    return Paragraph(f"{u.strftime('%d.%m. %H:%M')}<br/><font color='#6b7280'>{b.strftime('%H:%M')} Bln</font>", S[style])


def BOX(kind, title, paras, width):
    inner = [Paragraph(title, S["boxt"])] + [Paragraph(p, S["boxb"]) for p in paras]
    t = Table([[inner]], colWidths=[width])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BGB[kind]), ("LINEBEFORE", (0, 0), (0, -1), 3.2, BDB[kind]),
                           ("BOX", (0, 0), (-1, -1), 0.5, BDB[kind]), ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 4)]))
    return KeepTogether([t, Spacer(1, 5)])


def table(rows, widths, header=True, size="cell", zebra=True, first_bold=False):
    data = []
    for ri, r in enumerate(rows):
        data.append([Paragraph(c, S["cellh" if (header and ri == 0) else size]) if isinstance(c, str) else c for c in r])
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    st = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("GRID", (0, 0), (-1, -1), 0.4, LINEC), ("LEFTPADDING", (0, 0), (-1, -1), 4),
          ("RIGHTPADDING", (0, 0), (-1, -1), 4), ("TOPPADDING", (0, 0), (-1, -1), 2.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if header:
        st.append(("BACKGROUND", (0, 0), (-1, 0), NAVY))
    if zebra:
        st += [("BACKGROUND", (0, i), (-1, i), LIGHT) for i in range(2 if header else 1, len(data), 2)]
    t.setStyle(TableStyle(st))
    return t


# ------------------------------------------------------------------ Kurve
def cum_chart(width, height=150):
    pts = sorted([(dt(r["ausstieg_buchung_utc"]), r["netto_pct"]) for r in ROWS])
    d = Drawing(width, height)
    t0, t1 = datetime(2026, 8, 17, 10, 0), datetime.strptime(M["stichtag_utc"], "%d.%m.%Y %H:%M")
    cum, series = 0.0, [(t0, 0.0)]
    for t, p in pts:
        series.append((t, cum)); cum += p; series.append((t, cum))
    series.append((t1, cum))
    lo, hi = min(0, min(v for _, v in series)), max(v for _, v in series) * 1.08
    L, R, B, T_ = 38, width - 12, 20, height - 10
    sx = lambda t: L + (t - t0).total_seconds() / (t1 - t0).total_seconds() * (R - L)
    sy = lambda v: B + (v - lo) / (hi - lo) * (T_ - B)
    for gv in range(0, int(hi) + 1, 20):
        d.add(Line(L, sy(gv), R, sy(gv), strokeColor=LINEC, strokeWidth=0.4))
        d.add(String(L - 4, sy(gv) - 3, f"{gv}", fontName="Arial", fontSize=6.5, fillColor=GREY, textAnchor="end"))
    d.add(Line(L, sy(0), R, sy(0), strokeColor=colors.black, strokeWidth=0.7))
    for (ta, va), (tb, vb) in zip(series, series[1:]):
        d.add(Line(sx(ta), sy(va), sx(tb), sy(vb), strokeColor=NAVY, strokeWidth=1.1))
    cum = 0.0
    for t, p in pts:
        cum += p
        d.add(Circle(sx(t), sy(cum), 1.7, fillColor=GREEN if p > 0 else RED, strokeColor=None))
    cur = datetime(2026, 8, 24)
    while cur < t1:
        d.add(Line(sx(cur), B, sx(cur), B - 3, strokeColor=GREY, strokeWidth=0.5))
        d.add(String(sx(cur), B - 11, cur.strftime("%d.%m."), fontName="Arial", fontSize=6.5, fillColor=GREY, textAnchor="middle"))
        cur += timedelta(days=14)
    d.add(String(sx(t1) - 2, sy(cum) + 4, f"{f(cum, 1, True)} %", fontName="Arial-Bold", fontSize=8.5, fillColor=NAVY, textAnchor="end"))
    d.add(String(L, T_ + 1, "Gesamt-% kumuliert (Summe der Netto-% aller geschlossenen Trades, Stufe bei jedem Trade-Schluss)", fontName="Arial", fontSize=7, fillColor=GREY))
    return d


# ------------------------------------------------------------------ TradingView-Hinweis
def tv(sym):
    if sym.endswith("=X"):
        base = sym[:-2]
        return "FX:" + {"JPY": "USDJPY", "CAD": "USDCAD", "CHF": "USDCHF"}.get(base, base)
    if sym.endswith("-USD"):
        b = "".join(ch for ch in sym[:-4] if ch.isalpha())
        return "BINANCE:BNBUSDT" if b == "BNB" else f"COINBASE:{b}USD"
    if sym == "ZC=F":
        return "CBOT:ZC1!"
    if sym == "^FTSE":
        return "TVC:UKX"
    return sym


def on_portrait(c, doc):
    _footer(c, doc, PW, PH, 18 * mm)


def on_landscape(c, doc):
    _footer(c, doc, LW, LH, 10 * mm)


def _footer(c, doc, w, h, m):
    c.saveState()
    c.setStrokeColor(LINEC); c.setLineWidth(0.5)
    c.line(m, h - 11 * mm, w - m, h - 11 * mm)
    c.setFillColor(GREY); c.setFont("Arial", 7.5)
    c.drawString(m, h - 9 * mm, f"Pro.1 Baseline – Trade-Journal Zwei-Monats-Test · Stichtag {M['stichtag_berlin']} Uhr (Europe/Berlin)")
    c.line(m, 12 * mm, w - m, 12 * mm)
    c.drawString(m, 8 * mm, "Paper-Trading – keine echte Order, keine Anlageberatung")
    c.drawRightString(w - m, 8 * mm, f"Seite {doc.page}")
    c.restoreState()


def story():
    st = []
    # ================= Deckblatt
    st += [Spacer(1, 4), Paragraph("Pro.1 Baseline – alle Trades des Zwei-Monats-Tests", S["h1"]),
           Paragraph("Trade-Journal zum Nachprüfen: Wie sich die Gesamt-% angesammelt haben", S["sub"])]
    st.append(BOX("blue", "Zeitraum und Stand", [
        f"<b>Teststart:</b> {M['start_berlin']} Uhr (Europe/Berlin) &nbsp;·&nbsp; <b>Stichtag:</b> {M['stichtag_berlin']} Uhr (Europe/Berlin) = {M['stichtag_utc']} UTC.",
        f"Der Stichtag ist der Zeitpunkt des <b>zuletzt an die Gruppe gesendeten Zwischenberichts</b> ({M['report_file_time']} Uhr). "
        "Gezählt werden nur Trades, deren Ausstiegskerze zu diesem Zeitpunkt abgeschlossen war. Trades, die später geschlossen wurden, zählen nicht.",
        "<b>Variante Pro.1 Baseline:</b> die ungefilterte Grundstrategie, kein Break-even, nur auf dem Papier (Paper-Trading, kein echtes Geld)."], WP))
    kp = [["Kennzahl (nur geschlossene Trades)", "Wert"],
          ["Geschlossene Trades", f"<b>{TOT['closed']}</b>"],
          ["Gewinner / Verlierer", f"<b>{TOT['win']} / {TOT['loss']}</b>"],
          ["Trefferquote", f"{f(TOT['hit'], 1)} %"],
          ["Gesamt-% (Summe der Netto-%)", f"<b><font color='#1a9e5c'>{f(TOT['pct'], 1, True)} %</font></b>"],
          ["Netto-R (Summe)", f"<b>{f(TOT['r'], 2, True)} R</b>"],
          ["Offene Trades am Stichtag", f"{TOT['open']} (offen, nicht gewertet – siehe letzte Seite)"]]
    st.append(table(kp, [WP * 0.58, WP * 0.42]))
    st.append(Spacer(1, 4))
    st.append(Paragraph(
        f"<b>Abgleich mit dem Bericht:</b> Diese Zahlen sind identisch mit dem zuletzt gesendeten Zwischenbericht "
        f"({'bestätigt' if M['matches_report'] else 'ABWEICHUNG – siehe Erklärung'}: 65 Trades, 31 Gewinner / 34 Verlierer, +81,9 %, +4,01 R, 16 offen). "
        f"Seitdem wurden {len(M['later_closed'])} weitere Pro.1-Trades geschlossen ({', '.join(s.replace('=X','') for s, _ in M['later_closed'])}); "
        "sie zählen in diesem Stand nicht.", S["body"]))
    st.append(Paragraph("So setzt sich das Ergebnis zusammen", S["h2"]))
    comp = [["Teil", "Trades", "Summe Netto-%"],
            ["Trades, die das <b>Ziel</b> erreichten (Gewinner)", str(TOT["ziel_n"]), f"<font color='#1a9e5c'>{f(TOT['ziel_pct'], 2, True)} %</font>"],
            ["Trades, die der <b>Stop</b> traf (Verlierer)", str(TOT["stop_n"]), f"<font color='#c0392b'>{f(TOT['stop_pct'], 2, True)} %</font>"],
            ["<b>Gesamt-%</b>", f"<b>{TOT['closed']}</b>", f"<b>{f(TOT['pct'], 2, True)} %</b>"]]
    st.append(table(comp, [WP * 0.6, WP * 0.15, WP * 0.25]))
    st.append(Spacer(1, 4))
    cl = [["Instrumentklasse", "Trades", "Gewinner", "Summe Netto-%", "Summe Netto-R"]]
    for k, v in sorted(J["by_class"].items(), key=lambda kv: -kv[1]["n"]):
        cl.append([k, str(v["n"]), str(v["win"]), f(v["pct"], 2, True) + " %", f(v["r"], 2, True)])
    st.append(table(cl, [WP * 0.32, WP * 0.14, WP * 0.16, WP * 0.19, WP * 0.19]))
    st.append(Spacer(1, 6))
    st.append(cum_chart(WP))
    st.append(Paragraph("Jeder Punkt ist ein Trade (grün = Gewinner, rot = Verlierer) zum Zeitpunkt seines Schlusses; die Tabelle ab Seite 3 listet dieselben 65 Trades "
                        "nach Einstieg sortiert, die Spalte „kum. %“ dort summiert in dieser Reihenfolge und endet ebenfalls bei der Gesamt-%.", S["small"]))
    st += [NextPageTemplate("portrait"), PageBreak()]

    # ================= So liest man die Tabelle
    st.append(Paragraph("So liest man die Tabelle – so rechnet man nach", S["h1"]))
    st += [Paragraph("<b>1. Kerzen und Daten.</b>", S["body"])]
    for b in ["<b>Zeitrahmen 4h</b>, aggregiert aus 1-Stunden-Kerzen von Yahoo Finance. Anker 00:00 UTC: Die Kerzen beginnen um 00, 04, 08, 12, 16 und 20 Uhr UTC "
              "(= 02, 06, 10, 14, 18, 22 Uhr Berlin im Sommer). Nur vollständig abgeschlossene Kerzen zählen.",
              "<b>Alle Zeiten</b> stehen in UTC; darunter in kleiner grauer Schrift die Uhrzeit in Europe/Berlin (Sommerzeit, UTC+2).",
              "Eine Zeitangabe bei Einstieg und Ausstieg ist der <b>Beginn der 4h-Kerze</b>. Beim Ausstieg heißt das: In dieser Kerze wurde Stop oder Ziel berührt; "
              "die <b>genaue Minute ist nicht bekannt</b>."]:
        st.append(Paragraph(b, S["bul"], bulletText="•"))
    st.append(Paragraph("<b>2. Wie ein Trade entsteht und endet.</b>", S["body"]))
    for b in ["<b>Signal:</b> Die Bruchkerze ist die 4h-Kerze, die per Schlusskurs eine Trendlinie (Action Line) durchbricht.",
              "<b>Einstieg</b> = Eröffnungskurs der 4h-Kerze <b>nach</b> der Bruchkerze.",
              "<b>Stop</b> = Safety Line, 4 Kerzen vorausgerechnet, danach fest. Pro.1 hat <b>kein Break-even</b>, der Stop wandert nie.",
              "<b>Ziel</b> = nächste Unterstützungs-/Widerstandszone (S/R-Zone).",
              "<b>Ausstieg</b>, sobald das Hoch oder Tief einer 4h-Kerze Stop oder Ziel berührt; gebucht <b>exakt zum Stop- bzw. Zielpreis</b>. "
              f"Wird in derselben Kerze beides berührt, zählt der Stop (so geschehen bei {TOT['ambiguous']} Trade{'s' if TOT['ambiguous'] != 1 else ''}). "
              "Eröffnet eine Kerze mit einer Lücke jenseits des Stops, wird trotzdem zum Stoppreis gebucht – das ist leicht optimistisch."]:
        st.append(Paragraph(b, S["bul"], bulletText="•"))
    st.append(Paragraph("<b>3. Formeln.</b>", S["body"]))
    for b in ["<b>brutto-%</b> = Kursbewegung ÷ Einstieg × 100 (Long: Ausstieg − Einstieg, Short: Einstieg − Ausstieg).",
              "<b>netto-%</b> = brutto-% − Gebühren − Slippage. Gebühren fallen je Seite an (Einstieg und Ausstieg), Slippage ebenfalls.",
              "<b>Gesamt-%</b> = Summe aller netto-% bei <b>gleichem Einsatz je Trade</b>; kein Kapitalkonto, keine Positionsgrößen, keine Wiederanlage.",
              "<b>R</b> = Bewegung ÷ (Einstieg − Stop). 1R ist das geplante Risiko; <b>netto-R</b> = brutto-R − Kosten ÷ Risiko."]:
        st.append(Paragraph(b, S["bul"], bulletText="•"))
    st.append(table([["Instrumentklasse", "Gebühr je Seite", "Slippage je Seite"],
                     ["Devisen", "0,02 %", "0,05 ATR"], ["Aktien/ETFs", "0,02 %", "0,05 ATR"], ["Futures", "0,03 %", "0,05 ATR"],
                     ["Indizes", "0,03 %", "0,05 ATR"], ["Krypto", "0,10 %", "0,05 ATR"]], [WP * 0.4, WP * 0.3, WP * 0.3]))
    ex = next(r for r in ROWS if r["ausgang"] == "Ziel")
    move_pct = ex["brutto_pct"]
    st.append(Spacer(1, 5))
    st.append(BOX("green", f"Rechenbeispiel (Trade Nr. {ex['nr']}, {ex['symbol']} {ex['richtung']})", [
        f"Einstieg {price(ex['einstieg_kurs'])}, Ausstieg am Ziel {price(ex['ausstieg_kurs'])}, Stop {price(ex['stop'])}. "
        f"Risiko 1R = {price(ex['risiko_preis'])} ({f(ex['risiko_pct'], 2)} % vom Einstieg). "
        f"brutto-% = {f(move_pct, 2, True)} %; Kosten (Gebühren + Slippage) = {f(ex['kosten_pct'], 2)} %; "
        f"netto-% = {f(move_pct, 2, True)} − {f(ex['kosten_pct'], 2)} = <b>{f(ex['netto_pct'], 2, True)} %</b>; netto-R = <b>{f(ex['netto_r'], 2, True)}</b>."], WP))
    st.append(Paragraph("<b>4. Kurse nachprüfen.</b>", S["body"]))
    st.append(Paragraph("Datenquelle ist Yahoo Finance (Symbole wie in der Tabelle, z. B. GBPJPY=X, BTC-USD). Auf TradingView findet man dieselben Märkte "
                        "unter ähnlichen Symbolen; Kurse können je Datenanbieter <b>leicht abweichen</b> (andere Börse, Zeitzone, Kerzenraster). "
                        "Das Raster muss auf 4h mit Beginn 00:00 UTC eingestellt sein.", S["body"]))
    syms = sorted({r["symbol"] for r in ROWS} | {o["symbol"] for o in OPEN})
    third = (len(syms) + 2) // 3
    rows_tv = [["Yahoo", "TradingView", "Yahoo", "TradingView", "Yahoo", "TradingView"]]
    for i in range(third):
        line = []
        for c in range(3):
            j = i + c * third
            line += [syms[j], tv(syms[j])] if j < len(syms) else ["", ""]
        rows_tv.append(line)
    st.append(table(rows_tv, [WP * 0.14, WP * 0.19, WP * 0.14, WP * 0.19, WP * 0.14, WP * 0.20], size="t"))
    st.append(Paragraph("Die TradingView-Zuordnung ist ein Vorschlag (z. B. FX:GBPJPY, COINBASE:BTCUSD); je nach Anbieter heißen die Symbole anders.", S["small"]))
    st += [NextPageTemplate("landscape"), PageBreak()]

    # ================= Haupttabelle
    st.append(Paragraph(f"Alle {TOT['closed']} geschlossenen Pro.1-Trades bis zum Stichtag (chronologisch nach Einstieg)", S["h2"]))
    st.append(Paragraph("Zeiten: UTC, darunter Berlin (Bln). Risiko 1R = |Einstieg − Stop|. Gewinner grün, Verlierer rot. „kum. %“ = laufende Summe der netto-% in dieser Reihenfolge.", S["small"]))
    hdr = ["Nr", "Symbol", "Klasse", "Rtg.", "Signal (Bruchkerze)", "Einstieg (Zeit)", "Einstiegs-kurs", "Stop", "Ziel", "Risiko 1R<br/>Preis / %", "Ausstieg (Zeit)",
           "Ausstiegs-kurs", "Aus-gang", "Dauer (Tage)", "brutto-%", "netto-%", "netto-R", "kum. %"]
    wid = [6, 19, 11, 11, 19, 19, 17, 17, 17, 21, 19, 17, 11, 10, 13, 13, 11, 14]
    sc = WL / sum(wid)
    wid = [w * sc for w in wid]
    data = [[Paragraph(h, S["th"]) for h in hdr]]
    ts = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.3, LINEC),
          ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]
    for i, r in enumerate(ROWS, 1):
        win = r["netto_r"] > 0
        col = "#1a9e5c" if win else "#c0392b"
        pc = lambda v, d=2: f"<font color='{col}'>{f(v, d, True)}</font>"
        data.append([Paragraph(str(r["nr"]), S["t"]), Paragraph(f"<b>{r['symbol']}</b>", S["t"]), Paragraph(r["klasse"], S["t"]), Paragraph(r["richtung"], S["t"]),
                     tcell(r["signal_utc"]), tcell(r["einstieg_utc"]), Paragraph(price(r["einstieg_kurs"]), S["tr"]),
                     Paragraph(price(r["stop"]), S["tr"]), Paragraph(price(r["ziel"]), S["tr"]),
                     Paragraph(f"{price(r['risiko_preis'])}<br/>{f(r['risiko_pct'], 2)} %", S["tr"]), tcell(r["ausstieg_utc"]),
                     Paragraph(price(r["ausstieg_kurs"]), S["tr"]), Paragraph(f"<font color='{col}'><b>{r['ausgang']}</b></font>", S["t"]),
                     Paragraph(f(r["dauer_tage"], 1), S["tr"]), Paragraph(pc(r["brutto_pct"]), S["tr"]), Paragraph(f"<b>{pc(r['netto_pct'])}</b>", S["tr"]),
                     Paragraph(pc(r["netto_r"]), S["tr"]), Paragraph(f(r["kum_pct"], 2, True), S["tr"])])
        ts.append(("BACKGROUND", (0, i), (-1, i), GBG if win else RBG))
    n = len(data)
    data.append([Paragraph("<b>Σ</b>", S["t"]), Paragraph(f"<b>{TOT['closed']} Trades · {TOT['win']} Gewinner / {TOT['loss']} Verlierer</b>", S["t"])] + [""] * 12 +
                [Paragraph(f"<b>{f(TOT['brutto_pct'], 2, True)}</b>", S["tr"]), Paragraph(f"<b>{f(TOT['pct'], 2, True)}</b>", S["tr"]),
                 Paragraph(f"<b>{f(TOT['r'], 2, True)}</b>", S["tr"]), Paragraph(f"<b>{f(TOT['pct'], 2, True)}</b>", S["tr"])])
    ts += [("SPAN", (1, n), (13, n)), ("BACKGROUND", (0, n), (-1, n), colors.HexColor("#dbe3f0")), ("LINEABOVE", (0, n), (-1, n), 1, NAVY)]
    t = Table(data, colWidths=wid, repeatRows=1)
    t.setStyle(TableStyle(ts))
    st.append(t)

    # ================= Anhang Linienanker
    st.append(PageBreak())
    st.append(Paragraph("Anhang A – Linienanker zum Nachzeichnen im Chart (4h)", S["h2"]))
    st.append(Paragraph("Eine Linie läuft durch zwei Ankerpunkte (Datum = Beginn der 4h-Kerze in UTC, Kurs = Tief bzw. Hoch dieser Kerze). "
                        "<b>Action Line</b> = die gebrochene Trendlinie, <b>Safety Line</b> = die Gegenlinie, die den Stop bestimmt. Ein Stern (*) markiert einen Anker, "
                        "dessen Kerze in den heutigen Daten nicht exakt diesen Kurs trägt (Daten wurden nachträglich leicht korrigiert).", S["small"]))
    hdr = ["Nr", "Symbol", "Rtg.", "Action: Typ", "Anker 1 (UTC / Kurs)", "Anker 2 (UTC / Kurs)", "Taps", "Safety: Typ", "Anker 1 (UTC / Kurs)", "Anker 2 (UTC / Kurs)", "Taps"]
    wid = [7, 22, 12, 24, 38, 38, 8, 24, 38, 38, 8]
    sc = WL / sum(wid); wid = [w * sc for w in wid]
    data = [[Paragraph(h, S["th"]) for h in hdr]]
    ts = [("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.3, LINEC),
          ("LEFTPADDING", (0, 0), (-1, -1), 2), ("RIGHTPADDING", (0, 0), (-1, -1), 2), ("TOPPADDING", (0, 0), (-1, -1), 1.2), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2)]

    def anc(p):
        return Paragraph(f"{dt(p['time']).strftime('%d.%m.%y %H:%M')} / {price(p['price'])}{'' if p['exact'] else '*'}", S["t"])
    for i, r in enumerate(ROWS, 1):
        a, s = r["anker"]["action"], r["anker"]["safety"]
        data.append([Paragraph(str(r["nr"]), S["t"]), Paragraph(f"<b>{r['symbol']}</b>", S["t"]), Paragraph(r["richtung"], S["t"]),
                     Paragraph(a["kind_de"], S["t"]), anc(a["p"][0]), anc(a["p"][1]), Paragraph(str(a["taps"]), S["t"]),
                     Paragraph(s["kind_de"], S["t"]), anc(s["p"][0]), anc(s["p"][1]), Paragraph(str(s["taps"]), S["t"])])
        if i % 2 == 0:
            ts.append(("BACKGROUND", (0, i), (-1, i), LIGHT))
    t = Table(data, colWidths=wid, repeatRows=1)
    t.setStyle(TableStyle(ts))
    st.append(t)

    # ================= Offene Trades
    st.append(PageBreak())
    st.append(Paragraph(f"Am Stichtag offene Pro.1-Trades – offen, nicht gewertet ({len(OPEN)})", S["h2"]))
    st.append(Paragraph("Diese Trades sind in keiner Kennzahl enthalten. Stop und Ziel sind die festen Werte des Trades. "
                        "Ein Trade, dessen Einstiegskerze am Stichtag noch nicht eröffnet hatte, zeigt „–“. "
                        f"Hinweis: {sum(1 for o in OPEN if o['inzwischen_geschlossen'])} dieser Trades wurden nach dem Stichtag geschlossen (Ergebnis zählt in diesem Stand nicht).", S["small"]))
    hdr = ["Nr", "Symbol", "Klasse", "Richtung", "Signal (Bruchkerze)", "Einstieg (Zeit)", "Einstiegskurs", "Stop", "Ziel", "Status"]
    wid = [8, 26, 18, 18, 30, 30, 26, 26, 26, 38]
    sc = WL / sum(wid); wid = [w * sc for w in wid]
    data = [[Paragraph(h, S["th"]) for h in hdr]]
    for r in OPEN:
        data.append([Paragraph(r["nr"], S["t"]), Paragraph(f"<b>{r['symbol']}</b>", S["t"]), Paragraph(r["klasse"], S["t"]), Paragraph(r["richtung"], S["t"]),
                     tcell(r["signal_utc"]), tcell(r["einstieg_utc"]), Paragraph(price(r["einstieg_kurs"]) if r["einstieg_kurs"] else "–", S["tr"]),
                     Paragraph(price(r["stop"]), S["tr"]), Paragraph(price(r["ziel"]), S["tr"]),
                     Paragraph("offen, nicht gewertet" + (" (später geschlossen)" if r["inzwischen_geschlossen"] else ""), S["t"])])
    t = Table(data, colWidths=wid, repeatRows=1)
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"), ("GRID", (0, 0), (-1, -1), 0.3, LINEC),
                           ("LEFTPADDING", (0, 0), (-1, -1), 3), ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)] +
                          [("BACKGROUND", (0, i), (-1, i), LIGHT) for i in range(2, len(data), 2)]))
    st.append(t)
    return st


def main():
    doc = BaseDocTemplate(OUT, pagesize=A4, title="Pro.1 Baseline – Trade-Journal Zwei-Monats-Test", author="", subject="Paper-Trading, keine Anlageberatung")
    fp = Frame(18 * mm, 16 * mm, WP, PH - 30 * mm, id="p", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    fl = Frame(10 * mm, 16 * mm, WL, LH - 30 * mm, id="l", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
    doc.addPageTemplates([PageTemplate(id="portrait", frames=[fp], onPage=on_portrait, pagesize=A4),
                          PageTemplate(id="landscape", frames=[fl], onPage=on_landscape, pagesize=landscape(A4))])
    doc.build(story())
    print("OK:", OUT)


if __name__ == "__main__":
    main()
