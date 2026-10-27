"""Performance statistics that account for how many strategies were tried."""

from __future__ import annotations

import math

import numpy as np
import numpy.typing as npt
from scipy.stats import kurtosis, norm, skew

EULER_GAMMA = 0.5772156649015329


def sharpe(returns: npt.NDArray[np.float64]) -> float:
    """Per-period Sharpe ratio (not annualized)."""
    sd = float(np.std(returns, ddof=1))
    return float(np.mean(returns) / sd) if sd > 0 else 0.0


def expected_max_sharpe(trial_sharpes: npt.NDArray[np.float64]) -> float:
    """Expected maximum Sharpe ratio among N unskilled trials (Bailey and López de Prado, 2014)."""
    n = len(trial_sharpes)
    if n < 2:
        return 0.0
    sd = float(np.std(trial_sharpes, ddof=1))
    return float(sd) * float(
        (1 - EULER_GAMMA) * norm.ppf(1 - 1.0 / n) + EULER_GAMMA * norm.ppf(1 - 1.0 / (n * math.e))
    )


def probabilistic_sharpe(
    observed: float, benchmark: float, n_obs: int, skewness: float, kurt: float
) -> float:
    """P(true Sharpe > benchmark) given a per-period Sharpe estimate and its moments."""
    denominator = math.sqrt(max(1e-12, 1 - skewness * observed + (kurt - 1) / 4 * observed**2))
    return float(norm.cdf((observed - benchmark) * math.sqrt(n_obs - 1) / denominator))


def deflated_sharpe(returns: npt.NDArray[np.float64], trial_sharpes: npt.NDArray[np.float64]) -> float:
    """Deflated Sharpe ratio: the probabilistic Sharpe against the expected maximum of the trials."""
    observed = sharpe(returns)
    return probabilistic_sharpe(
        observed,
        expected_max_sharpe(trial_sharpes),
        len(returns),
        float(skew(returns)),
        float(kurtosis(returns, fisher=False)),
    )


def max_drawdown(equity: npt.NDArray[np.float64]) -> float:
    peak = np.maximum.accumulate(equity)
    return float((peak - equity).max())
