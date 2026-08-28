"""
Fixed-fixture regression eval for feed item summarization
(agent/pipelines/ingestion_steps.py::_summarize_for_feed) - the LLM call that produces
content_summary for both custom feed_items and shared common_feed_items rows. Reuses
the exact same function the live pipeline calls, on a fixed set of (article, feed)
pairs, so a prompt/model change shows up here before it reaches production - unlike
monitoring/quality_sampling.py's sample_custom_feed_quality/sample_common_feed_quality,
which continuously judge whatever the live pipeline already produced from real, changing
news.

One fixture, not two (custom vs common) - _summarize_for_feed itself doesn't distinguish
between the two (same function, same prompt, regardless of which table the caller will
insert into), so there's nothing to test separately. Classification correctness (which
feed an article gets matched to) is scored separately by score_classification.py,
deliberately scoped to common_feed_templates only - see that script's own docstring for
why custom feeds aren't in scope there. This eval is purely about summary quality once a
match has already happened, so the same reasoning doesn't apply here.

Usage:
    python -m agent.eval.run_feed_summary_eval
"""

import argparse
import json

from agent.pipelines.ingestion_steps import summarize_for_feed
from agent.eval.judge import judge_groundedness, judge_completeness, dump_unsupported_claims
from db.queries import insert_eval_run

DEFAULT_FIXTURE = "agent/eval/fixtures/feed_summary_test_set.json"


def run_one(row: dict) -> dict:
    article = {"title": row["article_title"], "publisher": row.get("publisher")}
    summary = summarize_for_feed(article, row["feed_name"], row["feed_description"])
    evidence = [{"source": "article", "content": row["article_title"]}]
    question = f"Why is this news item relevant to the '{row['feed_name']}' feed?"

    groundedness = judge_groundedness(summary, evidence)
    completeness = judge_completeness(question, summary, evidence)

    return {
        "ticker": row.get("ticker"),
        "feed_name": row["feed_name"],
        "feed_description": row["feed_description"],
        "article_title": row["article_title"],
        "summary": summary,
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
    print(f"Total pairs:        {summary['n_total']}")
    print(f"% fully grounded:   {summary['pct_grounded']}")
    print(f"Avg groundedness:   {summary['avg_groundedness_pct']}%")
    print(f"Avg completeness:   {summary['avg_completeness_pct']}%")


def run_feed_summary_eval(fixture_path: str = DEFAULT_FIXTURE, persist: bool = True) -> dict:
    """Runs the fixed fixture and returns {"summary", "results"} - the one function both
    this script's __main__ block AND the admin-triggered
    POST /api/admin/eval/feed-summary/trigger route call. Makes real, live Claude calls
    (ROUTER_MODEL for the summary itself, JUDGE_MODEL for judging) - not free, not instant."""
    with open(fixture_path, encoding="utf-8") as f:
        rows = json.load(f)

    results = [run_one(row) for row in rows]
    summary = summarize(results)

    if persist:
        insert_eval_run("feed_summary", {"fixture": fixture_path, "summary": summary, "results": results})

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
