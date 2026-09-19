"""
Fixed-fixture regression eval for chat-answer synthesis (agent/shared/synthesize.py::
synthesize_insight, called with `question` set - the exact function
agent/chat/analysis_node.py::conduct_analysis_node uses to turn gathered evidence into
the final answer). Same design as run_feed_summary_eval.py/run_insight_eval.py: a fixed
set of (ticker, question, evidence) triples, synthesized fresh each run, so a
prompt/model change shows up here before it reaches production.

Deliberately does NOT invoke the live chat graph/ReAct agent (unlike this file's
previous version) - retrieval quality (did the right tools get called, in the right
order, with the right ticker) is a different concern from synthesis quality (given this
evidence, is the answer grounded and complete), and mixing them meant this eval's result
depended on whatever the live retrieval pulled at run time, not just the prompt - the
exact non-reproducibility problem run_insight_eval.py's own docstring already flags for
the pipeline side. Retrieval/routing correctness now has its own coverage:
  - Advice-seeking routing: agent/eval/fixtures/input_guardrail_test_set.json
    (run_guardrail_eval.py) - already includes the "Should I buy TLS.AX" style questions
    this fixture used to carry for that purpose, so nothing was lost by removing them
    here.
  - Live end-to-end behavior (real retrieval, real routing, real traffic patterns):
    eval/runners/run_live_sample_eval.py, which continuously judges actual production
    conduct_analysis requests instead of a fixed set.

Usage:
    python -m agent.eval.runners.run_chat_answer_eval
"""

import argparse
import json

from agent.shared.synthesize import synthesize_insight
from agent.eval.judge import judge_groundedness, judge_completeness, dump_unsupported_claims
from agent.eval.fixture_version import compute_fixture_version
from db.queries import insert_eval_run

DEFAULT_FIXTURE = "agent/eval/fixtures/chat_answer_test_set.json"


def evaluate_chat_answer_case(row: dict) -> dict:
    ticker, question, evidence = row["ticker"], row["question"], row["evidence"]

    answer = synthesize_insight(ticker, evidence, question=question)

    groundedness = judge_groundedness(answer, evidence)
    completeness = judge_completeness(question, answer, evidence)

    return {
        "id": row.get("id"),
        "ticker": ticker,
        "question": question,
        "answer": answer,
        "evidence": evidence,
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
    print(f"Total questions judged: {summary['n_total']}")
    print(f"% fully grounded:       {summary['pct_grounded']}")
    print(f"Avg groundedness:       {summary['avg_groundedness_pct']}%")
    print(f"Avg completeness:       {summary['avg_completeness_pct']}%")


def run_chat_answer_eval(fixture_path: str = DEFAULT_FIXTURE, persist: bool = True) -> dict:
    """Runs the fixed fixture and returns {"summary", "results"} - the one function both
    this script's __main__ block AND the admin-triggered POST /api/admin/eval/chat-answer/
    trigger route call. Makes real, live Claude calls (ANALYSIS_MODEL for synthesis,
    JUDGE_MODEL for judging) - not free, not instant."""
    with open(fixture_path, encoding="utf-8") as f:
        rows = json.load(f)

    results = [evaluate_chat_answer_case(row) for row in rows]
    summary = summarize(results)

    if persist:
        insert_eval_run(
            "chat_answer", {"fixture": fixture_path, "summary": summary, "results": results},
            fixture_version=compute_fixture_version(fixture_path),
        )

    return {"summary": summary, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--output", default="agent/eval/results/chat_answer_eval.json")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    output = run_chat_answer_eval(args.fixture, persist=not args.no_persist)
    _print_summary(output["summary"])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote full detail to {args.output}")
    if not args.no_persist:
        print("Logged this run to eval_runs (visible on the admin page).")
