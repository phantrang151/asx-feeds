"""Tests for judge validation: the pure join/metrics (judge_validation_compare) and a guard that
no human label can reach a judge call (run_judge_validation_eval.judge_case). No real LLM calls."""

import json
import pytest

from agent.eval import judge_validation_compare as jvc
from agent.eval.judge import CompletenessJudgment, GroundednessJudgment
from agent.eval.runners import run_judge_validation_eval as runner


def _test_case():
    return {
        "id": "h1", "question": "What payout platform has CBA introduced?",
        "answer": "CBA launched PaidIt for businesses.",
        "evidence": [{"source": "news", "content": "CBA unveils PaidIt ahead of cheque exit."}],
        "claims": [{"claim": "CBA launched PaidIt", "covered_in_evidence": True},
                   {"claim": "PaidIt is for businesses", "covered_in_evidence": False}],
        "facts": [{"fact": "PaidIt launched ahead of cheque exit", "relevant": True, "covered_in_answer": False}],
    }


def _raw(claim_verdicts, fact_verdicts, whole=None):
    case = _test_case()
    return {
        "id": "h1", "question": case["question"], "answer": case["answer"], "evidence": case["evidence"],
        "claims": [{"claim": c["claim"], "judge_covered_in_evidence": v} for c, v in zip(case["claims"], claim_verdicts)],
        "facts": [{"fact": f["fact"], "judge_covered_in_answer": v, "judge_completeness_pct": 100 if v else 0}
                  for f, v in zip(case["facts"], fact_verdicts)],
        "whole_answer": whole or {"groundedness_pct": 70, "grounded": False, "completeness_pct": 40},
    }


def test_judge_inputs_contain_no_labels():
    inputs = jvc.judge_inputs(_test_case())
    assert "covered_in" not in json.dumps(inputs)
    assert inputs["claims"] == ["CBA launched PaidIt", "PaidIt is for businesses"]
    assert inputs["facts"] == ["PaidIt launched ahead of cheque exit"]


def test_judges_never_receive_a_label(monkeypatch):
    seen = []

    def fake_groundedness(text, evidence):
        seen.append((text, evidence))
        return GroundednessJudgment(grounded=True, groundedness_pct=100, unsupported_claims=[])

    def fake_completeness(question, answer, evidence):
        seen.append((question, answer, evidence))
        return CompletenessJudgment(coverage_pct=100, omitted_points=[])

    monkeypatch.setattr(runner, "judge_groundedness", fake_groundedness)
    monkeypatch.setattr(runner, "judge_completeness", fake_completeness)
    case = _test_case()
    for item in case["claims"]:
        item["covered_in_evidence"] = "LEAKED_LABEL"  # would show up in any judge argument if passed through
    case["facts"][0]["covered_in_answer"] = "LEAKED_LABEL"
    case["facts"][0]["relevant"] = "LEAKED_LABEL"

    runner.judge_case(jvc.judge_inputs(case))

    assert len(seen) == 2 + 1 + 2  # 2 claims, 1 fact, whole-answer groundedness + completeness
    dumped = json.dumps(seen)
    assert "LEAKED_LABEL" not in dumped and "covered_in" not in dumped and "relevant" not in dumped


def test_compare_outcomes_and_rates():
    # claim 0: human covered, judge rejects  -> wrongly_rejected (FP)
    # claim 1: human uncovered, judge rejects -> caught_unsupported (TP)
    # fact 0: human uncovered, judge covered -> missed_omission (FN)
    result = jvc.compare([_test_case()], [_raw([False, False], [True])])
    case = result["cases"][0]
    assert [c["outcome"] for c in case["claims"]] == ["wrongly_rejected", "caught_unsupported"]
    assert case["facts"][0]["outcome"] == "missed_omission"

    g = result["summary"]["groundedness_per_claim"]
    assert (g["caught_unsupported"], g["wrongly_rejected"]) == (1, 1)
    assert g["problem_catch_rate"] == 1.0 and g["false_alarm_rate"] == 1.0 and g["agreement_rate"] == 0.5
    assert result["summary"]["completeness_per_fact"]["problem_catch_rate"] == 0.0


def test_whole_answer_scores_against_human_percentages():
    w = jvc.compare([_test_case()], [_raw([True, False], [False])])["cases"][0]["whole_answer"]
    assert w["human_groundedness_pct"] == 50.0 and w["judge_groundedness_pct"] == 70
    assert w["human_grounded"] is False and w["human_completeness_pct"] == 0.0


def test_relabelling_is_fine_but_edited_claim_text_is_refused():
    jvc.compare([_test_case()], [_raw([True, True], [True])])  # labels differ from judge: fine
    raw = _raw([True, True], [True])
    raw["claims"][0]["claim"] = "CBA launched something else"
    with pytest.raises(ValueError, match="re-run the judges"):
        jvc.compare([_test_case()], [raw])


def test_unlabelled_cases_are_skipped_not_guessed():
    case = _test_case()
    case["claims"][0]["covered_in_evidence"] = None
    result = jvc.compare([case], [])
    assert result["summary"]["n_cases"] == 0 and result["summary"]["n_skipped_unlabelled"] == 1


def test_answer_absent_case_has_no_completeness():
    case = {**_test_case(), "facts": []}
    raw = {**_raw([True, False], []), "facts": [],
           "whole_answer": {"groundedness_pct": 50, "grounded": False, "completeness_pct": None}}
    w = jvc.compare([case], [raw])["cases"][0]["whole_answer"]
    assert w["human_completeness_pct"] is None and w["judge_completeness_pct"] is None


def test_irrelevant_facts_scored_separately_and_excluded_from_completeness():
    case = _test_case()
    case["facts"].append({"fact": "LGT reported a 17% rise in H1 profit", "relevant": False, "covered_in_answer": False})
    raw = _raw([True, False], [False])
    raw["facts"].append({"fact": "LGT reported a 17% rise in H1 profit", "judge_covered_in_answer": False,
                         "judge_completeness_pct": 0})
    result = jvc.compare([case], [raw])
    assert result["cases"][0]["facts"][1]["outcome"] == "wrongly_penalised"
    irr = result["summary"]["completeness_irrelevant_facts"]
    assert (irr["n"], irr["wrongly_penalised"], irr["not_penalised_rate"]) == (1, 1, 0.0)
    assert result["summary"]["completeness_per_fact"]["n"] == 1  # relevant facts only
    assert result["cases"][0]["whole_answer"]["human_completeness_pct"] == 0.0  # irrelevant fact not counted


def test_fact_without_relevance_label_is_unlabelled():
    case = _test_case()
    del case["facts"][0]["relevant"]
    assert not jvc.is_fully_labelled(case)


def test_output_csv_rows_contain_only_judge_inputs_and_structured_output():
    unsupported = [{"statement": "PaidIt is for businesses", "issue_type": "partially_supported",
                    "unsupported_part": "for businesses", "explanation": "not stated"}]
    raw = _raw([True, False], [False])
    raw["claims"][0]["judge_output"] = {"groundedness_pct": 100, "grounded": True, "unsupported_claims": []}
    raw["claims"][1]["judge_output"] = {"groundedness_pct": 0, "grounded": False, "unsupported_claims": unsupported}
    raw["facts"][0]["judge_output"] = {"coverage_pct": 0, "omitted_points": ["cheque exit"], "off_topic_points": []}
    raw["whole_answer"] = {"groundedness_output": {"groundedness_pct": 50, "grounded": False,
                                                   "unsupported_claims": unsupported},
                           "completeness_output": None}
    g_rows, c_rows = runner.output_csv_rows([raw])

    row = dict(zip(runner.GROUNDEDNESS_CSV_COLUMNS, g_rows[1]))
    assert (row["call"], row["text_judged"], row["grounded"]) == ("per_claim", "PaidIt is for businesses", False)
    assert json.loads(row["unsupported_claims"]) == unsupported   # list kept exactly as the judge returned it
    assert [r[1] for r in g_rows] == ["per_claim", "per_claim", "whole_answer"]
    assert [r[1] for r in c_rows] == ["per_fact"]                    # no whole-answer completeness call
    assert dict(zip(runner.COMPLETENESS_CSV_COLUMNS, c_rows[0]))["evidence_given"] == "PaidIt launched ahead of cheque exit"
    header = " ".join(runner.GROUNDEDNESS_CSV_COLUMNS + runner.COMPLETENESS_CSV_COLUMNS)
    assert "human" not in header and "outcome" not in header and "relevant" not in header


def test_relevance_verdict_compared_with_human_label():
    case = _test_case()
    case["facts"].append({"fact": "Tencent will raise AI spending", "relevant": False, "covered_in_answer": False})
    raw = _raw([True, False], [True])
    raw["facts"][0]["judge_relevant"] = False      # judge dismisses a RELEVANT fact - the dangerous error
    raw["facts"].append({"fact": "Tencent will raise AI spending", "judge_relevant": False,
                         "judge_covered_in_answer": True, "judge_completeness_pct": 100})
    result = jvc.compare([case], [raw])
    assert [f["relevance_outcome"] for f in result["cases"][0]["facts"]] == ["relevant_dismissed", "off_topic_dismissed"]
    rel = result["summary"]["fact_relevance"]
    assert (rel["n"], rel["relevant_dismissed"], rel["off_topic_dismissed"], rel["agreement_rate"]) == (2, 1, 1, 0.5)


def test_rejudge_completeness_keeps_groundedness(monkeypatch):
    def fake_completeness(question, answer, evidence):
        return CompletenessJudgment(coverage_pct=100, omitted_points=[], off_topic_points=[])

    monkeypatch.setattr(runner, "judge_completeness", fake_completeness)
    monkeypatch.setattr(runner, "judge_groundedness", lambda *a: pytest.fail("groundedness must not be re-run"))
    raw = _raw([True, False], [False], whole={"groundedness_pct": 70, "grounded": False, "completeness_pct": 40})
    out = runner.rejudge_completeness([_test_case()], [raw])[0]
    assert out["claims"] == raw["claims"] and out["whole_answer"]["groundedness_pct"] == 70
    assert out["facts"][0]["judge_relevant"] is True and out["whole_answer"]["completeness_pct"] == 100


def test_fact_covered_reads_omitted_points_not_the_hedged_percentage():
    # the judge names the fact as omitted but hedges the score - must count as missing
    assert jvc.fact_covered({"coverage_pct": 60, "omitted_points": ["banks' pace warning"], "off_topic_points": []}) is False
    assert jvc.fact_covered({"coverage_pct": 100, "omitted_points": [], "off_topic_points": []}) is True
    # an off-topic fact is excluded, not omitted - the answer isn't penalised for it
    assert jvc.fact_covered({"coverage_pct": 100, "omitted_points": [], "off_topic_points": ["Tencent..."]}) is True
