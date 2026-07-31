from langchain_groq import ChatGroq
from langgraph.types import Command

from config import MODEL, GROQ_API_KEY
from db.queries import get_feeds_for_user, get_feed_items, insert_ticker_insight
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

    llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY)
    plan = llm.with_structured_output(Plan).invoke(
        f"Given these feeds for {state['ticker']}: {feed_names}, produce an ordered list "
        "using those same feed names, in the order they should be reviewed to build a "
        "cross-feed insight."
    )
    return Command(goto="execute_step", update={"plan": plan.steps, "step_results": []})


def execute_step_node(state):
    """Executes the next un-run step of the plan: pulls stored feed_items for that feed.

    Known gap: get_feed_items() only reads feed_items, so a feed_type='common' feed
    (see schema.sql) always contributes zero evidence here, since common-feed
    classifications live in common_feed_items instead. Not fixed yet because this graph
    is currently dormant (only invoked from scripts/seed_single_user.py, not wired to
    any FastAPI route) - fix by reading from the user_feed_items view instead of
    get_feed_items() directly once insight generation is actually wired up.
    """
    step_index = len(state["step_results"])
    feed_name = state["plan"][step_index]

    feeds = get_feeds_for_user(state["user_id"], state["ticker"])
    feed = next((f for f in feeds if f["feed_name"] == feed_name), None)
    items = get_feed_items(feed["id"]) if feed else []

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
