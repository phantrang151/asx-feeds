import re
from typing import Optional

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from config import JUDGE_MODEL, ANTHROPIC_API_KEY

# Cheap first layer: phrasing that directly tells the reader what to do with the stock.
# Deliberately narrow (recommendation verbs + buy/sell/hold/invest) rather than matching
# every mention of "buy"/"sell" (a synthesized insight legitimately says things like
# "the company sold its logistics arm" or "customers are buying more mobile plans" -
# those aren't advice and shouldn't trip this layer).
_ADVICE_PATTERNS = [
    r"\byou should (buy|sell|hold|avoid|invest)\b",
    r"\b(buy|sell|hold) (this|the) stock\b",
    r"\bnow is a good time to (buy|sell|invest)\b",
    r"\bi recommend (buying|selling|holding|investing)\b",
    r"\b(strong |a )?(buy|sell|hold) rating\b",
    r"\bgood (investment|time to buy|time to invest)\b",
]
_ADVICE_RE = re.compile("|".join(_ADVICE_PATTERNS), re.IGNORECASE)

# Input-side mirror of the layer above: catches a user directly ASKING for a
# recommendation (e.g. "should I buy TLS.AX") rather than the model GIVING one.
# Deliberately narrow to first-person trade questions and "good investment/time to
# buy" phrasing - matches router_node's own is_advice_seeking examples so the cheap
# regex gate and the LLM's judgment agree on the obvious cases. Questions about what
# happened or why (even mentioning price/valuation, e.g. "is TLS.AX overvalued")
# should NOT match; those aren't asking for a trade decision.
_ADVICE_SEEKING_PATTERNS = [
    r"\bshould i (buy|sell|hold|avoid|invest)\b",
    r"\bis (now|this|it) (a )?good time to (buy|sell|invest)\b",
    r"\bis\b.{0,60}\bgood investment\b",
    r"\b(worth|a good idea to) (buy|buying|sell|selling|invest|investing)\b",
]
_ADVICE_SEEKING_RE = re.compile("|".join(_ADVICE_SEEKING_PATTERNS), re.IGNORECASE)


class AdviceJudgment(BaseModel):
    is_advice: bool = Field(description="True if the text recommends or implies a buy/sell/hold decision.")
    reasoning: str = Field(description="One short sentence explaining the judgment.")


def keyword_scan(text: str) -> list[str]:
    """Cheap first layer: regex scan for buy/sell/hold-recommendation phrasing.
    Returns the matched substrings; empty list = clean."""
    return [m.group(0) for m in _ADVICE_RE.finditer(text)]


def keyword_scan_advice_seeking(text: str) -> list[str]:
    """Cheap first gate on the INPUT side: regex scan for a user directly asking for a
    buy/sell/hold recommendation. Returns the matched substrings; empty list = clean.
    Used by router_node to skip the router LLM call entirely on an obvious match -
    router_node's own is_advice_seeking flag (from the LLM's structured output) remains
    the second, broader gate for phrasing this regex misses."""
    return [m.group(0) for m in _ADVICE_SEEKING_RE.finditer(text)]


def llm_judge_advice_check(text: str, callbacks: Optional[list] = None) -> AdviceJudgment:
    """Stronger second layer, only reached if keyword_scan is clean - catches phrasing
    that implies a recommendation without using an obviously flagged phrase. Uses a
    different, stronger model (JUDGE_MODEL) than the one that generated `text`
    (ANALYSIS_MODEL), so it isn't grading its own homework. Constructed inside the
    function (not at import time) so this module stays importable/unit-testable without
    a live ANTHROPIC_API_KEY, matching agent/shared/synthesize.py's own style.

    `callbacks`, if given, is passed straight into this call's config, tagged with
    metadata={"step_name": "output_guardrail_llm"} - same pattern as
    agent/shared/synthesize.py's synthesize_insight, so conduct_analysis_node can attach
    the per-user daily token-budget callback and RequestTracer here too (see
    agent/guardrails/daily_token_budget.py, agent/guardrails/tracer.py)."""
    llm = ChatAnthropic(model=JUDGE_MODEL, api_key=ANTHROPIC_API_KEY)
    judge = llm.with_structured_output(AdviceJudgment)
    prompt = (
        "You are a compliance reviewer for a financial analysis tool. This tool is only "
        "allowed to explain what happened to a stock and why - it must never recommend "
        "buying, selling, or holding, and never state or imply whether now is a good or "
        "bad time to invest. Does the following text cross that line?\n\n"
        f"Text:\n{text}"
    )
    config = {"callbacks": callbacks, "metadata": {"step_name": "output_guardrail_llm"}} if callbacks else None
    return judge.invoke(prompt, config=config)


def check_advice_avoidance(text: str, callbacks: Optional[list] = None, tracer=None) -> tuple[bool, list[str], str]:
    """Runs both layers, fail-fast on the keyword layer to save an LLM call. Returns
    (passed, matched_keywords, reasoning) - `passed` is True only if the text is clean
    at both layers. Reused verbatim by both the live gate in conduct_analysis_node AND
    agent/eval/judge.py's advice-avoidance score - one implementation, not a live copy plus a
    separately-drifting eval copy.

    `callbacks` is forwarded to llm_judge_advice_check unchanged - agent/eval/judge.py never
    passes any, since eval runs are offline and outside any live request's token budget.
    `tracer`, if given (a RequestTracer - see agent/guardrails/tracer.py), times the
    regex layer directly (no LLM/tool event exists for it to hook) and is also added to
    `callbacks` so it captures the LLM layer's timing automatically - kept as a separate
    param rather than folded into `callbacks` so callers that only want token-budget
    tracking (not full step tracing) aren't forced to construct a tracer."""
    if tracer:
        with tracer.step("output_guardrail_regex", "guardrail"):
            matches = keyword_scan(text)
    else:
        matches = keyword_scan(text)
    if matches:
        return False, matches, "Matched a banned recommendation phrase."

    all_callbacks = [c for c in ((callbacks or []) + ([tracer] if tracer else [])) if c]
    judgment = llm_judge_advice_check(text, callbacks=all_callbacks or None)
    return not judgment.is_advice, [], judgment.reasoning
