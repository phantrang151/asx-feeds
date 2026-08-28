"""I1 (docs/test_case_catalog.md): classify_and_store's idempotency under a crash
mid-run - the audit's top finding, traced through the exact write order.
classify_and_store inserts matched articles in a loop, then advances the
last_classified_at watermark in ONE bulk call AFTER the whole loop finishes - so a crash
between those two steps leaves the watermark un-advanced, and a retry re-fetches and
re-inserts the same already-classified articles as duplicates (feed_items has no unique
constraint to stop it)."""

from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from db.queries import create_feed, upsert_ticker_news, get_custom_feed_items, delete_feed
from agent.pipelines.ingestion_steps import classify_and_store


def _seed_feed_and_news(test_user_id, test_ticker, embedding, n_articles=3):
    feed = create_feed(
        user_id=test_user_id,
        ticker=test_ticker,
        feed_name="Integration test feed",
        feed_description="Test feed for classify_and_store integration tests",
        description_embedding=embedding,
    )
    upsert_ticker_news([
        {
            "ticker": test_ticker,
            "title": f"Article {i}",
            "publisher": "Test Publisher",
            "source_url": f"https://example.com/{test_ticker}/{i}",
            "published_at": datetime.now(timezone.utc).isoformat(),
            "content_embedding": embedding,
        }
        for i in range(n_articles)
    ])
    return feed


@pytest.mark.xfail(
    strict=True,
    reason=(
        "Confirmed audit finding: classify_and_store's watermark only advances after "
        "the FULL insert loop finishes (one bulk call), so a crash between the loop "
        "finishing and that call lands causes a retry to duplicate feed_items - "
        "feed_items has no unique constraint to stop it. Remove this marker once the "
        "watermark-per-article fix lands (this test will then genuinely pass)."
    ),
)
def test_crash_before_watermark_update_causes_duplicate_feed_items(
    test_user_id, test_ticker, embedding, cleanup_ticker
):
    feed = _seed_feed_and_news(test_user_id, test_ticker, embedding, n_articles=3)
    try:
        run_cutoff = datetime.now(timezone.utc).isoformat()

        # The first "run" crashes exactly where the real bug crashes: after every
        # insert_feed_item call has already succeeded, but before the watermark's bulk
        # update lands. Patching bulk_update_feed_last_classified_at to raise simulates
        # a process crash at that precise point.
        with patch(
            "agent.pipelines.ingestion_steps.bulk_update_feed_last_classified_at",
            side_effect=RuntimeError("simulated crash before watermark update"),
        ):
            with pytest.raises(RuntimeError):
                classify_and_store(test_user_id, test_ticker, run_cutoff)

        items_after_crash = get_custom_feed_items(feed["id"])
        assert len(items_after_crash) == 3  # the inserts DID happen before the crash

        # Retry, exactly as a real re-run would - the watermark was never advanced.
        classify_and_store(test_user_id, test_ticker, datetime.now(timezone.utc).isoformat())
        items_after_retry = get_custom_feed_items(feed["id"])

        assert len(items_after_retry) == 3, (
            f"feed_items grew to {len(items_after_retry)} after retrying a crashed run - "
            "the same 3 articles were re-classified and re-inserted as duplicates."
        )
    finally:
        delete_feed(feed["id"], test_user_id)


def test_normal_completed_run_is_idempotent_on_rerun(test_user_id, test_ticker, embedding, cleanup_ticker):
    """Control case: when a run completes NORMALLY (no crash), the watermark does
    advance, so a second call with no new news correctly classifies nothing new. This
    passes today - it's what proves the bug above is specifically about the crash
    window, not classify_and_store being broken in general."""
    feed = _seed_feed_and_news(test_user_id, test_ticker, embedding, n_articles=3)
    try:
        run_cutoff = datetime.now(timezone.utc).isoformat()
        classified_count, _ = classify_and_store(test_user_id, test_ticker, run_cutoff)
        assert classified_count == 3
        assert len(get_custom_feed_items(feed["id"])) == 3

        classify_and_store(test_user_id, test_ticker, datetime.now(timezone.utc).isoformat())
        assert len(get_custom_feed_items(feed["id"])) == 3
    finally:
        delete_feed(feed["id"], test_user_id)
