"""Inputs for strategy runs: order flow, grid state and model forecasts.

Protocol used for every reported number:

* days 1-2 train the LightGBM forecast,
* day 3 selects strategy parameters (the Spark sweep),
* days 4-5 are held out and touched only by the final comparison.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd

from microprice import backtest, features, lobster
from microprice.synth import DATES

TRAIN_DAYS = DATES[:2]
SELECT_DAYS = DATES[2:3]
HOLDOUT_DAYS = DATES[3:]


@dataclass(frozen=True)
class SessionInputs:
    symbol: str
    date: str
    columns: lobster.MessageColumns
    grid_ns: npt.NDArray[np.int64]
    mid: npt.NDArray[np.float64]
    sigma2: npt.NDArray[np.float64]
    forecast: npt.NDArray[np.float64]
    sentiment: npt.NDArray[np.float64]

    def window(self, start: int, end: int) -> SessionInputs:
        return SessionInputs(
            self.symbol,
            self.date,
            self.columns,
            self.grid_ns[start:end],
            self.mid[start:end],
            self.sigma2[start:end],
            self.forecast[start:end],
            self.sentiment[start:end],
        )


def load_session(
    data_root: Path, feature_table: pd.DataFrame, booster: lgb.Booster | None, symbol: str, date: str
) -> SessionInputs:
    rows = feature_table[(feature_table["sym"] == symbol) & (feature_table["date"] == date)].sort_values(
        "time"
    )
    messages = lobster.read_messages(lobster.message_file(data_root, symbol, date))
    columns = lobster.to_columns(messages)
    grid_ns = (
        (rows["time"] - rows["time"].dt.normalize()).dt.total_seconds().mul(1e9).round().astype(np.int64)
    )
    forecast = booster.predict(rows[features.FEATURE_COLUMNS]) if booster is not None else np.zeros(len(rows))
    return SessionInputs(
        symbol=symbol,
        date=date,
        columns=columns,
        grid_ns=grid_ns.to_numpy(),
        mid=rows["mid"].to_numpy(dtype=np.float64),
        sigma2=np.square(rows["rv60"].fillna(0).to_numpy(dtype=np.float64)),
        forecast=np.asarray(forecast, dtype=np.float64),
        sentiment=rows["sentiment"].to_numpy(dtype=np.float64),
    )


def run_session(session: SessionInputs, params: backtest.StrategyParams) -> dict[str, float]:
    result = backtest.run(
        session.columns,
        session.grid_ns,
        session.mid,
        session.sigma2,
        session.forecast,
        session.sentiment,
        params,
    )
    return backtest.summarize(result, session.grid_ns, session.mid)


@lru_cache(maxsize=1)
def cached_table(path: str) -> pd.DataFrame:
    return pd.read_parquet(path)


def load_booster(path: Path) -> lgb.Booster:
    return lgb.Booster(model_file=str(path))
