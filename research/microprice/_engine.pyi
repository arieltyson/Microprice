# Type stub for the pybind11 module built from engine/python/bindings.cpp.
from typing import Any

import numpy as np
import numpy.typing as npt

BUY: int
SELL: int
LIMIT: int
MARKET: int
IOC: int
ADD: int
EXECUTE: int
CANCEL: int

class Engine:
    def __init__(
        self, min_price: int = 1, max_price: int = 1_000_000, max_orders: int = 4_194_304
    ) -> None: ...
    def submit(self, id: int, side: int, type: int, price: int, qty: int, ts: int) -> int: ...
    def cancel(self, id: int, ts: int) -> int: ...
    def modify(self, id: int, price: int, qty: int, ts: int) -> int: ...
    def best_bid(self) -> int | None: ...
    def best_ask(self) -> int | None: ...
    def qty_at(self, price: int) -> int: ...
    def order_qty(self, id: int) -> int: ...
    def queue_ahead(self, id: int) -> int: ...
    def order_price(self, id: int) -> int | None: ...
    def contains(self, id: int) -> bool: ...
    def order_count(self) -> int: ...
    def top_levels(self, side: int, n: int) -> tuple[npt.NDArray[np.int64], npt.NDArray[np.int64]]: ...
    def apply_lobster(
        self,
        ts: npt.NDArray[np.int64],
        type: npt.NDArray[np.int32],
        id: npt.NDArray[np.uint64],
        size: npt.NDArray[np.int64],
        price: npt.NDArray[np.int64],
        direction: npt.NDArray[np.int8],
        start: int,
        end: int,
    ) -> int: ...
    def replay_top_of_book(
        self,
        ts: npt.NDArray[np.int64],
        type: npt.NDArray[np.int32],
        id: npt.NDArray[np.uint64],
        size: npt.NDArray[np.int64],
        price: npt.NDArray[np.int64],
        direction: npt.NDArray[np.int8],
    ) -> tuple[
        npt.NDArray[np.int64], npt.NDArray[np.int64], npt.NDArray[np.int64], npt.NDArray[np.int64]
    ]: ...
    def drain_events(self) -> dict[str, npt.NDArray[Any]]: ...
    def pending_events(self) -> int: ...

def run_market_maker(
    ts: npt.NDArray[np.int64],
    type: npt.NDArray[np.int32],
    id: npt.NDArray[np.uint64],
    size: npt.NDArray[np.int64],
    price: npt.NDArray[np.int64],
    direction: npt.NDArray[np.int8],
    grid_ns: npt.NDArray[np.int64],
    mid: npt.NDArray[np.float64],
    sigma2: npt.NDArray[np.float64],
    forecast: npt.NDArray[np.float64],
    sentiment: npt.NDArray[np.float64],
    params: dict[str, Any],
) -> dict[str, Any]: ...
