# -*- coding: utf-8 -*-
"""Trade-Benachrichtigungen (A4) mit Zustellmarken am Trade (at-least-once, die Queue dedupliziert).

Ein Telegram-Fehler aendert NIE einen Trade-Zustand: jede Meldung ist einzeln abgesichert; die Marken
`notif.opened` / `notif.closed` und `cplus.events[].sent` werden erst nach erfolgreichem Einreihen gesetzt.

Pro Eroeffnung werden zusaetzlich gespeichert (Wertung bleibt der theoretische Einstieg):
- booked_entry : gebuchter (theoretischer) Einstieg = Open der Folgekerze
- realistic    : realistischer Einstieg = Kurs beim Versand (1m/5m-Daten) samt Zeit/Verzoegerung
"""
from datetime import datetime, timezone

from . import entry_booking, livequote
from . import exit_cplus as XC


class TradeNotifier:
    def __init__(self, svc, trades, cache=None, runtime_dir=None, inst_by_sym=None,
                 quote_fn=None, book_fn=None, doc_fn=None, log=None, clock=None):
        self.svc, self.trades, self.cache, self.rt = svc, trades, cache, runtime_dir
        self.inst = inst_by_sym or {}
        self.quote_fn = quote_fn or livequote.fetch_quote
        self.book_fn = book_fn or entry_booking.book_entry
        self.doc_fn = doc_fn or (lambda t: None)       # Anhang (Trade-PDF / PNG) je Trade, None = kein Anhang
        self.log = log if log is not None else []
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._quotes = {}
        self._docs = {}
        self.first_sent_at = None

    def _quote(self, sym, asset_class):
        if sym not in self._quotes:
            q = None
            try:
                q = self.quote_fn(sym)
            except Exception as e:
                self.log.append(f"Kurs {sym}: {type(e).__name__}")
            self._quotes[sym] = q
            if self.rt:
                livequote.log_delay(self.rt, sym, asset_class, q)
        return self._quotes[sym]

    def refresh_bookings(self):
        """Bucht den Einstieg nach, sobald die Folgekerze eroeffnet ist (z. B. nach Marktschluss)."""
        for t in self.trades.trades:
            if t.status in ("pending_fill", "open") and not (t.booked_entry or {}).get("price"):
                inst = self.inst.get(t.symbol, {})
                try:
                    b = self.book_fn(self.cache, t.symbol, t.signal_time, inst.get("anchor_hour", 0),
                                     inst.get("session_hours"), self.clock())
                except Exception:
                    b = None
                if b:
                    t.booked_entry = {**(t.booked_entry or {}), **b}

    def notify_all(self):
        """Sendet alle noch nicht gemeldeten Eroeffnungen, C+-Ereignisse und Schliessungen."""
        sent_any = False
        for t in list(self.trades.trades):
            try:
                sent_any |= self._one(t)
            except Exception as e:
                self.log.append(f"Meldung {t.trade_id}: {type(e).__name__}")
        # Anhaenge (Trade-PDF/PNG) ZULETZT: alle Texte sind dann schon raus, die PDF-Erstellung verzoegert keine Meldung
        for t in list(self.trades.trades):
            if (t.notif or {}).get("opened") and not (t.notif or {}).get("doc"):
                try:
                    doc = self._doc(t)
                    if doc:
                        self.svc.trade_attachment(t, doc)
                        sent_any = True
                    if not (doc and str(doc).lower().endswith(".pdf")):
                        sent_any |= self._send_details(t)          # keine PDF -> Details als zweite, getrennte Nachricht
                    t.notif = {**(t.notif or {}), "doc": self.clock().isoformat()}
                    self.trades._save()
                except Exception as e:
                    self.log.append(f"Anhang {t.trade_id}: {type(e).__name__}")
        try:
            self.trades._save()
        except Exception:
            pass
        return sent_any

    def _one(self, t):
        sent = False
        now = self.clock()
        if not (t.notif or {}).get("opened"):
            inst = self.inst.get(t.symbol, {})
            booked = None
            if (t.booked_entry or {}).get("price"):
                booked = {"price": t.booked_entry["price"], "time": t.booked_entry["time"],
                          "partial": t.booked_entry.get("partial", False)}
            else:
                try:
                    booked = self.book_fn(self.cache, t.symbol, t.signal_time, inst.get("anchor_hour", 0),
                                          inst.get("session_hours"), now)
                except Exception:
                    booked = None
                if booked:
                    t.booked_entry = {**(t.booked_entry or {}), **booked}
            quote = self._quote(t.symbol, t.asset_class)
            if quote and not t.realistic:
                t.realistic = {"price": quote["price"], "quote_time": quote["bar_time"], "sent_at": now.isoformat(),
                               "interval": quote["interval"], "delay_s": quote.get("delay_s")}
            self.svc.trade_opened(t, chart_path=None, quote=quote, booked=booked)       # Text SOFORT
            t.notif = {**(t.notif or {}), "opened": now.isoformat()}
            self.first_sent_at = self.first_sent_at or now
            sent = True
            try:
                self.trades._save()                                                      # Marke vor dem (langsamen) Anhang sichern
            except Exception:
                pass
        if t.exit_mode in ("CPLUS", "D"):
            for ev in (t.cplus or {}).get("events", []):
                if not ev.get("sent"):
                    self.svc.cplus_event(t, ev)
                    ev["sent"] = True
                    sent = True
                    if ev["kind"] == XC.EV_EXIT:
                        t.notif = {**(t.notif or {}), "closed": now.isoformat()}
        elif t.status == "closed" and not (t.notif or {}).get("closed"):
            self.svc.trade_closed(t)
            t.notif = {**(t.notif or {}), "closed": now.isoformat()}
            sent = True
        return sent

    def _send_details(self, t):
        """Rueckfall ohne Trade-PDF: ausfuehrlicher Text (frueherer Meldungsinhalt) als ZWEITE Nachricht, aus den am Trade
        gespeicherten Werten (gebuchter Einstieg, realistischer Einstieg = Kurs beim Versand)."""
        fn = getattr(self.svc, "trade_details", None)
        if fn is None:
            return False
        rz = t.realistic or {}
        quote = None
        if rz.get("price") is not None:
            quote = {"price": rz["price"], "bar_time": rz.get("quote_time"), "interval": rz.get("interval") or "",
                     "delay_s": rz.get("delay_s"), "fetched_at": rz.get("sent_at")}
        be = t.booked_entry or {}
        booked = {"price": be["price"], "time": be["time"], "partial": be.get("partial", False)} if be.get("price") else None
        fn(t, quote=quote, booked=booked)
        return True

    def _doc(self, t):
        key = (t.parent_signal_id, t.exit_mode or "BASE")        # Pro.1/Pro.3 (Ziel) und C+ (kein Ziel) bekommen eigene Anhaenge
        if key not in self._docs:
            try:
                self._docs[key] = self.doc_fn(t)
            except Exception as e:
                self.log.append(f"Anhang {t.symbol}: {type(e).__name__}")
                self._docs[key] = None
        return self._docs[key]
