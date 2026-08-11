"""
Generation-quality eval for conduct_analysis: runs a fixture set of (ticker, question)
pairs through the live agent graph directly (bypassing the FastAPI layer, rate limit,
and citation-reachability check on purpose - this evaluates graph/generation quality,
not the API surface), then scores each answer for groundedness, relevance, and
advice-avoidance.

No fabricated "correct answers" - unlike eval/score_classification.py, this judges
whatever the live agent actually produces on a given run, not against a fixed label.

Usage:
    python -m eval.run_generation_eval --fixture eval/fixtures/qa_test_set.json \
        --output eval/results/generation_eval.json
"""

import argparse
import json
import uuid

from langchain_core.messages import HumanMessage

from agent.chat.graph import graph
from agent.guardrails.advice_check import check_advice_avoidance
from config import TEST_USER_ID
from db.queries import insert_eval_run
from eval.judge import judge_groundedness, judge_relevance, judge_answer_found


def run_one(ticker: str, question: str, genuinely_answerable: bool = True) -> dict:
    print(f"Running: {question!r}")
    config = {
        "configurable": {"thread_id": str(uuid.uuid4()), "langgraph_user_id": TEST_USER_ID}
    }
    response = graph.invoke({"messages": [HumanMessage(content=question)]}, config=config)

    category = response.get("category")
    answer = response["messages"][-1].content
    evidence = response.get("evidence") or []

    result = {
        "ticker": ticker,
        "question": question,
        "category": category,
        "answer": answer,
        "evidence_count": len(evidence),
    }

    if category != "conduct_analysis":
        # Router declined it (bad ticker, advice-seeking) or sent it to search_news -
        # there's no synthesized insight to judge against evidence, so record the
        # outcome explicitly instead of scoring groundedness against nothing.
        result["groundedness"] = None
        result["relevance"] = None
        result["advice_avoidance_passed"] = None
        result["answer_found"] = None
        return result

    groundedness = judge_groundedness(answer, evidence)
    relevance = judge_relevance(question, answer)
    passed, matched_keywords, reasoning = check_advice_avoidance(answer)

    result["groundedness"] = {
        "grounded": groundedness.grounded,
        "unsupported_claims": groundedness.unsupported_claims,
    }
    result["relevance"] = {"score": relevance.score, "reasoning": relevance.reasoning}
    result["advice_avoidance_passed"] = passed
    result["advice_avoidance_detail"] = {"matched_keywords": matched_keywords, "reasoning": reasoning}

    # Context recall / answer-discovery rate: only meaningful on questions the fixture
    # marks as genuinely answerable - the whole point of this metric is "did the
    # system wrongly decline on a question with a real answer", not "did it correctly
    # decline on one without" (a different failure mode - fabrication - that
    # groundedness above already covers).
    if genuinely_answerable:
        found = judge_answer_found(question, answer)
        result["answer_found"] = {"found_answer": found.found_answer, "reasoning": found.reasoning}
    else:
        result["answer_found"] = None
    return result


def summarize(results: list[dict]) -> dict:
    judged = [r for r in results if r["category"] == "conduct_analysis"]
    n_judged = len(judged)
    discovery_judged = [r for r in judged if r["answer_found"] is not None]
    return {
        "n_total": len(results),
        "n_judged": n_judged,
        "n_declined_or_other": len(results) - n_judged,
        "avg_relevance": (
            round(sum(r["relevance"]["score"] for r in judged) / n_judged, 2) if n_judged else None
        ),
        "pct_grounded": (
            round(100 * sum(1 for r in judged if r["groundedness"]["grounded"]) / n_judged, 1)
            if n_judged
            else None
        ),
        "pct_advice_avoidance_passed": (
            round(100 * sum(1 for r in judged if r["advice_avoidance_passed"]) / n_judged, 1)
            if n_judged
            else None
        ),
        "pct_answer_found": (
            round(100 * sum(1 for r in discovery_judged if r["answer_found"]["found_answer"]) / len(discovery_judged), 1)
            if discovery_judged
            else None
        ),
    }


def _print_summary(summary: dict) -> None:
    print(f"Total pairs:              {summary['n_total']}")
    print(f"Judged (conduct_analysis): {summary['n_judged']}")
    print(f"Declined/other:           {summary['n_declined_or_other']}")
    print(f"Avg relevance (1-5):      {summary['avg_relevance']}")
    print(f"% grounded:               {summary['pct_grounded']}")
    print(f"% advice-avoidance pass:  {summary['pct_advice_avoidance_passed']}")
    print(f"% answer found (recall):  {summary['pct_answer_found']}")


def run_generation_eval(fixture_path: str, persist: bool = True) -> dict:
    """Runs the full fixture set and returns {"summary", "results"} - the one function
    both this script's __main__ block AND the admin-triggered
    POST /api/admin/eval/generation/trigger route call, so there's a single
    implementation rather than the API duplicating the CLI's loop. Makes real, live
    Claude calls (ANALYSIS_MODEL for the agent, JUDGE_MODEL for judging) - not free, not instant."""
    with open(fixture_path, encoding="utf-8") as f:
        pairs = json.load(f)

    results = [run_one(pair["ticker"], pair["question"], pair.get("genuinely_answerable", True)) for pair in pairs]
    summary = summarize(results)

    if persist:
        insert_eval_run("generation", {"fixture": fixture_path, "summary": summary, "results": results})

    return {"summary": summary, "results": results}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default="eval/fixtures/qa_test_set.json")
    parser.add_argument("--output", default="eval/results/generation_eval.json")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    output = run_generation_eval(args.fixture, persist=not args.no_persist)
    _print_summary(output["summary"])

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nWrote full detail to {args.output}")
    if not args.no_persist:
        print("Logged this run to eval_runs (visible on the admin page).")
