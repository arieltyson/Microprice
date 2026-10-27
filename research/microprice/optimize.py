"""Mean-variance allocation of inventory limits across symbols with CVXPY.

Per-symbol strategy P&L per minute (from the selection day) gives an expected
return vector and covariance matrix per lot of inventory limit. The optimizer
spreads a fixed budget of lots across symbols:

    maximize   mu' w - risk_aversion * w' Sigma w
    subject to sum(w) = budget, 0 <= w <= cap

and the rounded weights become each symbol's max inventory in lots.
"""

from __future__ import annotations

from dataclasses import dataclass

import cvxpy as cp
import numpy as np
import numpy.typing as npt


@dataclass(frozen=True)
class Allocation:
    symbols: list[str]
    weights: npt.NDArray[np.float64]
    limits_lots: dict[str, int]
    expected_pnl_per_min: float
    risk_per_min: float


def allocate(
    symbols: list[str],
    minute_pnl: npt.NDArray[np.float64],  # shape (minutes, symbols), P&L per lot of limit
    budget_lots: float = 50.0,
    cap_lots: float = 10.0,
    risk_aversion: float = 0.05,
    min_lots: int = 1,
) -> Allocation:
    mu = minute_pnl.mean(axis=0)
    sigma = np.cov(minute_pnl, rowvar=False) + 1e-9 * np.eye(len(symbols))
    sigma = 0.5 * (sigma + sigma.T)  # exact symmetry for the PSD check
    w = cp.Variable(len(symbols))
    objective = cp.Maximize(mu @ w - risk_aversion * cp.quad_form(w, cp.psd_wrap(sigma)))
    problem = cp.Problem(objective, [cp.sum(w) == budget_lots, w >= 0, w <= cap_lots])
    problem.solve()
    if w.value is None:
        raise RuntimeError(f"allocation failed: {problem.status}")
    weights = np.clip(np.asarray(w.value, dtype=np.float64), 0, cap_lots)
    limits = {s: max(min_lots, round(float(x))) for s, x in zip(symbols, weights, strict=True)}
    return Allocation(
        symbols=symbols,
        weights=weights,
        limits_lots=limits,
        expected_pnl_per_min=float(mu @ weights),
        risk_per_min=float(np.sqrt(weights @ sigma @ weights)),
    )
