from agent.guardrails.research_order import (
    authorize_peer_news,
    authorize_research_source,
    blocked_tool_result,
    record_internal_news_result,
    research_guard,
)


def test_research_sources_require_internal_news_first():
    with research_guard():
        decision = authorize_research_source("search_news_tool")

    assert decision.allowed is False
    assert decision.reason == "internal_news_required"


def test_research_source_is_allowed_after_internal_news():
    with research_guard():
        record_internal_news_result(found=True)
        decision = authorize_research_source("search_financial_reports_tool")

    assert decision.allowed is True


def test_peer_news_requires_target_news():
    with research_guard():
        record_internal_news_result(found=False)
        decision = authorize_peer_news("search_internal_peer_news_tool")

    assert decision.allowed is False
    assert decision.reason == "target_news_required"


def test_blocked_result_preserves_internal_content():
    with research_guard():
        decision = authorize_research_source("search_news_tool")
        result = blocked_tool_result(decision)

    content, artifacts = result.as_content_and_artifact()
    assert content
    assert artifacts[0]["content"] == content
    assert artifacts[0]["visibility"] == "internal"
    assert artifacts[0]["outcome"] == "blocked"


def test_record_internal_news_last_write_wins():
    with research_guard():
        record_internal_news_result(found=True)
        record_internal_news_result(found=False)  # a second, different call overwrites the first
        decision = authorize_peer_news("search_internal_peer_news_tool")

    assert decision.allowed is False
    assert decision.reason == "target_news_required"


def test_authorize_research_source_idempotent_after_allow():
    with research_guard():
        record_internal_news_result(found=True)
        first = authorize_research_source("search_news_tool")
        second = authorize_research_source("search_news_tool")

    assert first.allowed is True
    assert second.allowed is True
