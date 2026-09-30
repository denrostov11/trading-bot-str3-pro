# Str.3 Pro Chart Viewer

Local dashboard for inspecting the paper-trading runtime with TradingView Lightweight Charts.

## Run

From `Prototyp/`:

```bash
../.venv/bin/python -m viewer.server
```

Open:

```text
http://127.0.0.1:8765
```

Optional port override:

```bash
STR3_VIEWER_PORT=8770 ../.venv/bin/python -m viewer.server
```

## What It Reads

- `paper_runtime*/data_cache/*__1h.csv` for OHLCV data
- `paper_runtime*/ledger.json` for candidates, action lines, safety lines, stops, and targets
- `paper_runtime*/trades.json` for paper trades
- `paper_runtime*/last_cycle_monitor.json` for cycle status

The viewer is read-only. It does not place orders and does not change bot state.
