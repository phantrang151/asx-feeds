from langgraph.graph import StateGraph, START, END

from .insight_schemas import InsightState
from .insight_nodes import planner_node, execute_step_node, synthesize_node

builder = StateGraph(InsightState)

builder.add_node("planner", planner_node)
builder.add_node("execute_step", execute_step_node)
builder.add_node("synthesize", synthesize_node)

builder.add_edge(START, "planner")
builder.add_edge("synthesize", END)
# planner and execute_step route dynamically via Command(goto=...) - see insight_nodes.py

insight_graph = builder.compile()
