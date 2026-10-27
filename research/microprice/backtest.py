"""Queue-aware market-making backtests.

The strategy's quotes are real orders in the C++ engine alongside the replayed
market flow, so a quote fills only when the volume ahead of it at its price
has traded or cancelled. Quote decisions are made on a fixed grid, and orders
reach the book after a configurable order entry latency, during which the
market keeps moving.

Quoting follows Avellaneda and Stoikov (2008) in tick units:

    reservation r = s - q * gamma * sigma^2 * tau + alpha * forecast + beta * sentiment
    total spread  d = gamma * sigma^2 * tau + (2 / gamma) * ln(1 + gamma / kappa)

where s is the mid, q is inventory in lots, sigma^2 is the per-second variance
of mid changes and tau is the risk horizon in seconds. Quotes are rounded
outward to ticks and never cross the opposite touch.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd

from microprice import _engine
from microprice.engine import new_engine
from microprice.lobster import MessageColumns

OUR_ID_BASE = 1 << 61
MINUTES_PER_YEAR = 390 * 252
MARKOUT_HORIZONS = (1, 10, 60)


@dataclass(frozen=True)
class StrategyParams:
    gamma: float = 0.1
    kappa: float = 1.5
    tau_s: float = 30.0
    quote_lots: int = 1
    max_inventory_lots: int = 10
    alpha: float = 0.0  # weight on the LightGBM forecast (ticks per tick of forecast)
    beta: float = 0.0  # ticks of skew per unit of decayed FinBERT sentiment
    latency_ms: float = 1.0
    min_sigma2: float = 0.05  # floor on the variance estimate, ticks^2 per second

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Quote:
    order_id: int = 0
    price: int = 0
    live: bool = False


@dataclass
class BacktestResult:
    params: StrategyParams
    equity: npt.NDArray[np.float64]  # marked to mid at each decision
    inventory: npt.NDArray[np.int64]
    fills: pd.DataFrame
    quotes_placed: int
    spread_capture: float
    final_pnl: float
    extra: dict[str, float] = field(default_factory=dict)


def quotes_for(
    mid: float, inventory_lots: float, sigma2: float, forecast: float, sentiment: float, p: StrategyParams
) -> tuple[float, float]:
    """Returns the (bid, ask) prices before rounding, in ticks."""
    risk = p.gamma * sigma2 * p.tau_s
    reservation = mid - inventory_lots * risk + p.alpha * forecast + p.beta * sentiment
    half = 0.5 * (risk + (2.0 / p.gamma) * math.log1p(p.gamma / p.kappa))
    return reservation - half, reservation + half


def run(
    columns: MessageColumns,
    grid_ns: npt.NDArray[np.int64],
    mid: npt.NDArray[np.float64],
    sigma2: npt.NDArray[np.float64],
    forecast: npt.NDArray[np.float64],
    sentiment: npt.NDArray[np.float64],
    params: StrategyParams,
    lot: int = 100,
) -> BacktestResult:
    """Runs one strategy over one symbol-day in C++ (engine/include/microprice/market_maker.hpp)."""
    raw = _engine.run_market_maker(
        columns.ts, columns.type, columns.order_id, columns.size, columns.price, columns.direction,
        np.ascontiguousarray(grid_ns, dtype=np.int64), np.ascontiguousarray(mid, dtype=np.float64),
        np.ascontiguousarray(sigma2, dtype=np.float64), np.ascontiguousarray(forecast, dtype=np.float64),
        np.ascontiguousarray(sentiment, dtype=np.float64), {**params.to_dict(), "lot": lot},
    )  # fmt: skip
    fills = pd.DataFrame(
        {
            "ts": raw["fill_ts"],
            "side": raw["fill_side"].astype(np.int64),
            "price": raw["fill_price"],
            "qty": raw["fill_qty"],
            "mid": raw["fill_mid"],
        }
    )
    return BacktestResult(
        params, raw["equity"], raw["inventory"], fills, int(raw["quotes_placed"]),
        float(raw["spread_capture"]), float(raw["final_pnl"]),
    )  # fmt: skip


def run_reference(
    columns: MessageColumns,
    grid_ns: npt.NDArray[np.int64],
    mid: npt.NDArray[np.float64],
    sigma2: npt.NDArray[np.float64],
    forecast: npt.NDArray[np.float64],
    sentiment: npt.NDArray[np.float64],
    params: StrategyParams,
    lot: int = 100,
) -> BacktestResult:
    """Pure Python version of `run`, kept as a readable reference for the parity test."""
    engine = new_engine()
    latency_ns = int(params.latency_ms * 1e6)
    cut = np.searchsorted(columns.ts, grid_ns, side="right")
    cut_late = np.searchsorted(columns.ts, grid_ns + latency_ns, side="right")
    # The book before the first decision is built without the strategy.
    first = int(cut[0])
    engine.apply_lobster(
        columns.ts, columns.type, columns.order_id, columns.size, columns.price, columns.direction, 0, first
    )
    engine.drain_events()
    done = first

    bid_quote, ask_quote = Quote(), Quote()
    next_id = OUR_ID_BASE
    inventory = 0
    cash = 0.0
    spread_capture = 0.0
    quotes_placed = 0
    fill_rows: list[tuple[int, int, int, int, float]] = []
    equity = np.zeros(len(grid_ns))
    inventory_path = np.zeros(len(grid_ns), dtype=np.int64)
    reference_mid = float(mid[0])

    def advance(to: int) -> None:
        nonlocal done, inventory, cash, spread_capture
        if to <= done:
            return
        engine.apply_lobster(
            columns.ts,
            columns.type,
            columns.order_id,
            columns.size,
            columns.price,
            columns.direction,
            done,
            to,
        )
        done = to
        events = engine.drain_events()
        ours = (events["type"] == _engine.EXECUTE) & (events["id"] >= OUR_ID_BASE)
        for i in np.flatnonzero(ours):
            qty = int(events["qty"][i])
            price = int(events["price"][i])
            side = 1 if int(events["side"][i]) == _engine.BUY else -1
            inventory += side * qty
            cash -= side * qty * price
            spread_capture += side * qty * (reference_mid - price)
            fill_rows.append((int(events["ts"][i]), side, price, qty, reference_mid))

    for k in range(len(grid_ns)):
        advance(int(cut[k]))
        m = float(mid[k])
        if not np.isfinite(m):
            equity[k] = equity[k - 1] if k else 0.0
            inventory_path[k] = inventory
            continue
        reference_mid = m
        equity[k] = cash + inventory * m
        inventory_path[k] = inventory

        bid_px, ask_px = quotes_for(
            m,
            inventory / lot,
            max(float(sigma2[k]), params.min_sigma2),
            float(forecast[k]),
            float(sentiment[k]),
            params,
        )
        # Orders reach the exchange one latency later; the market moves first.
        advance(int(cut_late[k]))
        ts = int(grid_ns[k] + latency_ns)
        best_bid, best_ask = engine.best_bid(), engine.best_ask()
        want_bid = math.floor(bid_px)
        want_ask = math.ceil(ask_px)
        if best_ask is not None:
            want_bid = min(want_bid, best_ask - 1)
        if best_bid is not None:
            want_ask = max(want_ask, best_bid + 1)
        size = params.quote_lots * lot
        allow_bid = inventory + size <= params.max_inventory_lots * lot
        allow_ask = inventory - size >= -params.max_inventory_lots * lot
        for quote, side, want, allowed in (
            (bid_quote, _engine.BUY, want_bid, allow_bid),
            (ask_quote, _engine.SELL, want_ask, allow_ask),
        ):
            alive = quote.live and engine.contains(quote.order_id)
            if not allowed:
                if alive:
                    engine.cancel(quote.order_id, ts)
                quote.live = False
            elif alive and quote.price == want:
                continue  # keep queue position
            elif alive:
                engine.modify(quote.order_id, want, size, ts)
                quote.price = want
                quotes_placed += 1
            else:
                engine.submit(next_id, side, _engine.LIMIT, want, size, ts)
                quote.order_id, quote.price, quote.live = next_id, want, True
                next_id += 1
                quotes_placed += 1
        advance(int(cut_late[k]))  # collect any immediate fills from our own requests

    # Flatten at the touch: pay the half spread instead of assuming the mid.
    last_mid = float(mid[np.isfinite(mid)][-1])
    liquidation_price = last_mid - 0.5 * np.sign(inventory)
    cash += inventory * liquidation_price
    final_pnl = cash
    fills = pd.DataFrame(fill_rows, columns=["ts", "side", "price", "qty", "mid"])
    return BacktestResult(params, equity, inventory_path, fills, quotes_placed, spread_capture, final_pnl)


def markouts(
    fills: pd.DataFrame,
    grid_ns: npt.NDArray[np.int64],
    mid: npt.NDArray[np.float64],
    horizons: tuple[int, ...] = MARKOUT_HORIZONS,
) -> dict[str, float]:
    """Average post-fill mid move in our favour, in ticks per share."""
    out: dict[str, float] = {}
    if fills.empty:
        return {f"markout_{h}s": float("nan") for h in horizons}
    filled_mid = pd.Series(mid).ffill().to_numpy()
    for h in horizons:
        at = np.searchsorted(grid_ns, fills["ts"].to_numpy() + int(h * 1e9), side="right") - 1
        later = filled_mid[np.clip(at, 0, len(mid) - 1)]
        move = fills["side"].to_numpy() * (later - fills["price"].to_numpy())
        out[f"markout_{h}s"] = float(np.average(move, weights=fills["qty"].to_numpy()))
    return out


def summarize(
    result: BacktestResult,
    grid_ns: npt.NDArray[np.int64],
    mid: npt.NDArray[np.float64],
    lot: int = 100,
    step_s: float = 1.0,
) -> dict[str, float]:
    per_minute = max(1, round(60 / step_s))
    minute_equity = result.equity[::per_minute]
    pnl = np.diff(minute_equity)
    sharpe = float(pnl.mean() / pnl.std() * math.sqrt(MINUTES_PER_YEAR)) if pnl.std() > 0 else 0.0
    peak = np.maximum.accumulate(result.equity)
    filled_qty = int(result.fills["qty"].sum()) if not result.fills.empty else 0
    summary = {
        "pnl_ticks": result.final_pnl,
        "pnl_usd": result.final_pnl * 0.01,
        "spread_capture_ticks": result.spread_capture,
        "inventory_pnl_ticks": result.final_pnl - result.spread_capture,
        "sharpe_annualized_1min": sharpe,
        "max_drawdown_ticks": float((peak - result.equity).max()),
        "fills": float(len(result.fills)),
        "filled_shares": float(filled_qty),
        "quotes_placed": float(result.quotes_placed),
        "fill_rate": float(len(result.fills) / result.quotes_placed) if result.quotes_placed else 0.0,
        "max_abs_inventory_lots": float(np.abs(result.inventory).max() / lot),
    }
    summary.update(markouts(result.fills, grid_ns, mid))
    return summary
