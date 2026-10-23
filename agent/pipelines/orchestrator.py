from datetime import datetime, timedelta, timezone

from config import NEWS_STALE_AFTER_DAYS

from db.queries import (
    get_all_watchlist_entries,
    get_distinct_watchlisted_tickers,
    get_ticker_insight_pairs,
    get_latest_news_published_at,
    create_pipeline_run,
    update_pipeline_run,
    insert_ops_alert,
)
from .ingestion_steps import (
    fetch_and_cache_news,
    classify_common_feeds,
    classify_and_store,
    ensure_company_sector_cached,
)
from .insight_graph import synthesize_insight_for
from agent.shared.structured_output import StructuredOutputError

from langchain_core.exceptions import ModelAPIError, ModelConnectionError, ModelRateLimitError, ModelTimeoutError
from tools.logger import get_logger

logger = get_logger(__name__)
RETRYABLE_ERRORS = (ModelAPIError, ModelConnectionError, ModelRateLimitError, ModelTimeoutError)



def _fetch_and_classify_common(tickers: list[str], errors: list[dict]) -> tuple[int, set[str], int]:
    """Phases 1 and 1.5: fetch + cache each ticker's news ONCE (not once per user
    watching it), then classify newly-cached articles against the shared common feed
    templates, once per ticker regardless of how many users have a common feed on it.
    Returns total number of articles classified into a common feed, the set of tickers
    with new common items, and how many articles the news source returned in total
    (before dedupe) - see _news_health_issue."""
    total_common_classified = 0
    tickers_with_new_common_items = set()
    total_consecutive_failures = 0
    total_articles_fetched = 0

    for ticker in tickers:
        try:
            fetch_result = fetch_and_cache_news(ticker)
            if fetch_result is not None:
                total_articles_fetched += fetch_result
                total_consecutive_failures = 0
                ensure_company_sector_cached(ticker)
                common_classified_count = classify_common_feeds(ticker)
                total_common_classified += common_classified_count
                if common_classified_count > 0:
                    tickers_with_new_common_items.add(ticker)
            else:
                total_consecutive_failures += 1
                if total_consecutive_failures >= 5:
                    logger.error(
                        "Pipeline failed during fetch_and_cache phase, and 5 consecutive tickers have failed. Aborting further processing."
                    )
                    total_common_classified = -1
                    break

        except Exception as e:
            error = {"ticker": ticker, "phase": "fetch_and_cache", "error": str(e)}
            logger.exception("Pipeline failed for %s during %s", ticker, error["phase"])
            errors.append(error)
            total_common_classified = -1
            break  # Stop processing further tickers after an exception

    return total_common_classified, tickers_with_new_common_items, total_articles_fetched


def _classify_custom_feeds(
    entries: list[dict],
    run_cutoff: str,
    tickers_with_new_common_items: set[str],
    errors: list[dict],
) -> tuple[int, int, list[dict]]:
    """Phase 2: classify each user's CUSTOM feeds against the cache - the only phase
    that still loops per (user, ticker) pair, and the only one that calls an LLM per
    user. Returns the totals classified/skipped, and the entries that need their
    insight regenerated: those with new custom-feed evidence this run, a new
    common-feed item from phase 1.5, or no insight generated yet at all (a one-time
    backfill for evidence classified before insight_graph existed)."""
    existing_insight_pairs = {
        (row["user_id"], row["ticker"]) for row in get_ticker_insight_pairs()
    }

    total_classified = 0
    total_skipped = 0
    entries_needing_insight = []

    for entry in entries:
        try:
            classified_count, skipped_count = classify_and_store(
                entry["user_id"], entry["ticker"], run_cutoff
            )
            total_classified += classified_count
            total_skipped += skipped_count
            pair = (entry["user_id"], entry["ticker"])
            if (
                classified_count > 0
                or entry["ticker"] in tickers_with_new_common_items
                or pair not in existing_insight_pairs
            ):
                entries_needing_insight.append(entry)
        except Exception as e:
            error = {
                "user_id": entry["user_id"],
                "ticker": entry["ticker"],
                "phase": "classify",
                "error": str(e),
            }
            logger.exception("Pipeline failed for %s during %s", entry["ticker"], error["phase"])
            errors.append(error)

    return total_classified, total_skipped, entries_needing_insight


def _synthesize_insights(entries_needing_insight: list[dict], errors: list[dict]) -> int:
    """Phase 4: re-synthesize insight_graph's cross-feed insight for each (user,
    ticker) pair phase 2 flagged as needing it. Once a pair has its first insight,
    it's only regenerated on genuine change, so repeat admin clicks don't burn one
    more LLM call per watchlisted ticker for nothing."""
    total_insights_generated = 0
    count_consecutive_local_failures = 0

    for entry in entries_needing_insight:
        if count_consecutive_local_failures >= 5:
            error = "Too many consecutive local failures for entrys in _synthesize_insights. Aborting further processing."
            errors.append(error)
            logger.error(error)
            return -1
        try:
            synthesize_insight_for(entry["user_id"], entry["ticker"])
            total_insights_generated += 1
            count_consecutive_local_failures = 0

        except Exception as e:
            error = {
                "user_id": entry["user_id"],
                "ticker": entry["ticker"],
                "phase": "insight_synthesis",
                "error": str(e),
            }
            logger.exception("Pipeline failed for %s during %s", entry["ticker"], error["phase"])
            errors.append(error)

            if isinstance(e, StructuredOutputError):
                # Repair-then-retry (see agent/shared/structured_output.py) already
                # failed twice by the time this is raised - not a transient blip worth
                # silently swallowing into the generic errors list alone. Surfaced as
                # an ops_alert so it shows up on the admin Alerts page for review,
                # with the raw unparseable args attached since that's what someone
                # would actually need to diagnose it.
                count_local_failures += 1
                insert_ops_alert(
                    request_trace_id=None,
                    user_id=entry["user_id"],
                    alert_type="structured_output_parse_failure",
                    threshold=e.attempts,
                    actual_value=e.attempts,
                    details={
                        "ticker": entry["ticker"],
                        "schema": e.schema_name,
                        "raw_args": e.raw_args,
                    },
                )

            elif isinstance(e, RETRYABLE_ERRORS):
                count_consecutive_local_failures += 1

            else:
                # stop the loop for unknown errors or any kind of non-retryable error, so the admin can see the failure and fix it
                return -1

    return total_insights_generated


def _news_health_issue(tickers: list[str], articles_fetched: int) -> str | None:
    """Why this run's news looks broken even though nothing crashed, or None if it looks fine.

    Catches the silent failure that hid a four-week outage: yfinance turned Yahoo's HTTP 502s
    into empty lists, every ticker read as "no news today", and every run reported success.
    Two signals - the source returned nothing at all for any ticker, or the newest stored
    article is older than NEWS_STALE_AFTER_DAYS (the source answers, but nothing new arrives)."""
    if not tickers:
        return None
    if articles_fetched == 0:
        return f"News source returned no articles for any of the {len(tickers)} watchlisted tickers."
    newest = get_latest_news_published_at()
    if newest and datetime.now(timezone.utc) - newest > timedelta(days=NEWS_STALE_AFTER_DAYS):
        return f"Newest stored article was published {newest.date().isoformat()}, over {NEWS_STALE_AFTER_DAYS} days ago."
    return None


def run_ingestion_for_all_watchlisted_tickers() -> dict:
    """
    Four phases, in order (see _fetch_and_classify_common, _classify_custom_feeds, and
    _synthesize_insights for what each one does). This is the single function both a
    scheduled cron job AND the admin 'trigger now' button call - one orchestrator, two
    triggers - so the logic for "what counts as a run" only lives in one place. Each
    ticker's/pair's failure is caught individually so one bad one doesn't take down the
    whole run.

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
    errors = []
    total_insights_generated = -1
    total_classified = -1
    total_skipped = -1
    total_common_classified = -1

    total_common_classified, tickers_with_new_common_items, total_articles_fetched = _fetch_and_classify_common(tickers, errors)

    if total_common_classified == -1:
        errors.append({"phase": "fetch_and_classify_common", "error": "System failures"})

    run_cutoff = datetime.now(timezone.utc).isoformat()

    if not errors:
        total_classified, total_skipped, entries_needing_insight = _classify_custom_feeds(
            entries, run_cutoff, tickers_with_new_common_items, errors
        )

    if not errors:
        total_insights_generated = _synthesize_insights(entries_needing_insight, errors)

    news_issue = None if errors else _news_health_issue(tickers, total_articles_fetched)
    if news_issue:
        # Not a crash - the run finished - but its output can't be trusted to be current.
        # Anything other than "success" makes scripts/run_weekly_job.py exit non-zero, so the
        # scheduled GitHub Actions run fails visibly instead of reporting green.
        logger.error("Pipeline run degraded: %s", news_issue)
        errors.append({"phase": "news_health", "error": news_issue})
        status = "degraded"
    elif not errors:
        status = "success"
    #elif total_classified > 0 or total_common_classified > 0:
    #    status = "partial_failure"
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
