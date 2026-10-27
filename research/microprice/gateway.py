"""WebSocket and JSON gateway for the dashboard.

* GET /api/backtests  results/holdout.json
* GET /api/sweeps     results/sweep_top.json
* WS  /live           replays one held-out session tick by tick: book, P&L split,
                      inventory and fills, at a configurable speed

The replay runs the selected strategy once in C++, then streams its state one
grid step at a time while a separate engine rebuilds the market book.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from collections.abc import Iterator
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from websockets.asyncio.server import Request, Response, ServerConnection, serve
from websockets.datastructures import Headers

from microprice import _engine, backtest, sweep
from microprice.engine import new_engine
from microprice.simulate import HOLDOUT_DAYS, load_booster, load_session

LEVELS = 5


@dataclass(frozen=True)
class GatewayConfig:
    results: Path
    data: Path
    features: Path
    model: Path
    symbol: str
    date: str
    variant: str
    steps_per_second: float


def session_ticks(config: GatewayConfig) -> Iterator[dict[str, Any]]:
    """Yields one message per grid step for the configured session."""
    holdout = json.loads((config.results / "holdout.json").read_text())
    row = holdout["params"][config.variant]
    row = {**row, **row.get("limits_by_symbol", {}).get(config.symbol, {})}
    params = sweep.strategy_params(row)
    table = pd.read_parquet(config.features)
    booster = load_booster(config.model)
    s = load_session(config.data, table, booster, config.symbol, config.date)
    micro_dev = (
        table[(table["sym"] == config.symbol) & (table["date"] == config.date)]
        .sort_values("time")["microDev"]
        .to_numpy()
    )
    result = backtest.run(s.columns, s.grid_ns, s.mid, s.sigma2, s.forecast, s.sentiment, params)
    fills = result.fills
    capture = np.cumsum(fills["side"] * fills["qty"] * (fills["mid"] - fills["price"])) if len(fills) else []
    fill_step = (
        np.searchsorted(s.grid_ns, fills["ts"].to_numpy(), side="left") if len(fills) else np.array([])
    )

    yield {"type": "meta", "symbol": config.symbol, "date": config.date, "variant": config.variant}
    market = new_engine()
    c = s.columns
    cut = np.searchsorted(c.ts, s.grid_ns, side="right")
    done = 0
    last_trade: int | None = None
    spread_capture = 0.0
    fill_index = 0
    for k, end in enumerate(cut):
        if end > done:
            market.apply_lobster(c.ts, c.type, c.order_id, c.size, c.price, c.direction, done, int(end))
            events = market.drain_events()
            executed = events["type"] == _engine.EXECUTE
            if executed.any():
                last_trade = int(events["price"][executed][-1])
            done = int(end)
        step_fills = []
        while fill_index < len(fills) and fill_step[fill_index] <= k:
            f = fills.iloc[fill_index]
            step_fills.append(
                {
                    "t": int(f["ts"]) / 1e9,
                    "side": int(f["side"]),
                    "price": int(f["price"]),
                    "qty": int(f["qty"]),
                }
            )
            spread_capture = float(capture.iloc[fill_index])
            fill_index += 1
        bid_px, bid_sz = market.top_levels(_engine.BUY, LEVELS)
        ask_px, ask_sz = market.top_levels(_engine.SELL, LEVELS)
        mid = float(s.mid[k])
        gap = not np.isfinite(mid)
        yield {
            "type": "tick",
            "t": int(s.grid_ns[k]) / 1e9,
            "mid": None if gap else mid,
            "micro": None if gap or not np.isfinite(micro_dev[k]) else mid + float(micro_dev[k]),
            "equity": float(result.equity[k]),
            "spreadCapture": spread_capture,
            "inventory": int(result.inventory[k]),
            "bids": [[int(p), int(q)] for p, q in zip(bid_px, bid_sz, strict=True) if q > 0],
            "asks": [[int(p), int(q)] for p, q in zip(ask_px, ask_sz, strict=True) if q > 0],
            "lastTrade": last_trade,
            "gap": gap,
            "fills": step_fills,
        }
    yield {"type": "end"}


def json_response(path: Path) -> Response:
    if not path.exists():
        return Response(HTTPStatus.NOT_FOUND.value, "Not Found", Headers(), b"")
    body = path.read_bytes()
    headers = Headers([("Content-Type", "application/json"), ("Cache-Control", "no-store")])
    return Response(HTTPStatus.OK.value, "OK", headers, body)


def make_server(config: GatewayConfig):  # type: ignore[no-untyped-def]
    routes = {"/api/backtests": "holdout.json", "/api/sweeps": "sweep_top.json"}

    def process_request(connection: ServerConnection, request: Request) -> Response | None:
        if request.path in routes:
            return json_response(config.results / routes[request.path])
        if request.path != "/live":
            return Response(HTTPStatus.NOT_FOUND.value, "Not Found", Headers(), b"")
        return None

    async def handler(connection: ServerConnection) -> None:
        delay = 1.0 / config.steps_per_second
        for message in session_ticks(config):
            await connection.send(json.dumps(message))
            await asyncio.sleep(delay)

    return process_request, handler


async def run(config: GatewayConfig, host: str, port: int) -> None:
    process_request, handler = make_server(config)
    async with serve(handler, host, port, process_request=process_request) as server:
        print(f"gateway listening on http://{host}:{port}")
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Dashboard gateway.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--results", type=Path, default=Path("../results"))
    parser.add_argument("--data", type=Path, default=Path("../data/synthetic"))
    parser.add_argument("--features", type=Path, default=Path("../data/features/features.parquet"))
    parser.add_argument("--model", type=Path, default=Path("models/lgbm_fwd10.txt"))
    parser.add_argument("--symbol", default="NVDA")
    parser.add_argument("--date", default=HOLDOUT_DAYS[0])
    parser.add_argument("--variant", default="signal")
    parser.add_argument("--speed", type=float, default=20.0, help="grid steps streamed per second")
    args = parser.parse_args()
    config = GatewayConfig(args.results, args.data, args.features, args.model, args.symbol, args.date,
                           args.variant, args.speed)  # fmt: skip
    asyncio.run(run(config, args.host, args.port))


if __name__ == "__main__":
    main()
