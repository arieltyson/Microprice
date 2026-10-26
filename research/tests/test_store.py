import shutil
import subprocess
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from microprice import features as F
from microprice import store

DAY = pd.Timestamp("2026-10-19")


def _quotes() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "time": DAY + pd.Timedelta(hours=9, minutes=30) + pd.to_timedelta([1, 2, 3], unit="s"),
            "sym": "AAPL",
            "bid": [100, 100, 101],
            "ask": [101, 102, 102],
            "bsize": [300, 200, 100],
            "asize": [100, 100, 400],
        }
    )


def _trades() -> pd.DataFrame:
    return pd.DataFrame(
        {"time": [DAY + pd.Timedelta(hours=9, minutes=30, seconds=2)], "sym": "AAPL", "price": [101], "size": [50],
         "side": np.array([1], dtype=np.int16)}
    )


def test_micro_price_and_imbalance() -> None:
    m = store.with_micro(_quotes())
    assert m["mid"].tolist() == [100.5, 101.0, 101.5]
    assert m.loc[0, "micro"] == pytest.approx((100 * 100 + 101 * 300) / 400)
    assert m.loc[0, "imb"] == pytest.approx(0.5)


def test_order_flow_imbalance_matches_hand_computed_values() -> None:
    assert store.ofi(_quotes())["e"].tolist() == [0.0, 0.0, -200.0]


def test_trade_sees_quote_strictly_before_it() -> None:
    joined = store.trades_with_quotes(_trades(), _quotes())
    assert (joined.loc[0, "bid"], joined.loc[0, "ask"]) == (100, 101)


def test_features_never_look_ahead() -> None:
    quotes = _quotes()
    g = F.grid("AAPL", "2026-10-19", 1.0).iloc[:3]
    base = F.l1_features(quotes, _trades(), g, (1,))
    # Perturb everything after the second grid point; earlier features must not change.
    future = quotes.copy()
    future.loc[future["time"] > g["time"].iloc[1], ["bid", "ask"]] += 50
    moved = F.l1_features(future, _trades(), g, (1,))
    cols = ["spread", "imb", "microDev", "mid", "ofi1"]
    pd.testing.assert_frame_equal(base.loc[:1, cols], moved.loc[:1, cols])
    assert base.loc[0, "fwd1"] == pytest.approx(0.5)


def test_news_score_decays_and_ignores_future_headlines() -> None:
    g = F.grid("AAPL", "2026-10-19", 1.0).iloc[:120]
    news = pd.DataFrame({"time": [34_200.0 + 30], "sentiment": [0.8]})
    score = F.news_features(news, g, half_life_s=60.0)
    assert (score.iloc[:29] == 0).all()
    assert score.iloc[29] == pytest.approx(0.8)
    assert score.iloc[89] == pytest.approx(0.4)


@pytest.mark.skipif(shutil.which("q") is None, reason="kdb+ (q) is not installed")
def test_q_analytics_unit_tests() -> None:
    root = Path(__file__).resolve().parents[2]
    result = subprocess.run(["q", "tickstore/tests/test_analytics.q", "-q"], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.skipif(not store.kdb_available(), reason="PyKX with a kdb+ license is not available")
def test_q_features_match_pandas(tmp_path: Path) -> None:  # pragma: no cover - needs a license
    import pykx as kx

    root = Path(__file__).resolve().parents[2]
    kx.q(f'\\l {root / "tickstore" / "schema.q"}')
    kx.q(f'\\l {root / "tickstore" / "analytics.q"}')
    g = F.grid("AAPL", "2026-10-19", 1.0).iloc[:3]
    expected = F.l1_features(_quotes(), _trades(), g, (1, 10))
    got = kx.q("features", kx.toq(_quotes()), kx.toq(_trades()), kx.toq(g), kx.toq(np.array([1, 10]))).pd()
    for column in ["spread", "imb", "microDev", "ofi1", "fwd1"]:
        np.testing.assert_allclose(got[column].to_numpy(float), expected[column].to_numpy(float), equal_nan=True)
