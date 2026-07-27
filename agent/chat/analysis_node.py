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
)
from agent.shared.synthesize import synthesize_insight
from tools.react_tools import search_news_tool, get_latest_price_tool, get_financial_summary_tool

_llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY)
_store = get_store()


def _build_prompt(state, config, store):
    """
    Rebuilt on every invocation - like the notebook's create_prompt - so the system prompt
    always reflects the CURRENT contents of procedural and episodic memory, not a snapshot
    taken when the agent was first created.
    """
    user_id = config["configurable"]["langgraph_user_id"]
    ticker = state["ticker"]
    current_question = state["messages"][-1].content if state["messages"] else ""

    procedural = get_procedural_instructions(user_id)
    episodic = get_episodic_examples(user_id, ticker, current_question)

    system_content = (
        f"{ANALYSIS_PROMPT}\n\n"
        f"< Procedural instructions (how you should reason) >\n{procedural}\n"
        f"</ Procedural instructions >\n\n"
        f"< Episodic examples (past analyses for this ticker) >\n{episodic}\n"
        f"</ Episodic examples >\n\n"
        "< Semantic memory >\n"
        "Use the manage_memory / search_memory tools to store or retrieve durable facts "
        "about this company as you reason (e.g. details about an outage or a strategic "
        "change you learn about while researching).\n"
        "</ Semantic memory >"
    )
    return [{"role": "system", "content": system_content}] + state["messages"]


@lru_cache(maxsize=32)
def _make_react_agent(ticker: str):
    """
    Cached per ticker: semantic memory tools are scoped to a ticker-specific namespace,
    so each ticker gets its own agent instance rather than rebuilding one on every call.
    """
    semantic_namespace = ("semantic", ticker)
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
    result = react_agent.invoke({"messages": state["messages"]}, config=config)

    evidence = _extract_tool_evidence(result["messages"])
    insight = synthesize_insight(ticker, evidence)

    store_episodic_example(user_id, ticker, current_question, insight)

    return Command(
        update={"result": insight, "messages": [AIMessage(content=insight)]}
    )


def _extract_tool_evidence(messages) -> list[dict]:
    evidence = []
    for msg in messages:
        if getattr(msg, "type", None) == "tool":
            evidence.append({"source": msg.name, "content": msg.content})
    return evidence
