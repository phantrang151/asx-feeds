from datetime import datetime, timezone

from langchain_groq import ChatGroq
from langgraph.types import Command

from config import MODEL, GROQ_API_KEY
from tools.search import search_news
from tools.embeddings import embed_batch
from db.queries import (
    get_feeds_for_user,
    match_feed_for_embedding,
    match_common_feed_template_for_embedding,
    upsert_ticker_news,
    get_unclassified_ticker_news,
    mark_ticker_news_common_classified,
    get_ticker_news_since,
    bulk_update_feed_last_classified_at,
    insert_feed_item,
    insert_common_feed_item,
    delete_feed_items,
    reset_feed_watermarks,
    clear_feeds_needs_rematch,
)

from .schemas import FetchState, ClassifyState


def _parse_published_at(published) -> str | None:
    """tools/search.py's `published` field is either an ISO pubDate string or a Unix
    providerPublishTime number, depending on which yfinance response shape came back."""
    if not published:
        return None
    if isinstance(published, (int, float)):
        return datetime.fromtimestamp(published, tz=timezone.utc).isoformat()
    return str(published)


def fetch_and_cache_news_node(state: FetchState):
    """Phase 1: pull this ticker's latest headlines ONCE - not once per user watching
    it - and cache them in ticker_news, embedding every title in a single batch call."""
    ticker = state["ticker"]
    articles = [a for a in search_news(ticker) if a.get("title")]

    embeddings = embed_batch([a["title"] for a in articles]) if articles else []

    rows = [
        {
            "ticker": ticker,
            "title": article["title"],
            "publisher": article.get("publisher"),
            "source_url": article.get("link"),
            "published_at": _parse_published_at(article.get("published")),
            "content_embedding": embedding,
        }
        for article, embedding in zip(articles, embeddings)
    ]

    upsert_ticker_news(rows)
    return Command(update={"articles_cached": len(rows)})


def classify_common_feeds_node(state: FetchState):
    """Phase 1.5: match this ticker's not-yet-evaluated cached news against the shared
    common feed templates (top-1, same pattern as custom-feed matching below) - runs
    once per ticker regardless of how many users have a common feed on it."""
    ticker = state["ticker"]
    articles = get_unclassified_ticker_news(ticker)

    common_classified = 0
    for article in articles:
        matches = match_common_feed_template_for_embedding(article["content_embedding"], match_count=1)
        if matches and matches[0]["similarity"] >= matches[0]["match_threshold"]:
            best = matches[0]
            summary = _summarize_for_feed(article, best["name"], best["description"])
            insert_common_feed_item(
                common_feed_template_id=best["id"],
                ticker=ticker,
                content_summary=summary,
                source_url=article.get("source_url"),
                content_embedding=article["content_embedding"],
            )
            common_classified += 1

    run_cutoff = datetime.now(timezone.utc).isoformat()
    mark_ticker_news_common_classified([a["id"] for a in articles], run_cutoff)
    return Command(update={"common_classified_count": common_classified})


def classify_and_store_node(state: ClassifyState):
    """
    Phase 2: for this user's CUSTOM feeds on this ticker, classify the ticker_news cached
    since each feed was last classified (or its full cached history, on a feed's first
    run - a brand-new feed on a long-tracked ticker still needs to see everything).
    Common feeds are handled entirely by classify_common_feeds_node and never reach here.
    """
    user_id = state["user_id"]
    ticker = state["ticker"]
    run_cutoff = state["run_cutoff"]

    feeds = get_feeds_for_user(user_id, ticker)
    custom_feeds = [f for f in feeds if f["feed_type"] == "custom"]
    if not custom_feeds:
        return Command(update={"classified_count": 0, "skipped_count": 0})

    # A feed flagged by the user's "Refresh" action (after editing its description or
    # threshold) gets its existing feed_items wiped and its watermark treated as unset for
    # this run, so it re-matches its entire ticker_news history under its current
    # settings instead of only newly-cached articles.
    refreshing_ids = [f["id"] for f in custom_feeds if f.get("needs_rematch")]
    if refreshing_ids:
        delete_feed_items(refreshing_ids)
        reset_feed_watermarks(refreshing_ids)
        for f in custom_feeds:
            if f["id"] in refreshing_ids:
                f["last_classified_at"] = None

    # Broadest possible candidate window: the earliest watermark among this user's
    # custom feeds for this ticker, or full history if any of them has never been
    # classified. The per-article check below re-narrows this to each article's actual
    # best-matching feed's own watermark, so a newly added feed still gets full history
    # while an already-classified feed doesn't get re-shown articles it already saw.
    watermarks = [f.get("last_classified_at") for f in custom_feeds]
    since = None if any(w is None for w in watermarks) else min(watermarks)
    articles = get_ticker_news_since(ticker, since, run_cutoff)

    classified = 0
    skipped = 0

    for article in articles:
        matches = match_feed_for_embedding(user_id, ticker, article["content_embedding"], match_count=1)
        if not matches:
            skipped += 1
            continue

        best = matches[0]
        if best["similarity"] < best["match_threshold"]:
            skipped += 1
            continue

        feed_watermark = best.get("last_classified_at")
        if feed_watermark and article["created_at"] <= feed_watermark:
            # Already considered for this specific feed in an earlier run - it only
            # showed up in this run's candidate window because another of the user's
            # feeds on this ticker has an older (or null) watermark.
            skipped += 1
            continue

        summary = _summarize_for_feed(article, best["feed_name"], best["feed_description"])
        insert_feed_item(
            feed_id=best["id"],
            source_type="news",
            content_summary=summary,
            source_url=article.get("source_url"),
            content_embedding=article["content_embedding"],
        )
        classified += 1

    bulk_update_feed_last_classified_at([f["id"] for f in custom_feeds], run_cutoff)
    if refreshing_ids:
        clear_feeds_needs_rematch(refreshing_ids)
    return Command(update={"classified_count": classified, "skipped_count": skipped})


def _summarize_for_feed(article: dict, feed_name: str, feed_description: str) -> str:
    """One LLM call per matched article - only for items that already cleared the
    vector-similarity threshold, to keep token usage low."""
    llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY)
    prompt = (
        f"Feed: {feed_name} ({feed_description})\n"
        f"News title: {article.get('title')}\n"
        f"Publisher: {article.get('publisher')}\n\n"
        "In one sentence, explain why this news item is relevant to this feed."
    )
    response = llm.invoke(prompt)
    return response.content.strip()
