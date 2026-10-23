from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import requests

from agent.pipelines.orchestrator import _news_health_issue
from tools.search import _search_news_rss, search_news

RSS_XML = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0"><channel><title>Yahoo! Finance: NAB.AX News</title>
<item>
  <description>Investing.com -- National Australia Bank plans to cut up to 2,500 jobs &amp; book a charge.</description>
  <link>https://au.finance.yahoo.com/news/nab-cut-2-500-jobs-020209081.html?.tsrc=rss</link>
  <pubDate>Tue, 20 Oct 2026 02:02:09 +0000</pubDate>
  <title>NAB to cut 2,500 jobs as bank moves to simplify operations</title>
</item>
<item>
  <description>&lt;p&gt;Shares closed higher.&lt;/p&gt;</description>
  <link>https://www.news.com.au/finance/markets/story?.tsrc=rss</link>
  <pubDate>Wed, 21 Oct 2026 06:39:07 +0000</pubDate>
  <title>RBA&#8217;s grim rate call fails to dent ASX gains</title>
</item>
<item><title>No link, skipped</title></item>
</channel></rss>"""

YF_ARTICLE = {"title": "From yfinance", "publisher": "Reuters", "link": "https://x", "published": "", "snippet": ""}


def _rss_response(content=RSS_XML, status=200):
    response = MagicMock(content=content, status_code=status)
    response.raise_for_status.side_effect = requests.HTTPError(f"{status}") if status >= 400 else None
    return response


def test_rss_items_map_to_the_search_news_shape():
    with patch("tools.search.requests.get", return_value=_rss_response()):
        articles = _search_news_rss("NAB.AX")
    assert articles == [
        {
            "title": "NAB to cut 2,500 jobs as bank moves to simplify operations",
            "publisher": "Yahoo Finance",
            "link": "https://au.finance.yahoo.com/news/nab-cut-2-500-jobs-020209081.html",
            "published": "2026-10-20T02:02:09+00:00",
            "snippet": "Investing.com -- National Australia Bank plans to cut up to 2,500 jobs & book a charge.",
        },
        {
            "title": "RBA’s grim rate call fails to dent ASX gains",
            "publisher": "news.com.au",
            "link": "https://www.news.com.au/finance/markets/story",
            "published": "2026-10-21T06:39:07+00:00",
            "snippet": "Shares closed higher.",
        },
    ]


def test_rss_failures_return_none_instead_of_raising():
    with patch("tools.search.requests.get", side_effect=requests.ConnectionError("down")):
        assert _search_news_rss("NAB.AX") is None
    with patch("tools.search.requests.get", return_value=_rss_response(status=502)):
        assert _search_news_rss("NAB.AX") is None
    with patch("tools.search.requests.get", return_value=_rss_response(content=b"<html>not xml")):
        assert _search_news_rss("NAB.AX") is None


def test_yfinance_results_are_used_when_present():
    with patch("tools.search._search_news_yfinance", return_value=[YF_ARTICLE]), \
         patch("tools.search._search_news_rss") as rss:
        assert search_news("NAB.AX") == [YF_ARTICLE]
    rss.assert_not_called()


def test_falls_back_to_rss_when_yfinance_returns_nothing():
    # The outage case: Yahoo's news API 502s and yfinance hands back an empty list.
    for yf_result in ([], None):
        with patch("tools.search._search_news_yfinance", return_value=yf_result), \
             patch("tools.search._search_news_rss", return_value=[YF_ARTICLE]):
            assert search_news("NAB.AX") == [YF_ARTICLE]


def test_both_sources_empty_keeps_yfinances_verdict():
    for yf_result, rss_result in (([], []), ([], None), (None, []), (None, None)):
        with patch("tools.search._search_news_yfinance", return_value=yf_result), \
             patch("tools.search._search_news_rss", return_value=rss_result):
            assert search_news("NAB.AX") == yf_result


def test_news_health_flags_a_run_that_fetched_nothing():
    issue = _news_health_issue(["NAB.AX", "CBA.AX"], articles_fetched=0)
    assert issue == "News source returned no articles for any of the 2 watchlisted tickers."


def test_news_health_flags_stale_news():
    old = datetime.now(timezone.utc) - timedelta(days=28)
    with patch("agent.pipelines.orchestrator.get_latest_news_published_at", return_value=old):
        issue = _news_health_issue(["NAB.AX"], articles_fetched=5)
    assert issue and "over 7 days ago" in issue


def test_news_health_passes_fresh_news_and_empty_watchlists():
    fresh = datetime.now(timezone.utc) - timedelta(days=1)
    with patch("agent.pipelines.orchestrator.get_latest_news_published_at", return_value=fresh):
        assert _news_health_issue(["NAB.AX"], articles_fetched=5) is None
    assert _news_health_issue([], articles_fetched=0) is None
