"""
One-off script for local testing with a single hardcoded user (no auth yet).
Run schema.sql against your Supabase project first.

Usage:
    python -m scripts.seed_single_user
"""

from datetime import datetime, timezone

from config import TEST_USER_ID
from tools.embeddings import embed
from db.queries import get_feeds_for_user, create_feed, get_feed_items
from agent.pipelines.news_ingestion_graph import news_fetch_and_cache_graph, feed_classification_graph
from agent.pipelines.insight_graph import insight_graph

TICKER = "TLS.AX"

# The five feeds from the original project idea: track whether Telstra's growth
# is coming from sustainable sources or from cost-cutting, alongside a scandal feed.
FEED_DEFINITIONS = [
    (
        "Revenue trend",
        "News and signals about whether Telstra's revenue is increasing or decreasing.",
    ),
    (
        "Profit trend",
        "News and signals about whether Telstra's profit is increasing or decreasing.",
    ),
    (
        "Stock price trend",
        "News and signals about Telstra's share price movement, up or down.",
    ),
    (
        "Growth drivers",
        "What is stimulating Telstra's growth - new products, layoffs, "
        "technology adoption, or other cost-cutting measures.",
    ),
    (
        "Scandal",
        "Controversies, outages, PR issues, or reputational damage affecting Telstra.",
    ),
]


def seed_feeds():
    existing = get_feeds_for_user(TEST_USER_ID, ticker=TICKER)
    existing_names = {f["feed_name"] for f in existing}

    for name, description in FEED_DEFINITIONS:
        if name in existing_names:
            print(f"Skipping '{name}' - already exists.")
            continue
        embedding = embed(description)
        create_feed(TEST_USER_ID, TICKER, name, description, embedding)
        print(f"Created feed '{name}'.")


def run_ingestion():
    fetch_result = news_fetch_and_cache_graph.invoke(
        {"ticker": TICKER, "articles_cached": 0, "common_classified_count": 0}
    )
    print(
        f"Cached {fetch_result['articles_cached']} articles, "
        f"classified {fetch_result['common_classified_count']} into common feeds."
    )

    run_cutoff = datetime.now(timezone.utc).isoformat()
    result = feed_classification_graph.invoke(
        {
            "user_id": TEST_USER_ID,
            "ticker": TICKER,
            "run_cutoff": run_cutoff,
            "classified_count": 0,
            "skipped_count": 0,
        }
    )
    print(f"Classified {result['classified_count']} articles, skipped {result['skipped_count']}.")


def run_insight_synthesis():
    result = insight_graph.invoke(
        {
            "user_id": TEST_USER_ID,
            "ticker": TICKER,
            "plan": [],
            "step_results": [],
            "insight_text": None,
            "based_on_feed_item_ids": [],
        }
    )
    print(f"\n=== Cross-feed insight for {TICKER} ===")
    print(result["insight_text"])


def print_feed_items():
    for feed in get_feeds_for_user(TEST_USER_ID, ticker=TICKER):
        items = get_feed_items(feed["id"])
        print(f"\n=== {feed['feed_name']} ({len(items)} items) ===")
        for item in items:
            print(f"- {item['content_summary']}")


if __name__ == "__main__":
    seed_feeds()
    run_ingestion()
    print_feed_items()
    run_insight_synthesis()
