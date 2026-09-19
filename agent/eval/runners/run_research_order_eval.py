"""
TP/FP scoring for the research-order guardrail (agent/guardrails/research_order.py) -
the ordering guard the chat ReAct agent's research tools call before running (see
tools/react_tools.py). The guard itself is deterministic, so this isn't judging
ambiguous natural language the way run_guardrail_eval.py's advice checks are - it's a
labeled regression check reusing the same shared confusion-matrix shape, so a future
change to research_order.py's state machine that breaks an ordering guarantee shows up
here (and on the admin page) rather than only failing tests/test_research_order.py locally.

Reuses the real authorize_research_source/authorize_peer_news/record_internal_news_result
functions inside a fresh research_guard() context per fixture row - never reimplements
the state machine, so this eval and the live guard can't drift apart.

Usage:
    python -m agent.eval.runners.run_research_order_eval
"""

import argparse
import json

from agent.guardrails.research_order import (
    research_guard,
    authorize_research_source,
    authorize_peer_news,
    record_internal_news_result,
)
from agent.eval.confusion_matrix import load_fixture, score_binary, print_layer
from agent.eval.fixture_version import compute_fixture_version
from db.queries import insert_eval_run

DEFAULT_FIXTURE = "agent/eval/fixtures/research_order_test_set.json"

_ACTIONS = {
    "record_internal_news_result": lambda step: record_internal_news_result(step["found"]),
    "authorize_research_source": lambda step: authorize_research_source(step["source"]),
    "authorize_peer_news": lambda step: authorize_peer_news(step["source"]),
}


def _replay(steps: list[dict]) -> bool:
    """Runs one fixture row's step sequence inside a fresh guard scope and returns
    whether the FINAL step was blocked - the outcome under test. Earlier steps set up
    guard state (e.g. record_internal_news_result) the same way real tool calls would."""
    with research_guard():
        decision = None
        for step in steps:
            decision = _ACTIONS[step["action"]](step)
        return not decision.allowed if decision is not None else False


def score_research_order(rows: list[dict]) -> dict:
    return score_binary(rows, lambda row: _replay(row["steps"]))


def run_research_order_eval(fixture_path: str = DEFAULT_FIXTURE, persist: bool = True) -> dict:
    rows = load_fixture(fixture_path)
    print(f"Scoring research-order guard ({len(rows)} labeled call sequences)...")
    scores = score_research_order(rows)
    print_layer("guard", scores)

    if persist:
        insert_eval_run(
            "research_order", {"fixture": fixture_path, "summary": scores},
            fixture_version=compute_fixture_version(fixture_path),
        )
        print("\nLogged this run to eval_runs (visible on the admin page).")

    return scores


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", default=DEFAULT_FIXTURE)
    parser.add_argument("--output", default=None, help="Optional path to also write the summary as JSON.")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    result = run_research_order_eval(args.fixture, persist=not args.no_persist)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote results to {args.output}")
