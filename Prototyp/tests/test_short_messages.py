# -*- coding: utf-8 -*-
"""Kurze Telegram-Meldungen (19.10.2026): Laengenbegrenzung, Pflichtfelder in der Nachricht, Details in der Trade-PDF
(Kurzbeschreibung S.3), Rueckfall (Details als zweite, getrennte Nachricht, wenn keine PDF entsteht)."""
import os, sys, json
import pandas as pd
import numpy as np
import pytest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from engine import tracker as T, exit_cplus as XC, exit_d as XD, notifier as NOTI, prewarn as PW, trade_doc
from engine.ledger import Ledger
from engine.cache import BarCache
from notify import trade_text as TT, messages as M
from notify.live import TelegramService
from notify.transport import MockTransport

ENV = {"TELEGRAM_BOT_TOKEN": "T", "STR3_PRO1_CHAT_ID": "-101", "STR3_PRO2_CHAT_ID": "-102", "STR3_PRO3_CHAT_ID": "-103",
       "STR3_PRO6_CHAT_ID": "-106", "STR3_COMPARISON_CHAT_ID": "-900", "STR3_SYSTEM_CHAT_ID": "-999"}
GROUPS = ["Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"]
CHAT = {"Str.3 Pro.1": "-101", "Str.3 Pro.3": "-103", "Str.3 C+": "-102", "Str.3 D": "-106"}
PAPER = "Paper-Trading - keine echte Order."
# bisherige Laengen (Beispielmeldungen vor der Kuerzung): Eroeffnung 818-1030 Zeichen / 17-18 Zeilen, Vorwarnung 277 / 7
OLD_OPEN_CHARS, OLD_PREWARN_CHARS = 818, 277
QUOTE = {"price": 75.81, "bar_time": "2026-08-17T12:03:00+00:00", "interval": "1m", "delay_s": 20.0, "fetched_at": "2026-08-17T12:04:00+00:00"}
BOOKED = {"price": 75.73, "time": "2026-08-17T12:00:00+00:00", "partial": True}
# alles, was NICHT mehr in der Meldung stehen darf (steht in der PDF)
DETAIL_WORDS = ("Aktueller Kurs", "Abstand", "Datenverzögerung", "realistisch", "Status", "Top-down", "Grund", "ATR", "1R",
                "parent_signal_id", "Signal-Kerze", "Vorzeichen", "Notfallnetz", "Schwelle")


def mk(sid="Str.3 Pro.1", mode="", direction="LONG"):
    return T.PaperTrade(
        trade_id="T1", variant_evaluation_id="v", parent_signal_id="PSIG-abc", strategy_id=sid, break_even="BE-1", symbol="SOL-USD",
        asset_class="crypto", direction=direction, signal_time="2026-08-17T08:00:00+00:00", stop_initial=74.4812,
        target=0.0 if mode else 78.55, atr=0.517143, exit_mode=mode, signal_end_time="2026-08-17T12:00:00+00:00",
        booked_entry={"signal_close": 75.70}, safety_line={"d0": -30, "p0": 73.9, "d1": -1, "p1": 74.9} if mode else {},
        cplus=(XD.new_state() if mode == "D" else XC.new_state()) if mode else {})


def svc_for(tmp_path):
    tr = MockTransport()
    return TelegramService(GROUPS, env=ENV, transport=tr, queue_path=str(tmp_path / "q.json")), tr


# ======================================================================== Eroeffnung
@pytest.mark.parametrize("sid,mode,short,goal", [("Str.3 Pro.1", "", "Pro.1", "Ziel: 78,55"), ("Str.3 Pro.3", "", "Pro.3", "Ziel: 78,55"),
                                                  ("Str.3 C+", "CPLUS", "C+", "Ausstieg nach C+"), ("Str.3 D", "D", "D", "Ausstieg nach D")])
def test_open_message_is_short_and_has_exactly_the_required_fields(tmp_path, sid, mode, short, goal):
    svc, tr = svc_for(tmp_path)
    svc.trade_opened(mk(sid, mode), quote=QUOTE, booked=BOOKED)
    txt = tr.texts_to(CHAT[sid])[0]
    ln = txt.splitlines()
    assert ln == [f"{short} · SOL-USD · LONG", "Einstieg: 17.08. 14:00 Uhr · Kurs 75,73", "Stop: 74,4812", goal,
                  "Details in der PDF", PAPER]
    assert len(ln) <= 6 and len(txt) <= 200 and len(txt) < OLD_OPEN_CHARS / 3
    assert not any(w in txt for w in DETAIL_WORDS)
    if mode:
        assert "Ziel:" not in txt


def test_open_message_waiting_for_entry_and_short_direction(tmp_path):
    svc, tr = svc_for(tmp_path)
    svc.trade_opened(mk(direction="SHORT"), quote=None, booked=None)
    ln = tr.texts_to("-101")[0].splitlines()
    assert ln[0] == "Pro.1 · SOL-USD · SHORT" and ln[1] == "Einstieg: ab 17.08. 14:00 Uhr · Kurs folgt" and len(ln) == 6


def test_attachment_caption_is_short(tmp_path):
    svc, tr = svc_for(tmp_path)
    svc.trade_attachment(mk(), "x.pdf")
    svc.trade_attachment(mk("Str.3 D", "D"), "y.png")
    pdf, png = tr.sent[0], tr.sent[1]
    assert pdf["kind"] == "document" and pdf["caption"].splitlines() == ["Pro.1 · SOL-USD · LONG · Trade-PDF", PAPER]
    assert png["caption"].splitlines() == ["D · SOL-USD · LONG · Chart", PAPER]


# ======================================================================== Rueckfall: Details als zweite Nachricht
def _notifier(base, doc, svc):
    store = T.PaperTradeStore(str(base / "t.json"))
    t = mk()
    t.status = "open"
    store.add(t)
    return NOTI.TradeNotifier(svc, store, doc_fn=lambda t: doc, quote_fn=lambda s: dict(QUOTE),
                              book_fn=lambda *a: dict(BOOKED)), store


def test_details_only_as_second_message_when_pdf_missing(tmp_path):
    svc, tr = svc_for(tmp_path)
    n, store = _notifier(tmp_path, None, svc)                      # keine PDF, kein PNG
    n.notify_all()
    texts = tr.texts_to("-101")
    assert len(texts) == 2 and len(texts[0].splitlines()) == 6                                       # 1. Nachricht bleibt kurz
    det = texts[1]
    assert det.splitlines()[0] == "Pro.1 · SOL-USD · LONG · Details (PDF nicht verfügbar)"
    for must in ("Signal-Kerze geschlossen: 17.08.2026 14:00 Uhr (MESZ)", "Status: Einstieg gebucht", "gebuchter Kurs 75,73",
                 "Aktueller Kurs: 75,81", "Abstand Kurs zu Einstieg", "Abstand Kurs zu Stop", "Abstand Kurs zu Ziel",
                 "Datenverzögerung: keine messbare", "realistischer Einstieg", "parent_signal_id: PSIG-abc", "Stop: 74,4812 (1R = "):
        assert must in det, must
    assert det.endswith(PAPER)
    n.notify_all()                                                  # idempotent: nichts doppelt
    assert len(tr.texts_to("-101")) == 2


def test_details_sent_with_png_fallback_but_not_with_pdf(tmp_path):
    a = tmp_path / "a"; a.mkdir()
    svc, tr = svc_for(a)
    n, _ = _notifier(a, "chart.png", svc)
    n.notify_all()
    assert [r["kind"] for r in tr.sent] == ["text", "document", "text"] and "Details (PDF nicht verfügbar)" in tr.sent[2]["payload"]
    b = tmp_path / "b"; b.mkdir()
    svc2, tr2 = svc_for(b)
    n2, _ = _notifier(b, "trade.pdf", svc2)
    n2.notify_all()
    assert [r["kind"] for r in tr2.sent] == ["text", "document"]                                      # PDF da -> keine zweite Textnachricht


# ======================================================================== Vorwarnung / Aufloesung / Ereignisse
def test_prewarn_text_is_half_length_or_less():
    b = pd.Timestamp("2026-08-17T12:00:00+00:00")
    for sid in ("Str.3 Pro.1", "Str.3 Pro.3", "Str.3 C+", "Str.3 D"):
        m = M.Message(sid, "v1", M.PREWARN, symbol="SOL-USD", signal_id="PW:x", compact=True,
                      body=PW.warn_text("SOL-USD", "LONG", b, sid), title=PW.warn_title("SOL-USD", "LONG"))
        txt = m.render_text()
        ln = txt.splitlines()
        assert len(ln) <= 3 and len(txt) <= OLD_PREWARN_CHARS / 2
        assert ln[0] == "Vorwarnung · SOL-USD · LONG" and ln[1].startswith("Kerze schließt um 14:00 Uhr") and ln[-1] == PAPER


def test_resolution_is_one_content_line():
    b = pd.Timestamp("2026-08-17T12:00:00+00:00")
    for res in ("bestätigt", "nicht bestätigt"):
        title = PW.resolve_title("SOL-USD", "SHORT", b, res)
        txt = M.Message("Str.3 Pro.1", "v1", M.PREWARN_RESOLVED, symbol="SOL-USD", signal_id="x", compact=True, body="", title=title).render_text()
        assert txt.splitlines() == [f"Vorwarnung 14:00 Uhr · SOL-USD · SHORT: {res}", PAPER]


def test_event_messages_are_short_and_keep_the_key_number(tmp_path):
    svc, tr = svc_for(tmp_path)
    for mode, sid in (("CPLUS", "Str.3 C+"), ("D", "Str.3 D")):
        t = mk(sid, mode)
        t.result = {"status": "closed", "netto_r": -0.35, "net_return_pct": -0.62, "exit_price": 74.9}
        short = "C+" if mode == "CPLUS" else "D"
        trail = {"id": "TRAIL:a", "kind": XC.EV_TRAIL, "time": "2026-08-19T08:00:00+00:00", "level": 77.12, "swing_price": 77.9, "swing_time": "x"}
        ex = {"id": "EXIT:a", "kind": XC.EV_EXIT, "time": "2026-08-20T12:00:00+00:00",
              "outcome": XD.OUT_STOP if mode == "D" else XC.OUT_LINE, "price": 74.9}
        svc.cplus_event(t, trail)
        svc.cplus_event(t, ex)
        tx, ex_txt = tr.texts_to(CHAT[sid])[-2:]
        assert len(tx.splitlines()) <= 3 and len(ex_txt.splitlines()) <= 3
        assert f"{'Neuer Stop' if mode == 'D' else 'Neue Schwelle'}: 77,12" in tx and tx.startswith(f"{short} · SOL-USD · LONG · ")
        assert "Kurs 74,9" in ex_txt and "−0,35 R netto" in ex_txt and "Ausstieg" in ex_txt.splitlines()[0]     # Ausstiegskurs + Ergebnis in R
        assert tx.endswith(PAPER) and ex_txt.endswith(PAPER)
    t = mk("Str.3 C+", "CPLUS")
    svc.cplus_event(t, {"id": "STAGE2:a", "kind": XC.EV_STAGE2, "time": "2026-08-18T16:00:00+00:00", "level": 75.86})
    s2 = tr.texts_to("-102")[-1]
    assert s2.splitlines()[:2] == ["C+ · SOL-USD · LONG · Stufe 2 erreicht", "Neue Schwelle: 75,86 (Einstand + Kosten)"] and len(s2.splitlines()) == 3


def test_pro1_result_message_is_short(tmp_path):
    svc, tr = svc_for(tmp_path)
    t = mk()
    t.status = "closed"
    t.result = {"status": "closed", "outcome": "TARGET", "netto_r": 2.12, "net_return_pct": 3.41, "exit_price": 78.55}
    svc.trade_closed(t)
    assert tr.texts_to("-101")[0].splitlines() == ["Pro.1 · SOL-USD · LONG · Ziel erreicht", "Kurs 78,55 · +2,12 R netto (+3,41 %)", PAPER]


# ======================================================================== Trade-PDF: ALLE entfernten Angaben stehen in der Beschreibung (S.3)
from mtf import data as D, trade_pdf as TP, telegram_text as MT


def _synthetic(hours=24 * 70, signal="2026-03-05T08:00:00+00:00"):
    t = pd.date_range("2026-01-01", periods=hours, freq="h", tz="UTC")
    rng = np.random.default_rng(7)
    o = 100 + np.cumsum(rng.normal(0, 0.15, hours))
    h1 = D.with_end(pd.DataFrame({"Time": t, "Open": o, "High": o + 0.2, "Low": o - 0.2, "Close": o + rng.normal(0, 0.05, hours), "Volume": 1.0}),
                    pd.Timedelta(hours=1))
    trade = {"symbol": "TEST-USD", "direction": "LONG", "signal_time": signal, "strategy_id": "Str.3 Pro.1", "asset_class": "crypto",
             "stop_initial": 98.0, "target": 103.0, "entry_price": 100.5, "entry_time": "2026-03-05T12:00:00+00:00",
             "parent_signal_id": "PSIG-test", "booked_entry": {"price": 100.5, "time": "2026-03-05T12:00:00+00:00", "partial": True}}
    return h1, trade


LIVE = {"price": 101.2, "time": "2026-03-05T12:03:00+00:00", "sent_at": "2026-03-05T12:04:00+00:00", "interval": "1m", "delay_s": 20.0}
COMMON = ("Symbol / Richtung : TEST-USD · LONG (Kauf) · Variante Str.3 Pro.1", "Status            : Einstieg gebucht",
          "Signal-Kerze      : Schluss 05.03.2026 13:00 MEZ", "Einstieg          : 05.03.2026 13:00 MEZ · Kurs 100,5 (gebucht, Open der Folgekerze",
          "Grund", "1R = 2,5", "ATR (14, 4h)", "Top-down", "Aktueller Kurs    : 101,2 (Kursbalken 13:03 MEZ, Versand 13:04 MEZ, 1m-Daten)",
          "Abstand Einstieg  : +0,7 (+0,28 R)", "Abstand Stop      : +3,2 (+1,28 R)", "Datenverzögerung  : keine messbare",
          "Realist. Einstieg : 101,2 (Kurs beim Versand, 13:04 MEZ)", "parent_signal_id  : PSIG-test", "Paper-Trading")


def test_pdf_description_has_all_details_pro1():
    h1, trade = _synthetic()
    A = TP.analyse(trade, None, h1, None, 0.0005, live_info=LIVE)
    desc = MT.description(A)
    for s_ in COMMON + ("Ziel              : 103", "Abstand Ziel      : +1,8 (+0,72 R)"):
        assert s_ in desc, s_
    assert len(TP._wrap(desc, 108, indent=20).splitlines()) <= 32                  # passt auf Seite 3


def test_pdf_description_exit_rules_for_cplus_and_d():
    h1, trade = _synthetic()
    lv = {"threshold": 97.0, "net": 96.0, "source": "SAFETY"}
    A = TP.analyse(dict(trade, exit_mode="CPLUS", exit_level=lv), None, h1, None, 0.0005, c_plus={}, live_info=LIVE)
    d = MT.description(A)
    assert "Ausstieg nach C+" in d and "Notfallnetz" in d and "Aktuelle Schwelle : ≈ 97 (bei Einstieg) · Notfallnetz ≈ 96" in d
    assert "Abstand Schwelle  : +4,2 (+1,68 R)" in d and "Ziel              : kein festes Ziel" in d
    A = TP.analyse(dict(trade, strategy_id="Str.3 D", exit_mode="D", target=0.0, exit_level=lv), None, h1, None, 0.0005, live_info=LIVE)
    d = MT.description(A)
    assert "Ausstieg nach D" in d and "jede Berührung, auch ein Docht, löst aus" in d and "Aktueller Stop    : ≈ 97" in d
    assert "Abstand akt. Stop : +4,2 (+1,68 R)" in d and "Variante Str.3 D" in d


def test_pdf_description_delay_deviation_and_missing_quote():
    h1, trade = _synthetic()
    A = TP.analyse(trade, None, h1, None, 0.0005, live_info=dict(LIVE, price=102.0, delay_s=900.0))
    d = MT.description(A)
    assert "ca. 15 Min. (letzter Kursbalken 13:03 MEZ)" in d
    assert "Kurs weicht bereits 0,60 R vom Einstieg ab (ungünstig für einen späteren Einstieg)" in d
    short = dict(trade, direction="SHORT", stop_initial=103.0, target=97.0)
    d = MT.description(TP.analyse(short, None, h1, None, 0.0005, live_info=dict(LIVE, price=102.0)))      # Short: Kurs gestiegen = gegen die Richtung
    assert "(günstig für einen späteren Einstieg)" in d
    pend = dict(trade, entry_price=0.0, entry_time="", booked_entry={})
    d = MT.description(TP.analyse(pend, None, h1, None, 0.0005))
    assert "wartet auf Einstieg" in d and "Aktueller Kurs    : nicht verfügbar" in d and "Realist. Einstieg : nicht verfügbar" in d


def test_pdf_with_new_description_has_three_pages_and_stays_valid(tmp_path):
    import re
    h1, trade = _synthetic()
    A = TP.analyse(dict(trade, exit_mode="CPLUS", exit_level={"threshold": 97.0, "net": 96.0}), None, h1, None, 0.0005, c_plus={}, live_info=LIVE)
    out = str(tmp_path / "d.pdf")
    TP.make_trade_pdf(out, A, MT.description(A))
    assert len(re.findall(rb"/Type /Page(?!s)", open(out, "rb").read())) == 3 and not os.path.exists(out + ".part")


# ======================================================================== trade_doc: reicht die Details an die PDF weiter
def _worker_dump_args(args, q):
    json.dump(args, open(args["out"] + ".json", "w"), default=str)
    open(args["out"], "wb").write(b"%PDF-1.4 fake")
    q.put(("ok", args["out"]))


def test_trade_doc_passes_booked_entry_live_details_and_exit_level(tmp_path):
    cache = BarCache(str(tmp_path / "c"))
    cache.merge("SOL-USD", "1h", pd.DataFrame({"Time": pd.date_range("2026-10-01", periods=50, freq="h", tz="UTC"),
                                              "Open": 1.0, "High": 1.0, "Low": 1.0, "Close": 1.0, "Volume": 1.0}))
    lg = Ledger(str(tmp_path / "l.json"))
    lg.record_candidate("PSIG-abc", "SOL-USD", "LONG", "ACCEPTED_PROVISIONAL", "2026-08-17T08:00:00+00:00", "t",
                        snapshot={"atr": 1.0, "action_anchor": [0, 1, 1, 1, "x", 3, 1.0], "safety_anchor": [0, 1, 1, 1, "x", 3, 1.0]})
    t = mk("Str.3 C+", "CPLUS")
    t.booked_entry = {"signal_close": 75.7, **BOOKED}
    t.realistic = {"price": 75.81, "quote_time": QUOTE["bar_time"], "sent_at": QUOTE["fetched_at"], "interval": "1m", "delay_s": 20.0}
    p = trade_doc._make_pdf(str(tmp_path), t, lg, cache, 60, [], worker=_worker_dump_args)
    a = json.load(open(p + ".json"))
    assert a["trade"]["entry_price"] == 75.73 and a["trade"]["entry_time"] == BOOKED["time"]
    assert a["live"] == {"price": 75.81, "time": QUOTE["bar_time"], "sent_at": QUOTE["fetched_at"], "interval": "1m", "delay_s": 20.0}
    lv = a["trade"]["exit_level"]
    assert lv["threshold"] is not None and lv["net"] is not None
