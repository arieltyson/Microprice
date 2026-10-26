"""Tick store access with a kdb+ backend and a pandas reference backend.

The q analytics in tickstore/analytics.q and the functions here share names and
output columns. The pandas versions run everywhere; KdbStore runs the q versions
when PyKX and a kdb+ license are available, and tests compare the two.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from microprice import lobster

REPO_ROOT = Path(__file__).resolve().parents[2]


def quote_trade_tables(
    messages: pd.DataFrame, orderbook: pd.DataFrame, symbol: str, date: str
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Builds level-1 quote and trade tables from a LOBSTER file pair (prices in ticks)."""
    midnight = pd.Timestamp(date)
    time = midnight + pd.to_timedelta(np.rint(messages["time"].to_numpy() * 1e9).astype(np.int64), unit="ns")
    quote = pd.DataFrame(
        {
            "time": time,
            "sym": symbol,
            # An empty side is null rather than LOBSTER's sentinel price.
            "bid": (orderbook["bid_price_1"] // lobster.LOBSTER_PRICE_PER_TICK).where(orderbook["bid_size_1"] > 0),
            "ask": (orderbook["ask_price_1"] // lobster.LOBSTER_PRICE_PER_TICK).where(orderbook["ask_size_1"] > 0),
            "bsize": orderbook["bid_size_1"].to_numpy(),
            "asize": orderbook["ask_size_1"].to_numpy(),
        }
    )
    executed = (messages["type"] == lobster.EXECUTE).to_numpy()
    trade = pd.DataFrame(
        {
            "time": time[executed],
            "sym": symbol,
            "price": messages.loc[executed, "price"].to_numpy() // lobster.LOBSTER_PRICE_PER_TICK,
            "size": messages.loc[executed, "size"].to_numpy(),
            "side": -messages.loc[executed, "direction"].to_numpy().astype(np.int16),
        }
    )
    return quote, trade


def with_micro(quote: pd.DataFrame) -> pd.DataFrame:
    out = quote.copy()
    bid, ask = out["bid"].astype(float), out["ask"].astype(float)
    bsize, asize = out["bsize"].astype(float), out["asize"].astype(float)
    out["mid"] = 0.5 * (bid + ask)
    out["spread"] = ask - bid
    out["imb"] = (bsize - asize) / (bsize + asize)
    out["micro"] = (bid * asize + ask * bsize) / (bsize + asize)
    return out


def ofi(quote: pd.DataFrame) -> pd.DataFrame:
    out = quote.copy()
    grouped = out.groupby("sym", sort=False)
    pb, pbs = grouped["bid"].shift(), grouped["bsize"].shift()
    pa, pas = grouped["ask"].shift(), grouped["asize"].shift()
    e = (
        (out["bid"] >= pb) * out["bsize"]
        - (out["bid"] <= pb) * pbs
        - (out["ask"] <= pa) * out["asize"]
        + (out["ask"] >= pa) * pas
    )
    out["e"] = e.fillna(0.0).astype(float)
    return out


def trades_with_quotes(trade: pd.DataFrame, quote: pd.DataFrame) -> pd.DataFrame:
    """Attaches the last quote strictly before each trade (q: aj on time-1)."""
    left = trade.assign(qtime=(trade["time"] - pd.Timedelta(1, "ns")).astype("datetime64[ns]")).sort_values("qtime")
    right = quote[["sym", "time", "bid", "ask", "bsize", "asize"]].rename(columns={"time": "qtime"})
    right["qtime"] = right["qtime"].astype("datetime64[ns]")
    merged = pd.merge_asof(left, right.sort_values("qtime"), on="qtime", by="sym", direction="backward")
    return merged.drop(columns="qtime").sort_values("time", kind="stable").reset_index(drop=True)


class TickStore(Protocol):
    def tables(self, symbol: str, date: str) -> tuple[pd.DataFrame, pd.DataFrame]: ...


@dataclass(frozen=True)
class LobsterStore:
    """Reads quote and trade tables straight from LOBSTER files."""

    root: Path

    def tables(self, symbol: str, date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        messages = lobster.read_messages(lobster.message_file(self.root, symbol, date))
        book = lobster.read_orderbook(lobster.orderbook_file(self.root, symbol, date), levels=1)
        return quote_trade_tables(messages, book, symbol, date)


class KdbStore:
    """Runs the q analytics through PyKX against a kdb+ HDB.

    Requires PyKX with a kdb+ license (KDB_LICENSE_B64 or a k4.lic file).
    """

    def __init__(self, hdb: Path) -> None:
        import pykx as kx  # imported lazily: optional dependency

        self._kx = kx
        kx.q(f'\\l {REPO_ROOT / "tickstore" / "schema.q"}')
        kx.q(f'\\l {REPO_ROOT / "tickstore" / "analytics.q"}')
        kx.q(f"\\l {hdb}")

    def tables(self, symbol: str, date: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        q = self._kx.q
        quote = q(f"select time, sym, bid, ask, bsize, asize from quote where date={date.replace('-', '.')}, sym=`{symbol}")
        trade = q(f"select time, sym, price, size, side from trade where date={date.replace('-', '.')}, sym=`{symbol}")
        return quote.pd(), trade.pd()

    def features(self, symbol: str, date: str, step_s: float, horizons: list[int]) -> pd.DataFrame:
        q = self._kx.q
        day = date.replace("-", ".")
        expr = (
            f"features[select from quote where date={day}, sym=`{symbol};"
            f" select from trade where date={day}, sym=`{symbol};"
            f" grid[`{symbol};{day};{step_s}]; {' '.join(str(h) for h in horizons)}]"
        )
        return q(expr).pd()


def kdb_available() -> bool:
    try:
        import pykx as kx

        return bool(kx.licensed)
    except Exception:
        return False
