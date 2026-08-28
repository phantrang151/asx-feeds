"""Shared binary-classification scoring for guardrail evals - every guardrail eval
(score_guardrails.py's regex/LLM advice checks, score_research_order.py's ordering
guard) reduces to the same question: does `predict(row)` flag/block a row that's
labeled actually-bad in a fixture? Kept as one shared implementation so a metric
definition (e.g. what counts as a false positive) can't drift between guardrail types.
"""

import json


def load_fixture(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def score_binary(rows: list[dict], predict) -> dict:
    """`predict(row) -> bool` (True = this layer would flag/block the row). Returns
    confusion-matrix counts plus true_positive_rate (recall on actually-bad rows) and
    false_positive_rate (rate of wrongly flagging actually-clean rows)."""
    tp = fp = tn = fn = 0
    for row in rows:
        predicted_bad = predict(row)
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


def print_layer(name: str, scores: dict) -> None:
    print(f"  {name}: n={scores['n']} tp={scores['tp']} fp={scores['fp']} tn={scores['tn']} fn={scores['fn']} "
          f"TPR={scores['true_positive_rate']} FPR={scores['false_positive_rate']}")
