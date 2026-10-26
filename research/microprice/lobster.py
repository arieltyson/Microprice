"""Read and write order flow in the LOBSTER file format.

A LOBSTER message file has one row per book change: time in seconds after
midnight, event type, order id, size, price in USD x 10000 and direction
(1 buy, -1 sell). Its companion order book file holds the top levels after each
message as ask price, ask size, bid price, bid size per level.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd

MESSAGE_COLUMNS = ["time", "type", "order_id", "size", "price", "direction"]

SUBMIT, PARTIAL_CANCEL, DELETE, EXECUTE, HIDDEN_EXECUTE, CROSS, HALT = 1, 2, 3, 4, 5, 6, 7

# Prices inside the platform are integer ticks of 0.01 USD.
LOBSTER_PRICE_PER_TICK = 100


@dataclass(frozen=True)
class MessageColumns:
    """Typed column arrays in the layout the C++ engine replays."""

    ts: npt.NDArray[np.int64]
    type: npt.NDArray[np.int32]
    order_id: npt.NDArray[np.uint64]
    size: npt.NDArray[np.int64]
    price: npt.NDArray[np.int64]
    direction: npt.NDArray[np.int8]

    def __len__(self) -> int:
        return len(self.ts)


def read_messages(path: Path) -> pd.DataFrame:
    frame = pd.read_csv(path, header=None, names=MESSAGE_COLUMNS)
    return frame.astype(
        {"type": "int32", "order_id": "uint64", "size": "int64", "price": "int64", "direction": "int8"}
    )


def write_messages(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame[MESSAGE_COLUMNS].to_csv(path, header=False, index=False, float_format="%.9f")


def orderbook_columns(levels: int) -> list[str]:
    names: list[str] = []
    for level in range(1, levels + 1):
        names += [f"ask_price_{level}", f"ask_size_{level}", f"bid_price_{level}", f"bid_size_{level}"]
    return names


def read_orderbook(path: Path, levels: int) -> pd.DataFrame:
    return pd.read_csv(path, header=None, names=orderbook_columns(levels)).astype("int64")


def write_orderbook(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, header=False, index=False)


def to_columns(frame: pd.DataFrame) -> MessageColumns:
    """Converts a message frame to contiguous arrays with nanosecond timestamps."""
    return MessageColumns(
        ts=np.rint(frame["time"].to_numpy(dtype=np.float64) * 1e9).astype(np.int64),
        type=np.ascontiguousarray(frame["type"].to_numpy(dtype=np.int32)),
        order_id=np.ascontiguousarray(frame["order_id"].to_numpy(dtype=np.uint64)),
        size=np.ascontiguousarray(frame["size"].to_numpy(dtype=np.int64)),
        price=np.ascontiguousarray(frame["price"].to_numpy(dtype=np.int64)),
        direction=np.ascontiguousarray(frame["direction"].to_numpy(dtype=np.int8)),
    )


def message_file(root: Path, symbol: str, date: str) -> Path:
    return root / symbol / f"{symbol}_{date}_34200000_57600000_message_1.csv"


def orderbook_file(root: Path, symbol: str, date: str) -> Path:
    return root / symbol / f"{symbol}_{date}_34200000_57600000_orderbook_1.csv"
