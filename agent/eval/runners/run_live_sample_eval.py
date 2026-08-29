"""
Judges a random sample of REAL recent conduct_analysis requests (not a fixed fixture
set - see eval/run_generation_eval.py for that) for groundedness, relevance, and
answer-discovery - continuous quality monitoring on actual production traffic at a
cost that stays predictable regardless of how much real traffic there is, by sampling
a small fixed N per run rather than judging every request live.

Reuses the exact same judge functions agent/eval/runners/run_generation_eval.py uses (agent/eval/judge.py)
- one implementation, not a separately-drifting live-sample copy.

Usage:
    python -m agent.eval.runners.run_live_sample_eval
    python -m agent.eval.runners.run_live_sample_eval --n 10 --hours 24
"""

import argparse

from db.queries import insert_eval_run, sample_recent_request_traces
from agent.eval.judge import judge_groundedness, judge_relevance, judge_answer_found, dump_unsupported_claims


def run_one(trace_row: dict) -> dict:
    question = trace_row["question"]
    answer = trace_row["answer"]
    evidence = trace_row["evidence"] or []
    print(f"Judging request_trace {trace_row['id']}: {question!r}")

    groundedness = judge_groundedness(answer, evidence)
    relevance = judge_relevance(question, answer)
    # No genuinely_answerable label on real traffic (unlike the offline fixture set) -
    # every sampled row is, by construction, a completed conduct_analysis request that
    # DID produce an insight, so "did it find an answer" is always a meaningful
    # question to ask here, not conditional the way run_generation_eval.py's is.
    found = judge_answer_found(question, answer)

    return {
        "request_trace_id": trace_row["id"],
        "groundedness": {
            "grounded": groundedness.grounded,
            "groundedness_pct": groundedness.groundedness_pct,
            "unsupported_claims": dump_unsupported_claims(groundedness.unsupported_claims),
        },
        "relevance": {"score": relevance.score, "reasoning": relevance.reasoning},
        "answer_found": {"found_answer": found.found_answer, "reasoning": found.reasoning},
    }


def summarize(results: list[dict]) -> dict:
    n = len(results)
    return {
        "n_sampled": n,
        "avg_relevance": round(sum(r["relevance"]["score"] for r in results) / n, 2) if n else None,
        "pct_grounded": round(100 * sum(1 for r in results if r["groundedness"]["grounded"]) / n, 1) if n else None,
        "pct_answer_found": round(100 * sum(1 for r in results if r["answer_found"]["found_answer"]) / n, 1) if n else None,
    }


def _print_summary(summary: dict) -> None:
    print(f"Sampled:                 {summary['n_sampled']}")
    print(f"Avg relevance (1-5):     {summary['avg_relevance']}")
    print(f"% grounded:              {summary['pct_grounded']}")
    print(f"% answer found (recall): {summary['pct_answer_found']}")


def run_live_sample_eval(n: int = 10, hours: int = 24, persist: bool = True) -> dict:
    """Samples up to `n` completed conduct_analysis requests from the last `hours` and
    judges each - the one function both this script's __main__ block AND the
    admin-triggered POST /api/admin/eval/live_sample/trigger route call. Makes real,
    live Claude calls (JUDGE_MODEL, 3 calls per sampled request) - not free, not instant,
    which is exactly why `n` defaults to a small fixed number rather than judging every
    request."""
    trace_rows = sample_recent_request_traces(n, hours=hours)
    results = [run_one(row) for row in trace_rows]
    summary = summarize(results)

    if persist:
        insert_eval_run("live_sample", {"n_requested": n, "window_hours": hours, "summary": summary, "results": results})

    return {"summary": summary, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10, help="How many recent requests to sample and judge.")
    parser.add_argument("--hours", type=int, default=24, help="Sample from requests in the last N hours.")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    output = run_live_sample_eval(args.n, args.hours, persist=not args.no_persist)
    _print_summary(output["summary"])
    if not args.no_persist:
        print("\nLogged this run to eval_runs (visible on the admin page).")
