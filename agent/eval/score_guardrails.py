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
    python -m agent.eval.score_guardrails
    python -m agent.eval.score_guardrails --output agent/eval/results/guardrail_scores.json
"""

import argparse
import json

from langchain_core.messages import HumanMessage

from agent.chat.nodes import classify_request
from agent.guardrails.advice_check import keyword_scan, keyword_scan_advice_seeking, llm_judge_advice_check
from db.queries import insert_eval_run

DEFAULT_INPUT_FIXTURE = "agent/eval/fixtures/input_guardrail_test_set.json"
DEFAULT_OUTPUT_FIXTURE = "agent/eval/fixtures/output_guardrail_test_set.json"


def _load(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _score(rows: list[dict], predict) -> dict:
    """`predict(text) -> bool` (True = this layer would flag/block it). Returns
    confusion-matrix counts plus true_positive_rate (recall on actually-bad items) and
    false_positive_rate (rate of wrongly flagging actually-clean items) - the two
    numbers 2.1/2.2 in the metrics catalog ask for."""
    tp = fp = tn = fn = 0
    for row in rows:
        predicted_bad = predict(row["text"])
        actual_bad = row["is_bad"]
        if predicted_bad and actual_bad:
            tp += 1
        elif predicted_bad and not actual_bad:
            fp += 1
        elif not predicted_bad and not actual_bad:
            tn += 1
        else:
            fn += 1
    n_bad = tp + fn
    n_clean = fp + tn
    return {
        "n": len(rows),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
        "true_positive_rate": round(tp / n_bad, 4) if n_bad else None,
        "false_positive_rate": round(fp / n_clean, 4) if n_clean else None,
    }


def score_input_guardrail(rows: list[dict]) -> dict:
    regex = _score(rows, lambda text: bool(keyword_scan_advice_seeking(text)))
    llm = _score(rows, lambda text: classify_request([HumanMessage(content=text)]).is_advice_seeking)
    return {"regex_layer": regex, "llm_layer": llm}


def score_output_guardrail(rows: list[dict]) -> dict:
    regex = _score(rows, lambda text: bool(keyword_scan(text)))
    llm = _score(rows, lambda text: llm_judge_advice_check(text).is_advice)
    return {"regex_layer": regex, "llm_layer": llm}


def _print_layer(name: str, scores: dict) -> None:
    print(f"  {name}: n={scores['n']} tp={scores['tp']} fp={scores['fp']} tn={scores['tn']} fn={scores['fn']} "
          f"TPR={scores['true_positive_rate']} FPR={scores['false_positive_rate']}")


def run_guardrail_eval(
    input_fixture: str = DEFAULT_INPUT_FIXTURE,
    output_fixture: str = DEFAULT_OUTPUT_FIXTURE,
    persist: bool = True,
) -> dict:
    input_rows = _load(input_fixture)
    output_rows = _load(output_fixture)

    print(f"Scoring input guardrail ({len(input_rows)} labeled questions)...")
    input_scores = score_input_guardrail(input_rows)
    print(f"Scoring output guardrail ({len(output_rows)} labeled answers)...")
    output_scores = score_output_guardrail(output_rows)

    summary = {"input_guardrail": input_scores, "output_guardrail": output_scores}

    print("\nInput guardrail (advice-seeking questions):")
    _print_layer("regex", input_scores["regex_layer"])
    _print_layer("llm  ", input_scores["llm_layer"])
    print("Output guardrail (advice-giving answers):")
    _print_layer("regex", output_scores["regex_layer"])
    _print_layer("llm  ", output_scores["llm_layer"])

    if persist:
        insert_eval_run("guardrails", {"input_fixture": input_fixture, "output_fixture": output_fixture, "summary": summary})
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
