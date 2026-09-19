"""
Runs the full pipeline eval suite end to end - the "before promoting to main" gate:

  3. Evidence selection   (runners/run_evidence_selection_eval.py) - deterministic, no judge
  4. Per-feed analysis    (runners/run_feed_summary_eval.py)    - groundedness + completeness
  5. Final synthesis      (runners/run_insight_eval.py)         - groundedness + completeness
  7. Judge drift check    (runners/run_judge_drift_check.py)        - diffs stage 4/5's new
                                                                    results against the
                                                                    PREVIOUSLY persisted run

Stages 1/2/6 (input guardrail, feed classification, output guardrail) already have their
own eval entry points (runners/run_guardrail_eval.py, run_classification_eval.py) -
deliberately not re-run here, this script covers only the stages this eval round
added/wired up.

Every stage persists to eval_runs as it goes (unless --no-persist), which is what makes
step 7 possible immediately: it compares the run this script JUST wrote against whatever
was there before. Step 7 never blocks - see run_judge_drift_check.py's own docstring for why
(no calibrated threshold to auto-gate on yet; flagged items are for human review).

Usage:
    python -m agent.eval.run_pre_merge_gate
    python -m agent.eval.run_pre_merge_gate --no-persist
"""

import argparse
import json

from agent.eval.runners.run_evidence_selection_eval import run_evidence_selection_eval
from agent.eval.runners.run_feed_summary_eval import run_feed_summary_eval
from agent.eval.runners.run_insight_eval import run_insight_eval
from agent.eval.runners.run_judge_drift_check import run_judge_drift_check


def run_pre_merge_gate(persist: bool = True, drift_threshold: int = 10) -> dict:
    print("=== Stage 3: evidence selection ===")
    evidence_selection = run_evidence_selection_eval(persist=persist)
    print(f"needs_reports accuracy={evidence_selection['summary']['needs_reports_accuracy']} "
          f"needs_peer_news accuracy={evidence_selection['summary']['needs_peer_news_accuracy']}")

    print("\n=== Stage 4: per-feed analysis (feed summary) ===")
    feed_summary = run_feed_summary_eval(persist=persist)
    print(f"avg groundedness={feed_summary['summary']['avg_groundedness_pct']}% "
          f"avg completeness={feed_summary['summary']['avg_completeness_pct']}%")

    print("\n=== Stage 5: final synthesis (insight) ===")
    insight = run_insight_eval(persist=persist)
    print(f"% grounded={insight['summary']['pct_grounded']} "
          f"avg completeness={insight['summary']['avg_completeness_pct']}%")

    print("\n=== Stage 7: judge drift (vs. previous run) ===")
    if not persist:
        print("Skipped - drift check needs this run persisted to compare against the next one; "
              "re-run without --no-persist to enable it.")
        drift = {"feed_summary": None, "insight_quality": None}
    else:
        drift = {
            "feed_summary": run_judge_drift_check("feed_summary", threshold=drift_threshold, persist=True),
            "insight_quality": run_judge_drift_check("insight_quality", threshold=drift_threshold, persist=True),
        }
        for eval_type, report in drift.items():
            if report["status"] == "no_baseline":
                print(f"[{eval_type}] {report['message']}")
            else:
                print(f"[{eval_type}] {report['n_flagged']}/{report['n_matched']} items flagged "
                      f"(>= {report['threshold']} pt delta) - see eval_runs (eval_type='judge_drift') for detail.")

    return {
        "evidence_selection": evidence_selection["summary"],
        "feed_summary": feed_summary["summary"],
        "insight": insight["summary"],
        "judge_drift": drift,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=int, default=10, help="Judge-drift flag threshold, in percentage points.")
    parser.add_argument("--output", default="agent/eval/results/pre_merge_gate.json")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Dry run - don't write any of these runs to eval_runs (also disables the stage 7 drift check, "
        "which needs a persisted previous run to compare against).",
    )
    args = parser.parse_args()

    output = run_pre_merge_gate(persist=not args.no_persist, drift_threshold=args.threshold)

    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, default=str)
    print(f"\nWrote full summary to {args.output}")
