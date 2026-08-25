from langgraph.graph import StateGraph, START, END

from .insight_schemas import InsightState
from .insight_nodes import planner_node, execute_step_node, synthesize_node

builder = StateGraph(InsightState)

builder.add_node("planner", planner_node)
builder.add_node("execute_step", execute_step_node)
builder.add_node("synthesize", synthesize_node)

builder.add_edge(START, "planner")
builder.add_edge("synthesize", END)
# planner and execute_step route dynamically via Command(goto=...) - see insight_nodes.py.

insight_graph = builder.compile()


def synthesize_insight_for(user_id: str, ticker: str) -> dict:
    """Runs the graph for one (user, ticker) pair, seeded with the same empty initial
    state every caller needs. The ingestion pipeline is the normal owner of classification
    and synthesis. The feeds API also calls it after deletion so the old GOD summary is
    replaced without the removed feed; feed creation waits for the next pipeline run."""
    return insight_graph.invoke(
        {
            "user_id": user_id,
            "ticker": ticker,
            "items_by_feed": {},
            "feed_embeddings": {},
            "source_decisions": {},
            "supplementary_items_by_feed": {},
            "plan": [],
            "step_results": [],
            "insight_text": None,
            "based_on_feed_item_ids": [],
        }
    )
