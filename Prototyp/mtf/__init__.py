# -*- coding: utf-8 -*-
"""mtf - Top-down-Mehrzeitrahmen-Analyse (Monat, Woche, Tag, 4h, 1h) nach Toris Methode, PROTOTYP.

Reine Auswertungs-/Darstellungsschicht: aendert KEINEN Engine-Code, ist NICHT in den Live-Lauf eingehangen.
Module
  params   - Skalierung der bar-basierten Parameter je Zeitrahmen (+ Kontext-Manager fuer scan_100)
  data     - Tages-/Wochen-/Monats-Aggregation, No-Look-ahead-Schnitt, unfertige Kerzen
  lines    - Linienerkennung je Zeitrahmen (kanonische scan_100-Funktionen mit skalierten Parametern)
  topdown  - informative Top-down-Auswertung (kein Filter)
  cplus_overlay - C+-Stufenpunkte (Muster-Darstellung)
  render   - Vektor-Charts + Trade-PDF
  telegram_text - kompakter Nachrichtenentwurf
Einhaengen nach dem 17.10.2026: trade_pdf.make_trade_pdf(...) mit einem DataProvider aus data.py aufrufen.
"""
