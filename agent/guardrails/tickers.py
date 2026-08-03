from db.queries import get_company
from tools.companies import ticker_exists_live


def validate_ticker(ticker: str) -> bool:
    """True if `ticker` resolves against the companies table OR (fallback, for a real
    but smaller/less-known ASX company outside the top-200 seed) a live yfinance
    existence check. False only when both miss - used by router_node to reject/clarify
    a hallucinated ticker before any live tool call is made against it."""
    if get_company(ticker):
        return True
    return ticker_exists_live(ticker)
