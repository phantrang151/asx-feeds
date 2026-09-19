"""
Scores a filled-in labeling worksheet (see export_labels.py) against the classifier's
own top-1 candidate match, computing precision, recall, and false-skip-rate - either at
each row's own deployed match_threshold, or swept across a list of candidate thresholds
to help tune common_feed_templates.match_threshold.

The worksheet only ever holds INPUT (title/snippet/publisher/...) and the human's
correct_feed/explanation label - never the classifier's own candidate_feed_name/
candidate_similarity/candidate_threshold. Those are computed fresh, every run, by
classify_rows() actually calling the live classifier (agent.shared.news_text
.format_news_content + tools.embeddings.embed + match_common_feed_template_for_embedding)
- the same three functions that decide a real article's feed in production. Storing the
classifier's own output as a static CSV column would mean this eval silently stops
reflecting reality the moment a template description, threshold, or embedding changes,
which is exactly what happened before this refactor: every template/embedding change
this session needed a manual "please re-run classification and update the CSV" step.
Computing fresh means that step no longer exists - re-running this script always
reflects whatever's live right now.

Definitions (all relative to the single top-1 candidate a row was checked against):
  - predicted label = candidate_feed_name if candidate_similarity >= threshold, else "none"
  - precision = of rows predicted into a feed (not "none"), how many match correct_feed
  - recall     = of rows whose correct_feed isn't "none", how many were predicted correctly
  - false_skip_rate = of rows whose correct_feed isn't "none", how many got skipped to
                      "none" by the threshold specifically (a subset of recall misses -
                      the other subset is "matched, but the wrong feed", reported
                      separately as wrong_feed_count)

Usage:
    python -m agent.eval.runners.run_classification_eval --labels agent/eval/fixtures/labeling_worksheet.csv
    python -m agent.eval.runners.run_classification_eval --labels agent/eval/fixtures/labeling_worksheet.csv \
    --sweep-thresholds 0.15,0.20,0.22,0.25,0.30 --output agent/eval/classification_scores.json
"""

import argparse
import csv
import json

from tools.embeddings import embed
from agent.shared.news_text import format_news_content
from agent.eval.fixture_version import compute_fixture_version
from db.queries import insert_eval_run, match_common_feed_template_for_embedding

# Conventional path a filled-in labeling worksheet is saved to (see export_labels.py's
# own --output default) - lets the admin-triggered route below re-score against
# whatever was labeled last without needing a file path passed in from the frontend.
DEFAULT_LABELS_PATH = "agent/eval/fixtures/labeling_worksheet.csv"


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


def classify_rows(rows: list[dict]) -> list[dict]:
    """Computes each row's real top-1 common-feed-template candidate fresh, by calling
    the same functions the live pipeline uses to classify a real article - never reads a
    precomputed candidate from the CSV (see this module's own docstring for why). Runs
    once regardless of --sweep-thresholds - the candidate itself doesn't depend on the
    threshold being tested, only the accept/reject decision does."""
    classified = []
    for row in rows:
        embedding = embed(format_news_content(row["title"], row.get("snippet") or None))
        matches = match_common_feed_template_for_embedding(embedding, match_count=1)
        top = matches[0] if matches else None
        classified.append({
            **row,
            "candidate_feed_name": top["name"] if top else "",
            "candidate_similarity": top["similarity"] if top else "",
            "candidate_threshold": top["match_threshold"] if top else "",
        })
    return classified


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

    # The threshold(s) actually live in common_feed_templates.match_threshold right now -
    # candidate_threshold is each row's own copy of whatever was deployed when it was
    # classified (see export_labels.py). Surfaced here as a plain fact about the labeled
    # sample, separate from `threshold` above (which is None in as-deployed mode, or
    # whatever --sweep-thresholds/--roc-auc is currently testing).
    deployed_thresholds = sorted({
        float(r["candidate_threshold"]) for r in rows if r.get("candidate_threshold") not in (None, "")
    })

    return {
        "threshold": threshold,
        "deployed_thresholds": deployed_thresholds,
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


def compute_pr_auc(rows: list[dict], beta: float = 2.0) -> dict:
    """Binarizes the multi-class matching problem into "should this row's own top-1
    candidate be accepted" (positive = candidate_feed_name is actually correct_feed,
    negative = it isn't - either a different feed was correct or none was) and sweeps
    every OBSERVED candidate_similarity value as a threshold, unlike --sweep-thresholds'
    fixed candidate list - giving a genuine precision-recall curve/AUC for tuning
    common_feed_templates.match_threshold. A row with no candidate scores 0.0 (can never
    be accepted at any real threshold, correctly penalizing recall throughout).

    Precision-recall, not ROC: real news is heavily skewed toward "belongs to none of
    the 3 templates" (most Yahoo coverage is valuation narrative or analyst commentary,
    not reported results or a specific strategic decision - see the labeling worksheet's
    own class balance). ROC's false-positive-rate term is diluted by that large negative
    pool and overstates how good a threshold looks; precision and recall never involve
    true negatives at all, so they stay honest about the tradeoff that actually matters
    on an imbalanced feed. The AUC here is Average Precision (sum of
    recall-step * precision, walking thresholds high to low) rather than naive
    trapezoidal area, since precision isn't guaranteed monotonic the way recall is.

    Reports TWO different "best threshold" picks, because they optimize for different
    error costs and neither is automatically right:
      - best_threshold (max F1) treats a missed match (false negative) and a
        wrongly-accepted match (false positive) as equally costly.
      - best_threshold_recall_weighted (max F-beta, beta > 1 weights recall over
        precision) - for this app, a missed match silently drops real evidence from a
        feed (the user never sees it), while a wrongly-accepted match is just noise the
        user skims past. beta=2 means recall matters ~4x as much as precision when
        picking the operating point; raise beta further to weight recall even more."""
    pairs = [
        (
            float(row.get("candidate_similarity") or 0.0),
            row["correct_feed"].strip().lower() not in ("none", "")
            and row["correct_feed"].strip().lower() == (row.get("candidate_feed_name") or "").strip().lower(),
        )
        for row in rows
    ]
    n_pos = sum(1 for _, label in pairs if label)
    if n_pos == 0:
        return {
            "auc": None,
            "beta": beta,
            "best_threshold": None,
            "best_threshold_metrics": None,
            "best_threshold_recall_weighted": None,
            "best_threshold_recall_weighted_metrics": None,
            "pr_points": [],
        }

    pairs.sort(key=lambda p: p[0], reverse=True)

    # sentinel: accept nothing - precision is undefined (0/0) here, left as None rather
    # than 0 so it can never win the F-score search below.
    pr_points = [{"threshold": None, "recall": 0.0, "precision": None}]
    tp = fp = 0
    prev_score = None
    for candidate_score, label in pairs:
        if prev_score is not None and candidate_score != prev_score:
            pr_points.append({
                "threshold": prev_score,
                "recall": round(tp / n_pos, 4),
                "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
            })
        tp, fp = (tp + 1, fp) if label else (tp, fp + 1)
        prev_score = candidate_score
    pr_points.append({
        "threshold": prev_score,
        "recall": round(tp / n_pos, 4),
        "precision": round(tp / (tp + fp), 4) if (tp + fp) else None,
    })

    # Average precision: recall is non-decreasing in this walk order (each step adds
    # either a TP, moving recall forward, or an FP, leaving it unchanged), so this sum
    # is well-defined without needing precision itself to be monotonic.
    auc = sum(
        (b["recall"] - a["recall"]) * b["precision"]
        for a, b in zip(pr_points, pr_points[1:])
        if b["precision"] is not None
    )

    def f1(point: dict) -> float:
        if not point["precision"]:  # None or 0.0 - nothing usable accepted at this point
            return -1.0
        precision, recall = point["precision"], point["recall"]
        return 2 * precision * recall / (precision + recall) if (precision + recall) else -1.0

    best = max((p for p in pr_points if p["threshold"] is not None), key=f1)

    def f_beta(point: dict) -> float:
        if not point["precision"]:  # None or 0.0 - nothing usable accepted at this point
            return -1.0
        precision, recall = point["precision"], point["recall"]
        denom = beta**2 * precision + recall
        return (1 + beta**2) * precision * recall / denom if denom else -1.0

    best_rw = max((p for p in pr_points if p["threshold"] is not None), key=f_beta)

    return {
        "auc": round(auc, 4),
        "beta": beta,
        "best_threshold": best["threshold"],
        "best_threshold_metrics": {"recall": best["recall"], "precision": best["precision"]},
        "best_threshold_recall_weighted": best_rw["threshold"],
        "best_threshold_recall_weighted_metrics": {
            "recall": best_rw["recall"],
            "precision": best_rw["precision"],
            "f_beta": round(f_beta(best_rw), 4),
        },
        "pr_points": pr_points,
    }


def _print_table(results: list[dict]) -> None:
    header = f"{'threshold':>9} {'deployed':>10} {'n':>4} {'precision':>9} {'recall':>7} {'false_skip_rate':>16}"
    print(header)
    print("-" * len(header))
    for r in results:
        deployed = ",".join(str(t) for t in r.get("deployed_thresholds") or []) or "-"
        print(
            f"{r['threshold']:>9} {deployed:>10} {r['n']:>4} "
            f"{r['precision'] if r['precision'] is not None else '-':>9} "
            f"{r['recall'] if r['recall'] is not None else '-':>7} "
            f"{r['false_skip_rate'] if r['false_skip_rate'] is not None else '-':>16}"
        )


def run_classification_eval(
    labels_path: str = DEFAULT_LABELS_PATH,
    sweep_thresholds: "list[float] | None" = None,
    pr_auc: bool = True,
    beta: float = 2.0,
    persist: bool = True,
) -> dict:
    """Scores `labels_path` (a filled-in labeling worksheet - see export_labels.py) and
    returns {"labels_file", "results", "pr_auc"} - the one function both this script's
    __main__ block AND the admin-triggered POST /api/admin/eval/classification/trigger
    route call. Unlike every other eval type, this needs a human-labeled file to exist
    on disk already; re-scoring an EXISTING one needs no new labeling, so this is safe
    to trigger repeatedly - e.g. right after changing match_threshold or the
    classifier's embedding/prompt - as long as the file's correct_feed ground truth is
    still valid for the current news. pr_auc defaults to True here (unlike the CLI's
    opt-in --pr-auc flag) since the admin trigger's whole point is a quick before/after
    comparison, and the curve is cheap to compute either way. `beta` controls
    compute_pr_auc's recall-weighted best-threshold pick - see that function's
    docstring; the default (2.0) reflects that a missed feed match costs more here than
    an extra false-positive one."""
    rows = load_labels(labels_path)
    rows = classify_rows(rows)

    if sweep_thresholds:
        results = [score(rows, t) for t in sweep_thresholds]
    else:
        # threshold=None -> each row scored against its OWN deployed candidate_threshold
        # (candidate_threshold can differ per template), not one global value.
        results = [score(rows, None)]
        results[0]["threshold"] = "as-deployed (each row's own candidate_threshold)"

    pr = compute_pr_auc(rows, beta=beta) if pr_auc else None
    output = {"labels_file": labels_path, "results": results, "pr_auc": pr}

    if persist:
        insert_eval_run("classification", output, fixture_version=compute_fixture_version(labels_path))

    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--labels", default=DEFAULT_LABELS_PATH)
    parser.add_argument("--sweep-thresholds", default=None, help="Comma-separated thresholds, e.g. 0.15,0.20,0.25")
    parser.add_argument(
        "--pr-auc", action="store_true",
        help="Also compute a full precision-recall curve/AUC (Average Precision), a best-F1 "
        "threshold, and a recall-weighted (F-beta) threshold, swept over every observed "
        "candidate_similarity value.",
    )
    parser.add_argument(
        "--beta", type=float, default=2.0,
        help="F-beta weight for the recall-weighted best threshold (beta > 1 favors recall over "
        "precision; default 2.0 - a missed feed match costs more here than an extra false positive).",
    )
    parser.add_argument("--output", default=None)
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    thresholds = [float(t) for t in args.sweep_thresholds.split(",")] if args.sweep_thresholds else None
    output = run_classification_eval(
        args.labels, sweep_thresholds=thresholds, pr_auc=args.pr_auc, beta=args.beta,
        persist=not args.no_persist,
    )

    _print_table(output["results"])
    if output["pr_auc"]:
        pr = output["pr_auc"]
        best, best_rw = pr["best_threshold_metrics"], pr["best_threshold_recall_weighted_metrics"]
        print(f"\nPR AUC (Average Precision): {pr['auc']}")
        print(f"Best threshold (max F1): {pr['best_threshold']} "
              f"(recall={best['recall'] if best else None}, "
              f"precision={best['precision'] if best else None})")
        print(f"Best threshold (recall-weighted, F{pr['beta']:g}): {pr['best_threshold_recall_weighted']} "
              f"(recall={best_rw['recall'] if best_rw else None}, "
              f"precision={best_rw['precision'] if best_rw else None})")

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(output, f, indent=2)
        print(f"\nWrote results to {args.output}")

    if not args.no_persist:
        print("Logged this run to eval_runs (visible on the admin page).")
