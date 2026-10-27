import numpy as np
import pytest

from microprice import stats


def test_sharpe_of_constant_positive_drift() -> None:
    returns = np.array([1.0, 2.0, 3.0, 2.0])
    assert stats.sharpe(returns) == pytest.approx(2.0 / np.std(returns, ddof=1))


def test_expected_max_sharpe_grows_with_trials() -> None:
    rng = np.random.default_rng(1)
    few = stats.expected_max_sharpe(rng.normal(0, 0.1, 10))
    many = stats.expected_max_sharpe(rng.normal(0, 0.1, 10_000))
    assert many > few > 0


def test_deflation_penalizes_the_best_of_many_noise_strategies() -> None:
    rng = np.random.default_rng(2)
    trials = rng.normal(0, 1, size=(2000, 250))
    sharpes = np.array([stats.sharpe(t) for t in trials])
    best = trials[int(np.argmax(sharpes))]
    # The luckiest noise strategy looks good on its own but not after deflation.
    assert stats.probabilistic_sharpe(stats.sharpe(best), 0.0, 250, 0.0, 3.0) > 0.99
    assert stats.deflated_sharpe(best, sharpes) < 0.5


def test_deflated_sharpe_keeps_a_real_edge() -> None:
    rng = np.random.default_rng(3)
    noise = np.array([stats.sharpe(rng.normal(0, 1, 250)) for _ in range(200)])
    real = rng.normal(0.4, 1, 250)
    assert stats.deflated_sharpe(real, noise) > 0.95


def test_max_drawdown() -> None:
    assert stats.max_drawdown(np.array([0.0, 5.0, 2.0, 6.0, 1.0])) == 5.0
