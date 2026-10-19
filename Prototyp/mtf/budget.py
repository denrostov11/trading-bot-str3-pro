# -*- coding: utf-8 -*-
"""Zeitbudget fuer die Mehrzeitrahmen-Analyse (harte Obergrenze, kein stilles Haengen).

MtfTimeout wird geworfen, wenn die GESAMTE PDF-Erstellung (analyse + make_trade_pdf) das Limit ueberschreitet; der Aufrufer
faengt sie ab und faellt auf das PNG zurueck. Innerhalb der Linien-Suche gilt zusaetzlich ein kleineres Budget je Zeitrahmen:
wird es ueberschritten, ergibt der Zeitrahmen "keine Linienaussage" (es wird nichts erfunden), die PDF entsteht trotzdem.
"""
import os
import time

TOTAL_SECONDS = float(os.environ.get("MTF_MAX_SECONDS", "60"))     # gesamte PDF-Erstellung
PER_TF_SECONDS = float(os.environ.get("MTF_TF_SECONDS", "6"))      # Linien-Suche je Zeitrahmen


class MtfTimeout(Exception):
    """Zeitlimit der Trade-PDF ueberschritten (Aufrufer: auf PNG zurueckfallen)."""


class Deadline:
    """Einfacher Zeitgeber (monotonic). remaining()/expired()/check()."""

    def __init__(self, seconds, label="Trade-PDF"):
        self.seconds = float(seconds)
        self.label = label
        self.t0 = time.monotonic()

    def elapsed(self):
        return time.monotonic() - self.t0

    def remaining(self):
        return self.seconds - self.elapsed()

    def expired(self):
        return self.remaining() <= 0

    def check(self, where=""):
        if self.expired():
            raise MtfTimeout(f"{self.label}: Zeitlimit {self.seconds:.0f} s überschritten" + (f" ({where})" if where else ""))

    def child(self, seconds, label=None):
        """Unterbudget, hoechstens so lang wie der Rest dieses Budgets."""
        return Deadline(max(0.0, min(float(seconds), self.remaining())), label or self.label)
