import numpy as np
import pytest

from microprice import optimize


def test_budget_and_caps_hold() -> None:
    rng = np.random.default_rng(0)
    pnl = rng.normal([1.0, 0.5, 0.2, -0.1], 1.0, size=(500, 4))
    a = optimize.allocate(["A", "B", "C", "D"], pnl, budget_lots=12, cap_lots=5)
    assert a.weights.sum() == pytest.approx(12, abs=1e-4)
    assert (a.weights <= 5 + 1e-6).all() and (a.weights >= -1e-6).all()


def test_prefers_higher_return_for_equal_risk() -> None:
    rng = np.random.default_rng(1)
    pnl = rng.normal([2.0, 0.0], 1.0, size=(2000, 2))
    a = optimize.allocate(["good", "flat"], pnl, budget_lots=10, cap_lots=10)
    assert a.weights[0] > a.weights[1]


def test_diversifies_between_equal_uncorrelated_strategies() -> None:
    rng = np.random.default_rng(2)
    pnl = rng.normal([1.0, 1.0], 1.0, size=(20_000, 2))
    a = optimize.allocate(["x", "y"], pnl, budget_lots=10, cap_lots=10, risk_aversion=1.0)
    assert a.weights[0] == pytest.approx(5, abs=0.5)
    assert set(a.limits_lots) == {"x", "y"}
