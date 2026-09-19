"""
Continuous production quality monitoring: samples a bounded percentage of each
surface's recent LLM-generated text - per-feed combined summaries, pipeline insight
summaries, and chat answers - judges it with the same groundedness/completeness judges
eval/judge.py already uses, and persists one row per judged item to quality_samples (see
schema.sql) so the admin page's Monitoring section can browse specific flagged examples,
not just an aggregate score.

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
    get_items_by_ids,
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
    every surface (run_quality_sampling calls all three samplers in one request)."""
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


def sample_feed_combine_quality(hours: int = QUALITY_SAMPLE_WINDOW_HOURS) -> dict:
    """Judges a rate-capped sample of real summarize_feed_items() output - the per-feed
    combined summary stored in ticker_insights.feed_summaries (see synthesize_node in
    agent/pipelines/insight_nodes.py) - against the real underlying news items it was
    built from, reconstructed by their item_ids via get_items_by_ids.

    Replaces the old sample_custom_feed_quality/sample_common_feed_quality: those judged
    the per-article content_summary, but classification time now stores content_summary
    as plain format_news_content(title, snippet) with no LLM call of its own (see
    ingestion_steps.py) - there's nothing left to audit at that stage. The only
    summarization LLM call left in the feed pipeline is summarize_feed_items, so that's
    what this audits instead.

    Candidates are individual (ticker_insight, feed_name) pairs flattened out of recent
    ticker_insights rows, not whole rows - one insight can have several feeds worth
    auditing independently, unlike sample_insight_quality which judges the god-summary
    as a whole. Each candidate's `id` (what _select_candidates dedupes on) is the FIRST
    id in that feed's item_ids - there's no id of its own for "this feed's combined
    summary in this run", so its first underlying item is used as a stable anchor (see
    schema.sql's quality_samples.source_id comment)."""
    insight_rows = get_recent_ticker_insights_in_window(hours)
    candidates = [
        {
            "id": fs["item_ids"][0],
            "ticker": insight_row["ticker"],
            "feed_name": fs["feed_name"],
            "summary": fs["summary"],
            "item_ids": fs["item_ids"],
        }
        for insight_row in insight_rows
        for fs in (insight_row.get("feed_summaries") or [])
        if fs.get("status") == "sufficient" and fs.get("summary") and fs.get("item_ids")
    ]
    chosen = _select_candidates(candidates, "feed_combine")

    all_item_ids = [item_id for c in chosen for item_id in c["item_ids"]]
    content_by_id = get_items_by_ids(all_item_ids)

    rows = []
    for c in chosen:
        evidence = [
            {"source": "news", "content": content_by_id[item_id]}
            for item_id in c["item_ids"]
            if item_id in content_by_id
        ]
        if not evidence:
            # Every underlying item was deleted/unreachable since this insight ran -
            # nothing to judge groundedness/completeness against, so skip rather than
            # unfairly flag it.
            continue
        row = _judge_and_build_row(
            surface_type="feed_combine",
            source_id=c["id"],
            ticker=c["ticker"],
            question=f"What do these items say about the '{c['feed_name']}' feed, and is the evidence sufficient?",
            context=c["feed_name"],
            text=c["summary"],
            evidence=evidence,
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
    """Runs all three samplers - the one function both the admin trigger route and a
    future scheduled job would call. Makes real, live JUDGE_MODEL calls (up to
    QUALITY_SAMPLE_CAP * 3 total) - not free, not instant."""
    return {
        "feed_combine": sample_feed_combine_quality(hours),
        "insight": sample_insight_quality(hours),
        "chat_answer": sample_chat_answer_quality(hours),
    }
