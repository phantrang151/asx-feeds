from langgraph.graph import StateGraph, START, END

from .schemas import State
from .nodes import router_node, search_news_node
from .analysis_node import conduct_analysis_node
from .persistence import get_store, get_checkpointer

builder = StateGraph(State)

builder.add_node("router", router_node)
builder.add_edge(START, "router")
builder.add_node("search_news", search_news_node)
builder.add_edge("search_news", END)
builder.add_node("conduct_analysis", conduct_analysis_node)
builder.add_edge("conduct_analysis", END)

graph = builder.compile(checkpointer=get_checkpointer(), store=get_store())
