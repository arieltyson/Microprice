import numpy as np
import pandas as pd

from microprice import _engine, lobster, synth


def _day(seed: int = 3) -> pd.DataFrame:
    messages, _ = synth.generate_day(synth.PROFILES[0], "2026-10-19", seed, duration_s=300)
    return messages


def test_generation_is_deterministic_for_a_seed() -> None:
    pd.testing.assert_frame_equal(_day(), _day())


def test_messages_replay_to_the_same_event_stream() -> None:
    messages = _day()
    columns = lobster.to_columns(messages)
    engine = _engine.Engine(1, 10_000_000, 1 << 21)
    engine.apply_lobster(
        columns.ts, columns.type, columns.order_id, columns.size, columns.price, columns.direction,
        0, len(columns),
    )
    replayed = synth._events_to_messages([engine.drain_events()])
    pd.testing.assert_frame_equal(replayed, messages)


def test_book_never_crosses() -> None:
    book = synth.top_of_book(_day())
    both = (book["ask_size_1"] > 0) & (book["bid_size_1"] > 0)
    assert (book.loc[both, "ask_price_1"] > book.loc[both, "bid_price_1"]).all()


def test_news_moves_fair_value_in_the_direction_of_sentiment() -> None:
    headlines = pd.DataFrame({"symbol": ["AAPL"], "headline": ["Record revenue"], "sentiment": [1.0]})
    params = synth.FlowParams(news_per_day=400.0, news_impact=0.02)
    up, news = synth.generate_day(synth.PROFILES[0], "2026-10-19", 5, headlines, params, duration_s=600)
    flat, _ = synth.generate_day(synth.PROFILES[0], "2026-10-19", 5, None, params, duration_s=600)
    assert len(news) > 0
    last = lambda m: m.loc[m["type"] == lobster.EXECUTE, "price"].iloc[-200:].mean()  # noqa: E731
    assert last(up) > last(flat)
    assert np.isfinite(last(up))
