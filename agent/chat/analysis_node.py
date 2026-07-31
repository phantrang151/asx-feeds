from functools import lru_cache

from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage
from langgraph.prebuilt import create_react_agent
from langgraph.types import Command
from langmem import create_manage_memory_tool, create_search_memory_tool

from config import MODEL, GROQ_API_KEY
from .prompts import ANALYSIS_PROMPT
from .persistence import get_store
from .analysis_memory import (
    get_procedural_instructions,
    get_episodic_examples,
    store_episodic_example,
    _namespace_ticker,
)
from agent.shared.synthesize import synthesize_insight
from tools.react_tools import (
    search_news_tool,
    get_latest_price_tool,
    get_financial_summary_tool,
    search_financial_reports_tool,
)

_llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY)
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
            get_financial_summary_tool,
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
    # ticker isn't part of the prebuilt react agent's own state schema (it only tracks
    # "messages"), so it's threaded through config instead - _build_prompt reads it back
    # out of config["configurable"] rather than state.
    sub_config = {**config, "configurable": {**config["configurable"], "ticker": ticker}}
    result = react_agent.invoke({"messages": state["messages"]}, config=sub_config)

    evidence = _extract_tool_evidence(result["messages"])
    insight = synthesize_insight(ticker, evidence)

    store_episodic_example(user_id, ticker, current_question, insight)

    # Semantic-memory tool calls (manage_memory/search_memory) are internal bookkeeping -
    # raw store keys/namespaces/scores the user has no way to independently check, unlike
    # a news article's link. They stay in `evidence` for synthesis (still useful context
    # for the model) but are filtered out of what's actually shown to the user.
    references = [e for e in evidence if e["source"] not in ("manage_memory", "search_memory")]

    return Command(
        update={"result": insight, "references": references, "messages": [AIMessage(content=insight)]}
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
