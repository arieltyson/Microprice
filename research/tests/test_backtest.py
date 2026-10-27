from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from microprice import backtest, features, lobster, synth

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def session(tmp_path_factory: pytest.TempPathFactory) -> dict[str, object]:
    root = tmp_path_factory.mktemp("lobster")
    messages, _ = synth.generate_day(synth.PROFILES[0], "2026-10-19", 9, duration_s=900)
    lobster.write_messages(messages, lobster.message_file(root, "AAPL", "2026-10-19"))
    lobster.write_orderbook(synth.top_of_book(messages), lobster.orderbook_file(root, "AAPL", "2026-10-19"))
    f = features.build_features(root, "AAPL", "2026-10-19").iloc[:880]
    grid_ns = (f["time"] - f["time"].dt.normalize()).dt.total_seconds().mul(1e9).round().astype(np.int64)
    rng = np.random.default_rng(0)
    return {
        "columns": lobster.to_columns(messages),
        "grid_ns": grid_ns.to_numpy(),
        "mid": f["mid"].to_numpy(float),
        "sigma2": np.square(f["rv60"].fillna(0).to_numpy(float)),
        "forecast": rng.normal(0, 1, len(f)),
        "sentiment": rng.normal(0, 0.1, len(f)),
    }


@pytest.mark.parametrize(
    "params",
    [
        backtest.StrategyParams(),
        backtest.StrategyParams(
            gamma=0.02, kappa=0.5, alpha=1.0, beta=3.0, latency_ms=5.0, max_inventory_lots=3
        ),
    ],
)
def test_cpp_strategy_matches_python_reference(session: dict, params: backtest.StrategyParams) -> None:
    args = [session[k] for k in ("columns", "grid_ns", "mid", "sigma2", "forecast", "sentiment")]
    fast = backtest.run(*args, params)
    reference = backtest.run_reference(*args, params)
    assert len(fast.fills) > 0
    pd.testing.assert_frame_equal(fast.fills, reference.fills, check_dtype=False)
    np.testing.assert_allclose(fast.equity, reference.equity)
    assert fast.quotes_placed == reference.quotes_placed
    assert fast.final_pnl == pytest.approx(reference.final_pnl)


def test_inventory_limit_is_respected(session: dict) -> None:
    args = [session[k] for k in ("columns", "grid_ns", "mid", "sigma2", "forecast", "sentiment")]
    result = backtest.run(*args, backtest.StrategyParams(max_inventory_lots=2, gamma=0.01, kappa=0.3))
    assert np.abs(result.inventory).max() <= 2 * 100


def test_markouts_measure_moves_in_our_favour() -> None:
    fills = pd.DataFrame({"ts": [0], "side": [1], "price": [100], "qty": [100], "mid": [100.5]})
    grid_ns = np.array([0, 1_000_000_000, 10_000_000_000, 60_000_000_000])
    mid = np.array([100.5, 101.0, 99.0, 100.0])
    out = backtest.markouts(fills, grid_ns, mid)
    assert out == {"markout_1s": 1.0, "markout_10s": -1.0, "markout_60s": 0.0}
