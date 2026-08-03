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
    TokenBudgetExceededError once the running total crosses `ceiling`. Must be a FRESH
    instance per request (never module-level/shared), or concurrent requests would
    corrupt each other's counts.

    raise_error=True is required: langchain_core's callback manager only re-raises a
    handler's exception if the handler instance sets this - by default (False) it just
    logs a warning and swallows it, which would make this a no-op (confirmed by reading
    langchain_core/callbacks/manager.py and testing live).
    """

    raise_error = True

    def __init__(self, ceiling: int):
        self.ceiling = ceiling
        self.total_tokens = 0

    def on_llm_end(self, response, **kwargs) -> None:
        usage = (response.llm_output or {}).get("token_usage") or {}
        self.total_tokens += usage.get("total_tokens", 0)
        if self.total_tokens > self.ceiling:
            raise TokenBudgetExceededError(self.total_tokens, self.ceiling)
