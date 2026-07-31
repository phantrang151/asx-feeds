from langgraph.graph import StateGraph, START, END

from .schemas import FetchState, ClassifyState
from .nodes import fetch_and_cache_news_node, classify_common_feeds_node, classify_and_store_node

# Ticker-scoped: fetches + caches a ticker's news once, then classifies it against the
# shared common feed templates once - both phases run once per distinct watchlisted
# ticker per pipeline run, never once per user.
fetch_builder = StateGraph(FetchState)
fetch_builder.add_node("fetch_and_cache_news", fetch_and_cache_news_node)
fetch_builder.add_node("classify_common_feeds", classify_common_feeds_node)
fetch_builder.add_edge(START, "fetch_and_cache_news")
fetch_builder.add_edge("fetch_and_cache_news", "classify_common_feeds")
fetch_builder.add_edge("classify_common_feeds", END)
news_fetch_and_cache_graph = fetch_builder.compile()

# (user, ticker)-scoped: classifies one user's CUSTOM feeds against the ticker_news
# cache already populated by news_fetch_and_cache_graph - no yfinance calls here.
classify_builder = StateGraph(ClassifyState)
classify_builder.add_node("classify_and_store", classify_and_store_node)
classify_builder.add_edge(START, "classify_and_store")
classify_builder.add_edge("classify_and_store", END)
feed_classification_graph = classify_builder.compile()
