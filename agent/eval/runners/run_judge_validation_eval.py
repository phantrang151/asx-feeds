"""
Validates the two LLM judges every quality number in this repo rests on -
agent/eval/judge.py::judge_groundedness and judge_completeness - against human labels,
instead of trusting them. (Why: an audit of the CBA retrieval experiment found ~37% of the
groundedness judge's "unsupported" flags were stated verbatim in the evidence.)

Three files, kept separate so judging and comparing never mix (see
agent/eval/judge_validation_compare.py):
  fixtures/judge_validation_test_set.json   ground truth (human labels)       - input
  results/judge_raw_answers.json            what the judges said              - step 1 writes
  results/judge_validation_comparison.json  judge vs human, item by item       - step 2 writes

Step 1 - judge (real JUDGE_MODEL calls, not free). Every judge sees only
judge_inputs(case), never a label:
  groundedness, per claim:   judge_groundedness(claim, evidence)
                             -> claims[].judge_covered_in_evidence
  completeness, per fact:    judge_completeness(question, answer, evidence=[that fact])
                             -> facts[].judge_covered_in_answer (true unless the judge lists the
                                fact in omitted_points - see fact_covered), raw % kept as
                                judge_completeness_pct. Run for relevant AND
                                irrelevant facts alike - the judge is never told which is which;
                                for an irrelevant fact the right answer is "not missing".
  whole answer, production-style (the judge finds its own claims/points):
                             judge_groundedness(answer, evidence), and
                             judge_completeness(question, answer, evidence) when the case has facts
Step 2 - compare (no LLM calls): joins the test set and the raw answers; persists the
summary to eval_runs. Also writes results/judge_groundedness_outputs.csv and
judge_completeness_outputs.csv - every judge call's full structured output (scores, issue
types, unsupported parts, explanations, omitted points) next to the human label, for reading
why the judge decided.

After editing only labels, re-run with --compare-only (free). After editing claim/fact
text or the judge prompts, run both steps.

Usage:
    python -m agent.eval.runners.run_judge_validation_eval --no-persist
    python -m agent.eval.runners.run_judge_validation_eval --only completeness --no-persist
    python -m agent.eval.runners.run_judge_validation_eval --compare-only --no-persist
"""

import argparse
import csv
import json
import os
from concurrent.futures import ThreadPoolExecutor

from agent.eval.confusion_matrix import load_fixture
from agent.eval.fixture_version import compute_fixture_version
from agent.eval.judge import judge_completeness, judge_groundedness
from agent.eval.judge_validation_compare import compare, fact_covered, is_fully_labelled, judge_inputs
from db.queries import insert_eval_run

DEFAULT_TEST_SET = "agent/eval/fixtures/judge_validation_test_set.json"
DEFAULT_RAW = "agent/eval/results/judge_raw_answers.json"
DEFAULT_COMPARISON = "agent/eval/results/judge_validation_comparison.json"
GROUNDEDNESS_CSV = "agent/eval/results/judge_groundedness_outputs.csv"
COMPLETENESS_CSV = "agent/eval/results/judge_completeness_outputs.csv"
# The two *_outputs.csv files show each judge call exactly as the application contract defines it:
# the inputs it was given, then the fields of GroundednessJudgment / CompletenessJudgment as returned
# (list fields kept as JSON text). No human labels and no derived verdicts - those are in the
# comparison file.
GROUNDEDNESS_CSV_COLUMNS = ["case_id", "call", "index", "text_judged", "evidence_given",
                            "groundedness_pct", "grounded", "unsupported_claims"]
COMPLETENESS_CSV_COLUMNS = ["case_id", "call", "index", "question", "answer", "evidence_given",
                            "coverage_pct", "omitted_points", "off_topic_points"]
MAX_WORKERS = 4  # parallel judge calls - keeps ~350 calls to minutes without hammering the API


def _completeness_calls(inputs: dict) -> tuple[list[dict], dict]:
    """Per-fact completeness calls plus the production-style whole-answer call (when the case
    has facts). `inputs` must come from judge_inputs() - it has no labels."""
    question, answer, evidence = inputs["question"], inputs["answer"], inputs["evidence"]

    def fact_call(fact: str) -> dict:
        c = judge_completeness(question, answer, [{"source": "expected_fact", "content": fact}])
        # the single fact is the only evidence, so any off_topic_points entry is the judge saying
        # this fact is off-topic for the question
        return {"fact": fact, "judge_relevant": not c.off_topic_points,
                "judge_covered_in_answer": fact_covered(c.model_dump()),
                "judge_completeness_pct": c.coverage_pct, "judge_output": c.model_dump()}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        facts = list(pool.map(fact_call, inputs["facts"]))
    whole = {"completeness_pct": None, "completeness_output": None}
    if inputs["facts"]:
        c = judge_completeness(question, answer, evidence)
        whole = {"completeness_pct": c.coverage_pct, "completeness_output": c.model_dump()}
    return facts, whole


def judge_case(inputs: dict) -> dict:
    """All judge calls for one case. `inputs` must come from judge_inputs() - it has no labels."""
    answer, evidence = inputs["answer"], inputs["evidence"]

    # judge_output keeps the judge's full structured response (scores, issue types, explanations)
    # so a human can see WHY it decided, not just the true/false it reduces to.
    def claim_call(claim: str) -> dict:
        g = judge_groundedness(claim, evidence)
        return {"claim": claim, "judge_covered_in_evidence": g.grounded, "judge_output": g.model_dump()}

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        claims = list(pool.map(claim_call, inputs["claims"]))
    facts, whole_completeness = _completeness_calls(inputs)

    g = judge_groundedness(answer, evidence)
    whole = {"groundedness_pct": g.groundedness_pct, "grounded": g.grounded,
             "groundedness_output": g.model_dump(), **whole_completeness}
    return {**{k: inputs[k] for k in ("id", "question", "answer", "evidence")},
            "claims": claims, "facts": facts, "whole_answer": whole}


def rejudge_completeness(test_set: list[dict], raw: list[dict]) -> list[dict]:
    """Re-runs only the completeness calls and keeps the existing groundedness results - for
    when only the completeness prompt (or the fact list) changed. Refuses if a case's claims or
    inputs changed since the groundedness run, since those results would then be stale."""
    raw_by_id = {r["id"]: r for r in raw}
    cases = [judge_inputs(c) for c in test_set if is_fully_labelled(c)]
    n_calls = sum(len(c["facts"]) + bool(c["facts"]) for c in cases)
    print(f"Step 1: re-judging completeness only for {len(cases)} cases ({n_calls} judge calls)...")
    out = []
    for c in cases:
        r = raw_by_id.get(c["id"])
        if r is None or any(r.get(k) != c[k] for k in ("question", "answer", "evidence"))                 or [x["claim"] for x in r["claims"]] != c["claims"]:
            raise SystemExit(f"{c['id']}: groundedness results are missing or stale - run without --only")
        facts, whole_completeness = _completeness_calls(c)
        out.append({**r, "facts": facts, "whole_answer": {**r["whole_answer"], **whole_completeness}})
    return out


def run_judges(test_set: list[dict], progress_path: str) -> list[dict]:
    """Judges every labelled case, saving each finished case to `progress_path` as it goes.
    A crash mid-run (API limit, network) then costs only the case in flight: re-running picks
    up the saved cases whose judge inputs are unchanged and judges only the rest. The progress
    file is deleted once the whole run completes."""
    cases = [judge_inputs(c) for c in test_set if is_fully_labelled(c)]
    done = {}
    if os.path.exists(progress_path):
        saved = {r["id"]: r for r in load_fixture(progress_path)}
        done = {c["id"]: saved[c["id"]] for c in cases if c["id"] in saved and _same_inputs(c, saved[c["id"]])}
    todo = [c for c in cases if c["id"] not in done]
    n_calls = sum(len(c["claims"]) + len(c["facts"]) + 1 + bool(c["facts"]) for c in todo)
    print(f"Step 1: judging {len(todo)} cases ({n_calls} judge calls); {len(done)} reused from an interrupted run...")
    for c in todo:
        done[c["id"]] = judge_case(c)
        with open(progress_path, "w", encoding="utf-8") as f:
            json.dump(list(done.values()), f, indent=2, ensure_ascii=False)
    return [done[c["id"]] for c in cases]


def _same_inputs(inputs: dict, saved: dict) -> bool:
    return (all(saved.get(k) == inputs[k] for k in ("question", "answer", "evidence"))
            and [c["claim"] for c in saved["claims"]] == inputs["claims"]
            and [f["fact"] for f in saved["facts"]] == inputs["facts"])


def output_csv_rows(raw: list[dict]) -> tuple[list[list], list[list]]:
    """One row per judge call: its inputs and its structured output, straight from the raw answers."""
    def evidence_text(evidence: list[dict]) -> str:
        return "\n".join(e["content"] for e in evidence)

    g_rows, c_rows = [], []
    for r in raw:
        full_evidence = evidence_text(r["evidence"])
        calls = [("per_claim", i, c["claim"], c["judge_output"]) for i, c in enumerate(r["claims"])]
        calls.append(("whole_answer", "", r["answer"], r["whole_answer"]["groundedness_output"]))
        for call, i, text, out in calls:
            g_rows.append([r["id"], call, i, text, full_evidence, out["groundedness_pct"], out["grounded"],
                           json.dumps(out["unsupported_claims"], ensure_ascii=False)])

        calls = [("per_fact", i, f["fact"], f["judge_output"]) for i, f in enumerate(r["facts"])]
        if r["whole_answer"].get("completeness_output"):
            calls.append(("whole_answer", "", full_evidence, r["whole_answer"]["completeness_output"]))
        for call, i, evidence_given, out in calls:
            c_rows.append([r["id"], call, i, r["question"], r["answer"], evidence_given, out["coverage_pct"],
                           json.dumps(out["omitted_points"], ensure_ascii=False),
                           json.dumps(out.get("off_topic_points", []), ensure_ascii=False)])
    return g_rows, c_rows


def run_judge_validation_eval(test_set_path: str = DEFAULT_TEST_SET, raw_path: str = DEFAULT_RAW,
                              comparison_path: str = DEFAULT_COMPARISON, compare_only: bool = False,
                              only: "str | None" = None, persist: bool = True) -> dict:
    test_set = load_fixture(test_set_path)
    if only == "completeness":
        raw = rejudge_completeness(test_set, load_fixture(raw_path))
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
        print(f"Wrote judge answers to {raw_path} (groundedness results kept)")
    elif not compare_only:
        progress_path = raw_path + ".progress"
        raw = run_judges(test_set, progress_path)
        with open(raw_path, "w", encoding="utf-8") as f:
            json.dump(raw, f, indent=2, ensure_ascii=False)
        os.remove(progress_path)
        print(f"Wrote judge answers to {raw_path}")
    raw = load_fixture(raw_path)

    print("Step 2: comparing judge answers with human labels...")
    comparison = compare(test_set, raw)
    with open(comparison_path, "w", encoding="utf-8") as f:
        json.dump(comparison, f, indent=2, ensure_ascii=False)
    print(f"Wrote comparison to {comparison_path}")

    g_rows, c_rows = output_csv_rows(raw)
    for path, columns, rows in ((GROUNDEDNESS_CSV, GROUNDEDNESS_CSV_COLUMNS, g_rows),
                                (COMPLETENESS_CSV, COMPLETENESS_CSV_COLUMNS, c_rows)):
        with open(path, "w", newline="", encoding="utf-8-sig") as f:  # utf-8-sig so Excel opens it cleanly
            writer = csv.writer(f)
            writer.writerow(columns)
            writer.writerows(rows)
    print(f"Wrote per-call judge outputs to {GROUNDEDNESS_CSV} and {COMPLETENESS_CSV}")

    if persist:
        insert_eval_run("judge_validation", {"test_set": test_set_path, "summary": comparison["summary"]},
                        fixture_version=compute_fixture_version(test_set_path))
        print("Logged this run to eval_runs (visible on the admin page).")
    return comparison


def _print_summary(s: dict) -> None:
    print(f"\nCases compared: {s['n_cases']} (skipped unlabelled: {s['n_skipped_unlabelled']})")
    for name in ("groundedness_per_claim", "completeness_per_fact"):
        c = s[name]
        counts = ", ".join(f"{k}={v}" for k, v in c.items() if k not in ("n",) and not k.endswith("rate"))
        print(f"{name}: n={c['n']} | {counts}")
        print(f"  agreement={c['agreement_rate']} problem_catch_rate={c['problem_catch_rate']} "
              f"false_alarm_rate={c['false_alarm_rate']}")
    i = s["completeness_irrelevant_facts"]
    print(f"completeness_irrelevant_facts: n={i['n']} | correctly_not_penalised={i['correctly_not_penalised']}, "
          f"wrongly_penalised={i['wrongly_penalised']} | not_penalised_rate={i['not_penalised_rate']}")
    r = s["fact_relevance"]
    print(f"fact_relevance: n={r['n']} | " + ", ".join(f"{k}={v}" for k, v in r.items() if k not in ("n", "agreement_rate"))
          + f" | agreement={r['agreement_rate']}")
    w = s["whole_answer"]
    print(f"whole answer: groundedness gap={w['groundedness_score_gap']} "
          f"grounded verdict agreement={w['grounded_verdict_agreement']}")
    print(f"              completeness gap={w['completeness_score_gap']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test-set", default=DEFAULT_TEST_SET)
    parser.add_argument("--raw", default=DEFAULT_RAW)
    parser.add_argument("--comparison", default=DEFAULT_COMPARISON)
    parser.add_argument("--compare-only", action="store_true",
                        help="Skip the judge calls; re-compare existing raw answers with the (edited) labels.")
    parser.add_argument("--only", choices=["completeness"], default=None,
                        help="Re-judge only completeness and keep the existing groundedness results.")
    parser.add_argument(
        "--no-persist", action="store_true",
        help="Skip writing this run to the eval_runs table (used by the admin page) - useful for a local dry run.",
    )
    args = parser.parse_args()

    result = run_judge_validation_eval(args.test_set, args.raw, args.comparison,
                                       compare_only=args.compare_only, only=args.only,
                                       persist=not args.no_persist)
    _print_summary(result["summary"])
