"""Pure-logic tests for validate_ticker's branch logic - db.queries.get_company and
tools.companies.ticker_exists_live are mocked, no real network/DB calls."""

from unittest.mock import patch

from agent.guardrails.tickers import validate_ticker


def test_validate_ticker_true_when_in_companies_table():
    with patch("agent.guardrails.tickers.get_company", return_value={"ticker": "TLS.AX"}) as mock_get, \
         patch("agent.guardrails.tickers.ticker_exists_live") as mock_live:
        assert validate_ticker("TLS.AX") is True
        mock_get.assert_called_once_with("TLS.AX")
        mock_live.assert_not_called()  # short-circuits, never needs the live fallback


def test_validate_ticker_true_via_live_fallback_when_not_in_table():
    with patch("agent.guardrails.tickers.get_company", return_value=None), \
         patch("agent.guardrails.tickers.ticker_exists_live", return_value=True) as mock_live:
        assert validate_ticker("SMALLCAP.AX") is True
        mock_live.assert_called_once_with("SMALLCAP.AX")


def test_validate_ticker_false_when_both_miss():
    with patch("agent.guardrails.tickers.get_company", return_value=None), \
         patch("agent.guardrails.tickers.ticker_exists_live", return_value=False):
        assert validate_ticker("XYZQ.AX") is False
