"""Financial headline sentiment, scored with FinBERT.

Two headline sources are supported:

* ``open`` (default): the Twitter Financial News dataset, about 12,000 market
  headlines under the MIT license, with human sentiment labels used here to
  check FinBERT's agreement.
* ``edgar``: titles of press releases filed as Exhibit 99.1 to Form 8-K, timed
  by EDGAR acceptance. The SEC requires a User-Agent with a real contact email
  (SEC_USER_AGENT) and at most 10 requests per second.
"""

from __future__ import annotations

import html
import json
import re
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pandas as pd
import requests

SEC_MIN_INTERVAL_S = 0.12  # stays under 10 requests per second
FINBERT_MODEL = "ProsusAI/finbert"
OPEN_HEADLINES_URL = (
    "https://huggingface.co/datasets/zeroshot/twitter-financial-news-sentiment/resolve/main/{split}.csv"
)
# Dataset labels: 0 bearish, 1 bullish, 2 neutral.
OPEN_LABEL_SIGN = {0: -1, 1: 1, 2: 0}


@dataclass(frozen=True)
class Headline:
    symbol: str
    accepted: pd.Timestamp
    text: str
    url: str


class SecClient:
    """Minimal EDGAR client that throttles itself to the fair access limit."""

    def __init__(self, user_agent: str, session: requests.Session | None = None) -> None:
        if "@" not in user_agent:
            raise ValueError("the SEC requires a User-Agent with a contact email address")
        self._session = session or requests.Session()
        self._session.headers.update({"User-Agent": user_agent, "Accept-Encoding": "gzip, deflate"})
        self._last = 0.0

    def get(self, url: str) -> requests.Response:
        wait = SEC_MIN_INTERVAL_S - (time.monotonic() - self._last)
        if wait > 0:
            time.sleep(wait)
        self._last = time.monotonic()
        response = self._session.get(url, timeout=30)
        response.raise_for_status()
        return response


_TAGS = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_SKIP = re.compile(r"^(exhibit|ex-?\s?99|press release|news release|for immediate release|contact)", re.I)


def headline_from_html(document: str) -> str | None:
    """Returns the first sentence-like line of a press release, or None."""
    body = re.sub(r"(?is)<(script|style).*?</\1>", " ", document)
    body = re.sub(r"(?i)<br\s*/?>|</(p|div|tr|h\d|td)>", "\n", body)
    for raw in html.unescape(_TAGS.sub(" ", body)).splitlines():
        line = _SPACE.sub(" ", raw).strip()
        words = line.split()
        if 6 <= len(words) <= 40 and not _SKIP.match(line) and any(c.islower() for c in line):
            return line
    return None


def ticker_to_cik(client: SecClient) -> dict[str, int]:
    data = client.get("https://www.sec.gov/files/company_tickers.json").json()
    return {row["ticker"].upper(): int(row["cik_str"]) for row in data.values()}


def fetch_headlines(client: SecClient, symbols: Iterable[str], per_symbol: int = 25) -> list[Headline]:
    ciks = ticker_to_cik(client)
    headlines: list[Headline] = []
    for symbol in symbols:
        cik = ciks[symbol.upper()]
        recent = client.get(f"https://data.sec.gov/submissions/CIK{cik:010d}.json").json()["filings"][
            "recent"
        ]
        found = 0
        for form, accession, accepted in zip(
            recent["form"], recent["accessionNumber"], recent["acceptanceDateTime"], strict=True
        ):
            if form != "8-K" or found >= per_symbol:
                continue
            folder = f"https://www.sec.gov/Archives/edgar/data/{cik}/{accession.replace('-', '')}"
            items = client.get(f"{folder}/index.json").json()["directory"]["item"]
            exhibit = next((i["name"] for i in items if re.search(r"ex-?99", i["name"], re.I)), None)
            if exhibit is None:
                continue
            text = headline_from_html(client.get(f"{folder}/{exhibit}").text)
            if text:
                headlines.append(Headline(symbol, pd.Timestamp(accepted), text, f"{folder}/{exhibit}"))
                found += 1
    return headlines


class FinBert:
    """FinBERT scores as P(positive) - P(negative), in [-1, 1]."""

    def __init__(self, model_name: str = FINBERT_MODEL) -> None:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._tokenizer = AutoTokenizer.from_pretrained(model_name)
        self._model = AutoModelForSequenceClassification.from_pretrained(model_name)
        self._model.eval()
        labels = {v.lower(): k for k, v in self._model.config.id2label.items()}
        self._positive = labels["positive"]
        self._negative = labels["negative"]

    def score(self, texts: Sequence[str], batch_size: int = 32) -> npt.NDArray[np.float64]:
        import torch

        scores: list[float] = []
        with torch.no_grad():
            for start in range(0, len(texts), batch_size):
                batch = list(texts[start : start + batch_size])
                tokens = self._tokenizer(
                    batch, padding=True, truncation=True, max_length=128, return_tensors="pt"
                )
                probabilities = torch.softmax(self._model(**tokens).logits, dim=-1)
                scores += (probabilities[:, self._positive] - probabilities[:, self._negative]).tolist()
        return np.asarray(scores, dtype=np.float64)


_URL = re.compile(r"https?://\S+")
_CASHTAG = re.compile(r"\$([A-Z]{1,5})\b")


def clean_tweet_headline(text: str) -> tuple[list[str], str]:
    """Splits a headline tweet into its cashtags and the headline text."""
    tickers = _CASHTAG.findall(text)
    body = _URL.sub("", text)
    body = re.sub(r"^(\s*\$[A-Z]{1,5}\s*)+(-\s*)?", "", body)
    return tickers, _SPACE.sub(" ", body).strip()


def fetch_open_headlines(symbols: Sequence[str]) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    wanted = set(symbols) | {"FB"}
    for split in ("sent_train", "sent_valid"):
        raw = pd.read_csv(OPEN_HEADLINES_URL.format(split=split))
        for text, label in zip(raw["text"], raw["label"], strict=True):
            tickers, body = clean_tweet_headline(str(text))
            if len(body.split()) < 4:
                continue
            match = next((t for t in tickers if t in wanted), None)
            symbol = "META" if match == "FB" else (match or "*")
            rows.append(
                {"symbol": symbol, "headline": body, "label": OPEN_LABEL_SIGN[int(label)], "source": split}
            )
    return pd.DataFrame(rows).drop_duplicates("headline").reset_index(drop=True)


def fetch_edgar_headlines(user_agent: str, symbols: Sequence[str], per_symbol: int) -> pd.DataFrame:
    headlines = fetch_headlines(SecClient(user_agent), symbols, per_symbol)
    return pd.DataFrame(
        {
            "symbol": [h.symbol for h in headlines],
            "accepted": [h.accepted for h in headlines],
            "headline": [h.text for h in headlines],
            "url": [h.url for h in headlines],
        }
    )


def build_headline_table(frame: pd.DataFrame, out: Path, source: str) -> pd.DataFrame:
    frame = frame.copy()
    frame["sentiment"] = FinBert().score(frame["headline"].tolist()) if len(frame) else []
    out.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(out, index=False)
    meta: dict[str, object] = {"model": FINBERT_MODEL, "source": source, "rows": len(frame)}
    if "label" in frame:
        signed = frame[frame["label"] != 0]
        meta["finbert_sign_agreement"] = float((np.sign(signed["sentiment"]) == signed["label"]).mean())
    out.with_suffix(".meta.json").write_text(json.dumps(meta, indent=2))
    return frame


def load_headlines(path: Path) -> pd.DataFrame:
    return pd.read_csv(path)


def main() -> None:
    import argparse
    import os

    from microprice.synth import PROFILES

    parser = argparse.ArgumentParser(description="Fetch financial headlines and score them with FinBERT.")
    parser.add_argument("--out", type=Path, default=Path("../data/headlines/headlines.csv"))
    parser.add_argument("--source", choices=["open", "edgar"], default="open")
    parser.add_argument("--per-symbol", type=int, default=25)
    parser.add_argument("--user-agent", default=os.environ.get("SEC_USER_AGENT", ""))
    args = parser.parse_args()
    symbols = [p.symbol for p in PROFILES]
    if args.source == "edgar":
        raw = fetch_edgar_headlines(args.user_agent, symbols, args.per_symbol)
    else:
        raw = fetch_open_headlines(symbols)
    frame = build_headline_table(raw, args.out, args.source)
    print(args.out.with_suffix(".meta.json").read_text())
    print(json.dumps({"by_symbol": frame["symbol"].value_counts().to_dict()}))


if __name__ == "__main__":
    main()
