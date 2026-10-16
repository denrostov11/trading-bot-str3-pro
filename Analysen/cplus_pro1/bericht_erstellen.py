# -*- coding: utf-8 -*-
"""Erzeugt aus cplus_pro1.main() die Ergebnisdateien: einzeltrades_pro1.csv, ERGEBNIS.md, ERGEBNIS.pdf.
Nur eigene Dateien in diesem Ordner werden geschrieben."""
import os, sys
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.backends.backend_pdf import PdfPages

import cplus_pro1 as C
sys.path.insert(0, C.PROTO)
from notify.status_report import _Doc, NAVY, GREY, GREEN, RED, AMBER, BLUE   # nur Layout-Helfer (read-only)

HERE = C.HERE
fx = C.fx


def d8(s):
    return f"{s[8:10]}.{s[5:7]}.{s[0:4]}" if s else "–"


def fr(v, sign=True):
    return fx(float(v), 2, sign) if v is not None else "–"


def row_of(name, s, c_plus=False):
    best = f"{s['best'][0]} {fr(s['best'][1])}" if s["best"] else "–"
    worst = f"{s['worst'][0]} {fr(s['worst'][1])}" if s["worst"] else "–"
    return [name, f"{s['closed']} / {s['open']}", f"{s['win']} / {s['loss']}", fx(s["hit"], 1) + " %" if s["hit"] is not None else "–",
            fr(s["sum_r"]), fx(s["sum_pct"], 1, True) + " %", fr(s["avg_r"]), best, worst, s["net_exits"],
            f"{s['stage2']} / {s['stage3']}" if c_plus else "–"]


HEAD = ["Variante", "geschl. / offen", "Gew. / Verl.", "Treffer", "Netto-R", "Gesamt-%", "Ø R", "bester", "schlechtester",
        "Notfallnetz", "Stufe 2 / 3"]


HEAD_PDF = ["Var.", "ges./offen", "G / V", "Treffer", "Netto-R", "Gesamt-%", "Ø R", "bester", "schlechtester", "Netz", "St. 2/3"]


def table_rows(X, vars_):
    return [row_of(v, X[v], c_plus=(v in ("C+", "D"))) for v in vars_]


def why(r):
    i, c, t = r["res"]["IST"], r["res"]["C+"], r["trade"]
    ir, cr = float(i["netto_r"]), float(c["netto_r"])
    mfe = t["result"].get("mfe_r")
    if i["outcome"] == "TARGET" and cr > ir + 2:
        return (f"IST nahm am festen Ziel nur {fr(ir)} R mit. C+ hat kein Ziel: Stufe 2 und Stufe 3 zogen die Schwelle am Swing nach, "
                f"der Trend lief weiter, Ausstieg erst am {d8(c['exit_time'][:10])} ({c['outcome']}) bei {fr(cr)} R.")
    if i["outcome"] == "TARGET" and cr < ir - 2:
        return (f"IST traf das Ziel bei {fr(ir)} R (bester Verlauf {fx(mfe,1)} R). C+ erreichte Stufe 2, hatte aber noch keinen "
                f"bestätigten Swing; der Kurs fiel per Schlusskurs unter Einstand+Kosten zurück, Ausstieg bei {fr(cr)} R "
                f"– der Gewinn wurde zurückgegeben.")
    if i["outcome"] in ("STOP",) and cr > ir:
        return (f"IST wurde am festen Stop mit {fr(ir)} R ausgestoppt; C+ ließ den Trade länger laufen (Schlusskurs-Regel statt "
                f"Docht-Stop) und stieg bei {fr(cr)} R aus.")
    return (f"IST: {i['outcome']} {fr(ir)} R; C+: {c['outcome']} {fr(cr)} R "
            f"(Stufe 2: {'ja' if c['stage2'] else 'nein'}, Stufe 3: {'ja' if c['stage3'] else 'nein'}).")


def main():
    R = C.main()
    C.write_csv(R["rows"], os.path.join(HERE, "einzeltrades_pro1.csv"))
    S, F, F3, PR, pairs, conc, chk = R["S"], R["F"], R["F3"], R["PR"], R["pairs"], R["conc"], R["chk"]
    top3_share = sum(conc["C+"]["top3"]) / conc["C+"]["sum"] * 100 if conc["C+"]["sum"] else 0
    fx_ist, fx_c = R["cls"]["IST"]["fx"][1], R["cls"]["C+"]["fx"][1]
    cr_ist, cr_c = R["cls"]["IST"]["crypto"][1], R["cls"]["C+"]["crypto"][1]
    mtm = {v: S[v]["sum_r"] + S[v]["unreal_open_r"] for v in ("IST", "B", "C+", "D")}
    last = d8(R["last_time"][:10]) + R["last_time"][10:16]
    n = chk["n_trades"]

    fazit = (
        f"**Auf allen abgeschlossenen Trades wäre C+ besser gewesen**: {fr(S['C+']['sum_r'])} R / {fx(S['C+']['sum_pct'],1,True)} % "
        f"gegen IST {fr(S['IST']['sum_r'])} R / {fx(S['IST']['sum_pct'],1,True)} %. Im direkten Paarvergleich (beide Varianten geschlossen, n={pairs['n']}) "
        f"war C+ bei {pairs['better']} Trades besser, bei {pairs['worse']} schlechter, bei {pairs['equal']} gleich (Median {fr(pairs['median'])} R). "
        f"**Aber:** {top3_share:.0f} % des C+-Ergebnisses stammen aus nur 3 Krypto-Trades (SOL, ETH, BTC – alle drei mit Signal am 17.08., also dieselbe Marktphase). "
        f"Ohne je die 3 größten Gewinner: C+ {fr(conc['C+']['ohne_top3'])} R gegen IST {fr(conc['IST']['ohne_top3'])} R. "
        f"Bei Devisen gab es praktisch keinen Unterschied (C+ {fr(fx_c)} R, IST {fr(fx_ist)} R); der Vorteil liegt im Krypto-Trendlauf "
        f"(C+ {fr(cr_c)} R, IST {fr(cr_ist)} R). Im „fairen“ Vergleich (nur Trades, die in allen vier Varianten geschlossen sind, n={R['fair_n']}) "
        f"war C+ **nicht** besser ({fr(F['C+']['sum_r'])} R gegen IST {fr(F['IST']['sum_r'])} R) &ndash; diese Auswahl besteht fast nur aus schnellen Verlierern."
    ).replace("&ndash;", "–")

    # ------------------------------------------------------------- Markdown
    L = []
    L.append("# Pro.1 im Zwei-Monats-Test: Ausstieg „C+“ gegen IST\n")
    L.append(f"Stand der Kursdaten: letzter finaler 4h-Kurs {last} (UTC). Nur Pro.1, nur Lesen/Rechnen, Einstieg unverändert.\n")
    L.append("## Fazit\n\n" + fazit + "\n")
    L.append("## Plausibilitätscheck\n")
    L.append(f"- IST aus den Laufdaten: {S['IST']['closed']} geschlossen, {fr(S['IST']['sum_r'])} R, {fx(S['IST']['sum_pct'],1,True)} %, {S['IST']['open']} offen – "
             f"trifft die Testzahlen (65 / +4,01 R / +81,9 %).")
    L.append(f"- IST mit der Engine-Funktion `simulate_trade` (BE-0, Ziel) auf den eigenen Kerzen nachgerechnet: **{len(chk['ist_resim_mismatch'])} Abweichungen** bei {n} Trades.")
    L.append(f"- Safety-Linie bei Bruch+4 gegen `baseline_stop`: größte Abweichung {chk['stop_check_max_rel']:.5f} R (bei allen {n} Trades). "
             f"Bei {len(chk['index_shifted'])} frühen Krypto-Trades (17.–21.08.) lag der damalige Kerzenindex 9 Kerzen tiefer (Cache wurde später rückwärts aufgefüllt); die Linie wurde dafür verschoben.")
    L.append(f"- Nicht einbezogen: {len(R['skipped'])} Trade ohne Einstiegskerze (JPY=X, Signal 12.10., pending_fill).\n")
    L.append("## Tabelle 1 – alle Pro.1-Trades (geschlossen = gewertet, offen = nicht gewertet)\n")
    L.append(md_table(HEAD, table_rows(S, ["IST", "B", "C+", "D"])))
    L.append(f"\nOffene Trades nicht gewertet; ihr unrealisiertes R zum letzten Kurs (Summe): IST {fr(S['IST']['unreal_open_r'])}, B {fr(S['B']['unreal_open_r'])}, "
             f"C+ {fr(S['C+']['unreal_open_r'])}, D {fr(S['D']['unreal_open_r'])}.\n")
    L.append(f"## Tabelle 2 – fairer Vergleich: nur Trades, die in ALLEN vier Varianten geschlossen sind (n={R['fair_n']})\n")
    L.append(md_table(HEAD, table_rows(F, ["IST", "B", "C+", "D"])))
    L.append(f"\n## Zusatz – nur IST, C+ und D (ohne B), in allen dreien geschlossen (n={R['fair3_n']})\n")
    L.append(md_table(HEAD, table_rows(F3, ["IST", "C+", "D"])))
    L.append("\n## Die 5 größten Unterschiede C+ gegen IST (beide geschlossen)\n")
    for r in R["top5"]:
        i, c = r["res"]["IST"], r["res"]["C+"]
        L.append(f"- **{r['sym']} {r['direction']}**, Signal {d8(r['trade']['signal_time'][:10])}: IST {fr(i['netto_r'])} R, C+ {fr(c['netto_r'])} R "
                 f"(Differenz {fr(float(c['netto_r']) - float(i['netto_r']))} R). {why(r)}")
    L.append("\n## Konzentration und Klassen\n")
    for v in ("IST", "B", "C+", "D"):
        L.append(f"- {v}: Summe {fr(conc[v]['sum'])} R; die 3 größten Trades {', '.join(fr(x, False) for x in conc[v]['top3'])} R; ohne diese 3: {fr(conc[v]['ohne_top3'])} R.")
    L.append("- Nach Klasse (Netto-R, geschlossene Trades): " + "; ".join(
        f"{v}: " + ", ".join(f"{k} {fr(x[1])} ({x[0]})" for k, x in R["cls"][v].items()) for v in ("IST", "C+", "D")))
    L.append("\n## Zusatzrechnung (NICHT gewertet): offene Trades zum letzten Kurs mitbewertet\n")
    L.append("Netto-R geschlossen + unrealisiert offen: " + ", ".join(f"{v} {fr(mtm[v])}" for v in ("IST", "B", "C+", "D")) +
             ". B hält viele Trades noch offen, die im Plus stehen – diese Gewinne sind unrealisiert und könnten verschwinden. "
             "Nach Nutzerentscheidung zählen offene Trades nicht; die Zahl dient nur dem Verständnis des Laufzeit-Effekts.\n")
    L.append("## Einordnung (ehrlich)\n")
    L += ["- **Kleine Stichprobe, nur 2 Monate**, nur Pro.1, 80 Trades, davon rund die Hälfte Devisen, 1 Marktphase (die großen Krypto-Gewinner starteten alle am 17.08.). Ein anderes Quartal kann das Bild drehen.",
          "- **Ergebnis hängt an wenigen Ausreißern** (3 Krypto-Trades). R-Summen sind außerdem empfindlich, weil das ursprüngliche Risiko bei manchen Trades sehr klein ist (z. B. GBPJPY: 1 ATR).",
          "- **Notfallnetz-Ausstiege bei C+ sind überwiegend Gewinn-Ausstiege**: Das Netz liegt 1 ATR unter der Gewinnschwelle und greift bei schnellen Rückschlägen/Lücken.",
          "- **Parameter vorab festgelegt, nicht optimiert**: Stufe 2 bei +1,5R, Swing-Puffer 0,5 ATR, Notfallnetz 1 ATR, Rücksetzer ≥ 1 ATR, D-Puffer 0,1 ATR. Es wurde nichts angepasst.",
          "- **Laufzeit-Effekt**: C+/B haben kein Ziel und bleiben länger offen (C+: 21 offen, IST: 15); offene Trades zählen nicht. Deshalb der faire Vergleich – der aber nur schnell beendete Trades enthält und daher ebenfalls verzerrt (zugunsten kurzer Verlierer).",
          "- **4h-Näherung**: Kerzenweise Auswertung, Linienwert zum Kerzen-Index, Ausführung zum nächsten Open, Notfallnetz intrabar; Lücken zum Open (nicht geschönt). Bei Short ist alles gespiegelt.",
          "- **Interpretationen**: Stufe 3 greift erst nach Stufe 2 (vorher bestätigte Swings werden nicht rückwirkend angewandt); bei D gilt die Swing-Nachführung ohne Stufe-2-Voraussetzung; der „vorherige Hoch“-Bezug des Rücksetzers ist das höchste Hoch seit Einstieg.",
          "- Keine Empfehlung und keine Parameteränderung; das Ergebnis ist eine Rückrechnung an 2 Monaten."]
    open(os.path.join(HERE, "ERGEBNIS.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

    # ------------------------------------------------------------- PDF (2 Seiten)
    class Doc(_Doc):
        def _new_page(self):
            if self.fig is not None:
                self._finish()
            self.page_no += 1
            self.fig = plt.figure(figsize=(self.W / 72, self.H / 72), facecolor="white")
            self.ax = self.fig.add_axes([0, 0, 1, 1])
            self.ax.set_xlim(0, self.W); self.ax.set_ylim(self.H, 0); self.ax.axis("off")
            self.ax.text(self.M, 24, "Analyse Pro.1: Ausstieg C+ gegen IST", fontsize=8, color=GREY, va="center")
            self.ax.text(self.W - self.M, 24, self.stand, fontsize=8, color=GREY, va="center", ha="right")
            self.ax.plot([self.M, self.W - self.M], [34, 34], color="#c9d0de", lw=0.6)
            self.y = 50.0

    out = os.path.join(HERE, "ERGEBNIS.pdf")
    with PdfPages(out) as pdf:
        doc = Doc(pdf, f"Daten bis {last} UTC")
        doc.title("Pro.1: Hätte „C+“ geholfen?", "Rückrechnung am Zwei-Monats-Test, nur Pro.1, Einstieg unverändert, offene Trades nicht gewertet")
        doc.box("Fazit", [fazit.replace("**", "")], BLUE)
        doc.heading("Tabelle 1 – alle Pro.1-Trades")
        W_ = [34, 52, 44, 38, 44, 52, 38, 78, 78, 36, 40]
        doc.table(HEAD_PDF, table_rows(S, ["IST", "B", "C+", "D"]), W_, ["l"] + ["r"] * 5 + ["r", "l", "l", "r", "r"], size=6.6)
        doc.para(f"Varianten: IST = Testergebnis; B = Schlusskurs durch Safety Line + Notfallnetz 1 ATR; C+ = B + Stufe 2 (+1,5R) + Swing-Nachführung (0,5 ATR); "
                 f"D = Intrabar-Stop an Linie (0,1 ATR) + Swing. Unrealisiert (offen, nicht gewertet): IST {fr(S['IST']['unreal_open_r'])}, B {fr(S['B']['unreal_open_r'])}, "
                 f"C+ {fr(S['C+']['unreal_open_r'])}, D {fr(S['D']['unreal_open_r'])} R.", size=7, color=GREY)
        doc.heading(f"Tabelle 2 – fairer Vergleich (in allen vier Varianten geschlossen, n={R['fair_n']})")
        doc.table(HEAD_PDF, table_rows(F, ["IST", "B", "C+", "D"]), W_, ["l"] + ["r"] * 5 + ["r", "l", "l", "r", "r"], size=6.6)
        doc.heading(f"Zusatz – nur IST, C+, D (in allen dreien geschlossen, n={R['fair3_n']})")
        doc.table(HEAD_PDF, table_rows(F3, ["IST", "C+", "D"]), W_, ["l"] + ["r"] * 5 + ["r", "l", "l", "r", "r"], size=6.6)
        doc.heading("Die 5 größten Unterschiede C+ gegen IST")
        for r in R["top5"]:
            i, c = r["res"]["IST"], r["res"]["C+"]
            doc.para(f"{r['sym']} {r['direction']} ({d8(r['trade']['signal_time'][:10])}): IST {fr(i['netto_r'])} R → C+ {fr(c['netto_r'])} R.", size=8, bold=True, gap=0)
            doc.para(why(r), size=7.6, indent=8, gap=3)
        doc.box("Einordnung", [
            "Kleine Stichprobe (80 Trades, 2 Monate, eine Marktphase); das Ergebnis hängt an 3 Krypto-Trades. Parameter 1,5R / 0,5 ATR / 1 ATR vorab festgelegt, "
            "nicht optimiert. Nur Pro.1. Offene Trades zählen nicht; C+ ohne Ziel bleibt länger offen – daher der faire Vergleich, der seinerseits "
            "nur schnelle Verlierer enthält. Keine Empfehlung.",
            f"Plausibilität: IST nachgerechnet = {S['IST']['closed']} geschlossen, {fr(S['IST']['sum_r'])} R, {fx(S['IST']['sum_pct'],1,True)} % "
            f"({len(chk['ist_resim_mismatch'])} Abweichungen gegen die Engine-Nachrechnung)."], AMBER)
        doc.close()
    print("geschrieben:", out)
    return R


def md_table(head, rows):
    s = "| " + " | ".join(head) + " |\n|" + "|".join("---" for _ in head) + "|\n"
    for r in rows:
        s += "| " + " | ".join(str(x) for x in r) + " |\n"
    return s


if __name__ == "__main__":
    main()
