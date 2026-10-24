from unittest.mock import patch

from agent.chat.nodes import _latest_news_ticker
from tools.react_tools import get_my_thesis_tool

USER_CONFIG = {"configurable": {"langgraph_user_id": "user-1"}}

FEEDS = [
    {"id": "f-rev", "feed_name": "Revenue Trend", "feed_description": "Whether revenue is rising or falling"},
    {"id": "f-ai", "feed_name": "AI Investment", "feed_description": "Spending on AI and technology"},
]


def _insight(created_at, text, feed_summaries):
    return {"created_at": created_at, "insight_text": text, "feed_summaries": feed_summaries}


def _call(ticker="NAB.AX", feeds=FEEDS, insights=()):
    """Invoke the tool the way the ReAct agent's ToolNode does (a tool call, so the artifact
    comes back too) and return (content, artifact, mocks)."""
    with patch("tools.react_tools.get_feeds_for_user", return_value=list(feeds)) as get_feeds, \
         patch("tools.react_tools.get_user_ticker_insights", return_value=list(insights)) as get_insights:
        message = get_my_thesis_tool.invoke(
            {"name": "get_my_thesis_tool", "args": {"ticker": ticker}, "id": "call-1", "type": "tool_call"},
            config=USER_CONFIG,
        )
    return message.content, message.artifact, get_feeds, get_insights


def test_model_cannot_choose_the_user():
    # Only the ticker is exposed to the model; the user comes from the injected run config.
    assert set(get_my_thesis_tool.args) == {"ticker"}


def test_reads_the_signed_in_users_thesis():
    _, _, get_feeds, get_insights = _call()
    get_feeds.assert_called_once_with("user-1", "NAB.AX")
    get_insights.assert_called_once_with("user-1", "NAB.AX", limit=2)


def test_compares_latest_and_previous_per_feed():
    latest = _insight("2026-10-20T01:00:00Z", "AI spend is rising.", [
        {"feed_id": "f-rev", "feed_name": "Revenue Trend", "status": "insufficient", "summary": None, "item_count": 0},
        {"feed_id": "f-ai", "feed_name": "AI Investment", "status": "sufficient", "summary": "New AI partnership.", "item_count": 3},
    ])
    previous = _insight("2026-10-13T01:00:00Z", "Little evidence.", [
        {"feed_id": "f-rev", "feed_name": "Revenue Trend", "status": "insufficient", "summary": None, "item_count": 0},
        {"feed_id": "f-ai", "feed_name": "AI Investment", "status": "insufficient", "summary": "One weak item.", "item_count": 1},
    ])
    content, artifact, _, _ = _call(insights=[latest, previous])

    assert "Latest insight (2026-10-20): AI spend is rising." in content
    assert "Previous insight (2026-10-13): Little evidence." in content
    assert "previous: insufficient, 1 items: One weak item." in content
    assert "latest: sufficient, 3 items: New AI partnership." in content
    assert "News published after 2026-10-20" in content
    # Feeds with a saved summary become references; empty ones don't.
    assert [r["content"] for r in artifact] == [
        "Your AI Investment feed - latest insight, 2026-10-20",
        "Your AI Investment feed - previous insight, 2026-10-13",
    ]
    assert all(r["url"] is None for r in artifact)


def test_matches_a_renamed_feed_by_feed_id():
    latest = _insight("2026-10-20", "x", [
        {"feed_id": "f-ai", "feed_name": "AI Spend", "status": "sufficient", "summary": "now", "item_count": 2}])
    previous = _insight("2026-10-13", "y", [
        {"feed_id": "f-ai", "feed_name": "AI Investment", "status": "sufficient", "summary": "before", "item_count": 1}])
    content, _, _, _ = _call(insights=[latest, previous])
    assert "AI Spend (renamed from AI Investment)" in content
    assert "not tracked in this snapshot" not in content


def test_legacy_snapshots_without_feed_id_match_by_name():
    latest = _insight("2026-10-20", "x", [{"feed_name": "Revenue Trend", "status": "sufficient", "summary": "up", "item_count": 2}])
    previous = _insight("2026-10-13", "y", [{"feed_name": "Revenue Trend", "status": "sufficient", "summary": "flat", "item_count": 2}])
    content, _, _, _ = _call(insights=[latest, previous])
    assert "previous: sufficient, 2 items: flat" in content
    assert "latest: sufficient, 2 items: up" in content


def test_single_snapshot_says_there_is_nothing_to_compare():
    content, _, _, _ = _call(insights=[_insight("2026-10-20", "x", [])])
    assert "only one snapshot" in content
    assert "predate per-feed summaries" in content


def test_no_feeds_and_no_insights():
    content, artifact, _, _ = _call(feeds=[], insights=[])
    assert "no feeds or saved insights for NAB.AX" in content
    assert artifact == []


def test_feeds_but_no_insight_yet():
    content, artifact, _, _ = _call(insights=[])
    assert "Revenue Trend: Whether revenue is rising or falling" in content
    assert "No insight has been generated" in content
    assert artifact == []


def test_thesis_question_skips_the_latest_news_shortcut():
    assert _latest_news_ticker("What has changed in my NAB.AX thesis based on the latest news?") is None
    assert _latest_news_ticker("Any latest news on my NAB.AX feeds?") is None
    # Plain headline lookups still take the shortcut.
    assert _latest_news_ticker("latest news on NAB.AX") == "NAB.AX"
