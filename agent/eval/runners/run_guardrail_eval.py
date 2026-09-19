"""
Per-layer true-positive/false-positive rate for both guardrails' two layers, against a
small hand-labeled adversarial+quality test set (see agent/eval/fixtures/*_guardrail_test_set.json).
Deliberately scores each layer INDEPENDENTLY on the full set - not the fail-fast
pipeline behaviour check_advice_avoidance/router_node actually run in production - so
you can see whether the cheap regex layer is pulling its weight (catching real cases
without adding false positives on legitimate questions/answers) or whether the LLM
layer is doing all the real work.

Reuses the exact same functions the live guardrails call
(agent.chat.nodes.classify_request, agent.guardrails.advice_check.keyword_scan/
keyword_scan_advice_seeking/llm_judge_advice_check) rather than reimplementing the
checks - so this eval and the live gates can never drift apart.

Makes real, live Groq calls for the LLM layers (router classification, advice-check
judge) - not free, not instant.

Usage:
    python -m agent.eval.runners.run_guardrail_eval
    python -m agent.eval.runners.run_guardrail_eval --output agent/eval/results/guardrail_scores.json
"""

import argparse
import json

from langchain_core.messages import HumanMessage

from agent.chat.nodes import classify_request
from agent.guardrails.advice_check import keyword_scan, keyword_scan_advice_seeking, llm_judge_advice_check
from agent.eval.confusion_matrix import load_fixture, score_binary, print_layer
from agent.eval.fixture_version import compute_fixture_version
from db.queries import insert_eval_run

DEFAULT_INPUT_FIXTURE = "agent/eval/fixtures/input_guardrail_test_set.json"
DEFAULT_OUTPUT_FIXTURE = "agent/eval/fixtures/output_guardrail_test_set.json"


def score_input_guardrail(rows: list[dict]) -> dict:
    regex = score_binary(rows, lambda row: bool(keyword_scan_advice_seeking(row["text"])))
    llm = score_binary(rows, lambda row: classify_request([HumanMessage(content=row["text"])]).is_advice_seeking)
    return {"regex_layer": regex, "llm_layer": llm}


def score_output_guardrail(rows: list[dict]) -> dict:
    regex = score_binary(rows, lambda row: bool(keyword_scan(row["text"])))
    llm = score_binary(rows, lambda row: llm_judge_advice_check(row["text"]).is_advice)
    return {"regex_layer": regex, "llm_layer": llm}


def run_guardrail_eval(
    input_fixture: str = DEFAULT_INPUT_FIXTURE,
    output_fixture: str = DEFAULT_OUTPUT_FIXTURE,
    persist: bool = True,
) -> dict:
    input_rows = load_fixture(input_fixture)
    output_rows = load_fixture(output_fixture)

    print(f"Scoring input guardrail ({len(input_rows)} labeled questions)...")
    input_scores = score_input_guardrail(input_rows)
    print(f"Scoring output guardrail ({len(output_rows)} labeled answers)...")
    output_scores = score_output_guardrail(output_rows)

    summary = {"input_guardrail": input_scores, "output_guardrail": output_scores}

    print("\nInput guardrail (advice-seeking questions):")
    print_layer("regex", input_scores["regex_layer"])
    print_layer("llm  ", input_scores["llm_layer"])
    print("Output guardrail (advice-giving answers):")
    print_layer("regex", output_scores["regex_layer"])
    print_layer("llm  ", output_scores["llm_layer"])

    if persist:
        insert_eval_run(
            "guardrails", {"input_fixture": input_fixture, "output_fixture": output_fixture, "summary": summary},
            fixture_version=compute_fixture_version(input_fixture, output_fixture),
        )
        print("\nLogged this run to eval_runs (visible on the admin page).")

    return summary


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-fixture", default=DEFAULT_INPUT_FIXTURE)
    parser.add_argument("--output-fixture", default=DEFAULT_OUTPUT_FIXTURE)
    parser.add_argument("--output", default=None, help="Optional path to also write the summary as JSON.")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    result = run_guardrail_eval(args.input_fixture, args.output_fixture, persist=not args.no_persist)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"Wrote results to {args.output}")
