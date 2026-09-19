"""
Stage 7 of the pipeline eval plan: judge calibration / drift check.

When the judge prompt (agent/eval/judge.py) or a scored stage's own prompt changes, this
compares the LATEST persisted eval_runs row for a given eval_type against the run before
it, item-by-item (matched on each fixture row's stable "id"), for groundedness_pct and
completeness coverage_pct. It does NOT call a judge LLM itself - "did the judge's
opinion change" is answered by diffing two already-recorded score sets, not by asking a
third model to grade the difference. See the project's saved eval-architecture notes for
why: a second judge grading the first judge is an unanchored infinite regress, and
doesn't tell you whether a change is a regression or an improvement - only a human (or,
for the correctness question specifically, a small human-labeled gold set) can decide
that. This script's job is narrower and mechanical: surface which items moved, and by
how much, so a human doesn't have to eyeball a full diff.

Bootstrapping: if fewer than 2 runs exist yet for this eval_type, there is nothing to
diff against - every item is reported as "no baseline yet", meaning a human should
review the full run directly (see run_feed_summary_eval.py / run_insight_eval.py output)
rather than relying on this script. That first human-reviewed run becomes round 1's
baseline for every future drift check.

This is a soft gate, not a hard one: flagged items are reported for human review, never
used to fail a build or block a merge on their own (a threshold that hasn't been
calibrated yet WILL produce false positives - see the project's eval-architecture memory
for why an auto-block was deliberately rejected here).

Usage:
    python -m agent.eval.runners.run_judge_drift_check --eval-type feed_summary
    python -m agent.eval.runners.run_judge_drift_check --eval-type insight_quality --threshold 15
"""

import argparse
import json

from db.queries import get_recent_eval_runs, insert_eval_run

DEFAULT_THRESHOLD = 10  # percentage points, on either groundedness_pct or coverage_pct

# Which two 0-100 metrics to diff for each eval_type's per-item results, and where to
# read them from (run_feed_summary_eval.py / run_insight_eval.py both use this same
# {"groundedness": {"groundedness_pct": ...}, "completeness": {"coverage_pct": ...}}
# shape - see run_one() in each runner).
_METRIC_PATHS = {
    "groundedness_pct": ("groundedness", "groundedness_pct"),
    "completeness_pct": ("completeness", "coverage_pct"),
}


def _get(item: dict, path: tuple) -> "int | None":
    node = item
    for key in path:
        if node is None:
            return None
        node = node.get(key)
    return node


def _index_by_id(results: list[dict]) -> dict:
    return {r["id"]: r for r in results if r.get("id")}


def diff_runs(old_results: list[dict], new_results: list[dict], threshold: int) -> dict:
    old_by_id = _index_by_id(old_results)
    new_by_id = _index_by_id(new_results)

    matched, new_items, removed_items = [], [], []

    for item_id, new_item in new_by_id.items():
        old_item = old_by_id.get(item_id)
        if old_item is None:
            new_items.append(item_id)
            continue

        deltas = {}
        flagged = False
        for metric_name, path in _METRIC_PATHS.items():
            old_val, new_val = _get(old_item, path), _get(new_item, path)
            delta = (new_val - old_val) if (old_val is not None and new_val is not None) else None
            deltas[metric_name] = {"old": old_val, "new": new_val, "delta": delta}
            if delta is not None and abs(delta) >= threshold:
                flagged = True

        matched.append({"id": item_id, "deltas": deltas, "flagged": flagged})

    removed_items = [item_id for item_id in old_by_id if item_id not in new_by_id]

    n_matched = len(matched)
    n_flagged = sum(1 for m in matched if m["flagged"])

    return {
        "threshold": threshold,
        "n_matched": n_matched,
        "n_flagged": n_flagged,
        "flagged_rate": round(n_flagged / n_matched, 4) if n_matched else None,
        "matched": matched,
        "new_items_no_baseline": new_items,
        "removed_items": removed_items,
    }


def run_judge_drift_check(eval_type: str, threshold: int = DEFAULT_THRESHOLD, persist: bool = True) -> dict:
    runs = get_recent_eval_runs(eval_type, limit=2)

    if len(runs) < 2:
        report = {
            "eval_type": eval_type,
            "status": "no_baseline",
            "message": (
                f"Fewer than 2 recorded runs for eval_type={eval_type!r} - nothing to diff yet. "
                "This is expected for the first run of a new judge/prompt: review this run's "
                "results directly (run_feed_summary_eval.py / run_insight_eval.py output), since "
                "a human review of THIS run becomes the baseline every future drift check compares against."
            ),
        }
        if persist:
            insert_eval_run("judge_drift", report)
        return report

    new_run, old_run = runs[0], runs[1]
    old_results = old_run["summary"].get("results", [])
    new_results = new_run["summary"].get("results", [])

    diff = diff_runs(old_results, new_results, threshold)
    # fixture_version (see agent/eval/fixture_version.py) is a content hash of the
    # fixture file(s) each run was scored against. If it differs between the two runs
    # being compared, any per-item delta below may be caused by someone editing the
    # fixture (a new/changed feed_description, article, evidence set, ...), not by the
    # judge or prompt actually drifting - the two are otherwise indistinguishable from
    # score deltas alone, so this has to be surfaced explicitly rather than left for a
    # human to discover only after mis-attributing a flagged item.
    fixture_changed = (
        old_run.get("fixture_version") is not None
        and new_run.get("fixture_version") is not None
        and old_run.get("fixture_version") != new_run.get("fixture_version")
    )
    report = {
        "eval_type": eval_type,
        "status": "compared",
        "old_run_id": old_run.get("id"),
        "old_run_created_at": old_run.get("created_at"),
        "old_fixture_version": old_run.get("fixture_version"),
        "new_run_id": new_run.get("id"),
        "new_run_created_at": new_run.get("created_at"),
        "new_fixture_version": new_run.get("fixture_version"),
        "fixture_changed": fixture_changed,
        **diff,
    }

    if persist:
        insert_eval_run("judge_drift", report)

    return report


def _print_report(report: dict) -> None:
    if report["status"] == "no_baseline":
        print(report["message"])
        return

    print(f"Comparing eval_type={report['eval_type']!r}: "
          f"run {report['old_run_created_at']} -> {report['new_run_created_at']}")
    if report.get("fixture_changed"):
        print(f"** FIXTURE CHANGED between these two runs ({report['old_fixture_version']} -> "
              f"{report['new_fixture_version']}) - deltas below may reflect an edited test case, "
              "not judge/prompt drift. **")
    print(f"Matched items: {report['n_matched']}  Flagged (>= {report['threshold']} pt delta): {report['n_flagged']} "
          f"({report['flagged_rate']})")
    if report["new_items_no_baseline"]:
        print(f"New items with no prior baseline (skipped from drift calc): {report['new_items_no_baseline']}")
    if report["removed_items"]:
        print(f"Items in the old run no longer in the fixture: {report['removed_items']}")

    if report["n_flagged"]:
        print("\nFlagged for human review:")
        for m in report["matched"]:
            if not m["flagged"]:
                continue
            g, c = m["deltas"]["groundedness_pct"], m["deltas"]["completeness_pct"]
            print(f"  - {m['id']}: groundedness {g['old']} -> {g['new']} (Δ{g['delta']}), "
                  f"completeness {c['old']} -> {c['new']} (Δ{c['delta']})")
    else:
        print("No items exceeded the drift threshold.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-type", required=True, choices=["feed_summary", "insight_quality"])
    parser.add_argument("--threshold", type=int, default=DEFAULT_THRESHOLD)
    parser.add_argument("--output", default=None, help="Optional path to also write the report as JSON.")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    result = run_judge_drift_check(args.eval_type, threshold=args.threshold, persist=not args.no_persist)
    _print_report(result)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2)
        print(f"\nWrote report to {args.output}")
