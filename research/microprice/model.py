"""Short-horizon mid-price forecasts with LightGBM.

Training uses purged walk-forward splits: each test block is a later trading
day, every earlier day is training data, and training rows whose label window
reaches into the test block (plus an embargo) are dropped (López de Prado,
2018). Results are compared with a one-feature baseline that regresses the
forward move on the micro-price deviation.
"""

from __future__ import annotations

import json
from collections.abc import Iterator, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path

import lightgbm as lgb
import numpy as np
import numpy.typing as npt
import pandas as pd
from scipy.stats import spearmanr

from microprice import features
from microprice.synth import DATES, PROFILES

TARGET_HORIZON = 10
LGBM_PARAMS = {
    "objective": "regression",
    "learning_rate": 0.05,
    "num_leaves": 31,
    "min_data_in_leaf": 200,
    "feature_fraction": 0.9,
    "bagging_fraction": 0.8,
    "bagging_freq": 1,
    "lambda_l2": 1.0,
    "verbose": -1,
    "seed": 7,
    # Few threads: OpenMP barriers stall badly when the machine is oversubscribed.
    "num_threads": 2,
}
NUM_ROUNDS = 200
MAX_TRAIN_ROWS = 250_000  # random subsample per fold; keeps training fast and decorrelates rows


def _one(task: tuple[Path, str, str]) -> pd.DataFrame:
    root, symbol, date = task
    return features.build_features(root, symbol, date)


def load_dataset(root: Path, cache: Path, workers: int = 8) -> pd.DataFrame:
    """Builds (or reads cached) grid features for every symbol-day."""
    if cache.exists():
        return pd.read_parquet(cache)
    tasks = [(root, p.symbol, d) for p in PROFILES for d in DATES]
    with ProcessPoolExecutor(max_workers=workers) as pool:
        frames = list(pool.map(_one, tasks))
    data = (
        pd.concat(frames, ignore_index=True)
        .sort_values(["time", "sym"], kind="stable")
        .reset_index(drop=True)
    )
    cache.parent.mkdir(parents=True, exist_ok=True)
    data.to_parquet(cache)
    return data


def usable(data: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Drops rows whose label window passes the close or whose book was one-sided."""
    close = data["time"].dt.normalize() + pd.Timedelta(hours=16)
    ok = (
        (data["time"] + pd.Timedelta(seconds=horizon) <= close)
        & data[f"fwd{horizon}"].notna()
        & data["mid"].notna()
    )
    frame: pd.DataFrame = data[ok].reset_index(drop=True)
    return frame


def subsample(frame: pd.DataFrame, rows: int = MAX_TRAIN_ROWS) -> pd.DataFrame:
    return frame if len(frame) <= rows else frame.sample(n=rows, random_state=7)


@dataclass(frozen=True)
class Split:
    test_day: str
    train: npt.NDArray[np.int64]
    test: npt.NDArray[np.int64]


def purged_walk_forward(
    times: pd.Series, days: Sequence[str], horizon_s: int, embargo_s: int = 60, min_train_days: int = 2
) -> Iterator[Split]:
    day_of = times.dt.strftime("%Y-%m-%d").to_numpy()
    for i in range(min_train_days, len(days)):
        test_mask = day_of == days[i]
        test_start = times[test_mask].min()
        cutoff = test_start - pd.Timedelta(seconds=horizon_s + embargo_s)
        train_mask = (times < cutoff).to_numpy() & np.isin(day_of, days[:i])
        yield Split(days[i], np.flatnonzero(train_mask), np.flatnonzero(test_mask))


def evaluate(prediction: npt.NDArray[np.float64], realized: npt.NDArray[np.float64]) -> dict[str, float]:
    moved = realized != 0
    ic = spearmanr(prediction, realized).statistic
    hit = float(np.mean(np.sign(prediction[moved]) == np.sign(realized[moved])))
    residual = realized - prediction
    r2 = 1.0 - float(np.var(residual) / np.var(realized))
    return {"ic": float(ic), "hit_rate": hit, "r2": r2, "n": float(len(realized))}


def baseline_fit(train: pd.DataFrame, target: str) -> tuple[float, float]:
    x, y = train["microDev"].fillna(0).to_numpy(), train[target].to_numpy()
    slope, intercept = np.polyfit(x, y, 1)
    return float(slope), float(intercept)


def walk_forward(data: pd.DataFrame, horizon: int = TARGET_HORIZON) -> dict[str, object]:
    target = f"fwd{horizon}"
    frame = usable(data, horizon)
    folds: list[dict[str, object]] = []
    predictions = np.full(len(frame), np.nan)
    for split in purged_walk_forward(frame["time"], DATES, horizon):
        train, test = subsample(frame.iloc[split.train]), frame.iloc[split.test]
        booster = lgb.train(
            LGBM_PARAMS, lgb.Dataset(train[features.FEATURE_COLUMNS], train[target]), NUM_ROUNDS
        )
        pred = booster.predict(test[features.FEATURE_COLUMNS])
        predictions[split.test] = pred
        slope, intercept = baseline_fit(train, target)
        base = slope * test["microDev"].fillna(0).to_numpy() + intercept
        folds.append(
            {
                "test_day": split.test_day,
                "train_rows": len(split.train),
                "lightgbm": evaluate(np.asarray(pred), test[target].to_numpy()),
                "microprice_baseline": evaluate(base, test[target].to_numpy()),
            }
        )
    importance = dict(zip(features.FEATURE_COLUMNS, booster.feature_importance("gain").tolist(), strict=True))
    return {"horizon_s": horizon, "folds": folds, "feature_gain": importance, "predictions": predictions}


def fit_final(data: pd.DataFrame, train_days: Sequence[str], horizon: int = TARGET_HORIZON) -> lgb.Booster:
    frame = usable(data, horizon)
    train = subsample(frame[frame["date"].isin(train_days)])
    return lgb.train(
        LGBM_PARAMS, lgb.Dataset(train[features.FEATURE_COLUMNS], train[f"fwd{horizon}"]), NUM_ROUNDS
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Walk-forward LightGBM mid-price forecasts.")
    parser.add_argument("--data", type=Path, default=Path("../data/synthetic"))
    parser.add_argument("--cache", type=Path, default=Path("../data/features/features.parquet"))
    parser.add_argument("--out", type=Path, default=Path("../results"))
    args = parser.parse_args()

    data = load_dataset(args.data, args.cache)
    summary: dict[str, object] = {"rows": len(data)}
    for horizon in features.HORIZONS:
        result = walk_forward(data, horizon)
        result.pop("predictions")
        summary[f"fwd{horizon}"] = result
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "forecast.json").write_text(json.dumps(summary, indent=2))
    models = Path("models")
    models.mkdir(exist_ok=True)
    fit_final(data, DATES[:2]).save_model(str(models / f"lgbm_fwd{TARGET_HORIZON}.txt"))
    for horizon in features.HORIZONS:
        folds = summary[f"fwd{horizon}"]["folds"]  # type: ignore[index]
        ic = np.mean([f["lightgbm"]["ic"] for f in folds])
        base = np.mean([f["microprice_baseline"]["ic"] for f in folds])
        print(f"fwd{horizon}: LightGBM IC {ic:.3f} vs micro-price baseline {base:.3f}")


if __name__ == "__main__":
    main()
