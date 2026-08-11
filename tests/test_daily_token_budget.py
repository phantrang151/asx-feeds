"""Pure-logic tests for enforce_daily_token_budget - db.queries.sum_recent_token_usage
is mocked, no real network/DB calls."""

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from agent.guardrails.daily_token_budget import enforce_daily_token_budget
from agent.guardrails.token_budget import DailyTokenBudgetCallback
from config import TOKEN_CEILING_PER_USER_PER_DAY


def test_raises_429_when_already_at_ceiling():
    with patch(
        "agent.guardrails.daily_token_budget.sum_recent_token_usage",
        return_value=TOKEN_CEILING_PER_USER_PER_DAY,
    ):
        with pytest.raises(HTTPException) as exc_info:
            enforce_daily_token_budget("user-1")
        assert exc_info.value.status_code == 429


def test_raises_429_when_over_ceiling():
    with patch(
        "agent.guardrails.daily_token_budget.sum_recent_token_usage",
        return_value=TOKEN_CEILING_PER_USER_PER_DAY + 1,
    ):
        with pytest.raises(HTTPException):
            enforce_daily_token_budget("user-1")


def test_returns_callback_seeded_with_remaining_allowance_when_under_ceiling():
    used_already = 50_000
    with patch(
        "agent.guardrails.daily_token_budget.sum_recent_token_usage",
        return_value=used_already,
    ):
        cb = enforce_daily_token_budget("user-1")
    assert isinstance(cb, DailyTokenBudgetCallback)
    assert cb.ceiling == TOKEN_CEILING_PER_USER_PER_DAY - used_already
    assert cb.total_tokens == 0


def test_returns_full_ceiling_when_nothing_used_yet():
    with patch("agent.guardrails.daily_token_budget.sum_recent_token_usage", return_value=0):
        cb = enforce_daily_token_budget("user-1")
    assert cb.ceiling == TOKEN_CEILING_PER_USER_PER_DAY
