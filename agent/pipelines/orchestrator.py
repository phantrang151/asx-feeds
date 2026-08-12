from datetime import datetime, timezone

from db.queries import (
    get_all_watchlist_entries,
    get_distinct_watchlisted_tickers,
    get_ticker_insight_pairs,
    create_pipeline_run,
    update_pipeline_run,
)
from .news_ingestion_graph import news_fetch_and_cache_graph, feed_classification_graph
from .insight_graph import insight_graph


def run_ingestion_for_all_watchlisted_tickers() -> dict:
    """
    Four phases, in order. This is the single function both a scheduled cron job AND
    the admin 'trigger now' button call - one orchestrator, two triggers - so the logic
    for "what counts as a run" only lives in one place. Each ticker's/pair's failure is
    caught individually so one bad one doesn't take down the whole run.

      1. Fetch + cache each distinct watchlisted ticker's news ONCE - not once per user
         watching it.
      2. Classify each newly-cached article against the shared common feed templates,
         once per ticker, regardless of how many users have a common feed on it.
      3. Classify each user's CUSTOM feeds against the cache - the only phase that still
         loops per (user, ticker) pair, and the only one that calls an LLM per user.
      4. Re-synthesize insight_graph's cross-feed insight for each (user, ticker) pair
         that either saw new evidence this run (a new custom-feed item from phase 3, or
         a new common-feed item on that ticker from phase 2) or has never had an insight
         generated at all. That second condition is a one-time backfill for evidence
         that was already classified before this phase existed - without it, a pair
         with old feed_items but zero ticker_insights rows would wait forever for the
         "new evidence" condition to fire again. Once a pair has its first insight, it's
         only regenerated on genuine change, so repeat admin clicks don't burn one more
         LLM call per watchlisted ticker for nothing.

    run_cutoff is captured once, after phases 1-2 finish and before phase 3 starts, and
    used as both phase 3's read-bound and write-bound - so every article cached earlier
    in this same run is guaranteed to be visible to phase 3, and a feed's watermark
    always advances to a point no later than what it actually saw.

    Runs synchronously in the request/response cycle when called from the admin API -
    fine for a demo with a handful of tickers, but a real production version of this
    would run as a background job (a task queue, not a blocking HTTP request), since
    this can take a while once there are many tickers and each one involves LLM calls.
    """
    run_id = create_pipeline_run()

    tickers = get_distinct_watchlisted_tickers()
    entries = get_all_watchlist_entries()

    total_common_classified = 0
    total_classified = 0
    total_skipped = 0
    total_insights_generated = 0
    errors = []

    tickers_with_new_common_items = set()

    for ticker in tickers:
        try:
            result = news_fetch_and_cache_graph.invoke(
                {"ticker": ticker, "articles_cached": 0, "common_classified_count": 0}
            )
            total_common_classified += result["common_classified_count"]
            if result["common_classified_count"] > 0:
                tickers_with_new_common_items.add(ticker)
        except Exception as e:
            errors.append({"ticker": ticker, "phase": "fetch_and_cache", "error": str(e)})

    run_cutoff = datetime.now(timezone.utc).isoformat()

    existing_insight_pairs = {
        (row["user_id"], row["ticker"]) for row in get_ticker_insight_pairs()
    }
    entries_needing_insight = []

    for entry in entries:
        try:
            result = feed_classification_graph.invoke(
                {
                    "user_id": entry["user_id"],
                    "ticker": entry["ticker"],
                    "run_cutoff": run_cutoff,
                    "classified_count": 0,
                    "skipped_count": 0,
                }
            )
            total_classified += result["classified_count"]
            total_skipped += result["skipped_count"]
            pair = (entry["user_id"], entry["ticker"])
            if (
                result["classified_count"] > 0
                or entry["ticker"] in tickers_with_new_common_items
                or pair not in existing_insight_pairs
            ):
                entries_needing_insight.append(entry)
        except Exception as e:
            errors.append(
                {"user_id": entry["user_id"], "ticker": entry["ticker"], "phase": "classify", "error": str(e)}
            )

    for entry in entries_needing_insight:
        try:
            insight_graph.invoke(
                {
                    "user_id": entry["user_id"],
                    "ticker": entry["ticker"],
                    "plan": [],
                    "step_results": [],
                    "insight_text": None,
                    "based_on_feed_item_ids": [],
                }
            )
            total_insights_generated += 1
        except Exception as e:
            errors.append(
                {
                    "user_id": entry["user_id"],
                    "ticker": entry["ticker"],
                    "phase": "insight_synthesis",
                    "error": str(e),
                }
            )

    if not errors:
        status = "success"
    elif total_classified > 0 or total_common_classified > 0:
        status = "partial_failure"
    else:
        status = "failed"

    update_pipeline_run(
        run_id,
        status=status,
        tickers_processed=len(tickers),
        feeds_classified=total_classified,
        common_items_classified=total_common_classified,
        items_skipped=total_skipped,
        insights_generated=total_insights_generated,
        errors=errors,
    )

    return {
        "run_id": run_id,
        "status": status,
        "tickers_processed": len(tickers),
        "feeds_classified": total_classified,
        "common_items_classified": total_common_classified,
        "items_skipped": total_skipped,
        "insights_generated": total_insights_generated,
        "errors": errors,
    }
