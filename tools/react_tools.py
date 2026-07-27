from langchain_core.tools import tool

from tools.search import search_news as _search_news
from tools.price import get_latest_price as _get_latest_price
from tools.financials import get_financial_summary as _get_financial_summary


@tool
def search_news_tool(ticker: str) -> str:
    """Get recent news headlines for an ASX ticker. Input is the ticker symbol, e.g. 'TLS.AX'."""
    articles = _search_news(ticker)
    if not articles:
        return f"No recent news found for {ticker}."
    return "\n".join(f"- {a['title']} ({a['publisher']})" for a in articles)


@tool
def get_latest_price_tool(ticker: str) -> str:
    """Get the latest share price for an ASX ticker. Input is the ticker symbol, e.g. 'TLS.AX'."""
    return _get_latest_price(ticker)


@tool
def get_financial_summary_tool(ticker: str) -> str:
    """Get the latest stored financial record (revenue, profit, headcount) for an ASX ticker."""
    return _get_financial_summary(ticker)
