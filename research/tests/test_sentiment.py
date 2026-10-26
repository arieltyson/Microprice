import pytest

from microprice import sentiment


def test_headline_is_first_sentence_like_line() -> None:
    document = """<html><body><p>Exhibit 99.1</p><p>FOR IMMEDIATE RELEASE</p>
    <p><b>Apple reports fourth quarter results with record services revenue</b></p>
    <p>CUPERTINO, California</p></body></html>"""
    assert sentiment.headline_from_html(document) == (
        "Apple reports fourth quarter results with record services revenue"
    )


def test_headline_missing_returns_none() -> None:
    assert sentiment.headline_from_html("<p>EX-99.1</p><p>TABLE</p>") is None


def test_sec_client_requires_contact_email() -> None:
    with pytest.raises(ValueError):
        sentiment.SecClient("no contact")


def test_tweet_headline_is_split_into_tickers_and_text() -> None:
    tickers, body = sentiment.clean_tweet_headline("$AAPL $MSFT - Apple, Microsoft lift guidance https://t.co/x")
    assert tickers == ["AAPL", "MSFT"]
    assert body == "Apple, Microsoft lift guidance"
