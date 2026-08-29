"""
Continuous production quality monitoring: samples a bounded percentage of each
surface's recent LLM-generated text - custom feed item summaries, common feed item
summaries, pipeline insight summaries, and chat answers - judges it with the same
groundedness/completeness judges eval/judge.py already uses, and persists one row per
judged item to quality_samples (see schema.sql) so the admin page's Monitoring section
can browse specific flagged examples, not just an aggregate score.

Complements agent/eval/ (fixed test cases / manually-triggered aggregate scoring,
re-run on prompt or code change) rather than replacing it - this module is purely
additive.
"""

import logging
import math
import random

from config import (
    QUALITY_SAMPLE_RATE,
    QUALITY_SAMPLE_CAP,
    QUALITY_SAMPLE_WINDOW_HOURS,
    QUALITY_COMPLETENESS_THRESHOLD_PCT,
)
from db.queries import (
    get_recent_custom_feed_items_for_sampling,
    get_recent_common_feed_items_for_sampling,
    get_ticker_news_titles,
    get_recent_ticker_insights_in_window,
    get_eligible_request_traces_for_sampling,
    get_sampled_source_ids,
    insert_quality_samples,
)
from agent.eval.judge import judge_groundedness, judge_completeness, dump_unsupported_claims
from agent.eval.insight_evidence import build_insight_evidence

logger = logging.getLogger(__name__)


def _sample_size(eligible_n: int, rate: float = QUALITY_SAMPLE_RATE, cap: int = QUALITY_SAMPLE_CAP) -> int:
    """min(cap, eligible_n, ceil(rate * eligible_n)) - a flat percentage would scale
    with traffic and make judge-call cost unpredictable as usage grows (see
    QUALITY_SAMPLE_CAP's own comment in config.py)."""
    if eligible_n <= 0:
        return 0
    return min(cap, eligible_n, math.ceil(rate * eligible_n))


def _is_flagged(grounded: bool, completeness_pct: "int | None") -> bool:
    """Zero tolerance on unsupported claims (a financial-context hallucination can bias
    a user's decision); completeness gets a threshold instead, since dropping a minor
    point isn't the same risk as stating something false outright."""
    if not grounded:
        return True
    return completeness_pct is not None and completeness_pct < QUALITY_COMPLETENESS_THRESHOLD_PCT


def _judge_and_build_row(
    *,
    surface_type: str,
    source_id: str,
    ticker: "str | None",
    question: str,
    text: str,
    evidence: list[dict],
    context: "str | None" = None,
) -> "dict | None":
    """Runs both judges and shapes one quality_samples row - shared by every sampler
    below so the row shape and flagging logic can't drift between surfaces. `context` is
    display-only (the admin panel's first column for feed rows - see schema.sql) and
    plays no part in judging, unlike `question` which is fed to judge_completeness.

    Returns None (skipping this item, not the whole batch) if either judge call raises -
    JUDGE_MODEL's structured-output parsing occasionally returns a malformed shape (e.g.
    a stringified list instead of an actual list), which is rare but real, and losing
    one sample to it shouldn't cost the rest of this run's already-judged items across
    every surface (run_quality_sampling calls all four samplers in one request)."""
    try:
        groundedness = judge_groundedness(text, evidence)
        completeness_pct = None
        omitted_points = []
        if evidence:
            completeness = judge_completeness(question, text, evidence)
            completeness_pct = completeness.coverage_pct
            omitted_points = completeness.omitted_points
    except Exception:
        logger.warning("quality_sampling: judge call failed for %s source_id=%s", surface_type, source_id, exc_info=True)
        return None

    return {
        "surface_type": surface_type,
        "source_id": source_id,
        "ticker": ticker,
        "question": question,
        "context": context,
        "text": text,
        "evidence": evidence,
        "groundedness_pct": groundedness.groundedness_pct,
        "grounded": groundedness.grounded,
        "unsupported_claims": dump_unsupported_claims(groundedness.unsupported_claims),
        "completeness_pct": completeness_pct,
        "omitted_points": omitted_points,
        "flagged": _is_flagged(groundedness.grounded, completeness_pct),
    }


def _select_candidates(candidates: list[dict], surface_type: str, id_key: str = "id") -> list[dict]:
    """Excludes already-sampled items (via get_sampled_source_ids) BEFORE spending a
    judge call on them, then randomly picks _sample_size(...) of what's left. Shared by
    every sampler below."""
    already_sampled = get_sampled_source_ids(surface_type, [c[id_key] for c in candidates])
    fresh = [c for c in candidates if c[id_key] not in already_sampled]
    return random.sample(fresh, _sample_size(len(fresh)))


def sample_custom_feed_quality(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Judges a rate-capped sample of recent custom feed_items' content_summary against
    the source article title reconstructed from ticker_news (feed_items itself only
    stores the summary, not the source text - see get_ticker_news_titles)."""
    chosen = _select_candidates(get_recent_custom_feed_items_for_sampling(hours), "custom_feed")

    by_ticker: dict[str, list[str]] = {}
    for item in chosen:
        if item.get("source_url"):
            by_ticker.setdefault(item["ticker"], []).append(item["source_url"])
    titles_by_ticker = {ticker: get_ticker_news_titles(ticker, urls) for ticker, urls in by_ticker.items()}

    rows = []
    for item in chosen:
        source = titles_by_ticker.get(item["ticker"], {}).get(item.get("source_url"))
        if not source:
            # No matching ticker_news row (e.g. no source_url) - nothing to judge
            # groundedness/completeness against, so skip rather than unfairly flag it.
            continue
        row = _judge_and_build_row(
            surface_type="custom_feed",
            source_id=item["id"],
            ticker=item["ticker"],
            question=f"Why is this news item relevant to the '{item['feed_name']}' feed?",
            context=item.get("feed_description"),
            text=item["content_summary"],
            evidence=[{"source": "ticker_news", "content": source["title"], "url": item.get("source_url")}],
        )
        if row:
            rows.append(row)

    inserted = insert_quality_samples(rows)
    return {"n_sampled": len(inserted), "n_flagged": sum(1 for r in inserted if r["flagged"])}


def sample_common_feed_quality(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Same as sample_custom_feed_quality above, for common_feed_items."""
    chosen = _select_candidates(get_recent_common_feed_items_for_sampling(hours), "common_feed")

    by_ticker: dict[str, list[str]] = {}
    for item in chosen:
        if item.get("source_url"):
            by_ticker.setdefault(item["ticker"], []).append(item["source_url"])
    titles_by_ticker = {ticker: get_ticker_news_titles(ticker, urls) for ticker, urls in by_ticker.items()}

    rows = []
    for item in chosen:
        source = titles_by_ticker.get(item["ticker"], {}).get(item.get("source_url"))
        if not source:
            continue
        row = _judge_and_build_row(
            surface_type="common_feed",
            source_id=item["id"],
            ticker=item["ticker"],
            question=f"Why is this news item relevant to the '{item['feed_name']}' feed?",
            context=item.get("feed_description"),
            text=item["content_summary"],
            evidence=[{"source": "ticker_news", "content": source["title"], "url": item.get("source_url")}],
        )
        if row:
            rows.append(row)

    inserted = insert_quality_samples(rows)
    return {"n_sampled": len(inserted), "n_flagged": sum(1 for r in inserted if r["flagged"])}


def sample_insight_quality(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Judges a rate-capped sample of recent ticker_insights rows, reusing the same
    evidence reconstruction agent/eval/runners/run_insight_eval.py uses (build_insight_evidence)
    so both surfaces are graded against the exact same evidence shape."""
    chosen = _select_candidates(get_recent_ticker_insights_in_window(hours), "insight")

    rows = []
    for insight_row in chosen:
        evidence = build_insight_evidence(insight_row["feed_summaries"])
        if not evidence:
            continue
        row = _judge_and_build_row(
            surface_type="insight",
            source_id=insight_row["id"],
            ticker=insight_row["ticker"],
            question=f"What's happening with {insight_row['ticker']} and why?",
            text=insight_row["insight_text"],
            evidence=evidence,
        )
        if row:
            rows.append(row)

    inserted = insert_quality_samples(rows)
    return {"n_sampled": len(inserted), "n_flagged": sum(1 for r in inserted if r["flagged"])}


def sample_chat_answer_quality(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Judges a rate-capped sample of recent completed conduct_analysis chat answers -
    question/answer/evidence are already stored directly on request_trace, no
    reconstruction needed (unlike the three surfaces above)."""
    chosen = _select_candidates(get_eligible_request_traces_for_sampling(hours), "chat_answer")

    rows = []
    for trace_row in chosen:
        evidence = trace_row.get("evidence") or []
        if not evidence:
            continue
        row = _judge_and_build_row(
            surface_type="chat_answer",
            source_id=trace_row["id"],
            ticker=trace_row.get("ticker"),
            question=trace_row["question"],
            text=trace_row["answer"],
            evidence=evidence,
        )
        if row:
            rows.append(row)

    inserted = insert_quality_samples(rows)
    return {"n_sampled": len(inserted), "n_flagged": sum(1 for r in inserted if r["flagged"])}


def run_quality_sampling(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Runs all four samplers - the one function both the admin trigger route and a
    future scheduled job would call. Makes real, live JUDGE_MODEL calls (up to
    QUALITY_SAMPLE_CAP * 4 total) - not free, not instant."""
    return {
        "custom_feed": sample_custom_feed_quality(hours),
        "common_feed": sample_common_feed_quality(hours),
        "insight": sample_insight_quality(hours),
        "chat_answer": sample_chat_answer_quality(hours),
    }
