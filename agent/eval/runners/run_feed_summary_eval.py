"""
Fixed-fixture regression eval for feed item summarization
(agent/pipelines/insight_nodes.py::summarize_feed_items) - the LLM call that combines a
feed's own news items (title+snippet, concatenated - see
agent/shared/news_text.py::format_news_content) into one summary + sufficiency
judgment, for both custom feeds and common-feed-template items. Reuses the exact same
function the live insight pipeline calls, on a fixed set of (feed, [news items]) pairs,
so a prompt/model change shows up here before it reaches production - unlike
monitoring/quality_sampling.py's sample_feed_combine_quality, which continuously judges
whatever the live pipeline already produced from real, changing news.

One fixture, not two (custom vs common) - summarize_feed_items itself doesn't
distinguish between the two (same function, same prompt, regardless of which table the
items came from), so there's nothing to test separately. Classification correctness
(which feed an article gets matched to) is scored separately by run_classification_eval.py,
deliberately scoped to common_feed_templates only - see that script's own docstring for
why custom feeds aren't in scope there. This eval is purely about combine-quality once a
feed's items are already known, so the same reasoning doesn't apply here.

There's no separate per-article summarization step to test any more - classification
time now stores each item's content_summary as format_news_content(title, snippet)
directly (see ingestion_steps.py), with no LLM call of its own. summarize_feed_items is
the only summarization LLM call left in the feed pipeline, which is why this eval calls
it directly instead of a per-article function.

Usage:
    python -m agent.eval.runners.run_feed_summary_eval
"""

import argparse
import json

from agent.pipelines.insight_nodes import summarize_feed_items
from agent.eval.judge import judge_groundedness, judge_completeness, dump_unsupported_claims
from agent.shared.news_text import format_news_content
from agent.eval.fixture_version import compute_fixture_version
from db.queries import insert_eval_run

DEFAULT_FIXTURE = "agent/eval/fixtures/feed_summary_test_set.json"


def run_one(row: dict) -> dict:
    items = [{"content_summary": format_news_content(n["title"], n.get("snippet"))} for n in row["news"]]
    result = summarize_feed_items(row["feed_name"], row["feed_description"], row["ticker"], items)
    evidence = [{"source": "news", "content": item["content_summary"]} for item in items]
    question = f"What do these items say about the '{row['feed_name']}' feed, and is the evidence sufficient?"

    groundedness = judge_groundedness(result.summary, evidence)
    completeness = judge_completeness(question, result.summary, evidence)

    return {
        "id": row.get("id"),
        "ticker": row.get("ticker"),
        "feed_name": row["feed_name"],
        "feed_description": row["feed_description"],
        "news_titles": [n["title"] for n in row["news"]],
        "summary": result.summary,
        "sufficient": result.sufficient,
        "groundedness": {
            "grounded": groundedness.grounded,
            "groundedness_pct": groundedness.groundedness_pct,
            "unsupported_claims": dump_unsupported_claims(groundedness.unsupported_claims),
        },
        "completeness": {
            "coverage_pct": completeness.coverage_pct,
            "omitted_points": completeness.omitted_points,
        },
    }


def summarize(results: list[dict]) -> dict:
    n = len(results)
    return {
        "n_total": n,
        "pct_grounded": round(100 * sum(1 for r in results if r["groundedness"]["grounded"]) / n, 1) if n else None,
        "avg_groundedness_pct": (
            round(sum(r["groundedness"]["groundedness_pct"] for r in results) / n, 1) if n else None
        ),
        "avg_completeness_pct": (
            round(sum(r["completeness"]["coverage_pct"] for r in results) / n, 1) if n else None
        ),
    }


def _print_summary(summary: dict) -> None:
    print(f"Total feeds:        {summary['n_total']}")
    print(f"% fully grounded:   {summary['pct_grounded']}")
    print(f"Avg groundedness:   {summary['avg_groundedness_pct']}%")
    print(f"Avg completeness:   {summary['avg_completeness_pct']}%")


def run_feed_summary_eval(fixture_path: str = DEFAULT_FIXTURE, persist: bool = True) -> dict:
    """Runs the fixed fixture and returns {"summary", "results"} - the one function both
    this script's __main__ block AND the admin-triggered
    POST /api/admin/eval/feed-summary/trigger route call. Makes real, live Claude calls
    (ANALYSIS_MODEL for the summary itself, JUDGE_MODEL for judging) - not free, not instant."""
    with open(fixture_path, encoding="utf-8") as f:
        rows = json.load(f)

    results = [run_one(row) for row in rows]
    summary = summarize(results)

    if persist:
        insert_eval_run(
            "feed_summary", {"fixture": fixture_path, "summary": summary, "results": results},
            fixture_version=compute_fixture_version(fixture_path),
        )

    return {"summary": summary, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--output", default="agent/eval/results/feed_summary_eval.json")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    output = run_feed_summary_eval(args.fixture, persist=not args.no_persist)
    _print_summary(output["summary"])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote full detail to {args.output}")
    if not args.no_persist:
        print("Logged this run to eval_runs (visible on the admin page).")
