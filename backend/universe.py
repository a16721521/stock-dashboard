"""Load the marketwide scan universe (S&P 500 + Nasdaq-100), de-duplicated."""

from pathlib import Path

_DIR = Path(__file__).parent / "constituents"


def _read(name):
    text = (_DIR / name).read_text()
    return [line.strip() for line in text.splitlines() if line.strip()]


def load_universe():
    tickers = set(_read("sp500.txt")) | set(_read("nasdaq100.txt"))
    return sorted(tickers)
