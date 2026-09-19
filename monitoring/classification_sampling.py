"""
Continuous production monitoring for feed classification correctness (custom_feed_items
and common_feed_items). Complements agent/eval/runners/run_classification_eval.py's Evaluation
panel (same live classifier - db/queries.py::match_feed_for_embedding /
match_common_feed_template_for_embedding - scored against a hand-labeled CSV) rather
than replacing it: that's still the source of truth for precision/recall/PR-AUC, but it
needs a human labeling pass first. This samples real recent classifications and judges
each with agent/eval/judge.py::judge_feed_classification (JUDGE_MODEL) - no labeling
required, so it can run continuously against whatever the pipeline just classified.

Reuses db/queries.py's get_recent_custom_feed_items_for_sampling /
get_recent_common_feed_items_for_sampling / get_ticker_news_titles - the exact same
candidate-fetching and evidence-reconstruction monitoring/quality_sampling.py already
built for judging these same feed items' summary quality, since both need the same
underlying data (the item, its parent feed's name/description, and the source article's
title+snippet, via agent/shared/news_text.py::format_news_content).
"""

import logging
import math
import random

from config import QUALITY_SAMPLE_RATE, QUALITY_SAMPLE_CAP, QUALITY_SAMPLE_WINDOW_HOURS
from db.queries import (
    get_recent_custom_feed_items_for_sampling,
    get_recent_common_feed_items_for_sampling,
    get_ticker_news_titles,
    get_sampled_classification_source_ids,
    insert_classification_samples,
)
from agent.eval.judge import judge_feed_classification
from agent.shared.news_text import format_news_content

logger = logging.getLogger(__name__)


def _sample_size(eligible_n: int, rate: float = QUALITY_SAMPLE_RATE, cap: int = QUALITY_SAMPLE_CAP) -> int:
    """Same rate-with-a-ceiling sizing as monitoring/quality_sampling.py and
    monitoring/guardrail_sampling.py, so cost stays just as predictable here."""
    if eligible_n <= 0:
        return 0
    return min(cap, eligible_n, math.ceil(rate * eligible_n))


def _select_candidates(candidates: list[dict], classification_type: str) -> list[dict]:
    """Same dedup-then-sample pattern as monitoring/quality_sampling.py and
    monitoring/guardrail_sampling.py."""
    already_sampled = get_sampled_classification_source_ids(classification_type, [c["id"] for c in candidates])
    fresh = [c for c in candidates if c["id"] not in already_sampled]
    return random.sample(fresh, _sample_size(len(fresh)))


def _sample_feed_classification(classification_type: str, items: list[dict]) -> dict:
    """Shared body for both classification types below - the only difference between
    custom and common feed items, by this point, is which fetcher supplied `items`."""
    chosen = _select_candidates(items, classification_type)

    by_ticker: dict[str, list[str]] = {}
    for item in chosen:
        if item.get("source_url"):
            by_ticker.setdefault(item["ticker"], []).append(item["source_url"])
    titles_by_ticker = {ticker: get_ticker_news_titles(ticker, urls) for ticker, urls in by_ticker.items()}

    rows = []
    for item in chosen:
        source = titles_by_ticker.get(item["ticker"], {}).get(item.get("source_url"))
        if not source:
            # No matching ticker_news row (e.g. no source_url) - nothing to judge the
            # classification against, so skip rather than guessing.
            continue
        try:
            article_content = format_news_content(source["title"], source.get("snippet"))
            evaluation = judge_feed_classification(article_content, item["feed_name"], item["feed_description"])
        except Exception:
            logger.warning(
                "classification_sampling: judge call failed for %s source_id=%s",
                classification_type, item["id"], exc_info=True,
            )
            continue

        rows.append({
            "classification_type": classification_type,
            "source_id": item["id"],
            "ticker": item["ticker"],
            "article_title": source["title"],
            "feed_name": item["feed_name"],
            "feed_description": item["feed_description"],
            "eval_correct": evaluation.is_correct_match,
            "eval_reasoning": evaluation.reasoning,
            "flagged": not evaluation.is_correct_match,
        })

    inserted = insert_classification_samples(rows)
    return {"n_sampled": len(inserted), "n_flagged": sum(1 for r in inserted if r["flagged"])}


def sample_custom_feed_classification(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    return _sample_feed_classification("custom_feed", get_recent_custom_feed_items_for_sampling(hours))


def sample_common_feed_classification(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    return _sample_feed_classification("common_feed", get_recent_common_feed_items_for_sampling(hours))


def run_classification_sampling(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Runs both classification types - the one function both the admin trigger route
    and a future scheduled job would call."""
    return {
        "custom_feed": sample_custom_feed_classification(hours),
        "common_feed": sample_common_feed_classification(hours),
    }
