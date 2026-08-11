import logging
from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.messages import AIMessage
from langgraph.errors import GraphRecursionError
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command
from langmem import create_manage_memory_tool, create_search_memory_tool

from config import ANALYSIS_MODEL, ANTHROPIC_API_KEY, REACT_RECURSION_LIMIT, TOKEN_CEILING_PER_REQUEST
from . import decline_messages
from .prompts import ANALYSIS_PROMPT
from .persistence import get_store
from .analysis_memory import (
    get_procedural_instructions,
    get_episodic_examples,
    store_episodic_example,
    _namespace_ticker,
)
from agent.guardrails.advice_check import check_advice_avoidance
from agent.guardrails.token_budget import TokenBudgetCallback, TokenBudgetExceededError
from agent.shared.synthesize import synthesize_insight
from tools.react_tools import (
    search_news_tool,
    get_latest_price_tool,
    search_financial_reports_tool,
)

logger = logging.getLogger(__name__)

_llm = ChatAnthropic(model=ANALYSIS_MODEL, api_key=ANTHROPIC_API_KEY)
_store = get_store()


def _build_prompt(state, config, store):
    """
    Rebuilt on every invocation - like the notebook's create_prompt - so the system prompt
    always reflects the CURRENT contents of procedural and episodic memory, not a snapshot
    taken when the agent was first created.
    """
    user_id = config["configurable"]["langgraph_user_id"]
    # The react_agent's own state only carries "messages" (see conduct_analysis_node's
    # invoke call below) - ticker is passed via config instead, not state, since it's
    # not part of the prebuilt react agent's state schema.
    ticker = config["configurable"]["ticker"]
    current_question = state["messages"][-1].content if state["messages"] else ""

    procedural = get_procedural_instructions(user_id)
    episodic = get_episodic_examples(user_id, ticker, current_question)

    system_content = (
        f"{ANALYSIS_PROMPT}\n\n"
        f"Ticker: {ticker}\n\n"
        f"< Procedural instructions (how you should reason) >\n{procedural}\n"
        f"</ Procedural instructions >\n\n"
        f"< Episodic examples (past analyses for this ticker) >\n{episodic}\n"
        f"</ Episodic examples >\n\n"
        "< Semantic memory >\n"
        "Use the manage_memory / search_memory tools to store or retrieve durable facts "
        "about this company as you reason (e.g. details about an outage or a strategic "
        "change you learn about while researching).\n"
        "</ Semantic memory >\n\n"
        "Prefer search_financial_reports_tool over general knowledge whenever the "
        "question could plausibly be answered by an admin-uploaded report - it searches "
        "actual uploaded documents for this ticker, not just news headlines."
    )
    return [{"role": "system", "content": system_content}] + state["messages"]


@lru_cache(maxsize=32)
def _make_react_agent(ticker: str):
    """
    Cached per ticker: semantic memory tools are scoped to a ticker-specific namespace,
    so each ticker gets its own agent instance rather than rebuilding one on every call.
    """
    semantic_namespace = ("semantic", _namespace_ticker(ticker))
    semantic_tools = [
        create_manage_memory_tool(namespace=semantic_namespace),
        create_search_memory_tool(namespace=semantic_namespace),
    ]
    return create_react_agent(
        _llm,
        tools=[
            search_news_tool,
            get_latest_price_tool,
            search_financial_reports_tool,
            *semantic_tools,
        ],
        prompt=_build_prompt,
        store=_store,
    )


def conduct_analysis_node(state, config):
    """
    ReAct + three memory types:
      - procedural: fixed reasoning rules, fetched by key
      - episodic: past Q -> insight pairs for this ticker, fetched by similarity search
      - semantic: durable company facts, read/written by the agent itself mid-loop via tools
    After the loop, the result is written back as a new episodic example, so the next
    similar question on this ticker benefits from this run.
    """
    ticker = state["ticker"]
    user_id = config["configurable"]["langgraph_user_id"]
    current_question = state["messages"][-1].content if state["messages"] else ""

    react_agent = _make_react_agent(ticker)
    # Fresh per request - never module-level/shared, or concurrent requests would
    # corrupt each other's cumulative token counts. Passed into both the ReAct loop
    # below AND synthesize_insight, so the ceiling covers the whole request.
    budget_cb = TokenBudgetCallback(TOKEN_CEILING_PER_REQUEST)
    # Per-user daily budget (see agent/guardrails/daily_token_budget.py) - one instance
    # per /api/ask request, shared with router_node via configurable (set in
    # app/main.py::ask_endpoint), attached here too so it also covers this node's calls.
    # Unlike budget_cb above, a trip here is NOT caught by the except clause below -
    # DailyTokenBudgetExceededError propagates up to ask_endpoint and becomes a 429.
    # .get(), not [...]: not set when this graph is invoked directly (see router_node's
    # matching comment) - falls back to only the per-request ceiling in that case.
    daily_cb = config["configurable"].get("daily_token_cb")
    # Same .get() reasoning as daily_cb - only set by app/main.py::ask_endpoint, absent
    # for eval/direct-invoke callers, which don't need step tracing.
    tracer = config["configurable"].get("tracer")
    react_callbacks = [c for c in (budget_cb, daily_cb, tracer) if c]
    # ticker isn't part of the prebuilt react agent's own state schema (it only tracks
    # "messages"), so it's threaded through config instead - _build_prompt reads it back
    # out of config["configurable"] rather than state.
    sub_config = {
        **config,
        "configurable": {**config["configurable"], "ticker": ticker},
        "recursion_limit": REACT_RECURSION_LIMIT,
        "callbacks": react_callbacks,
        # Labels every LLM call INSIDE the ReAct loop that isn't otherwise tagged
        # (its own reasoning turns between tool calls) - actual tool calls still get
        # their real tool name from RequestTracer.on_tool_start regardless of this.
        "metadata": {"step_name": "conduct_analysis_reasoning"},
    }

    try:
        result = react_agent.invoke({"messages": state["messages"]}, config=sub_config)
        evidence = _extract_tool_evidence(result["messages"])
        insight = synthesize_insight(ticker, evidence, callbacks=react_callbacks)
    except (GraphRecursionError, TokenBudgetExceededError) as e:
        # Cost/runaway-loop guardrails: no partial answer on abort - the react agent has
        # no checkpointer of its own between invoke calls, so there's nothing reliably
        # extractable to salvage, and half a synthesized insight is worse than none.
        message = (
            decline_messages.RECURSION_LIMIT_REACHED
            if isinstance(e, GraphRecursionError)
            else decline_messages.TOKEN_CEILING_REACHED
        )
        logger.warning("conduct_analysis aborted for %s: %s", ticker, e)
        return Command(
            update={
                "category": "declined",
                "result": message,
                "references": [],
                "evidence": [],
                "messages": [AIMessage(content=message)],
            }
        )

    # Semantic-memory tool calls (manage_memory/search_memory) are internal bookkeeping -
    # raw store keys/namespaces/scores the user has no way to independently check, unlike
    # a news article's link. They stay in `evidence` for synthesis (still useful context
    # for the model) but are filtered out of what's actually shown to the user.
    references = []
    seen = set()
    for e in evidence:
        if e["source"] in ("manage_memory", "search_memory"):
            continue
        # The ReAct loop can call the same retrieval tool more than once (e.g. two
        # different sub-queries against search_financial_reports_tool) and get back the
        # same chunk both times - dedupe so the user doesn't see the same bullet twice.
        key = (e["content"], e["url"])
        if key in seen:
            continue
        seen.add(key)
        references.append(e)

    # Compliance-critical output gate: run AFTER synthesis, BEFORE the insight is written
    # into episodic memory - a flagged insight must never become a future few-shot
    # example, or it poisons later retrieval for this ticker.
    passed, matched_keywords, reasoning = check_advice_avoidance(
        insight, callbacks=[daily_cb] if daily_cb else None, tracer=tracer,
    )
    if not passed:
        logger.warning(
            "conduct_analysis advice-avoidance check failed for %s: keywords=%s reasoning=%s",
            ticker, matched_keywords, reasoning,
        )
        return Command(
            update={
                "category": "declined",
                "result": decline_messages.ADVICE_LANGUAGE_DETECTED,
                "references": [],
                "evidence": evidence,
                "evidence_count": len(evidence),
                "output_guardrail_regex_matched": bool(matched_keywords),
                # None (not False) when matched_keywords is non-empty - the LLM layer
                # is never reached once the regex layer alone fails (see
                # check_advice_avoidance's fail-fast), so "did the LLM call it advice"
                # is genuinely unknown in that case, not "no".
                "output_guardrail_llm_is_advice": True if not matched_keywords else None,
                "messages": [AIMessage(content=decline_messages.ADVICE_LANGUAGE_DETECTED)],
            }
        )

    store_episodic_example(user_id, ticker, current_question, insight)

    return Command(
        update={
            "result": insight,
            "references": references,
            "evidence": evidence,
            "evidence_count": len(evidence),
            "output_guardrail_regex_matched": False,
            "output_guardrail_llm_is_advice": False,
            "messages": [AIMessage(content=insight)],
        }
    )


def _extract_tool_evidence(messages) -> list[dict]:
    """
    One entry per piece of evidence a tool call actually returned - used both as input to
    synthesize_insight and (after filtering out internal-memory tool calls, see above) as
    the user-facing reference list. Tools that return multiple citable items (news
    articles, report chunks) attach their own list of {"content", "url"} dicts as an
    artifact (see tools/react_tools.py) so each becomes its own entry; other tools only
    return plain text, so those become one entry with no URL.
    """
    evidence = []
    for msg in messages:
        if getattr(msg, "type", None) != "tool":
            continue
        items = getattr(msg, "artifact", None)
        if items:
            for item in items:
                evidence.append({"source": msg.name, "content": item["content"], "url": item.get("url")})
        else:
            evidence.append({"source": msg.name, "content": msg.content, "url": None})
    return evidence
