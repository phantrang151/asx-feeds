from unittest.mock import patch, MagicMock
import pytest
import logging
from tools.search import search_news
from yfinance.exceptions import YFRateLimitError, YFException
from requests.exceptions import HTTPError
from tools.search import NewsRateLimitError
from requests.exceptions import ConnectionError
from requests.exceptions import Timeout
from requests import Response


@pytest.fixture(autouse=True)
def no_rss_fallback(request):
    """These tests exercise the yfinance path; a yfinance miss would otherwise fall through to
    a live Yahoo RSS request (see tests/test_news_fallback.py for the fallback itself). The
    live end-to-end test keeps the real fallback."""
    if request.node.name == "test_search_news_valid_ticker":
        yield
        return
    with patch("tools.search._search_news_rss", return_value=None):
        yield


def test_search_news_valid_ticker():
    result = search_news("TLS.AX")
    assert len(result) > 0

def test_search_news_invalid_ticker(caplog):
    with caplog.at_level(logging.WARNING):
        invalid_ticker = ""
        result = search_news(invalid_ticker)
    assert result is None
    assert f"No ticker provided for news search." in caplog.text
    
def test_search_news_return_empty_list(caplog):
    fake_stock = MagicMock()
    fake_stock.news = []
    with patch('tools.search.yf.Ticker', return_value=fake_stock):
        test_ticker = "TLS.AX"
        with caplog.at_level(logging.INFO):
            result = search_news(test_ticker)
    assert result == []
    assert f"No news found for ticker: {test_ticker}" in caplog.text

def test_search_Yahoo_contract_changed(caplog):
    fake_stock = MagicMock()
    fake_stock.news = [
        {
        "content": {
            "title": None,
            "canonicalUrl": {
                "url": None
            },
            "link": None
        }
    }
    ]
    with patch('tools.search.yf.Ticker', return_value=fake_stock):
        test_ticker = "TLS.AX"
        with caplog.at_level(logging.INFO):
            result = search_news(test_ticker)
    assert result is None
    assert f"Yahoo contract has changed. No valid news articles found for ticker: {test_ticker}" in caplog.text

def test_connection_timeout(caplog):
    test_ticker = "TLS.AX"

    with patch('tools.search.yf.Ticker') as mock_ticker:
        mock_ticker.side_effect = Timeout(f"Timeout occurred while fetching news for ticker {test_ticker}.")

        with caplog.at_level(logging.ERROR):
            result = search_news(test_ticker)

    assert result is None
    assert f"Timeout occurred while fetching news for ticker {test_ticker}." in caplog.text

def test_rate_limit_error():
    test_ticker = "TLS.AX"
    response = Response()
    response.status_code = 429
    http_error = HTTPError(response=response) 

    with patch('tools.search.yf.Ticker') as mock_ticker:
        mock_ticker.side_effect = http_error

        with pytest.raises(NewsRateLimitError) as excinfo:
            search_news(test_ticker)

    assert (f"Rate limit exceeded for ticker {test_ticker}." in str(excinfo.value))
