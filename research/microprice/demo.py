"""Exports a static copy of the dashboard's data for hosting without the gateway.

Writes dashboard/public/demo/: the held-out results, the sweep table and one
recorded replay session. The replay keeps every `stride`-th grid step and
carries the fills from skipped steps forward, so the file stays small while
every fill is still shown.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Any

from microprice.gateway import GatewayConfig, session_ticks
from microprice.simulate import HOLDOUT_DAYS

ROOT = Path(__file__).resolve().parents[2]


def recorded_replay(config: GatewayConfig, stride: int) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    pending: list[dict[str, Any]] = []
    step = 0
    for message in session_ticks(config):
        if message["type"] != "tick":
            out.append(message)
            continue
        pending += message["fills"]
        if step % stride == 0 or message["gap"]:
            out.append({**message, "fills": pending})
            pending = []
        step += 1
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description="Export static dashboard data.")
    parser.add_argument("--results", type=Path, default=ROOT / "results")
    parser.add_argument("--out", type=Path, default=ROOT / "dashboard" / "public" / "demo")
    parser.add_argument("--symbol", default="NVDA")
    parser.add_argument("--date", default=HOLDOUT_DAYS[0])
    parser.add_argument("--stride", type=int, default=5, help="keep one grid step in this many")
    args = parser.parse_args()

    args.out.mkdir(parents=True, exist_ok=True)
    shutil.copy(args.results / "holdout.json", args.out / "backtests.json")
    shutil.copy(args.results / "sweep_top.json", args.out / "sweeps.json")
    config = GatewayConfig(
        args.results,
        ROOT / "data" / "synthetic",
        ROOT / "data" / "features" / "features.parquet",
        ROOT / "research" / "models" / "lgbm_fwd10.txt",
        args.symbol,
        args.date,
        "signal",
        0.0,
    )
    replay = recorded_replay(config, args.stride)
    (args.out / "replay.json").write_text(json.dumps(replay, separators=(",", ":")))
    print(f"wrote {len(replay)} messages to {args.out}")


if __name__ == "__main__":
    main()
