from .advice_check import check_advice_avoidance, keyword_scan_advice_seeking
from .contracts import GuardrailDecision, ToolResult
from .research_order import (
    authorize_peer_news,
    authorize_research_source,
    blocked_tool_result,
    record_internal_news_result,
    research_guard,
)
from .tickers import validate_ticker

__all__ = [
    "GuardrailDecision",
    "ToolResult",
    "authorize_peer_news",
    "authorize_research_source",
    "blocked_tool_result",
    "check_output",
    "keyword_scan_advice_seeking",
    "record_internal_news_result",
    "research_guard",
    "validate_ticker",
]


def check_output(text: str, callbacks=None, tracer=None):
    """Public output-safety entry point shared by chat and pipeline callers."""
    return check_advice_avoidance(text, callbacks=callbacks, tracer=tracer)
