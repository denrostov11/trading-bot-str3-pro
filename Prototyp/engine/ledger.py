# -*- coding: utf-8 -*-
"""Kandidaten-Ledger: protokolliert JEDEN geprueften Kandidaten und JEDE Varianten-Bewertung -
auch abgelehnte/nicht auswertbare (REJECTED_*/NOT_EVALUABLE/DIAGNOSTIC). Ohne dieses Log ist der
Variantenvergleich unmoeglich (behebt D1).

Persistenz: append-only JSON-Datei. Neustart-fest. Keine Secrets. Die lokale Datei ist verbindliche
Quelle (Telegram ist nur Ausgabe). parent_signal_id verbindet Kandidat und alle Varianten-Bewertungen.
"""
import json, os, hashlib, time


def make_candidate_id(parent_signal_id):
    return "CAND-" + hashlib.sha1(parent_signal_id.encode("utf-8")).hexdigest()[:12]


def make_variant_eval_id(parent_signal_id, strategy_id, break_even="BE-1"):
    raw = f"{parent_signal_id}|{strategy_id}|{break_even}"
    return "VE-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


class Ledger:
    def __init__(self, path):
        self.path = path
        self.candidates = []          # Baseline-Kandidaten (inkl. abgelehnter)
        self.variant_evals = []       # Varianten-Bewertungen
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            self.candidates = data.get("candidates", [])
            self.variant_evals = data.get("variant_evals", [])

    def _save(self):
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump({"candidates": self.candidates, "variant_evals": self.variant_evals},
                      f, indent=1, default=str)
        os.replace(tmp, self.path)

    def record_candidate(self, parent_signal_id, symbol, direction, status, signal_time,
                         data_cutoff, rejection_reason="", diagnostics=None, snapshot=None):
        rec = {
            "candidate_id": make_candidate_id(parent_signal_id),
            "parent_signal_id": parent_signal_id, "symbol": symbol, "direction": direction,
            "status": status, "signal_time": signal_time, "data_cutoff_time": data_cutoff,
            "rejection_reason": rejection_reason, "diagnostics": diagnostics or {},
            "snapshot": snapshot, "created_at": time.time(),
        }
        # Idempotenz: je parent_signal_id nur EIN Kandidat
        if not any(c["parent_signal_id"] == parent_signal_id for c in self.candidates):
            self.candidates.append(rec)
            self._save()
        return rec["candidate_id"]

    def record_variant_eval(self, parent_signal_id, strategy_id, strategy_version, status,
                            filter_values=None, rejection_reason="", break_even="BE-1"):
        rec = {
            "variant_evaluation_id": make_variant_eval_id(parent_signal_id, strategy_id, break_even),
            "candidate_id": make_candidate_id(parent_signal_id),
            "parent_signal_id": parent_signal_id, "strategy_id": strategy_id,
            "strategy_version": strategy_version, "break_even": break_even, "status": status,
            "filter_values": filter_values or {}, "rejection_reason": rejection_reason,
            "created_at": time.time(),
        }
        key = rec["variant_evaluation_id"]
        if not any(v["variant_evaluation_id"] == key for v in self.variant_evals):
            self.variant_evals.append(rec)
            self._save()
        return key

    # ---------- Abfragen fuer Berichte / paarweisen Vergleich ----------
    def by_parent(self, parent_signal_id):
        cand = next((c for c in self.candidates if c["parent_signal_id"] == parent_signal_id), None)
        evals = [v for v in self.variant_evals if v["parent_signal_id"] == parent_signal_id]
        return cand, evals

    def variant_evals_for(self, strategy_id):
        return [v for v in self.variant_evals if v["strategy_id"] == strategy_id]

    def counts_by_status(self, strategy_id):
        out = {}
        for v in self.variant_evals_for(strategy_id):
            out[v["status"]] = out.get(v["status"], 0) + 1
        return out
