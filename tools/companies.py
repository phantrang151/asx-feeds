from typing import Optional

import yfinance as yf


def ticker_exists_live(ticker: str) -> bool:
    """Live fallback existence check for a ticker not found in the `companies` table
    (e.g. a real ASX company outside the top-200 Wikipedia seed). Same fail-safe style
    as tools/price.py::get_latest_price - any exception is treated as 'not confirmed',
    never raised."""
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        return not hist.empty
    except Exception:
        return False


def fetch_sector_industry_live(ticker: str) -> tuple[Optional[str], Optional[str]]:
    """Live yfinance lookup for sector/industry, used to cache peer-ticker metadata (see
    ingestion_steps.py::ensure_company_sector_cached). The only place in this codebase
    that calls yfinance's `.info` (search_news/ticker_exists_live use `.news`/`.history`
    instead) - `.info` is a much heavier call, so it's deliberately not used elsewhere.
    Fail-safe like ticker_exists_live: any exception returns (None, None) rather than
    raising, so a lookup failure never crashes the ingestion pipeline."""
    try:
        info = yf.Ticker(ticker).info
        return info.get("sector"), info.get("industry")
    except Exception:
        return None, None
