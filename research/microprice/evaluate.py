"""Held-out comparison of the baseline and signal-driven market makers.

Parameters come from the sweep on the selection day: the signal strategy is the
best parameter set overall, the baseline is the best set with both signal
weights at zero. Both then run on every symbol for the held-out days, which no
earlier step has seen. Outputs:

* results/holdout.json        per-session metrics and the portfolio comparison
* results/holdout_fills.csv   every fill with its signals and later mids (for R)
* results/sweep_top.json      top sweep rows with deflated Sharpe ratios
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from microprice import backtest, optimize, stats, sweep
from microprice.simulate import HOLDOUT_DAYS, SELECT_DAYS, load_booster, load_session
from microprice.synth import PROFILES

MID_AFTER = (1, 2, 5, 10, 30, 60)


def choose(results: pd.DataFrame) -> tuple[dict[str, Any], dict[str, Any]]:
    best = results.sort_values("sharpe_1min", ascending=False).iloc[0].to_dict()
    no_signal = results[(results["alpha"] == 0) & (results["beta"] == 0)]
    baseline = no_signal.sort_values("sharpe_1min", ascending=False).iloc[0].to_dict()
    return baseline, best


def deflate(results: pd.DataFrame, best: dict[str, Any], packed: list[Path]) -> dict[str, float]:
    """Deflated Sharpe of the selected set, against every trial in the sweep."""
    sessions = [sweep.load_packed(p) for p in packed]
    params = sweep.strategy_params(best)
    minute = []
    for full in sessions:
        s = full.window(*sweep.WINDOW)
        r = backtest.run(s.columns, s.grid_ns, s.mid, s.sigma2, s.forecast, s.sentiment, params)
        minute.append(np.diff(r.equity[::60]))
    combined = np.sum(minute, axis=0)
    trials = results["sharpe_1min"].to_numpy(dtype=float)
    return {
        "trials": float(len(trials)),
        "raw_sharpe_1min": stats.sharpe(combined),
        "expected_max_sharpe_1min": stats.expected_max_sharpe(trials),
        "deflated_sharpe": stats.deflated_sharpe(combined, trials),
    }


def allocate_limits(
    data_root: Path, table: pd.DataFrame, booster: Any, signal: dict[str, Any]
) -> dict[str, Any]:
    """Sets per-symbol inventory limits from full selection-day P&L of the signal strategy."""
    params = sweep.strategy_params(signal)
    per_symbol = []
    for profile in PROFILES:
        s = load_session(data_root, table, booster, profile.symbol, SELECT_DAYS[0])
        r = backtest.run(s.columns, s.grid_ns, s.mid, s.sigma2, s.forecast, s.sentiment, params)
        per_symbol.append(np.diff(r.equity[::60]) / params.max_inventory_lots)
    symbols = [p.symbol for p in PROFILES]
    budget = params.max_inventory_lots * len(symbols)
    allocation = optimize.allocate(symbols, np.column_stack(per_symbol), budget_lots=budget,
                                   cap_lots=2 * params.max_inventory_lots)  # fmt: skip
    return {
        "budget_lots": budget,
        "limits_lots": allocation.limits_lots,
        "expected_pnl_per_min": allocation.expected_pnl_per_min,
        "risk_per_min": allocation.risk_per_min,
    }


def mid_after(fills: pd.DataFrame, grid_ns: np.ndarray, mid: np.ndarray) -> pd.DataFrame:
    filled = pd.Series(mid).ffill().to_numpy()
    out = fills.copy()
    for h in MID_AFTER:
        at = np.searchsorted(grid_ns, fills["ts"].to_numpy() + int(h * 1e9), side="right") - 1
        out[f"mid_after_{h}"] = filled[np.clip(at, 0, len(mid) - 1)]
    return out


def run_holdout(data_root: Path, table: pd.DataFrame, booster: Any, variants: dict[str, dict[str, Any]],
                fills_out: Path) -> tuple[list[dict[str, Any]], dict[str, dict[str, float]]]:  # fmt: skip
    sessions: list[dict[str, Any]] = []
    minute: dict[str, dict[str, list[np.ndarray]]] = {v: {} for v in variants}
    fill_frames: list[pd.DataFrame] = []
    for date in HOLDOUT_DAYS:
        for profile in PROFILES:
            s = load_session(data_root, table, booster, profile.symbol, date)
            rows = table[(table["sym"] == profile.symbol) & (table["date"] == date)].sort_values("time")
            for variant, row in variants.items():
                row = {**row, **row.get("limits_by_symbol", {}).get(profile.symbol, {})}
                params = sweep.strategy_params(row)
                result = backtest.run(s.columns, s.grid_ns, s.mid, s.sigma2, s.forecast, s.sentiment, params)
                summary = backtest.summarize(result, s.grid_ns, s.mid)
                sessions.append({"variant": variant, "symbol": profile.symbol, "date": date, **summary})
                minute[variant].setdefault(date, []).append(np.diff(result.equity[::60]))
                if not result.fills.empty:
                    at = np.clip(
                        np.searchsorted(s.grid_ns, result.fills["ts"].to_numpy(), side="right") - 1, 0, None
                    )
                    f = mid_after(result.fills, s.grid_ns, s.mid)
                    f["forecast"] = s.forecast[at]
                    f["imbalance"] = rows["imb"].to_numpy()[at]
                    f["sentiment"] = s.sentiment[at]
                    f.insert(0, "variant", variant)
                    f.insert(1, "symbol", profile.symbol)
                    f.insert(2, "date", date)
                    fill_frames.append(f)
    pd.concat(fill_frames, ignore_index=True).to_csv(fills_out, index=False)

    frame = pd.DataFrame(sessions)
    summary_by_variant: dict[str, dict[str, float]] = {}
    for variant in variants:
        portfolio = np.concatenate([np.sum(minute[variant][d], axis=0) for d in HOLDOUT_DAYS])
        per_minute = stats.sharpe(portfolio)
        v = frame[frame["variant"] == variant]
        summary_by_variant[variant] = {
            "pnl_usd": float(v["pnl_usd"].sum()),
            "sharpe": per_minute * math.sqrt(backtest.MINUTES_PER_YEAR),
            "sharpe_1min": per_minute,
            "markout_10s": float(
                np.average(v["markout_10s"].fillna(0), weights=v["filled_shares"].clip(lower=1))
            ),
            "fills": float(v["fills"].sum()),
            "filled_shares": float(v["filled_shares"].sum()),
            "max_drawdown_usd": float(stats.max_drawdown(np.cumsum(portfolio)) / 100),
        }
    return sessions, summary_by_variant


def main() -> None:
    parser = argparse.ArgumentParser(description="Held-out evaluation of the selected strategies.")
    parser.add_argument("--data", type=Path, default=Path("../data/synthetic"))
    parser.add_argument("--features", type=Path, default=Path("../data/features/features.parquet"))
    parser.add_argument("--model", type=Path, default=Path("models/lgbm_fwd10.txt"))
    parser.add_argument("--sweep", type=Path, default=Path("../results/sweep.parquet"))
    parser.add_argument("--packed", type=Path, default=Path("../data/sessions"))
    parser.add_argument("--out", type=Path, default=Path("../results"))
    args = parser.parse_args()

    results = pd.read_parquet(args.sweep)
    baseline, signal = choose(results)
    packed = sorted(args.packed.glob(f"*_{SELECT_DAYS[0]}.npz"))
    deflation = deflate(results, signal, packed)

    table = pd.read_parquet(args.features)
    booster = load_booster(args.model)
    allocation = allocate_limits(args.data, table, booster, signal)
    optimized = {
        **signal,
        "limits_by_symbol": {s: {"max_inventory_lots": n} for s, n in allocation["limits_lots"].items()},
    }
    variants = {"baseline": baseline, "signal": signal, "signal_optimized": optimized}
    sessions, summary = run_holdout(args.data, table, booster, variants, args.out / "holdout_fills.csv")
    lift = (summary["signal"]["sharpe"] - summary["baseline"]["sharpe"]) / abs(summary["baseline"]["sharpe"])
    clean = lambda row: {k: (v.item() if hasattr(v, "item") else v) for k, v in row.items()}  # noqa: E731
    holdout = {
        "holdout_days": HOLDOUT_DAYS,
        "params": {k: clean(v) for k, v in variants.items()},
        "selection": deflation,
        "allocation": allocation,
        "summary": summary,
        "sharpe_lift": lift,
        "sessions": sessions,
    }
    (args.out / "holdout.json").write_text(json.dumps(holdout, indent=2, default=float))

    trials = results["sharpe_1min"].to_numpy(dtype=float)
    benchmark = stats.expected_max_sharpe(trials)
    top = results.sort_values("sharpe_1min", ascending=False).head(25).copy()
    # Per-row deflation with normal moments over the 30-minute selection window.
    top["deflated_sharpe"] = [
        stats.probabilistic_sharpe(s, benchmark, 30, 0.0, 3.0) for s in top["sharpe_1min"]
    ]
    sweep_meta = json.loads(args.sweep.with_suffix(".json").read_text())
    (args.out / "sweep_top.json").write_text(json.dumps({
        "parameter_sets": sweep_meta["parameter_sets"],
        "backtests": sweep_meta["backtests"],
        "best_raw_sharpe": deflation["raw_sharpe_1min"],
        "best_deflated_sharpe": deflation["deflated_sharpe"],
        "top": [clean(r) for r in top.to_dict(orient="records")],
    }, indent=2, default=float))  # fmt: skip
    print(
        json.dumps({"summary": summary, "sharpe_lift": lift, "selection": deflation}, indent=2, default=float)
    )


if __name__ == "__main__":
    main()
