"""
Deterministic regression check for the pipeline's evidence-source planning
(agent/pipelines/insight_nodes.py::decide_feed_sources) - the batched LLM call that
decides, per feed, whether financial reports and/or peer-industry news should be pulled
in as supplementary evidence beyond that feed's own matched news items (see
execute_step_node, which acts on these needs_reports/needs_peer_news flags).

Reuses the real decide_feed_sources() function against a small hand-labeled fixture
(feed name/description -> expected needs_reports/needs_peer_news), rather than
reimplementing the decision - so a change to SOURCE_DECISION_PROMPT shows up here.
Scoring itself is plain comparison against the labels, no judge LLM involved - the two
flags are close to deterministic per feed type by design (see the prompt's own worked
examples for Business Strategy/Investment in AI/Revenue Trend).

Usage:
    python -m agent.eval.runners.run_evidence_selection_eval
"""

import argparse
import json

from agent.pipelines.insight_nodes import decide_feed_sources
from agent.eval.fixture_version import compute_fixture_version
from db.queries import insert_eval_run

DEFAULT_FIXTURE = "agent/eval/fixtures/evidence_selection_test_set.json"


def score_row(row: dict) -> dict:
    decisions = decide_feed_sources(row["ticker"], row["feeds"])
    per_feed = []
    for feed_name, expected in row["expected"].items():
        decision = decisions.get(feed_name)
        predicted = (
            {"needs_reports": decision.needs_reports, "needs_peer_news": decision.needs_peer_news}
            if decision is not None
            else {"needs_reports": None, "needs_peer_news": None}
        )
        per_feed.append({
            "feed_name": feed_name,
            "expected": expected,
            "predicted": predicted,
            "reports_correct": predicted["needs_reports"] == expected["needs_reports"],
            "peer_news_correct": predicted["needs_peer_news"] == expected["needs_peer_news"],
        })
    return {"ticker": row["ticker"], "per_feed": per_feed}


def summarize(results: list[dict]) -> dict:
    flat = [f for r in results for f in r["per_feed"]]
    n = len(flat)
    reports_correct = sum(1 for f in flat if f["reports_correct"])
    peer_news_correct = sum(1 for f in flat if f["peer_news_correct"])
    both_correct = sum(1 for f in flat if f["reports_correct"] and f["peer_news_correct"])
    return {
        "n_feeds": n,
        "needs_reports_accuracy": round(reports_correct / n, 4) if n else None,
        "needs_peer_news_accuracy": round(peer_news_correct / n, 4) if n else None,
        "exact_match_accuracy": round(both_correct / n, 4) if n else None,
    }


def _print_summary(summary: dict) -> None:
    print(f"Feeds scored:                {summary['n_feeds']}")
    print(f"needs_reports accuracy:      {summary['needs_reports_accuracy']}")
    print(f"needs_peer_news accuracy:    {summary['needs_peer_news_accuracy']}")
    print(f"Exact match (both flags):    {summary['exact_match_accuracy']}")


def run_evidence_selection_eval(fixture_path: str = DEFAULT_FIXTURE, persist: bool = True) -> dict:
    """Runs the fixed fixture and returns {"summary", "results"}. Makes a real, live
    Claude call per ticker (ANALYSIS_MODEL, via decide_feed_sources) - not free, not
    instant. No judge model involved: correctness is checked directly against the
    hand-labeled `expected` field in the fixture."""
    with open(fixture_path, encoding="utf-8") as f:
        rows = json.load(f)

    results = [score_row(row) for row in rows]
    summary = summarize(results)

    if persist:
        insert_eval_run(
            "evidence_selection", {"fixture": fixture_path, "summary": summary, "results": results},
            fixture_version=compute_fixture_version(fixture_path),
        )

    return {"summary": summary, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--output", default="agent/eval/results/evidence_selection_eval.json")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    output = run_evidence_selection_eval(args.fixture, persist=not args.no_persist)
    _print_summary(output["summary"])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote full detail to {args.output}")
    if not args.no_persist:
        print("Logged this run to eval_runs (visible on the admin page).")
