"""Single place that sizes matching engines for the research layer."""

from __future__ import annotations

from microprice import _engine

# Price levels are allocated for every tick from 0.01 to MAX_PRICE_TICKS, so the
# ceiling is set just above the highest price in the dataset (2,000.00 USD).
MAX_PRICE_TICKS = 200_000
MAX_ORDERS = 1 << 21


def new_engine() -> _engine.Engine:
    return _engine.Engine(1, MAX_PRICE_TICKS, MAX_ORDERS)
