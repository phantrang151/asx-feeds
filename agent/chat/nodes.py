from typing import Optional

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command

from .schemas import State, Router
from .prompts import ROUTER_PROMPT
from . import decline_messages
from agent.guardrails.advice_check import keyword_scan_advice_seeking
from agent.guardrails.tickers import validate_ticker
from config import ROUTER_MODEL, ANTHROPIC_API_KEY
from tools.search import search_news


def _declined(ticker: Optional[str], message: str, **trace_fields) -> Command:
    """Shared shape for every router-level guardrail short-circuit - routes straight to
    END with a decline message instead of the LLM's chosen category, same
    messages/references/evidence contract every other terminal node returns so
    /api/ask's response shape and the frontend's AnswerBlock stay unaffected.
    `trace_fields` carries whichever guardrail-verdict State fields are already known
    at this particular decline site (see schemas.py) - request_trace reads them back
    from the final graph state in app/main.py::ask_endpoint."""
    return Command(
        goto=END,
        update={
            "ticker": ticker,
            "category": "declined",
            "result": message,
            "references": [],
            "evidence": [],
            "messages": [AIMessage(content=message)],
            **trace_fields,
        },
    )


def classify_request(messages: list, callbacks: Optional[list] = None) -> Router:
    """The router LLM call in isolation - what router_node below calls for the live
    gate, and what eval/score_guardrails.py calls directly to score the input
    guardrail's LLM layer (response.is_advice_seeking) against a labeled test set in
    isolation from the regex layer and ticker-validation gate. One implementation, not
    a live copy plus a separately-drifting eval copy - same reasoning as
    agent/guardrails/advice_check.py::check_advice_avoidance's own docstring.

    `callbacks`, if given, is tagged with metadata={"step_name": "router"} for
    RequestTracer (see agent/guardrails/tracer.py)."""
    llm = ChatAnthropic(model=ROUTER_MODEL, api_key=ANTHROPIC_API_KEY)
    llm_router = llm.with_structured_output(Router)
    config = {"callbacks": callbacks, "metadata": {"step_name": "router"}} if callbacks else None
    return llm_router.invoke([SystemMessage(content=ROUTER_PROMPT)] + messages, config=config)


def router_node(state: State, config):
    """Determine the category of the request and the ticker symbol."""
    human_message = state["messages"]
    tracer = config["configurable"].get("tracer")

    # Gate 1 (cheap, regex): catch obviously advice-seeking phrasing before spending an
    # LLM call at all. No ticker known yet at this point, so decline without one.
    question = human_message[-1].content if human_message else ""
    if tracer:
        with tracer.step("input_guardrail_regex", "guardrail"):
            regex_matches = keyword_scan_advice_seeking(question)
    else:
        regex_matches = keyword_scan_advice_seeking(question)
    if regex_matches:
        return _declined(None, decline_messages.ADVICE_SEEKING, input_guardrail_regex_matched=True)

    # Daily per-user token budget (see agent/guardrails/daily_token_budget.py) - shared
    # across every LLM call this whole /api/ask request makes, not just this one, so
    # it's threaded through configurable rather than built here. Raises
    # DailyTokenBudgetExceededError straight out of this node if it trips - deliberately
    # uncaught here, propagates to app/main.py::ask_endpoint, which turns it into a 429.
    # .get(), not [...]: eval/run_generation_eval.py and scripts/test_conduct_analysis.py
    # invoke this graph directly without setting it, same as they already intentionally
    # bypass the rate limiter and citation check - offline runs aren't a live user's
    # daily spend.
    daily_cb = config["configurable"].get("daily_token_cb")
    callbacks = [c for c in (daily_cb, tracer) if c]

    response = classify_request(human_message, callbacks=callbacks)

    # Gate 2 (ticker allowlist) and gate 3 (LLM's own is_advice_seeking judgment,
    # catching advice-seeking phrasing the regex gate above missed), checked before any
    # live tool call is made against the LLM's ticker guess: reject a ticker that
    # doesn't resolve against a real ASX-listed company, then decline anything asking
    # for a buy/sell/hold recommendation rather than an explanation - independent of
    # whichever category the LLM picked, since an advice-seeking question can get
    # routed to either search_news or conduct_analysis.
    if not validate_ticker(response.ticker):
        return _declined(
            response.ticker, decline_messages.TICKER_NOT_FOUND,
            input_guardrail_regex_matched=False, input_guardrail_llm_is_advice=response.is_advice_seeking,
        )
    if response.is_advice_seeking:
        return _declined(
            response.ticker, decline_messages.ADVICE_SEEKING,
            input_guardrail_regex_matched=False, input_guardrail_llm_is_advice=True,
        )

    return Command(
        goto=response.category,
        update={
            "ticker": response.ticker,
            "category": response.category,
            "input_guardrail_regex_matched": False,
            "input_guardrail_llm_is_advice": False,
        },
    )


def search_news_node(state: State, config):
    """Search for news based on the ticker symbol."""
    ticker = state["ticker"]
    tracer = config["configurable"].get("tracer")

    if tracer:
        with tracer.step("tool:search_news", "tool"):
            articles = search_news(ticker)
    else:
        articles = search_news(ticker)

    if not articles:
        answer = f"No recent news found for {ticker}."
        references = []
    else:
        answer = "\n".join(f"- {a['title']} ({a.get('publisher') or 'Unknown'})" for a in articles)
        references = [
            {
                "source": "search_news",
                "content": f"{a['title']} ({a.get('publisher') or 'Unknown'})",
                "url": a.get("link"),
            }
            for a in articles
        ]

    return Command(
        update={"result": answer, "references": references, "messages": [AIMessage(content=answer)]}
    )
