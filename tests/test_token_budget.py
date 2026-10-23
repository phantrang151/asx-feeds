"""Pure-logic tests for the token-budget callbacks - no network/DB, no live LLM call.
Simulates on_llm_end the same way LangChain's callback manager would call it."""

import pytest
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, Generation, LLMResult

from agent.guardrails.token_budget import (
    TokenBudgetCallback,
    TokenBudgetExceededError,
    DailyTokenBudgetCallback,
    DailyTokenBudgetExceededError,
    total_tokens_from,
)


def _FakeResponse(total_tokens: int) -> LLMResult:
    """A real LLMResult in the shape ChatAnthropic returns: token usage on the message's
    usage_metadata (LangChain's provider-neutral field). The previous fake only carried the
    Groq-style llm_output["token_usage"], which Claude never sends - so these tests kept
    passing while real Claude calls were counted as 0."""
    msg = AIMessage(content="x", usage_metadata={
        "input_tokens": total_tokens, "output_tokens": 0, "total_tokens": total_tokens})
    return LLMResult(generations=[[ChatGeneration(message=msg)]])


def _GroqStyleResponse(total_tokens: int) -> LLMResult:
    """Older provider shape: no usage_metadata, tokens only in llm_output["token_usage"]."""
    return LLMResult(generations=[[Generation(text="x")]],
                     llm_output={"token_usage": {"total_tokens": total_tokens}})


def test_total_tokens_from_reads_claude_usage_metadata():
    assert total_tokens_from(_FakeResponse(14)) == 14


def test_total_tokens_from_falls_back_to_groq_style_llm_output():
    assert total_tokens_from(_GroqStyleResponse(7)) == 7


def test_total_tokens_from_returns_0_and_warns_when_usage_missing(caplog):
    no_usage = LLMResult(generations=[[Generation(text="x")]], llm_output=None)
    with caplog.at_level("WARNING", logger="agent.guardrails.token_budget"):
        assert total_tokens_from(no_usage) == 0
    assert "total_tokens" in caplog.text


def test_token_budget_callback_accumulates_across_calls():
    cb = TokenBudgetCallback(ceiling=1000)
    cb.on_llm_end(_FakeResponse(400))
    cb.on_llm_end(_FakeResponse(400))
    assert cb.total_tokens == 800


def test_token_budget_callback_raises_once_ceiling_crossed():
    cb = TokenBudgetCallback(ceiling=500)
    cb.on_llm_end(_FakeResponse(400))
    with pytest.raises(TokenBudgetExceededError):
        cb.on_llm_end(_FakeResponse(200))


def test_daily_token_budget_callback_raises_its_own_error_type():
    cb = DailyTokenBudgetCallback(ceiling=500)
    cb.on_llm_end(_FakeResponse(400))
    with pytest.raises(DailyTokenBudgetExceededError):
        cb.on_llm_end(_FakeResponse(200))


def test_daily_token_budget_error_is_not_a_token_budget_error():
    # Load-bearing: conduct_analysis_node's except clause specifically catches
    # TokenBudgetExceededError (the per-request ceiling) and turns it into a graceful
    # in-graph decline. DailyTokenBudgetExceededError must NOT be an instance of that
    # type, or a daily-budget trip inside conduct_analysis_node would be silently
    # swallowed there instead of propagating up to ask_endpoint's 429.
    assert not issubclass(DailyTokenBudgetExceededError, TokenBudgetExceededError)
    err = DailyTokenBudgetExceededError(600, 500)
    assert not isinstance(err, TokenBudgetExceededError)
