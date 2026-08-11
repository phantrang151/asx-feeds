from langchain_core.callbacks.base import BaseCallbackHandler


class TokenBudgetExceededError(RuntimeError):
    """Raised mid-request once cumulative token usage crosses the configured ceiling.
    Not a Groq/network error - deliberately its own type so conduct_analysis_node can
    catch it specifically and return a graceful decline instead of a 500."""

    def __init__(self, total_tokens: int, ceiling: int):
        self.total_tokens = total_tokens
        self.ceiling = ceiling
        super().__init__(f"Token budget exceeded: {total_tokens} > {ceiling}")


class TokenBudgetCallback(BaseCallbackHandler):
    """Accumulates token usage across every Groq call it's attached to and raises
    `exception_cls` once the running total crosses `ceiling`. Must be a FRESH instance
    per request (never module-level/shared), or concurrent requests would corrupt each
    other's counts.

    raise_error=True is required: langchain_core's callback manager only re-raises a
    handler's exception if the handler instance sets this - by default (False) it just
    logs a warning and swallows it, which would make this a no-op (confirmed by reading
    langchain_core/callbacks/manager.py and testing live).
    """

    raise_error = True
    exception_cls = TokenBudgetExceededError

    def __init__(self, ceiling: int):
        self.ceiling = ceiling
        self.total_tokens = 0

    def on_llm_end(self, response, **kwargs) -> None:
        usage = (response.llm_output or {}).get("token_usage") or {}
        self.total_tokens += usage.get("total_tokens", 0)
        if self.total_tokens > self.ceiling:
            raise self.exception_cls(self.total_tokens, self.ceiling)


class DailyTokenBudgetExceededError(RuntimeError):
    """Raised once a user's cumulative token usage for the trailing day crosses
    config.TOKEN_CEILING_PER_USER_PER_DAY. Deliberately NOT a TokenBudgetExceededError
    subclass: conduct_analysis_node's except clause specifically catches the per-request
    error and turns it into a graceful in-graph decline - this one is meant to propagate
    all the way up to app/main.py::ask_endpoint uncaught by that clause, and become a
    429, the same as agent/guardrails/daily_token_budget.py's pre-request gate."""

    def __init__(self, total_tokens: int, ceiling: int):
        self.total_tokens = total_tokens
        self.ceiling = ceiling
        super().__init__(f"Daily token budget exceeded: {total_tokens} > {ceiling}")


class DailyTokenBudgetCallback(TokenBudgetCallback):
    """Same accumulate-and-raise mechanics as TokenBudgetCallback, but for the
    per-user-per-day ceiling: one instance is created per /api/ask request (seeded with
    the user's REMAINING allowance, not the full ceiling - see
    agent/guardrails/daily_token_budget.py) and shared across every Groq call that
    request makes - router classification, conduct_analysis's ReAct loop + synthesis,
    and the advice-avoidance judge call - unlike TokenBudgetCallback above, which only
    covers conduct_analysis's own ReAct loop + synthesis."""

    exception_cls = DailyTokenBudgetExceededError
