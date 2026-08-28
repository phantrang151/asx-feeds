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
    python -m agent.eval.score_classification --labels agent/eval/labeling_worksheet_filled.csv
    python -m agent.eval.score_classification --labels agent/eval/labeling_worksheet_filled.csv \
    --sweep-thresholds 0.15,0.20,0.22,0.25,0.30 --output agent/eval/classification_scores.json
"""

import argparse
import csv
import json

from db.queries import insert_eval_run

# Conventional path a filled-in labeling worksheet is saved to (see export_labels.py's
# own --output default) - lets the admin-triggered route below re-score against
# whatever was labeled last without needing a file path passed in from the frontend.
DEFAULT_LABELS_PATH = "agent/eval/labeling_worksheet_filled.csv"


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
    scored_rows = []

    for row in rows:
        correct = row["correct_feed"].strip()
        predicted = predict_label(row, threshold)
        is_relevant = correct.lower() != "none"
        if is_relevant:
            n_relevant += 1

        if predicted == "none":
            outcome = "false_skip" if is_relevant else "correct"
            if is_relevant:
                false_skip += 1
        elif predicted == correct:
            outcome = "correct"
            tp += 1
        else:
            outcome = "wrong_feed"
            fp += 1
            if is_relevant:
                wrong_feed += 1

        # title/ticker_news_id come straight from export_labels.py's worksheet columns -
        # the admin page's per-item card view needs the article's own headline text,
        # which the aggregate counts above don't carry.
        scored_rows.append({
            "title": row.get("title"),
            "correct_feed": correct,
            "predicted_feed": predicted,
            "similarity": float(row["candidate_similarity"]) if row.get("candidate_similarity") else None,
            "outcome": outcome,
        })

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
        "rows": scored_rows,
    }


def compute_roc_auc(rows: list[dict]) -> dict:
    """Binarizes the multi-class matching problem into "should this row's own top-1
    candidate be accepted" (positive = candidate_feed_name is actually correct_feed,
    negative = it isn't - either a different feed was correct or none was) and sweeps
    every OBSERVED candidate_similarity value as a threshold, unlike --sweep-thresholds'
    fixed candidate list - giving a genuine ROC curve/AUC and a data-derived best
    threshold (Youden's J: the point maximizing tpr - fpr) for tuning
    common_feed_templates.match_threshold. A row with no candidate scores 0.0 (can never
    be accepted at any real threshold, correctly penalizing recall throughout)."""
    pairs = [
        (
            float(row.get("candidate_similarity") or 0.0),
            row["correct_feed"].strip().lower() not in ("none", "")
            and row["correct_feed"].strip().lower() == (row.get("candidate_feed_name") or "").strip().lower(),
        )
        for row in rows
    ]
    n_pos = sum(1 for _, label in pairs if label)
    n_neg = len(pairs) - n_pos
    if n_pos == 0 or n_neg == 0:
        return {"auc": None, "best_threshold": None, "best_threshold_metrics": None, "roc_points": []}

    pairs.sort(key=lambda p: p[0], reverse=True)

    roc_points = [{"threshold": None, "fpr": 0.0, "tpr": 0.0}]  # sentinel: accept nothing
    tp = fp = 0
    prev_score = None
    for candidate_score, label in pairs:
        if prev_score is not None and candidate_score != prev_score:
            roc_points.append({"threshold": prev_score, "fpr": round(fp / n_neg, 4), "tpr": round(tp / n_pos, 4)})
        tp, fp = (tp + 1, fp) if label else (tp, fp + 1)
        prev_score = candidate_score
    roc_points.append({"threshold": prev_score, "fpr": round(fp / n_neg, 4), "tpr": round(tp / n_pos, 4)})

    auc = sum(
        (b["fpr"] - a["fpr"]) * (a["tpr"] + b["tpr"]) / 2 for a, b in zip(roc_points, roc_points[1:])
    )
    best = max((p for p in roc_points if p["threshold"] is not None), key=lambda p: p["tpr"] - p["fpr"])

    return {
        "auc": round(auc, 4),
        "best_threshold": best["threshold"],
        "best_threshold_metrics": {"tpr": best["tpr"], "fpr": best["fpr"]},
        "roc_points": roc_points,
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


def run_classification_eval(
    labels_path: str = DEFAULT_LABELS_PATH,
    sweep_thresholds: "list[float] | None" = None,
    roc_auc: bool = True,
    persist: bool = True,
) -> dict:
    """Scores `labels_path` (a filled-in labeling worksheet - see export_labels.py) and
    returns {"labels_file", "results", "roc_auc"} - the one function both this script's
    __main__ block AND the admin-triggered POST /api/admin/eval/classification/trigger
    route call. Unlike every other eval type, this needs a human-labeled file to exist
    on disk already; re-scoring an EXISTING one needs no new labeling, so this is safe
    to trigger repeatedly - e.g. right after changing match_threshold or the
    classifier's embedding/prompt - as long as the file's correct_feed ground truth is
    still valid for the current news. roc_auc defaults to True here (unlike the CLI's
    opt-in --roc-auc flag) since the admin trigger's whole point is a quick before/after
    comparison, and the curve is cheap to compute either way."""
    rows = load_labels(labels_path)

    if sweep_thresholds:
        results = [score(rows, t) for t in sweep_thresholds]
    else:
        # threshold=None -> each row scored against its OWN deployed candidate_threshold
        # (candidate_threshold can differ per template), not one global value.
        results = [score(rows, None)]
        results[0]["threshold"] = "as-deployed (each row's own candidate_threshold)"

    roc = compute_roc_auc(rows) if roc_auc else None
    output = {"labels_file": labels_path, "results": results, "roc_auc": roc}

    if persist:
        insert_eval_run("classification", output)

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=DEFAULT_LABELS_PATH)
    parser.add_argument("--sweep-thresholds", default=None, help="Comma-separated thresholds, e.g. 0.15,0.20,0.25")
    parser.add_argument(
        "--roc-auc", action="store_true",
        help="Also compute a full ROC curve/AUC and data-derived best threshold (Youden's J) "
        "swept over every observed candidate_similarity value.",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    thresholds = [float(t) for t in args.sweep_thresholds.split(",")] if args.sweep_thresholds else None
    output = run_classification_eval(
        args.labels, sweep_thresholds=thresholds, roc_auc=args.roc_auc, persist=not args.no_persist,
    )

    _print_table(output["results"])
    if output["roc_auc"]:
        best = output["roc_auc"]["best_threshold_metrics"]
        print(f"\nROC AUC: {output['roc_auc']['auc']}")
        print(f"Best threshold (Youden's J): {output['roc_auc']['best_threshold']} "
              f"(tpr={best['tpr'] if best else None}, fpr={best['fpr'] if best else None})")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"\nWrote results to {args.output}")

    if not args.no_persist:
        print("Logged this run to eval_runs (visible on the admin page).")
