"""
Scores a filled-in labeling worksheet (see export_labels.py) against the classifier's
own top-1 candidate match, computing precision, recall, and false-skip-rate - either at
each row's own deployed match_threshold, or swept across a list of candidate thresholds
to help tune common_feed_templates.match_threshold.

Definitions (all relative to the single top-1 candidate a row was checked against):
  - predicted label = candidate_feed_name if candidate_similarity >= threshold, else "none"
  - precision = of rows predicted into a feed (not "none"), how many match correct_feed
  - recall     = of rows whose correct_feed isn't "none", how many were predicted correctly
  - false_skip_rate = of rows whose correct_feed isn't "none", how many got skipped to
                      "none" by the threshold specifically (a subset of recall misses -
                      the other subset is "matched, but the wrong feed", reported
                      separately as wrong_feed_count)

Usage:
    python -m eval.score_classification --labels eval/labeling_worksheet_filled.csv
    python -m eval.score_classification --labels eval/labeling_worksheet_filled.csv \
        --sweep-thresholds 0.15,0.20,0.22,0.25,0.30 --output eval/classification_scores.json
"""

import argparse
import csv
import json

from db.queries import insert_eval_run


def load_labels(path: str) -> list[dict]:
    with open(path, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    missing = [r["ticker_news_id"] for r in rows if not r.get("correct_feed", "").strip()]
    if missing:
        raise ValueError(
            f"{len(missing)} row(s) have no correct_feed filled in - label every row "
            f"('none' if no feed applies) before scoring."
        )
    return rows


def predict_label(row: dict, threshold: "float | None" = None) -> str:
    """threshold=None means 'use this row's own deployed candidate_threshold' - what
    scoring without --sweep-thresholds does, so each row is judged against the
    threshold it was actually classified with, not one global value."""
    similarity = row.get("candidate_similarity")
    if not similarity:
        return "none"
    effective_threshold = threshold if threshold is not None else float(row.get("candidate_threshold") or 0.0)
    return row["candidate_feed_name"] if float(similarity) >= effective_threshold else "none"


def score(rows: list[dict], threshold: "float | None" = None) -> dict:
    tp = fp = wrong_feed = false_skip = 0
    n_relevant = 0  # rows whose correct_feed isn't "none"

    for row in rows:
        correct = row["correct_feed"].strip()
        predicted = predict_label(row, threshold)
        is_relevant = correct.lower() != "none"
        if is_relevant:
            n_relevant += 1

        if predicted == "none":
            if is_relevant:
                false_skip += 1
        elif predicted == correct:
            tp += 1
        else:
            fp += 1
            if is_relevant:
                wrong_feed += 1

    fn = false_skip + wrong_feed
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / n_relevant if n_relevant else None
    false_skip_rate = false_skip / n_relevant if n_relevant else None

    return {
        "threshold": threshold,
        "n": len(rows),
        "n_relevant": n_relevant,
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "wrong_feed_count": wrong_feed,
        "false_skip_count": false_skip,
        "precision": round(precision, 4) if precision is not None else None,
        "recall": round(recall, 4) if recall is not None else None,
        "false_skip_rate": round(false_skip_rate, 4) if false_skip_rate is not None else None,
    }


def _print_table(results: list[dict]) -> None:
    header = f"{'threshold':>9} {'n':>4} {'precision':>9} {'recall':>7} {'false_skip_rate':>16}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r['threshold']:>9} {r['n']:>4} "
            f"{r['precision'] if r['precision'] is not None else '-':>9} "
            f"{r['recall'] if r['recall'] is not None else '-':>7} "
            f"{r['false_skip_rate'] if r['false_skip_rate'] is not None else '-':>16}"
        )


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", required=True)
    parser.add_argument("--sweep-thresholds", default=None, help="Comma-separated thresholds, e.g. 0.15,0.20,0.25")
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    rows = load_labels(args.labels)

    if args.sweep_thresholds:
        thresholds = [float(t) for t in args.sweep_thresholds.split(",")]
        results = [score(rows, t) for t in thresholds]
    else:
        # threshold=None -> each row scored against its OWN deployed candidate_threshold
        # (candidate_threshold can differ per template), not one global value.
        results = [score(rows, None)]
        results[0]["threshold"] = "as-deployed (each row's own candidate_threshold)"

    _print_table(results)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=2)
        print(f"\nWrote results to {args.output}")

    if not args.no_persist:
        insert_eval_run("classification", {"labels_file": args.labels, "results": results})
        print("Logged this run to eval_runs (visible on the admin page).")
