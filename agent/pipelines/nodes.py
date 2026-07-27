from langchain_groq import ChatGroq
from langgraph.types import Command

from config import MODEL, GROQ_API_KEY
from tools.search import search_news
from tools.embeddings import embed
from db.queries import match_feed_for_embedding, insert_feed_item

from .schemas import PipelineState


def fetch_news_node(state: PipelineState):
    """Pull the latest news headlines for this ticker."""
    ticker = state["ticker"]
    articles = search_news(ticker)
    return Command(update={"raw_articles": articles})


def classify_and_store_node(state: PipelineState):
    """
    For each article: embed the title, find the best-matching feed for this
    user + ticker via pgvector similarity, and if it clears that feed's
    match_threshold, write an LLM-generated summary into feed_items.
    Articles that don't clear any feed's threshold are skipped, not force-fit.
    """
    user_id = state["user_id"]
    ticker = state["ticker"]
    articles = state.get("raw_articles", [])

    classified = 0
    skipped = 0

    for article in articles:
        title = article.get("title", "")
        if not title:
            skipped += 1
            continue

        embedding = embed(title)
        matches = match_feed_for_embedding(user_id, ticker, embedding, match_count=1)

        if not matches:
            skipped += 1
            continue

        best = matches[0]
        if best["similarity"] < best["match_threshold"]:
            skipped += 1
            continue

        summary = _summarize_for_feed(article, best["feed_name"], best["feed_description"])

        insert_feed_item(
            feed_id=best["id"],
            source_type="news",
            content_summary=summary,
            source_url=article.get("link"),
            content_embedding=embedding,
        )
        classified += 1

    return Command(update={"classified_count": classified, "skipped_count": skipped})


def _summarize_for_feed(article: dict, feed_name: str, feed_description: str) -> str:
    """One LLM call per matched article - only for items that already cleared
    the vector-similarity threshold, to keep token usage low."""
    llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY)
    prompt = (
        f"Feed: {feed_name} ({feed_description})\n"
        f"News title: {article.get('title')}\n"
        f"Publisher: {article.get('publisher')}\n\n"
        "In one sentence, explain why this news item is relevant to this feed."
    )
    response = llm.invoke(prompt)
    return response.content.strip()
