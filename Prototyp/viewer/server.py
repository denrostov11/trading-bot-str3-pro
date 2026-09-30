# -*- coding: utf-8 -*-
"""Local TradingView Lightweight Charts dashboard.

Run from Prototyp/:
    ../.venv/bin/python -m viewer.server
"""
from __future__ import annotations

import json
import os
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pandas as pd

from engine import aggregate_4h
from engine.instruments import classify
from engine.cache import _safe


PROTO_DIR = Path(__file__).resolve().parents[1]
STATIC_DIR = Path(__file__).resolve().parent / "static"
DEFAULT_PORT = int(os.environ.get("STR3_VIEWER_PORT", "8765"))
RUNTIME_PREFIX = "paper_runtime"


def _runtime_dirs() -> list[Path]:
    dirs = []
    for path in PROTO_DIR.iterdir():
        if path.is_dir() and path.name.startswith(RUNTIME_PREFIX):
            dirs.append(path)
    return sorted(dirs, key=lambda p: (p.name != "paper_runtime", p.name))


def _runtime_by_name(name: str | None) -> Path:
    runtimes = _runtime_dirs()
    if not runtimes:
        raise FileNotFoundError("No paper_runtime folders found. Run one paper cycle first.")
    if not name:
        return runtimes[0]
    for runtime in runtimes:
        if runtime.name == name:
            return runtime
    raise FileNotFoundError(f"Unknown runtime: {name}")


def _symbol_index(runtime: Path) -> dict[str, dict]:
    cache_dir = runtime / "data_cache"
    out: dict[str, dict] = {}
    if not cache_dir.exists():
        return out

    known = {}
    try:
        import scan_100

        for display_name, candidates in scan_100.INSTRUMENTS:
            for symbol in candidates:
                known[_safe(symbol)] = {"symbol": symbol, "name": display_name}
    except Exception:
        known = {}

    for csv_path in sorted(cache_dir.glob("*__1h.csv")):
        safe_name = csv_path.name[: -len("__1h.csv")]
        meta = known.get(safe_name, {"symbol": safe_name, "name": safe_name})
        symbol = meta["symbol"]
        out[symbol] = {
            "symbol": symbol,
            "name": meta["name"],
            "file": csv_path.name,
        }
    return out


def _read_json(path: Path, fallback):
    if not path.exists():
        return fallback
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def _load_4h(runtime: Path, symbol: str) -> pd.DataFrame:
    cache_path = runtime / "data_cache" / f"{_safe(symbol)}__1h.csv"
    if not cache_path.exists():
        raise FileNotFoundError(f"No cache for symbol {symbol}")
    df = pd.read_csv(cache_path)
    df["Time"] = pd.to_datetime(df["Time"], utc=True)
    cfg = classify(symbol)
    bars = aggregate_4h.aggregate(
        df,
        anchor_hour=cfg["anchor_hour"],
        session_hours=cfg["session_hours"],
    )
    return aggregate_4h.final_only(bars)


def _num(value):
    if pd.isna(value):
        return None
    return float(value)


def _time_to_epoch(value) -> int:
    return int(pd.Timestamp(value).timestamp())


def _bars_payload(df: pd.DataFrame) -> tuple[list[dict], list[dict]]:
    candles = []
    volume = []
    for _, row in df.iterrows():
        ts = _time_to_epoch(row["Time"])
        candles.append(
            {
                "time": ts,
                "open": _num(row["Open"]),
                "high": _num(row["High"]),
                "low": _num(row["Low"]),
                "close": _num(row["Close"]),
            }
        )
        volume.append(
            {
                "time": ts,
                "value": _num(row.get("Volume", 0)) or 0,
                "color": "rgba(109, 123, 142, 0.34)",
            }
        )
    return candles, volume


def _line_payload(anchor, df: pd.DataFrame, signal_time: str | None = None):
    if not anchor or len(anchor) < 4:
        return None
    i0, p0, i1, p1 = int(anchor[0]), float(anchor[1]), int(anchor[2]), float(anchor[3])
    if i0 < 0 or i1 < 0 or i0 >= len(df) or i1 >= len(df) or i0 == i1:
        return None
    points = [
        {"time": _time_to_epoch(df.iloc[i0]["Time"]), "value": p0},
        {"time": _time_to_epoch(df.iloc[i1]["Time"]), "value": p1},
    ]
    if signal_time:
        signal_ts = pd.Timestamp(signal_time)
        matches = df.index[df["Time"] == signal_ts]
        if len(matches):
            idx = int(matches[0])
            if idx > i1:
                slope = (p1 - p0) / (i1 - i0)
                points.append(
                    {
                        "time": _time_to_epoch(df.iloc[idx]["Time"]),
                        "value": p0 + slope * (idx - i0),
                    }
                )
    return points


def _candidate_payload(runtime: Path, symbol: str, df: pd.DataFrame) -> list[dict]:
    ledger = _read_json(runtime / "ledger.json", {"candidates": [], "variant_evals": []})
    evals_by_parent: dict[str, list[dict]] = {}
    for item in ledger.get("variant_evals", []):
        evals_by_parent.setdefault(item.get("parent_signal_id", ""), []).append(item)

    candidates = []
    for cand in ledger.get("candidates", []):
        if cand.get("symbol") != symbol:
            continue
        snap = cand.get("snapshot") or {}
        candidates.append(
            {
                "candidate_id": cand.get("candidate_id"),
                "parent_signal_id": cand.get("parent_signal_id"),
                "symbol": symbol,
                "direction": cand.get("direction"),
                "status": cand.get("status"),
                "signal_time": cand.get("signal_time"),
                "signal_close": snap.get("signal_close"),
                "stop": snap.get("baseline_stop"),
                "target": snap.get("baseline_target"),
                "rr": snap.get("baseline_rr"),
                "rejection_reason": cand.get("rejection_reason", ""),
                "diagnostics": cand.get("diagnostics", {}),
                "action_line": _line_payload(snap.get("action_anchor"), df, cand.get("signal_time")),
                "safety_line": _line_payload(snap.get("safety_anchor"), df, cand.get("signal_time")),
                "variants": evals_by_parent.get(cand.get("parent_signal_id"), []),
            }
        )
    return candidates


def _trade_payload(runtime: Path, symbol: str) -> list[dict]:
    raw = _read_json(runtime / "trades.json", [])
    return [item for item in raw if item.get("symbol") == symbol]


def _chart_payload(query: dict[str, list[str]]) -> dict:
    runtime = _runtime_by_name(query.get("runtime", [""])[0])
    symbol = query.get("symbol", [""])[0]
    if not symbol:
        symbols = _symbol_index(runtime)
        if not symbols:
            raise FileNotFoundError(f"No cached symbols in {runtime.name}")
        symbol = sorted(symbols)[0]

    df = _load_4h(runtime, symbol)
    candles, volume = _bars_payload(df)
    candidates = _candidate_payload(runtime, symbol, df)
    trades = _trade_payload(runtime, symbol)
    monitor = _read_json(runtime / "last_cycle_monitor.json", {})
    return {
        "runtime": runtime.name,
        "symbol": symbol,
        "candles": candles,
        "volume": volume,
        "candidates": candidates,
        "trades": trades,
        "monitor": monitor,
    }


class ViewerHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, fmt, *args):
        print("[viewer] " + fmt % args)

    def _json(self, payload, status=200):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/runtimes":
            self._json({"runtimes": [p.name for p in _runtime_dirs()]})
            return
        if parsed.path == "/api/symbols":
            try:
                runtime = _runtime_by_name(parse_qs(parsed.query).get("runtime", [""])[0])
                self._json({"runtime": runtime.name, "symbols": list(_symbol_index(runtime).values())})
            except Exception as exc:
                self._json({"error": str(exc)}, status=404)
            return
        if parsed.path == "/api/chart":
            try:
                self._json(_chart_payload(parse_qs(parsed.query)))
            except Exception as exc:
                self._json({"error": str(exc)}, status=500)
            return
        if parsed.path == "/":
            self.path = "/index.html"
        return super().do_GET()


def main():
    port = DEFAULT_PORT
    server = ThreadingHTTPServer(("127.0.0.1", port), ViewerHandler)
    print(f"Str.3 chart viewer: http://127.0.0.1:{port}")
    print("Press Ctrl+C to stop.")
    server.serve_forever()


if __name__ == "__main__":
    main()
