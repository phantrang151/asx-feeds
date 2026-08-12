from langchain_anthropic import ChatAnthropic
from langgraph.types import Command

from config import ANALYSIS_MODEL, ANTHROPIC_API_KEY
from db.queries import (
    get_feeds_for_user,
    get_feed_items,
    get_common_feed_items,
    insert_ticker_insight,
)
from agent.shared.synthesize import synthesize_insight

from .insight_schemas import Plan


def planner_node(state):
    """
    Plan-Execute: the plan is structurally fixed (review each of this user's feeds for this
    ticker), but which feeds exist and what order makes sense isn't hardcoded - the LLM
    produces the plan, which leaves room for a future re-plan step (e.g. skip an empty feed,
    add financial_records as an extra step) without changing the graph's shape.
    """
    feeds = get_feeds_for_user(state["user_id"], state["ticker"])
    feed_names = [f["feed_name"] for f in feeds]

    if not feed_names:
        return Command(goto="synthesize", update={"plan": [], "step_results": []})

    llm = ChatAnthropic(model=ANALYSIS_MODEL, api_key=ANTHROPIC_API_KEY)
    plan = llm.with_structured_output(Plan).invoke(
        f"Given these feeds for {state['ticker']}: {feed_names}, produce an ordered list "
        "using those same feed names, in the order they should be reviewed to build a "
        "cross-feed insight."
    )
    return Command(goto="execute_step", update={"plan": plan.steps, "step_results": []})


def execute_step_node(state):
    """Executes the next un-run step of the plan: pulls stored items for that feed.

    A 'common' feed's classified items live in common_feed_items (keyed by
    common_feed_template_id + ticker), not feed_items (keyed by feed_id) - see
    feeds.feed_type in schema.sql - so which table to read depends on the feed's type.
    Getting this wrong silently starves the insight of evidence for any ticker whose
    feeds are all common ones, which is common (a fresh ticker only gets the shared
    common feeds until a user adds a custom one).
    """
    step_index = len(state["step_results"])
    feed_name = state["plan"][step_index]

    feeds = get_feeds_for_user(state["user_id"], state["ticker"])
    feed = next((f for f in feeds if f["feed_name"] == feed_name), None)

    if not feed:
        items = []
    elif feed["feed_type"] == "common":
        items = get_common_feed_items(feed["common_feed_template_id"], state["ticker"])
    else:
        items = get_feed_items(feed["id"])

    new_results = state["step_results"] + [{"step": feed_name, "items": items}]
    next_node = "execute_step" if len(new_results) < len(state["plan"]) else "synthesize"

    return Command(goto=next_node, update={"step_results": new_results})


def synthesize_node(state):
    """Flattens every step's feed_items into evidence, then reuses the SAME
    synthesize_insight() function conduct_analysis (ReAct) uses - only the
    evidence-gathering differed between the two patterns."""
    evidence = []
    item_ids = []
    for step_result in state["step_results"]:
        for item in step_result["items"]:
            evidence.append({"source": step_result["step"], "content": item["content_summary"]})
            item_ids.append(item["id"])

    insight_text = synthesize_insight(state["ticker"], evidence)
    insert_ticker_insight(state["user_id"], state["ticker"], insight_text, item_ids)

    return Command(update={"insight_text": insight_text, "based_on_feed_item_ids": item_ids})
