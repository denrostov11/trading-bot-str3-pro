# -*- coding: utf-8 -*-
"""mtf - Top-down-Mehrzeitrahmen-Analyse (Monat, Woche, Tag, 4h, 1h) nach Toris Methode, PROTOTYP.

Reine Auswertungs-/Darstellungsschicht: aendert KEINEN Engine-Code.
Module
  params   - Skalierung der bar-basierten Parameter je Zeitrahmen (+ Kontext-Manager fuer scan_100)
  budget   - Zeitlimit (60 s gesamt, 6 s Linien-Suche je Zeitrahmen), MtfTimeout
  data     - Tages-/Wochen-/Monats-Aggregation, No-Look-ahead-Schnitt, unfertige Kerzen, konfigurierbarer Cache (MTF_CACHE_DIR)
  fastlines- schnelle, begrenzte Variante von scan_100.find_lines (identische Ergebnisse)
  lines    - Linienerkennung je Zeitrahmen (kanonische scan_100-Funktionen mit skalierten Parametern)
  topdown  - informative Top-down-Auswertung (Struktur + Lage + Bruch; kein Filter)
  cplus_overlay - C+-Stufenpunkte (Muster-Darstellung)
  render   - Vektor-Charts
  trade_pdf- analyse(...) + make_trade_pdf(...): 3-seitige Trade-PDF (Live-faehig, ohne Ausgangsdaten)
  telegram_text - Kurzbeschreibung (S.3) und Telegram-Text unter der PDF
"""
