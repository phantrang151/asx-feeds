"""Pure logic for judge validation - no I/O, no LLM calls, unit-tested in
tests/test_judge_validation_compare.py. Three files, three jobs:

  fixtures/judge_validation_test_set.json   ground truth - human labels
        claims[].covered_in_evidence  (is this answer statement supported by the evidence?)
        facts[].relevant              (is this evidence point relevant to the question at all?
                                       borderline counts as relevant; only off-topic is false)
        facts[].covered_in_answer     (is this evidence point in the answer?)
  results/judge_raw_answers.json            what the judges said - same shape, judge_* fields,
                                            written by runners/run_judge_validation_eval.py
  results/judge_validation_comparison.json  derived here: the two joined item by item

`judge_inputs` is the only thing the runner may hand to a judge: an explicit allow-list of
fields, so no human label can leak into a judge call - adding a label field to the fixture
later can't change what the judges see.
"""

from statistics import mean

def fact_covered(completeness_output: dict) -> bool:
    """Per-fact verdict from a completeness call whose only evidence is that one fact: covered
    unless the judge lists it in omitted_points. Deliberately NOT read from coverage_pct - the
    judge often names a fact as omitted yet hedges the % at 50-90 (validation run, 2026-10-15:
    a >=50 cut-off caught 9 of 14 deliberate omissions, the omitted_points list caught 13)."""
    return not completeness_output["omitted_points"]

CLAIM_OUTCOMES = {  # (human covered_in_evidence, judge covered_in_evidence) -> outcome
    (False, False): "caught_unsupported",   # TP: judge rejects a claim the human found unsupported
    (True, True): "accepted_supported",     # TN
    (True, False): "wrongly_rejected",      # FP: judge rejects a supported claim
    (False, True): "wrongly_accepted",      # FN: judge lets an unsupported claim through
}
FACT_OUTCOMES = {  # relevant facts: (human covered_in_answer, judge covered_in_answer) -> outcome
    (False, False): "caught_missing",       # TP: judge spots a fact the answer left out
    (True, True): "confirmed_covered",      # TN
    (True, False): "wrongly_flagged_missing",  # FP
    (False, True): "missed_omission",       # FN: judge thinks a missing fact is covered
}
# Irrelevant facts: the completeness judge is told off-topic evidence must not count against an
# answer, so the right behaviour is "not missing" (not in omitted_points) whether or not
# the answer happens to mention it.
IRRELEVANT_OUTCOMES = {True: "correctly_not_penalised", False: "wrongly_penalised"}
RELEVANCE_OUTCOMES = {  # (human relevant, judge relevant) -> outcome; judge relevant = fact not in off_topic_points
    (True, True): "relevant_kept",
    (True, False): "relevant_dismissed",      # the dangerous error: a real omission would be hidden
    (False, False): "off_topic_dismissed",
    (False, True): "off_topic_kept",          # milder: the answer is unfairly penalised
}


def judge_inputs(case: dict) -> dict:
    """The label-free view of a test case - the only data any judge call may use."""
    return {
        "id": case["id"],
        "question": case["question"],
        "answer": case["answer"],
        "evidence": case["evidence"],
        "claims": [c["claim"] for c in case["claims"]],
        "facts": [f["fact"] for f in case.get("facts") or []],
    }


def is_fully_labelled(case: dict) -> bool:
    claims, facts = case.get("claims") or [], case.get("facts") or []
    return bool(claims) and all(c.get("covered_in_evidence") in (True, False) for c in claims) and all(
        f.get("covered_in_answer") in (True, False) and f.get("relevant") in (True, False) for f in facts
    )


def _pct(flags: list[bool]) -> "float | None":
    return round(100 * sum(flags) / len(flags), 1) if flags else None


def _rate(num: int, den: int) -> "float | None":
    return round(num / den, 4) if den else None


def _counts(outcomes: list[str], table: dict) -> dict:
    names = list(table.values())  # dict order above: TP, TN, FP, FN
    n = {name: outcomes.count(name) for name in names}
    tp, tn, fp, fn = (n[name] for name in names)
    return {"n": len(outcomes), **n,
            # of items the human marked as a problem, share the judge also flagged
            "problem_catch_rate": _rate(tp, tp + fn),
            # of items the human marked fine, share the judge wrongly flagged
            "false_alarm_rate": _rate(fp, fp + tn),
            "agreement_rate": _rate(tp + tn, len(outcomes))}


def _score_gap(pairs: list[tuple]) -> dict:
    pairs = [(j, h) for j, h in pairs if j is not None and h is not None]
    if not pairs:
        return {"n": 0, "mean_abs_diff": None, "mean_diff_judge_minus_human": None}
    diffs = [j - h for j, h in pairs]
    return {"n": len(pairs), "mean_abs_diff": round(mean(abs(d) for d in diffs), 1),
            "mean_diff_judge_minus_human": round(mean(diffs), 1)}


def compare(test_set: list[dict], raw: list[dict]) -> dict:
    """Join ground truth and judge answers on case id + item position. Refuses to compare if
    the raw answers were produced from different claim/fact text (labels edited is fine,
    claims or facts edited means the judges must be re-run)."""
    raw_by_id = {r["id"]: r for r in raw}
    cases, claim_outcomes, fact_outcomes, irrelevant_outcomes, relevance_outcomes = [], [], [], [], []
    for case in test_set:
        if not is_fully_labelled(case):
            continue
        r = raw_by_id.get(case["id"])
        if r is None:
            raise ValueError(f"{case['id']}: no judge answers - re-run the judges")
        if [c["claim"] for c in case["claims"]] != [c["claim"] for c in r["claims"]] or \
                [f["fact"] for f in case.get("facts") or []] != [f["fact"] for f in r.get("facts") or []]:
            raise ValueError(f"{case['id']}: claims/facts changed since the judges ran - re-run the judges")

        claims = []
        for h, j in zip(case["claims"], r["claims"]):
            outcome = CLAIM_OUTCOMES[(h["covered_in_evidence"], j["judge_covered_in_evidence"])]
            claim_outcomes.append(outcome)
            claims.append({"claim": h["claim"], "human_covered_in_evidence": h["covered_in_evidence"],
                           "judge_covered_in_evidence": j["judge_covered_in_evidence"], "outcome": outcome})
        facts = []
        for h, j in zip(case.get("facts") or [], r.get("facts") or []):
            if h["relevant"]:
                outcome = FACT_OUTCOMES[(h["covered_in_answer"], j["judge_covered_in_answer"])]
                fact_outcomes.append(outcome)
            else:
                outcome = IRRELEVANT_OUTCOMES[j["judge_covered_in_answer"]]
                irrelevant_outcomes.append(outcome)
            item = {"fact": h["fact"], "relevant": h["relevant"], "human_covered_in_answer": h["covered_in_answer"],
                    "judge_covered_in_answer": j["judge_covered_in_answer"], "outcome": outcome}
            if "judge_relevant" in j:  # raw answers from before the off_topic_points field have no verdict
                item["judge_relevant"] = j["judge_relevant"]
                item["relevance_outcome"] = RELEVANCE_OUTCOMES[(h["relevant"], j["judge_relevant"])]
                relevance_outcomes.append(item["relevance_outcome"])
            facts.append(item)

        whole = r.get("whole_answer") or {}
        human_g = _pct([c["covered_in_evidence"] for c in case["claims"]])
        human_c = _pct([f["covered_in_answer"] for f in case.get("facts") or [] if f["relevant"]])
        cases.append({
            "id": case["id"], "question": case["question"], "claims": claims, "facts": facts,
            "whole_answer": {
                "human_groundedness_pct": human_g, "judge_groundedness_pct": whole.get("groundedness_pct"),
                "human_grounded": human_g == 100.0, "judge_grounded": whole.get("grounded"),
                "human_completeness_pct": human_c, "judge_completeness_pct": whole.get("completeness_pct"),
            },
        })

    w = [c["whole_answer"] for c in cases]
    return {
        "summary": {
            "n_cases": len(cases),
            "n_skipped_unlabelled": sum(1 for c in test_set if not is_fully_labelled(c)),
            "groundedness_per_claim": _counts(claim_outcomes, CLAIM_OUTCOMES),
            "completeness_per_fact": _counts(fact_outcomes, FACT_OUTCOMES),
            "completeness_irrelevant_facts": {
                "n": len(irrelevant_outcomes),
                **{name: irrelevant_outcomes.count(name) for name in IRRELEVANT_OUTCOMES.values()},
                "not_penalised_rate": _rate(irrelevant_outcomes.count("correctly_not_penalised"),
                                            len(irrelevant_outcomes)),
            },
            "fact_relevance": {"n": len(relevance_outcomes),
                               **{name: relevance_outcomes.count(name) for name in RELEVANCE_OUTCOMES.values()},
                               "agreement_rate": _rate(relevance_outcomes.count("relevant_kept")
                                                       + relevance_outcomes.count("off_topic_dismissed"),
                                                       len(relevance_outcomes))},
            "whole_answer": {
                "groundedness_score_gap": _score_gap([(x["judge_groundedness_pct"], x["human_groundedness_pct"]) for x in w]),
                "grounded_verdict_agreement": _rate(
                    sum(1 for x in w if x["judge_grounded"] == x["human_grounded"]), len(w)),
                "completeness_score_gap": _score_gap([(x["judge_completeness_pct"], x["human_completeness_pct"]) for x in w]),
            },
        },
        "cases": cases,
    }
