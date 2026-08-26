import re

from db.queries import get_company
from tools.companies import ticker_exists_live

_ASX_TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,10}\.AX$")


def validate_ticker(ticker: str) -> bool:
    """True if `ticker` resolves against the companies table OR (fallback, for a real
    but smaller/less-known ASX company outside the top-200 seed) a live yfinance
    existence check. False only when both miss - used by router_node to reject/clarify
    a hallucinated ticker before any live tool call is made against it."""
    if not _ASX_TICKER_PATTERN.fullmatch(ticker):
        return False
    if get_company(ticker):
        return True
    return ticker_exists_live(ticker)
