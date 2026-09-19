"""
One-off migration: re-embed ticker_news (title+snippet) and feeds (name+description)
with the corrected format_news_content/format_feed_content formulas, refresh common-type
feeds' feed_description snapshot from their linked template, then reset every downstream
classification so the next ingestion run recomputes custom_feed_items/common_feed_items/insights
against the corrected embeddings instead of leaving stale matches in place.

Safe to re-run. Not wired into the app - run manually once:
    python -m scripts.backfill_embeddings_and_recascade
"""

from db.queries import (
    get_client,
    delete_feed_items,
    reset_feed_watermarks,
)
from tools.embeddings import embed, embed_batch
from agent.shared.news_text import format_news_content, format_feed_content
from agent.pipelines.orchestrator import run_ingestion_for_all_watchlisted_tickers


def reembed_ticker_news():
    client = get_client()
    rows = client.table("ticker_news").select("id, title, snippet").execute().data
    if not rows:
        print("ticker_news: nothing to re-embed")
        return
    texts = [format_news_content(r["title"], r.get("snippet")) for r in rows]
    embeddings = embed_batch(texts)
    for row, embedding in zip(rows, embeddings):
        client.table("ticker_news").update({"content_embedding": embedding}).eq("id", row["id"]).execute()
    print(f"ticker_news: re-embedded {len(rows)} rows")


def refresh_and_reembed_feeds():
    client = get_client()
    feeds = client.table("feeds").select("*").execute().data
    templates = {t["id"]: t for t in client.table("common_feed_templates").select("*").execute().data}

    for feed in feeds:
        feed_description = feed["feed_description"]
        if feed["feed_type"] == "common":
            template = templates.get(feed["common_feed_template_id"])
            if template:
                feed_description = template["description"]

        embedding = embed(format_feed_content(feed["feed_name"], feed_description))
        client.table("feeds").update(
            {"feed_description": feed_description, "description_embedding": embedding}
        ).eq("id", feed["id"]).execute()

    print(f"feeds: refreshed description + re-embedded {len(feeds)} rows")
    return [f["id"] for f in feeds]


def reset_classification_state(feed_ids: list[str]):
    client = get_client()
    client.table("common_feed_items").delete().neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    client.table("ticker_news").update({"common_classified_at": None}).neq(
        "id", "00000000-0000-0000-0000-000000000000"
    ).execute()
    delete_feed_items(feed_ids)
    reset_feed_watermarks(feed_ids)
    print("reset: cleared common_feed_items, custom_feed_items, and every watermark")


if __name__ == "__main__":
    reembed_ticker_news()
    feed_ids = refresh_and_reembed_feeds()
    reset_classification_state(feed_ids)
    print("Re-running ingestion pipeline to recompute matches under corrected embeddings...")
    result = run_ingestion_for_all_watchlisted_tickers()
    print(result)
