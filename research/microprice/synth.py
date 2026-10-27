"""Synthetic order flow in LOBSTER format.

The generator drives the real matching engine with a stochastic order flow
around a latent fair value V:

* V follows a random walk, plus a gradual drift after each news headline whose
  size and sign follow the headline's FinBERT score.
* Limit orders arrive on both sides, more often on the side V is moving
  toward, at a geometric depth from the touch.
* Market orders are informed: the chance of a buy rises with V - mid.
* Each resting order is cancelled at a constant hazard rate, so book depth
  settles where arrivals balance cancellations and executions (as in the
  Cont, Stoikov and Talreja queueing model).

Because order flow leans toward V, book imbalance and the micro-price carry
real information about the next mid-price move, which is the structure the
research layer has to find. Every book event is written as a LOBSTER message,
and the order book file is produced by replaying those messages through a
fresh engine, which also checks that the file reproduces the book exactly.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict, dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from microprice import _engine, lobster
from microprice.engine import new_engine

OPEN_S = 34_200.0  # 09:30:00
CLOSE_S = 57_600.0  # 16:00:00
TICK_USD = 0.01
LOT = 100


@dataclass(frozen=True)
class SymbolProfile:
    symbol: str
    price_usd: float
    daily_vol: float  # standard deviation of the daily return
    rate_per_s: float  # limit and market order arrivals per second


PROFILES = [
    SymbolProfile("AAPL", 230.0, 0.015, 6.0),
    SymbolProfile("MSFT", 420.0, 0.014, 5.5),
    SymbolProfile("AMZN", 190.0, 0.019, 5.8),
    SymbolProfile("GOOG", 165.0, 0.017, 5.5),
    SymbolProfile("NVDA", 135.0, 0.030, 6.5),
    SymbolProfile("META", 570.0, 0.021, 5.2),
    SymbolProfile("JPM", 220.0, 0.013, 5.2),
    SymbolProfile("XOM", 120.0, 0.014, 5.0),
    SymbolProfile("JNJ", 160.0, 0.010, 5.0),
    SymbolProfile("PG", 170.0, 0.009, 5.0),
]

DATES = ["2026-10-19", "2026-10-20", "2026-10-21", "2026-10-22", "2026-10-23"]


@dataclass(frozen=True)
class FlowParams:
    limit_share: float = 0.85  # of arrivals; the remainder are market orders
    cancel_rate: float = 0.30  # per resting order per second
    informed_kappa: float = 0.15  # logistic slope of market order direction, per tick of V - mid
    limit_tilt: float = 0.05  # logistic slope of limit side choice, per tick of V - mid
    depth_geometric_p: float = 0.50
    news_per_day: float = 4.0
    news_impact: float = 0.006  # fair value move for a sentiment score of 1, as a fraction of price
    news_horizon_s: float = 120.0  # the move is absorbed linearly over this window
    seed_levels: int = 15


def _sigmoid(x: float) -> float:
    return float(1.0 / (1.0 + np.exp(-x)))


def generate_day(
    profile: SymbolProfile,
    date: str,
    seed: int,
    headlines: pd.DataFrame | None = None,
    params: FlowParams | None = None,
    duration_s: float = CLOSE_S - OPEN_S,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Returns (LOBSTER messages, news events) for one symbol and day."""
    params = params or FlowParams()
    rng = np.random.default_rng(seed)
    engine = new_engine()
    fair = profile.price_usd / TICK_USD
    sigma = profile.price_usd * profile.daily_vol / np.sqrt(CLOSE_S - OPEN_S) / TICK_USD  # ticks per sqrt(s)

    news = _draw_news(rng, profile, headlines, params, duration_s)
    news_drift = np.zeros(0)
    news_until = np.zeros(0)

    next_id = 1
    live: list[int] = []
    t = OPEN_S
    ts = int(t * 1e9)
    for level in range(1, params.seed_levels + 1):
        for side, price in ((_engine.BUY, round(fair) - level), (_engine.SELL, round(fair) + level)):
            engine.submit(next_id, side, _engine.LIMIT, price, 3 * LOT, ts)
            live.append(next_id)
            next_id += 1

    batches: list[dict[str, np.ndarray]] = []
    news_index = 0
    news_time = news["time"].to_numpy(dtype=float)
    news_sentiment = news["sentiment"].to_numpy(dtype=float)
    end = OPEN_S + duration_s
    while True:
        cancel_rate = params.cancel_rate * engine.order_count()
        dt = rng.exponential(1.0 / (profile.rate_per_s + cancel_rate))
        t += dt
        if t >= end:
            break
        ts = int(t * 1e9)
        while news_index < len(news_time) and news_time[news_index] <= t:
            published = float(news_time[news_index])
            move = float(news_sentiment[news_index]) * params.news_impact * fair
            news_drift = np.append(news_drift, move / params.news_horizon_s)
            news_until = np.append(news_until, published + params.news_horizon_s)
            news_index += 1
        active = news_until > t
        fair += sigma * np.sqrt(dt) * rng.standard_normal() + float(news_drift[active].sum()) * dt

        bid, ask = engine.best_bid(), engine.best_ask()
        mid = (bid + ask) / 2 if bid is not None and ask is not None else fair
        roll = rng.random() * (profile.rate_per_s + cancel_rate)
        if roll < profile.rate_per_s * params.limit_share:
            side = _engine.BUY if rng.random() < _sigmoid(params.limit_tilt * (fair - mid)) else _engine.SELL
            depth = int(rng.geometric(params.depth_geometric_p)) - 1
            if side == _engine.BUY:
                price = round(fair) - 1 - depth
                if ask is not None:
                    price = min(price, ask - 1)
            else:
                price = round(fair) + 1 + depth
                if bid is not None:
                    price = max(price, bid + 1)
            engine.submit(next_id, side, _engine.LIMIT, max(price, 1), LOT * int(rng.geometric(0.45)), ts)
            live.append(next_id)
            next_id += 1
        elif roll >= profile.rate_per_s:
            for _ in range(20):
                if not live:
                    break
                pick = int(rng.integers(len(live)))
                order_id = live[pick]
                remaining = engine.order_qty(order_id)
                if remaining == 0:
                    live[pick] = live[-1]
                    live.pop()
                    continue
                resting_price = engine.order_price(order_id)
                if remaining > LOT and resting_price is not None and rng.random() < 0.2:
                    engine.modify(order_id, resting_price, remaining // (2 * LOT) * LOT or LOT, ts)
                else:
                    engine.cancel(order_id, ts)
                    live[pick] = live[-1]
                    live.pop()
                break
        else:
            side = (
                _engine.BUY if rng.random() < _sigmoid(params.informed_kappa * (fair - mid)) else _engine.SELL
            )
            if (side == _engine.BUY and ask is not None) or (side == _engine.SELL and bid is not None):
                engine.submit(next_id, side, _engine.MARKET, 0, LOT * int(rng.geometric(0.55)), ts)
                next_id += 1
        if engine.pending_events() > 20_000:
            batches.append(engine.drain_events())
    batches.append(engine.drain_events())
    return _events_to_messages(batches), news


def _draw_news(
    rng: np.random.Generator,
    profile: SymbolProfile,
    headlines: pd.DataFrame | None,
    params: FlowParams,
    duration_s: float,
) -> pd.DataFrame:
    count = int(rng.poisson(params.news_per_day * duration_s / (CLOSE_S - OPEN_S)))
    if headlines is None or headlines.empty or count == 0:
        return pd.DataFrame({"time": [], "headline": [], "sentiment": []})
    pool = headlines[headlines["symbol"] == profile.symbol]
    pool = pool if len(pool) else headlines
    rows = pool.sample(n=count, replace=True, random_state=int(rng.integers(2**31)))
    times = np.sort(rng.uniform(OPEN_S + 60, OPEN_S + duration_s - 60, size=count))
    return pd.DataFrame(
        {"time": times, "headline": rows["headline"].to_numpy(), "sentiment": rows["sentiment"].to_numpy()}
    )


def _events_to_messages(batches: list[dict[str, np.ndarray]]) -> pd.DataFrame:
    events = {key: np.concatenate([b[key] for b in batches]) for key in batches[0]}
    kind = events["type"]
    lobster_type = np.select(
        [kind == _engine.ADD, kind == _engine.EXECUTE, events["remaining"] > 0],
        [lobster.SUBMIT, lobster.EXECUTE, lobster.PARTIAL_CANCEL],
        default=lobster.DELETE,
    )
    return pd.DataFrame(
        {
            "time": events["ts"] / 1e9,
            "type": lobster_type.astype(np.int32),
            "order_id": events["id"],
            "size": events["qty"],
            "price": events["price"] * lobster.LOBSTER_PRICE_PER_TICK,
            "direction": np.where(events["side"] == _engine.BUY, 1, -1).astype(np.int8),
        }
    )


def top_of_book(messages: pd.DataFrame) -> pd.DataFrame:
    columns = lobster.to_columns(messages)
    engine = new_engine()
    ask_px, ask_sz, bid_px, bid_sz = engine.replay_top_of_book(
        columns.ts, columns.type, columns.order_id, columns.size, columns.price, columns.direction
    )
    return pd.DataFrame(
        {"ask_price_1": ask_px, "ask_size_1": ask_sz, "bid_price_1": bid_px, "bid_size_1": bid_sz}
    )


def _generate_one(task: tuple[SymbolProfile, str, int, Path, Path | None]) -> dict[str, object]:
    profile, date, seed, out, headlines_path = task
    headlines = pd.read_csv(headlines_path) if headlines_path and headlines_path.exists() else None
    messages, news = generate_day(profile, date, seed, headlines)
    lobster.write_messages(messages, lobster.message_file(out, profile.symbol, date))
    lobster.write_orderbook(top_of_book(messages), lobster.orderbook_file(out, profile.symbol, date))
    news.to_csv(out / profile.symbol / f"{profile.symbol}_{date}_news.csv", index=False)
    return {
        "symbol": profile.symbol,
        "date": date,
        "seed": seed,
        "messages": len(messages),
        "news": len(news),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate synthetic LOBSTER-format order flow.")
    parser.add_argument("--out", type=Path, default=Path("../data/synthetic"))
    parser.add_argument("--headlines", type=Path, default=Path("../data/headlines/headlines.csv"))
    parser.add_argument("--days", type=int, default=len(DATES))
    parser.add_argument("--symbols", nargs="*", default=[p.symbol for p in PROFILES])
    parser.add_argument("--seed", type=int, default=20261026)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    profiles = [p for p in PROFILES if p.symbol in args.symbols]
    tasks = [
        (profile, date, args.seed + 1000 * i + j, args.out, args.headlines)
        for i, profile in enumerate(profiles)
        for j, date in enumerate(DATES[: args.days])
    ]
    with ProcessPoolExecutor(max_workers=args.workers) as pool:
        summary = list(pool.map(_generate_one, tasks))
    manifest = {
        "generator": "microprice.synth",
        "params": asdict(FlowParams()),
        "profiles": [asdict(p) for p in profiles],
        "files": summary,
        "total_messages": int(sum(int(str(row["messages"])) for row in summary)),
    }
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(json.dumps({"files": len(summary), "total_messages": manifest["total_messages"]}))


if __name__ == "__main__":
    main()
