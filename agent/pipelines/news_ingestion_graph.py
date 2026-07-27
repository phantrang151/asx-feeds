from langgraph.graph import StateGraph, START, END

from .schemas import PipelineState
from .nodes import fetch_news_node, classify_and_store_node

builder = StateGraph(PipelineState)

builder.add_node("fetch_news", fetch_news_node)
builder.add_node("classify_and_store", classify_and_store_node)

builder.add_edge(START, "fetch_news")
builder.add_edge("fetch_news", "classify_and_store")
builder.add_edge("classify_and_store", END)

news_ingestion_graph = builder.compile()
