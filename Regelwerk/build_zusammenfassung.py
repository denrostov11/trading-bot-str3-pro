# -*- coding: utf-8 -*-
"""Kompakte Bot-Zusammenfassung (max. 4 Seiten) + angehängte Beispiel-Trade-PDF (top-down).

Aufruf (System-Python mit reportlab + pypdf):
    python build_zusammenfassung.py
"""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from pypdf import PdfReader, PdfWriter

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = os.path.dirname(HERE)
OUT = os.path.join(HERE, "Bot_Zusammenfassung_Strategie3Pro.pdf")
BEISPIEL = os.path.join(BASE, "Analysen", "mtf_muster", "v2", "Live_gbpaud_long_2026-10-15.pdf")

pdfmetrics.registerFont(TTFont("Arial", "C:/Windows/Fonts/arial.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Bold", "C:/Windows/Fonts/arialbd.ttf"))
pdfmetrics.registerFont(TTFont("Arial-Italic", "C:/Windows/Fonts/ariali.ttf"))
pdfmetrics.registerFontFamily("Arial", normal="Arial", bold="Arial-Bold", italic="Arial-Italic",
                              boldItalic="Arial-Bold")

INK, MUTED, ACCENT, SOFT, LINE, NEW, NEW_BG = (colors.HexColor(c) for c in (
    "#1d2433", "#5b6478", "#1f5fa8", "#eef3fa", "#c9d2e0", "#6b3fa0", "#f3eefa"))
S = {
    "title": ParagraphStyle("t", fontName="Arial-Bold", fontSize=16, leading=20, textColor=INK),
    "sub": ParagraphStyle("s", fontName="Arial", fontSize=8.5, leading=11.5, textColor=MUTED),
    "h": ParagraphStyle("h", fontName="Arial-Bold", fontSize=11, leading=14, textColor=ACCENT,
                        spaceBefore=5, spaceAfter=2),
    "p": ParagraphStyle("p", fontName="Arial", fontSize=8.2, leading=10.8, textColor=INK, spaceAfter=3),
    "c": ParagraphStyle("c", fontName="Arial", fontSize=7.7, leading=9.7, textColor=INK),
    "cb": ParagraphStyle("cb", fontName="Arial-Bold", fontSize=7.7, leading=9.7, textColor=INK),
}


def P(t, st="p"):
    return Paragraph(t, S[st])


def table(rows, widths, head=True, bg=SOFT):
    data = [[P(c, "cb" if (head and i == 0) else "c") for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if head else 0)
    st = [("GRID", (0, 0), (-1, -1), 0.4, LINE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
          ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4),
          ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 2.5)]
    if head:
        st.append(("BACKGROUND", (0, 0), (-1, 0), bg))
    t.setStyle(TableStyle(st))
    return t


def box(title, lines, color=ACCENT, bg=SOFT):
    rows = [[P(f"<b>{title}</b>", "c")]] + [[P(l, "c")] for l in lines]
    t = Table(rows, colWidths=[174 * mm])
    t.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), bg),
                           ("LINEBEFORE", (0, 0), (0, -1), 3, color),
                           ("LEFTPADDING", (0, 0), (-1, -1), 7), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 1.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 1.5)]))
    return KeepTogether([Spacer(1, 3), t, Spacer(1, 3)])


W2 = [44, 130]
story = [
    P("Strategie 3 Pro – der Trading-Bot kompakt", "title"),
    P("Alle Regeln und wichtigen Infos auf einen Blick · Stand 16.10.2026 · gilt ab dem Neustart am "
      "17.10.2026 · Anhang: Beispiel-Trade-PDF (Monat bis 1h)", "sub"),

    P("1. Der Bot auf einen Blick", "h"),
    table([
        ["Was", "Regel"],
        ["Art", "Reiner <b>Paper-Trading</b>-Simulator: kein Broker, keine echte Order, kein echtes Geld."],
        ["Daten", "Yahoo Finance, 1-Stunden-Kerzen → daraus <b>4h-Kerzen</b> (Raster 00/04/08/12/16/20 UTC). "
                  "Nur fertige Kerzen zählen. War der PC aus, werden verpasste Kerzen der Reihe nach nachgeholt."],
        ["Instrumente", "94: Krypto, Devisen, Futures, Indizes, einige Aktien/ETFs."],
        ["Methode", "Trendlinien nach Tori Trades: <b>Action Line</b> wird per Schlusskurs gebrochen, die "
                    "gegenläufige <b>Safety Line</b> begrenzt das Risiko. Gehandelt wird nur der Bruch (Break)."],
        ["Varianten ab 17.10.", "<b>Pro.1 Baseline</b> (Grundstrategie) · <b>Pro.3 Volumen</b> (Pro.1 + "
                                "Volumenfilter) · <b>C+</b> (Pro.1-Einstiege, neuer Ausstieg; ehemals Pro.2-Gruppe). "
                                "Pro.2 und Pro.4–8 laufen nicht mehr."],
        ["4h-Schlusszeiten (Berlin)", "Sommerzeit 02, 06, 10, 14, 18, 22 Uhr · Winterzeit (ab 25.10.) "
                                      "01, 05, 09, 13, 17, 21 Uhr."],
    ], W2),

    P("2. Begriffe", "h"),
    table([
        ["Begriff", "Bedeutung (Beispiel Gold: Einstieg 2.000 $, Safety Line 1.980 $)"],
        ["<b>R</b>", "Das geplante Risiko eines Trades = Abstand Einstieg → Stop. Hier 1R = 20 $. "
                     "+2R = doppeltes Risiko gewonnen, −1R = geplanter Verlust."],
        ["<b>ATR</b>", "Typische Kerzenlänge eines Instruments (Durchschnitt der letzten 14 4h-Kerzen). "
                       "Z. B. 1 ATR = 10 $. Dadurch passen Regeln für ruhige und wilde Märkte gleichermaßen."],
        ["Docht / Schlusskurs", "Docht = wohin der Kurs zwischendurch lief. Schlusskurs = wo die Kerze endet. "
                                "Signale und C+-Ausstiege zählen nur per Schlusskurs."],
        ["Keil / Apex", "Action und Safety Line laufen aufeinander zu; der Treffpunkt (Apex) liegt höchstens "
                        "180 Kerzen voraus."],
    ], W2),

    P("3. Linien und Signal", "h"),
    table([
        ["Kriterium", "Regel im Code"],
        ["Eckpunkte", "Fraktal K = 3 (Tief/Hoch niedriger bzw. höher als je 3 Kerzen links und rechts), "
                      "erst nach 3 Kerzen bestätigt."],
        ["Berührung (Tap)", "Docht höchstens 0,25 ATR von der Linie; Taps mindestens 6 Kerzen auseinander."],
        ["Action Line", "Mindestens <b>3 Taps</b>, Dauer ≥ 90 Kerzen, Winkel unter 45°."],
        ["Safety Line", "Mindestens 2 Taps, ≥ 90 Kerzen, ≤ 45°, intakt (nie per Schluss gebrochen), richtige Seite, "
                        "ältester Tap höchstens 4 Monate alt. Ohne Safety Line kein Signal."],
        ["Bruch = Signal", "Die gerade fertige 4h-Kerze schließt mehr als 0,15 ATR jenseits der Action Line. "
                           "Nach oben = LONG, nach unten = SHORT."],
        ["Datenqualität", "Futures: Signal innerhalb ±2 Tagen eines Rollover-Verdachts wird abgelehnt. "
                          "Mindestens 90 fertige 4h-Kerzen Historie."],
        ["Sperren", "Je Variante: pro Instrument nur ein offener Trade, danach 24 h Pause, jede Linie nur einmal."],
    ], W2),

    P("4. Einstieg, Stop, Ziel – Pro.1 und Pro.3", "h"),
    table([
        ["Baustein", "Regel"],
        ["Einstieg", "Eröffnungskurs der nächsten 4h-Kerze = genau zum Schluss der Signalkerze. Die Meldung kommt "
                     "künftig 2–5 Min. danach (Ziel); zusätzlich wird ein „realistischer“ Einstieg zum Meldezeitpunkt "
                     "mitgebucht und verglichen."],
        ["Stop", "Wert der Safety Line 4 Kerzen nach dem Bruch, danach <b>fest</b>. Löst intrabar aus (auch per Docht), "
                 "Ausführung zum Stop-Preis. Pro.1 ohne Break-even; Pro.3 mit Break-even BE-1 (ab +0,3 % bei "
                 "Devisen/Indizes bzw. +1,0 % sonst: Stop auf Einstand + 0,02 ATR)."],
        ["Ziel", "Nächste Unterstützungs-/Widerstandszone (≥ 2 Eckpunkte innerhalb 0,6 ATR), mindestens 0,5R entfernt. "
                 "Ohne Zone kein Trade. Die 2R-Mindestregel wird nur protokolliert, nicht erzwungen."],
        ["Gleiche Kerze", "Berührt eine Kerze Stop und Ziel, zählt der Stop (vorsichtig gerechnet)."],
        ["Pro.3 Volumen", "Volumen der Bruchkerze ≥ 1,2 × Median der 20 Kerzen davor. Devisen haben kein Volumen → "
                          "dort handelt Pro.3 nicht."],
        ["Kosten", "Gebühr je Seite: Devisen/Aktien 0,02 %, Indizes/Futures 0,03 %, Krypto 0,10 %; dazu Slippage "
                   "0,05 ATR je Seite. Alle Ergebnisse brutto und netto."],
        ["Wertung", "Ergebnis in R und in Gesamt-% (Summe der Netto-% aller geschlossenen Trades, gleicher Einsatz je "
                    "Trade, kein Kapitalkonto). Offene Trades werden nicht gewertet."],
    ], W2),

    P("5. C+ – der neue Ausstieg (Variante C+)", "h"),
    P("Gleiche Einstiege wie Pro.1, aber <b>kein festes Ziel</b>: Der Trend darf laufen, Gewinne werden stufenweise "
      "gesichert. Alle Schwellen in R und ATR, damit eine Regel für alle Instrumente passt."),
    table([
        ["Stufe", "Wann", "Was passiert (Gold-Beispiel, 1R = 20 $, 1 ATR = 10 $)"],
        ["Grundregel", "immer", "Raus erst, wenn eine 4h-Kerze jenseits der <b>mitwandernden</b> Safety Line "
                                "<b>schließt</b> – Ausführung zum nächsten Eröffnungskurs. Dochte zählen nicht."],
        ["Notfallnetz", "immer", "1 ATR hinter der jeweils gültigen Schwelle; löst sofort aus (Absturz, Kurslücke). "
                                 "Bei Lücke zum tatsächlichen Eröffnungskurs."],
        ["1 Atmen lassen", "Plus unter 1,5R", "Nichts wird nachgezogen."],
        ["2 Kein Verlust", "ab Schluss ≥ +1,5R", "Schwelle auf Einstand + Kosten (≈ 2.002 $), schlusskursbasiert."],
        ["3 Gewinn sichern", "nach jedem bestätigten Zwischentief",
         "Schwelle auf Zwischentief − 0,5 ATR (Rücksetzer ≥ 1 ATR, danach wieder Anstieg; Fraktal K = 3). "
         "Beispiel: 2.060 → 2.040 → 2.070 $ → Schwelle 2.035 $."],
    ], [26, 34, 114]),
    P("Es gilt immer die günstigere von Safety Line und Gewinnschwelle; die Schwelle bewegt sich nur in Gewinnrichtung."),
    box("Nachrechnung Zwei-Monats-Test, nur Pro.1, gleiche Einstiege (abgeschlossene Trades)", [
        "IST (bisher) <b>+81,9 %</b> / +4,0 R · B (nur Schlusskurs) −58,5 % / −36,4 R · <b>C+ +226,5 % / +56,8 R</b> · "
        "D (Docht-Stop nachgezogen) +185,0 % / +69,8 R.",
        "Einordnung: rund 80 % des C+-Vorteils stammen aus drei Krypto-Trends (SOL, ETH, BTC vom 17.08.); bei Devisen "
        "kaum Unterschied. Schwachstelle: zwischen Stufe 2 und erstem Zwischentief kann viel Gewinn verloren gehen "
        "(GBPJPY +9,4 R → −0,1 R). Nur 2 Monate – eine Richtung, kein Beweis.",
    ]),

    P("6. Meldungen und Berichte ab 17.10.", "h"),
    table([
        ["Wo", "Was"],
        ["STR3 System", "Nur noch: <b>Bericht alle 2 Wochen</b> (sonntags 20:00, erstmals 01.11.) · <b>Bericht auf "
                        "Abruf</b> mit „bericht“ · kurze <b>Ausfall-Meldung</b>, wenn ein Eingriff nötig ist (plus „läuft "
                        "wieder“) · <b>Erinnerung an die Zeitumstellung</b> (Vorabend 20:00 und am Tag 08:00). "
                        "Keine Zyklus-Meldungen, kein Herzschlag."],
        ["Bericht-PDF", "Oben groß das Gesamt-% je Gruppe (grün/rot) mit Balkendiagramm; Vergleichstabelle, Details je "
                        "Variante, Klassen, offene Trades („nicht gewertet“), letzte Trades, Systemstatus."],
        ["Gruppen Pro.1 / Pro.3 / C+", "Je Trade: Signal-Schlusszeit, Einstiegszeit und -kurs, aktueller Kurs beim "
                                       "Versand, Abstand zu Einstieg, Stop und Ziel in Preis und R, Status „Einstieg "
                                       "gebucht“. Bei C+ zusätzlich „Stufe 2 erreicht“, „Schwelle nachgezogen“, "
                                       "„Ausstieg (Grund)“."],
        ["Vorwarnungen", "30 und 15 Min. vor 4h-Schluss, wenn ein Bruch möglich ist – nur Information, kein Einstieg; "
                         "danach „bestätigt“ oder „nicht bestätigt“. Nachtruhe 23–07 Uhr. Einstellbar ohne Neustart."],
        ["Trade-PDF", "Statt Bild: Vektor-PDF (zoombar, ca. 250 KB), je Zeitrahmen ein Chart, 2 pro Seite – S.1 Monat + "
                      "Woche, S.2 Tag + 4h, S.3 1h + Kurzbeschreibung. Linien des größeren Zeitrahmens gestrichelt im "
                      "kleineren. Top-down-Bewertung je Zeitrahmen „stützt / neutral / widerspricht“ (Struktur der "
                      "Hochs/Tiefs, Lage zur Linie, frischer Bruch) – nur Information, kein Filter. Beispiel im Anhang."],
    ], W2),

    P("7. Grenzen, die man kennen sollte", "h"),
    table([
        ["Punkt", "Was genau"],
        ["Datenquelle", "Yahoo: Devisen und Krypto nahezu in Echtzeit, Futures und einige Börsen oft 10–15 Min. verzögert."],
        ["Aktien", "Durch das 00:00-UTC-Raster nur 1–2 volle 4h-Kerzen pro Handelstag; bisher keine Aktien-Trades."],
        ["Ausstiege Pro.1/Pro.3", "Immer genau zum Stop- bzw. Zielpreis, auch bei Kurslücken – leicht optimistisch. "
                                  "C+ rechnet Lücken realistisch."],
        ["Spezifikation ↔ Code", "Mindestdauer 90 Kerzen statt 21 Tage; 2R-Regel nur Diagnose; S/R-Zonen bestimmen das "
                                 "Ziel. Maßgeblich ist der Code (Details im Regelwerk)."],
        ["Backtest", "18 Monate (01/2025–06/2026) vorhanden; Vergleich IST / B / C+ / D / „Hälfte bei +2R verkaufen“ folgt "
                     "nach dem Neustart (Werte an 12 Monaten wählen, an 6 Monaten prüfen)."],
    ], W2),

    P("8. Sicherheit", "h"),
    P("Nur Papiergeld · Telegram nur Ausgabe plus „bericht“ – keine Handelsbefehle · Zugangsdaten nur in der geschützten "
      "Konfigurationsdatei, nie im Code oder auf GitHub · Code auf GitHub ohne Daten und Geheimnisse."),
    box("Kurzinfo: Echter Handel später über MetaTrader 5 (MT5)", [
        "<b>Empfehlung:</b> MT5 bei einem EU-regulierten Broker (BaFin o. ä.). Du handelst per App/TradingView, der Bot "
        "über die MT5-Python-Schnittstelle (Windows).",
        "<b>Zwei getrennte Konten:</b> eins für dich, eins nur für den Bot – klare Trennung und direkter Vergleich.",
        "<b>Reihenfolge:</b> erst beide Konten als Demo einige Wochen parallel, dann entscheidest du über Echtgeld. "
        "Konten, Einzahlung, Zugangsdaten und das Einschalten des Echtgeld-Modus liegen bei dir; echte Orders setzt "
        "Claude nicht selbst. Vorher Sicherungen: Risiko-Grenzen, Verlust-Stopp, Not-Aus per Telegram.",
        "CFDs mit Hebel sind riskant (viele Privatkunden verlieren Geld). Technische Empfehlung, keine Anlageberatung.",
    ], color=NEW, bg=NEW_BG),
]


def footer(c, doc):
    c.saveState()
    c.setFont("Arial", 7.5)
    c.setFillColor(MUTED)
    c.drawString(18 * mm, 10 * mm, "Strategie 3 Pro · Paper-Trading – keine echte Order, keine Anlageberatung")
    c.drawRightString(192 * mm, 10 * mm, f"Seite {doc.page}")
    c.restoreState()


tmp = OUT + ".teil1.pdf"
doc = SimpleDocTemplate(tmp, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=12 * mm,
                        bottomMargin=16 * mm, title="Strategie 3 Pro – der Trading-Bot kompakt", author="")
doc.build(story, onFirstPage=footer, onLaterPages=footer)

w = PdfWriter()
main = PdfReader(tmp)
for p in main.pages:
    w.add_page(p)
n_main = len(main.pages)
if os.path.exists(BEISPIEL):
    ex = PdfReader(BEISPIEL)
    for p in ex.pages:
        w.add_page(p)
    w.add_outline_item("Zusammenfassung", 0)
    w.add_outline_item("Anhang: Beispiel-Trade-PDF (GBP/AUD Long, 15.10.)", n_main)
w.add_metadata({"/Title": "Strategie 3 Pro – der Trading-Bot kompakt", "/Author": ""})
with open(OUT, "wb") as fh:
    w.write(fh)
os.remove(tmp)
print("Hauptteil", n_main, "Seiten; gesamt", len(w.pages), "->", OUT)
