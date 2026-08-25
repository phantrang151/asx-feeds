"""
One-off script for local testing with a single hardcoded user (no auth yet).
Run schema.sql against your Supabase project first.

Usage:
    python -m scripts.seed_single_user
"""

from datetime import datetime, timezone

from config import TEST_USER_ID
from tools.embeddings import embed
from db.queries import get_feeds_for_user, create_feed, get_custom_feed_items
from agent.pipelines.ingestion_steps import fetch_and_cache_news, classify_common_feeds, classify_and_store
from agent.pipelines.insight_graph import insight_graph

TICKER = "TLS.AX"

# The five feeds from the original project idea: track whether Telstra's growth
# is coming from sustainable sources or from cost-cutting, alongside a scandal feed.
FEED_DEFINITIONS = [
    (
        "Revenue trend",
        "News and signals about Telstra's revenue performance, growth drivers, and composition, "
        "including business segments, products, services, customers, geographic markets, pricing, "
        "volumes, acquisitions, and other factors affecting revenue.",
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
    articles_cached = fetch_and_cache_news(TICKER)
    common_classified_count = classify_common_feeds(TICKER)
    print(f"Cached {articles_cached} articles, classified {common_classified_count} into common feeds.")

    run_cutoff = datetime.now(timezone.utc).isoformat()
    classified_count, skipped_count = classify_and_store(TEST_USER_ID, TICKER, run_cutoff)
    print(f"Classified {classified_count} articles, skipped {skipped_count}.")


def run_insight_synthesis():
    result = insight_graph.invoke(
        {
            "user_id": TEST_USER_ID,
            "ticker": TICKER,
            "items_by_feed": {},
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
        items = get_custom_feed_items(feed["id"])
        print(f"\n=== {feed['feed_name']} ({len(items)} items) ===")
        for item in items:
            print(f"- {item['content_summary']}")


if __name__ == "__main__":
    seed_feeds()
    run_ingestion()
    print_feed_items()
    run_insight_synthesis()
