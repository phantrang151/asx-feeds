from datetime import datetime, timezone
import logging

from db.queries import (
    get_all_watchlist_entries,
    get_distinct_watchlisted_tickers,
    get_ticker_insight_pairs,
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

logger = logging.getLogger(__name__)


def _fetch_and_classify_common(tickers: list[str], errors: list[dict]) -> tuple[int, set[str]]:
    """Phases 1 and 1.5: fetch + cache each ticker's news ONCE (not once per user
    watching it), then classify newly-cached articles against the shared common feed
    templates, once per ticker regardless of how many users have a common feed on it.
    Returns the total common-feed items classified and the set of tickers that got at
    least one, for phase 3 to use as an insight-regeneration trigger."""
    total_common_classified = 0
    tickers_with_new_common_items = set()

    for ticker in tickers:
        try:
            fetch_and_cache_news(ticker)
            ensure_company_sector_cached(ticker)
            common_classified_count = classify_common_feeds(ticker)
            total_common_classified += common_classified_count
            if common_classified_count > 0:
                tickers_with_new_common_items.add(ticker)
        except Exception as e:
            error = {"ticker": ticker, "phase": "fetch_and_cache", "error": str(e)}
            logger.exception("Pipeline failed for %s during %s", ticker, error["phase"])
            errors.append(error)

    return total_common_classified, tickers_with_new_common_items


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

    for entry in entries_needing_insight:
        try:
            synthesize_insight_for(entry["user_id"], entry["ticker"])
            total_insights_generated += 1
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

    return total_insights_generated


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

    total_common_classified, tickers_with_new_common_items = _fetch_and_classify_common(tickers, errors)

    run_cutoff = datetime.now(timezone.utc).isoformat()

    total_classified, total_skipped, entries_needing_insight = _classify_custom_feeds(
        entries, run_cutoff, tickers_with_new_common_items, errors
    )

    total_insights_generated = _synthesize_insights(entries_needing_insight, errors)

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
