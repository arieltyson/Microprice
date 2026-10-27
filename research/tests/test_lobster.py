from pathlib import Path

import numpy as np
import pandas as pd

from microprice import lobster


def test_messages_round_trip(tmp_path: Path) -> None:
    frame = pd.DataFrame(
        {
            "time": [34200.000000001, 34200.5],
            "type": [1, 4],
            "order_id": [7, 7],
            "size": [100, 40],
            "price": [2301200, 2301200],
            "direction": [-1, -1],
        }
    )
    path = lobster.message_file(tmp_path, "AAPL", "2026-10-19")
    lobster.write_messages(frame, path)
    back = lobster.read_messages(path)
    assert back["order_id"].tolist() == [7, 7]
    columns = lobster.to_columns(back)
    assert columns.ts.tolist() == [34_200_000_000_001, 34_200_500_000_000]
    assert columns.type.dtype == np.int32
    assert len(columns) == 2


def test_orderbook_columns_follow_lobster_order() -> None:
    assert lobster.orderbook_columns(2) == [
        "ask_price_1",
        "ask_size_1",
        "bid_price_1",
        "bid_size_1",
        "ask_price_2",
        "ask_size_2",
        "bid_price_2",
        "bid_size_2",
    ]
