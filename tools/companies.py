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
