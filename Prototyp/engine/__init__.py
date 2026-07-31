# -*- coding: utf-8 -*-
"""
Str.3 Pro - Strategie-/Daten-Engine (Phase B, MIGRATION_PLAN S1-S11).

Increment (S1/S2): Datenzugriffsschicht.
  dataaccess  - gekapselter Downloader mit Retry/Backoff/Timeout/Batch (injizierbar, testbar)
  cache       - persistenter, additiver lokaler Kursdaten-Cache (Merge/Dedup/Monotonie, nie kuerzen)
  aggregate_4h- session-/vollstaendigkeitsbewusste 1h->4h-Aggregation (is_final/completeness)

Behebt KRITISCH: A1 (unvollstaendige letzte 4h-Kerze), A2 (Aggregation ohne Anker/Session),
C1 (kein Cache), C2 (kein Retry). Noch NICHT verdrahtet in den laufenden Bot; reiner Neucode.
Cache-Format vorerst CSV (pyarrow/Parquet nicht installiert) - Interface storage-agnostisch.
"""
