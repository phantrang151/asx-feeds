"""Pure-logic tests for citation reachability - requests.head/get are mocked, no real
network calls."""

from unittest.mock import MagicMock, patch

import requests

from agent.guardrails.citations import _is_reachable, filter_reachable_references


def _resp(status_code):
    resp = MagicMock()
    resp.status_code = status_code
    return resp


def test_is_reachable_true_on_200():
    with patch("agent.guardrails.citations.requests.head", return_value=_resp(200)):
        assert _is_reachable("https://example.com/article") is True


def test_is_reachable_sends_a_browser_user_agent():
    # finance.yahoo.com (where tools/search.py's yfinance links often actually point,
    # even for e.g. GuruFocus/Simply Wall St-attributed articles) 429s a request with
    # no User-Agent while serving the same URL 200 with a normal browser one -
    # confirmed by hand. Without this header every syndicated article looked dead.
    with patch("agent.guardrails.citations.requests.head", return_value=_resp(200)) as mock_head:
        _is_reachable("https://finance.yahoo.com/markets/stocks/articles/example.html")
        assert "User-Agent" in mock_head.call_args.kwargs["headers"]


def test_is_reachable_true_on_403():
    # Bot-protected sites 403 every automated request regardless of method/UA - that
    # means "blocked our checker", not "link is dead", so this should NOT strip a
    # working link.
    with patch("agent.guardrails.citations.requests.head", return_value=_resp(403)):
        assert _is_reachable("https://example.com/article") is True


def test_is_reachable_true_on_401():
    with patch("agent.guardrails.citations.requests.head", return_value=_resp(401)):
        assert _is_reachable("https://example.com/article") is True


def test_is_reachable_false_on_404():
    with patch("agent.guardrails.citations.requests.head", return_value=_resp(404)):
        assert _is_reachable("https://example.com/gone") is False


def test_is_reachable_false_on_request_exception():
    with patch("agent.guardrails.citations.requests.head", side_effect=requests.RequestException):
        assert _is_reachable("https://example.com/timeout") is False


def test_is_reachable_falls_back_to_get_on_405():
    with patch("agent.guardrails.citations.requests.head", return_value=_resp(405)), \
         patch("agent.guardrails.citations.requests.get", return_value=_resp(200)) as mock_get:
        assert _is_reachable("https://example.com/head-not-allowed") is True
        mock_get.assert_called_once()


def test_filter_reachable_references_nulls_only_dead_links():
    references = [
        {"source": "search_news", "content": "Reachable", "url": "https://ok.example.com"},
        {"source": "search_news", "content": "Bot-blocked", "url": "https://blocked.example.com/a"},
        {"source": "search_news", "content": "Dead", "url": "https://dead.example.com"},
        {"source": "search_news", "content": "No url given", "url": None},
    ]
    reachability = {
        "https://ok.example.com": True,
        "https://blocked.example.com/a": True,
        "https://dead.example.com": False,
    }
    with patch("agent.guardrails.citations._is_reachable", side_effect=lambda u: reachability[u]):
        result = filter_reachable_references(references)

    assert result[0]["url"] == "https://ok.example.com"
    assert result[1]["url"] == "https://blocked.example.com/a"
    assert result[2]["url"] is None
    assert result[3]["url"] is None
