"""Features and labels on a regular time grid.

Level-1 features mirror `features` in tickstore/analytics.q column for column.
Depth features replay the LOBSTER messages through the C++ engine to read five
levels per side, and news features decay FinBERT scores of headlines already
published. Every feature at grid time t uses only data timestamped at or
before t; labels are forward mid-price changes in ticks.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import numpy as np
import pandas as pd

from microprice import _engine, lobster
from microprice.store import LobsterStore, ofi, with_micro

OPEN = pd.Timedelta(hours=9, minutes=30)
SESSION_S = 23_400
HORIZONS = (1, 10, 60)
DEPTH_LEVELS = 5
NEWS_HALF_LIFE_S = 60.0


def grid(symbol: str, date: str, step_s: float) -> pd.DataFrame:
    n = round(SESSION_S / step_s)
    start = pd.Timestamp(date) + OPEN
    offsets = pd.to_timedelta(np.rint(1e9 * step_s * np.arange(1, n + 1)).astype(np.int64), unit="ns")
    return pd.DataFrame({"sym": symbol, "time": start + offsets})


def sample_at(g: pd.DataFrame, table: pd.DataFrame, columns: Sequence[str], shift_s: float) -> pd.DataFrame:
    """As-of sample (last row at or before each shifted grid time)."""
    shifted = g.assign(time=(g["time"] + pd.Timedelta(seconds=shift_s)).astype("datetime64[ns]"))
    right = table[["sym", "time", *columns]].assign(time=table["time"].astype("datetime64[ns]"))
    joined = pd.merge_asof(shifted, right, on="time", by="sym", direction="backward")
    return joined[list(columns)].reset_index(drop=True)


def l1_features(quote: pd.DataFrame, trade: pd.DataFrame, g: pd.DataFrame, horizons: Sequence[int]) -> pd.DataFrame:
    qq = ofi(with_micro(quote.sort_values(["sym", "time"], kind="stable")))
    qq["cofi"] = qq.groupby("sym")["e"].cumsum()
    tv = trade.sort_values(["sym", "time"], kind="stable").copy()
    tv["csv"] = (tv["size"] * tv["side"]).groupby(tv["sym"]).cumsum().astype(float)

    now = sample_at(g, qq, ["mid", "micro", "spread", "imb", "cofi"], 0)
    f = g.reset_index(drop=True).copy()
    f["spread"] = now["spread"]
    f["imb"] = now["imb"]
    f["microDev"] = now["micro"] - now["mid"]
    f["mid"] = now["mid"]
    f["ofi1"] = now["cofi"] - sample_at(g, qq, ["cofi"], -1)["cofi"]
    f["ofi10"] = now["cofi"] - sample_at(g, qq, ["cofi"], -10)["cofi"]
    f["tradeImb10"] = (sample_at(g, tv, ["csv"], 0)["csv"] - sample_at(g, tv, ["csv"], -10)["csv"]).fillna(0.0)
    f["ret10"] = f["mid"] - sample_at(g, qq, ["mid"], -10)["mid"]
    f["rv60"] = f["mid"].diff().fillna(0.0).rolling(60, min_periods=1).std(ddof=0)
    for h in horizons:
        f[f"fwd{h}"] = sample_at(g, qq, ["mid"], h)["mid"] - f["mid"]
    return f


def depth_features(messages: pd.DataFrame, g: pd.DataFrame, levels: int = DEPTH_LEVELS) -> pd.DataFrame:
    columns = lobster.to_columns(messages)
    engine = _engine.Engine(1, 10_000_000, 1 << 21)
    grid_ns = (g["time"] - g["time"].dt.normalize()).dt.total_seconds().mul(1e9).round().astype(np.int64).to_numpy()
    cut = np.searchsorted(columns.ts, grid_ns, side="right")
    imbalance = np.full(len(g), np.nan)
    weighted = np.full(len(g), np.nan)
    weights = 1.0 / np.arange(1, levels + 1)
    done = 0
    for i, end in enumerate(cut):
        if end > done:
            engine.apply_lobster(
                columns.ts, columns.type, columns.order_id, columns.size, columns.price, columns.direction, done, end
            )
            engine.drain_events()
            done = int(end)
        _, bid_sizes = engine.top_levels(_engine.BUY, levels)
        _, ask_sizes = engine.top_levels(_engine.SELL, levels)
        total = bid_sizes.sum() + ask_sizes.sum()
        if total > 0:
            imbalance[i] = (bid_sizes.sum() - ask_sizes.sum()) / total
            wb, wa = (weights * bid_sizes).sum(), (weights * ask_sizes).sum()
            weighted[i] = (wb - wa) / (wb + wa)
    return pd.DataFrame({"depthImb5": imbalance, "depthImbW5": weighted})


def news_features(news: pd.DataFrame, g: pd.DataFrame, half_life_s: float = NEWS_HALF_LIFE_S) -> pd.Series:
    """Sum of FinBERT scores of past headlines, decayed by their age."""
    seconds = (g["time"] - g["time"].dt.normalize()).dt.total_seconds().to_numpy()
    decay = np.log(2) / half_life_s
    score = np.zeros(len(g))
    for t, s in zip(news.get("time", []), news.get("sentiment", []), strict=True):
        age = seconds - float(t)
        live = age >= 0
        score[live] += float(s) * np.exp(-decay * age[live])
    return pd.Series(score, name="sentiment")


def build_features(
    root: Path, symbol: str, date: str, step_s: float = 1.0, horizons: Sequence[int] = HORIZONS
) -> pd.DataFrame:
    store = LobsterStore(root)
    quote, trade = store.tables(symbol, date)
    g = grid(symbol, date, step_s)
    f = l1_features(quote, trade, g, horizons)
    messages = lobster.read_messages(lobster.message_file(root, symbol, date))
    f = pd.concat([f, depth_features(messages, g)], axis=1)
    news_path = root / symbol / f"{symbol}_{date}_news.csv"
    news = pd.read_csv(news_path) if news_path.exists() else pd.DataFrame({"time": [], "sentiment": []})
    f["sentiment"] = news_features(news, g).to_numpy()
    f["date"] = date
    return f


FEATURE_COLUMNS = [
    "spread", "imb", "microDev", "ofi1", "ofi10", "tradeImb10", "ret10", "rv60",
    "depthImb5", "depthImbW5", "sentiment",
]
