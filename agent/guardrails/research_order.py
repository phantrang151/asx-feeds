from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Iterator

from .contracts import GuardrailDecision, ToolResult


@dataclass
class ResearchOrderGuard:
    """Tracks research-source ordering for one interactive analysis request."""

    internal_news_called: bool = False
    target_news_found: bool = False

    def authorize(self, source_name: str) -> GuardrailDecision:
        if not self.internal_news_called:
            return GuardrailDecision(
                allowed=False,
                reason="internal_news_required",
                metadata={"source": source_name},
            )
        return GuardrailDecision(allowed=True)

    def record_internal_news(self, found: bool) -> None:
        self.internal_news_called = True
        self.target_news_found = found

    def authorize_peer_news(self, source_name: str) -> GuardrailDecision:
        decision = self.authorize(source_name)
        if not decision.allowed:
            return decision
        if not self.target_news_found:
            return GuardrailDecision(
                allowed=False,
                reason="target_news_required",
                metadata={"source": source_name},
            )
        return GuardrailDecision(allowed=True)


_current_guard: ContextVar[ResearchOrderGuard | None] = ContextVar(
    "research_order_guard", default=None
)


@contextmanager
def research_guard() -> Iterator[ResearchOrderGuard]:
    """Scope research ordering to one request without sharing state across users."""
    guard = ResearchOrderGuard()
    token = _current_guard.set(guard)
    try:
        yield guard
    finally:
        _current_guard.reset(token)


def authorize_research_source(source_name: str) -> GuardrailDecision:
    guard = _current_guard.get()
    return guard.authorize(source_name) if guard else GuardrailDecision(allowed=True)


def authorize_peer_news(source_name: str) -> GuardrailDecision:
    guard = _current_guard.get()
    return guard.authorize_peer_news(source_name) if guard else GuardrailDecision(allowed=True)


def record_internal_news_result(found: bool) -> None:
    guard = _current_guard.get()
    if guard:
        guard.record_internal_news(found)


def blocked_tool_result(decision: GuardrailDecision) -> ToolResult:
    messages = {
        "internal_news_required": (
            "{source} is blocked until search_internal_news_tool has been called first. "
            "Call search_internal_news_tool for the target ticker before using another research source."
        ),
        "target_news_required": (
            "Peer news is blocked because no relevant target-company news was found."
        ),
    }
    source = decision.metadata.get("source", "This research source")
    template = messages.get(decision.reason, "This research source is blocked.")
    content = template.format(source=source)
    return ToolResult(
        content=content,
        artifacts=[{"content": content, "visibility": "internal", "outcome": "blocked"}],
        outcome="blocked",
        metadata={"reason": decision.reason, "source": source},
    )
