"""
Fixed-fixture regression eval for the pipeline's insight synthesis
(agent/pipelines/insight_nodes.py::synthesize_node, which calls
agent/shared/synthesize.py::synthesize_insight with no `question` - the proactive "god
summary" path, as opposed to conduct_analysis's Q&A path that run_generation_eval.py
already scores). Runs a fixed set of (ticker, evidence) pairs through
synthesize_insight() FRESH each time and judges the result - the pipeline-side
counterpart to run_generation_eval.py's chat-answer scoring, same reasoning: a
reproducible, controlled input so a prompt/model change shows up here before it reaches
production.

Deliberately NOT sampling real ticker_insights rows the way this script used to (and the
way monitoring/quality_sampling.py's sample_insight_quality still does) - that couples
the eval's result to whatever real news happened to exist when it was run, so two runs
before/after a prompt change could differ just because the news changed, not because the
prompt did. Continuous monitoring of real production insights is what
monitoring/quality_sampling.py is for; this is the fixed regression-test counterpart.

Usage:
    python -m agent.eval.run_insight_eval
"""

import argparse
import json

from agent.shared.synthesize import synthesize_insight
from agent.eval.judge import judge_groundedness, judge_relevance, judge_completeness, dump_unsupported_claims
from db.queries import insert_eval_run

DEFAULT_FIXTURE = "agent/eval/fixtures/insight_test_set.json"


def run_one(row: dict) -> dict:
    ticker = row["ticker"]
    evidence = row["evidence"]
    question = f"What's happening with {ticker} and why?"

    insight_text = synthesize_insight(ticker, evidence)

    groundedness = judge_groundedness(insight_text, evidence)
    relevance = judge_relevance(question, insight_text)
    completeness = judge_completeness(question, insight_text, evidence)

    return {
        "ticker": ticker,
        "question": question,
        "insight_text": insight_text,
        "evidence": evidence,
        "groundedness": {
            "grounded": groundedness.grounded,
            "groundedness_pct": groundedness.groundedness_pct,
            "unsupported_claims": dump_unsupported_claims(groundedness.unsupported_claims),
        },
        "relevance": {"score": relevance.score, "reasoning": relevance.reasoning},
        "completeness": {
            "coverage_pct": completeness.coverage_pct,
            "omitted_points": completeness.omitted_points,
        },
    }


def summarize(results: list[dict]) -> dict:
    n = len(results)
    return {
        "n_total": n,
        "avg_relevance": round(sum(r["relevance"]["score"] for r in results) / n, 2) if n else None,
        "pct_grounded": round(100 * sum(1 for r in results if r["groundedness"]["grounded"]) / n, 1) if n else None,
        "avg_completeness_pct": (
            round(sum(r["completeness"]["coverage_pct"] for r in results) / n, 1) if n else None
        ),
    }


def _print_summary(summary: dict) -> None:
    print(f"Total insights judged:  {summary['n_total']}")
    print(f"Avg relevance (1-5):    {summary['avg_relevance']}")
    print(f"% grounded:             {summary['pct_grounded']}")
    print(f"Avg evidence coverage:  {summary['avg_completeness_pct']}%")


def run_insight_eval(fixture_path: str = DEFAULT_FIXTURE, persist: bool = True) -> dict:
    """Runs the fixed fixture and returns {"summary", "results"} - the one function both
    this script's __main__ block AND POST /api/admin/eval/insight/trigger call. Makes
    real, live Claude calls (ANALYSIS_MODEL for synthesis, JUDGE_MODEL for judging) -
    not free, not instant."""
    with open(fixture_path, encoding="utf-8") as f:
        rows = json.load(f)

    results = [run_one(row) for row in rows]
    summary = summarize(results)

    if persist:
        insert_eval_run("insight_quality", {"fixture": fixture_path, "summary": summary, "results": results})

    return {"summary": summary, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--output", default="agent/eval/results/insight_eval.json")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    output = run_insight_eval(args.fixture, persist=not args.no_persist)
    _print_summary(output["summary"])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote full detail to {args.output}")
    if not args.no_persist:
        print("Logged this run to eval_runs (visible on the admin page).")
