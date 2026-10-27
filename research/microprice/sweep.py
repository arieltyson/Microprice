"""Distributed strategy parameter sweeps on Apache Spark.

Each parameter set is scored on the selection day (day 3) for all ten
symbols over the opening half hour, so 1,280 parameter sets make 12,800
backtests. Sessions are packed into .npz files once, and every
Spark partition loads them a single time before running its share of the grid.
The same function runs on a laptop with `local[*]` and on Amazon EMR.
"""

from __future__ import annotations

import argparse
import itertools
import json
import time
from collections.abc import Iterator
from dataclasses import fields
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from microprice import backtest, lobster, stats
from microprice.simulate import SELECT_DAYS, SessionInputs, load_booster, load_session
from microprice.synth import PROFILES

GRID: dict[str, list[Any]] = {
    "gamma": [0.02, 0.05, 0.1, 0.2, 0.4],
    "kappa": [0.5, 1.0, 1.5, 3.0],
    "tau_s": [10.0, 30.0, 60.0, 120.0],
    "alpha": [0.0, 0.5, 1.0, 2.0],
    "beta": [0.0, 2.0, 5.0, 10.0],
}
# Grid indices 09:30:01 to 10:00:00. Starting at the open means no run has to
# replay earlier order flow before its first decision.
WINDOW = (0, 1800)


def param_grid() -> list[dict[str, Any]]:
    keys = list(GRID)
    return [dict(zip(keys, values, strict=True), param_id=i)
            for i, values in enumerate(itertools.product(*GRID.values()))]  # fmt: skip


def pack_sessions(data_root: Path, features_path: Path, model_path: Path, out: Path, day: str) -> list[Path]:
    table = pd.read_parquet(features_path)
    booster = load_booster(model_path)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for profile in PROFILES:
        s = load_session(data_root, table, booster, profile.symbol, day)
        path = out / f"{profile.symbol}_{day}.npz"
        np.savez(
            path, ts=s.columns.ts, type=s.columns.type, order_id=s.columns.order_id,
            size=s.columns.size, price=s.columns.price, direction=s.columns.direction,
            grid_ns=s.grid_ns, mid=s.mid, sigma2=s.sigma2, forecast=s.forecast, sentiment=s.sentiment,
        )  # fmt: skip
        paths.append(path)
    return paths


def load_packed(path: Path) -> SessionInputs:
    z = np.load(path)
    columns = lobster.MessageColumns(z["ts"], z["type"], z["order_id"], z["size"], z["price"], z["direction"])
    symbol, day = path.stem.split("_", 1)
    return SessionInputs(
        symbol, day, columns, z["grid_ns"], z["mid"], z["sigma2"], z["forecast"], z["sentiment"]
    )


def strategy_params(row: dict[str, Any]) -> backtest.StrategyParams:
    names = {f.name for f in fields(backtest.StrategyParams)}
    return backtest.StrategyParams(**{k: v for k, v in row.items() if k in names})


def evaluate(
    row: dict[str, Any], sessions: list[SessionInputs], window: tuple[int, int] = WINDOW
) -> dict[str, Any]:
    params = strategy_params(row)
    minute_pnl: list[np.ndarray] = []
    pnl = fills = quotes = 0.0
    markout10: list[float] = []
    for full in sessions:
        s = full.window(*window)
        result = backtest.run(s.columns, s.grid_ns, s.mid, s.sigma2, s.forecast, s.sentiment, params)
        minute_pnl.append(np.diff(result.equity[::60]))
        pnl += result.final_pnl
        fills += len(result.fills)
        quotes += result.quotes_placed
        m = backtest.markouts(result.fills, s.grid_ns, s.mid, (10,))["markout_10s"]
        if np.isfinite(m):
            markout10.append(m)
    combined = np.sum(minute_pnl, axis=0)  # portfolio P&L per minute across symbols
    return {
        **row,
        "pnl_ticks": pnl,
        "sharpe_1min": stats.sharpe(combined),
        "max_drawdown_ticks": stats.max_drawdown(np.cumsum(combined)),
        "fills": fills,
        "fill_rate": fills / quotes if quotes else 0.0,
        "markout_10s": float(np.mean(markout10)) if markout10 else float("nan"),
    }


def _partition(rows: Iterator[dict[str, Any]], session_paths: list[str]) -> Iterator[dict[str, Any]]:
    sessions = [load_packed(Path(p)) for p in session_paths]
    for row in rows:
        yield evaluate(row, sessions)


def run_spark(session_paths: list[Path], master: str, partitions: int, limit: int | None) -> pd.DataFrame:
    from pyspark.sql import SparkSession

    builder = SparkSession.builder.appName("microprice-sweep")
    if master:  # empty under spark-submit, which supplies the cluster master
        builder = builder.master(master)
    spark = (
        builder
        .config("spark.driver.memory", "4g").config("spark.ui.showConsoleProgress", "false")
        .getOrCreate()
    )  # fmt: skip
    grid = param_grid()[:limit] if limit else param_grid()
    paths = [str(p.resolve()) for p in session_paths]
    rdd = spark.sparkContext.parallelize(grid, partitions).mapPartitions(lambda rows: _partition(rows, paths))
    results = pd.DataFrame(rdd.collect())
    spark.stop()
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Strategy parameter sweep on Spark.")
    parser.add_argument("--data", type=Path, default=Path("../data/synthetic"))
    parser.add_argument("--features", type=Path, default=Path("../data/features/features.parquet"))
    parser.add_argument("--model", type=Path, default=Path("models/lgbm_fwd10.txt"))
    parser.add_argument("--packed", type=Path, default=Path("../data/sessions"))
    parser.add_argument("--out", type=Path, default=Path("../results/sweep.parquet"))
    parser.add_argument("--master", default="local[*]")
    parser.add_argument("--partitions", type=int, default=64)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    day = SELECT_DAYS[0]
    paths = sorted(args.packed.glob(f"*_{day}.npz")) or pack_sessions(
        args.data, args.features, args.model, args.packed, day
    )
    start = time.time()
    results = run_spark(paths, args.master, args.partitions, args.limit)
    elapsed = time.time() - start
    args.out.parent.mkdir(parents=True, exist_ok=True)
    results.to_parquet(args.out)
    summary = {
        "parameter_sets": len(results),
        "backtests": len(results) * len(paths),
        "seconds": round(elapsed, 1),
        "best_sharpe_1min": float(results["sharpe_1min"].max()),
    }
    (args.out.with_suffix(".json")).write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
