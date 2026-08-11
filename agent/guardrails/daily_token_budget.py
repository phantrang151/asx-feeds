from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from config import TOKEN_CEILING_PER_USER_PER_DAY, TOKEN_CEILING_WINDOW_HOURS
from db.queries import sum_recent_token_usage
from agent.guardrails.token_budget import DailyTokenBudgetCallback

DAILY_BUDGET_MESSAGE = (
    f"You've used your token budget for today - please try again later "
    f"(limit: {TOKEN_CEILING_PER_USER_PER_DAY} tokens per {TOKEN_CEILING_WINDOW_HOURS} hours)."
)


def enforce_daily_token_budget(user_id: str) -> DailyTokenBudgetCallback:
    """Raises HTTPException(429) if `user_id` has already used
    >= TOKEN_CEILING_PER_USER_PER_DAY tokens in the trailing TOKEN_CEILING_WINDOW_HOURS;
    otherwise returns a fresh DailyTokenBudgetCallback seeded with the REMAINING
    allowance (ceiling minus what's already used), not the full ceiling - attach it to
    every Groq call this request makes (router, conduct_analysis's ReAct loop +
    synthesis, advice-check judge) so it trips mid-request if this one request alone
    would push the user over the daily line.

    Same "runs before the graph is invoked -> real HTTP error" split as
    agent/guardrails/rate_limit.py::enforce_rate_limit: this covers the
    already-exhausted case up front. A mid-request trip instead raises
    DailyTokenBudgetExceededError, which app/main.py::ask_endpoint catches and turns
    into the identical 429 - the user sees the same error either way.

    DB-backed (llm_token_usage_log), same trailing-window style as enforce_rate_limit.
    Count(sum)-then-insert isn't atomic, so a concurrent burst from the same user could
    slightly exceed the limit - same acceptable-at-this-scale tradeoff enforce_rate_limit
    already makes.
    """
    since = (datetime.now(timezone.utc) - timedelta(hours=TOKEN_CEILING_WINDOW_HOURS)).isoformat()
    used_today = sum_recent_token_usage(user_id, since)
    if used_today >= TOKEN_CEILING_PER_USER_PER_DAY:
        raise HTTPException(status_code=429, detail=DAILY_BUDGET_MESSAGE)
    return DailyTokenBudgetCallback(TOKEN_CEILING_PER_USER_PER_DAY - used_today)
