"""Pure-logic tests for the token-budget callbacks - no network/DB, no live LLM call.
Simulates on_llm_end the same way LangChain's callback manager would call it."""

import pytest

from agent.guardrails.token_budget import (
    TokenBudgetCallback,
    TokenBudgetExceededError,
    DailyTokenBudgetCallback,
    DailyTokenBudgetExceededError,
)


class _FakeResponse:
    def __init__(self, total_tokens: int):
        self.llm_output = {"token_usage": {"total_tokens": total_tokens}}


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
