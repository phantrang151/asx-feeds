"""Tests for run_retrieval_config_eval - fusion, answer sharing, report maths, and that judges never
see the gold article ids. No real LLM, embedding or database calls."""

import json
from types import SimpleNamespace

from agent.eval.judge import CompletenessJudgment, GroundednessJudgment
from agent.eval.runners import run_retrieval_config_eval as rce


def _row(article_id, title="t"):
    return {"id": article_id, "title": title, "snippet": None, "publisher": "P", "source_url": None}


def test_rrf_fuses_both_lists_and_breaks_ties_deterministically():
    semantic = [_row("a"), _row("b"), _row("c")]
    lexical = [_row("c"), _row("d"), _row("a")]
    fused = rce.rrf_fuse(semantic, lexical, constant=60)
    # a: 1/61 + 1/63; c: 1/63 + 1/61 -> tie, both best rank 1 -> broken by id
    assert [r["id"] for r in fused] == ["a", "c", "b", "d"]
    assert abs(fused[0]["rrf_score"] - (1 / 61 + 1 / 63)) < 1e-12


def test_runs_with_identical_retrieval_share_one_generation_key():
    run = lambda cfg, ids: {"question_id": "q1", "config": cfg, "retrieved": [{"article_id": i} for i in ids]}  # noqa: E731
    assert rce.generation_key(run("semantic_k10", ["a", "b"])) == rce.generation_key(run("hybrid_k10", ["a", "b"]))
    assert rce.generation_key(run("semantic_k10", ["a", "b"])) != rce.generation_key(run("hybrid_k10", ["b", "a"]))


def test_judges_never_see_gold_article_ids(monkeypatch):
    seen = []

    def fake_groundedness(text, evidence):
        seen.append((text, evidence))
        return GroundednessJudgment(groundedness_pct=100, unsupported_claims=[], grounded=True)

    def fake_completeness(question, answer, evidence):
        seen.append((question, answer, evidence))
        return CompletenessJudgment(coverage_pct=100, omitted_points=[], off_topic_points=[])

    class FakeExtractor:
        def invoke(self, prompt):
            seen.append(prompt)
            return SimpleNamespace(claims=["CBA launched PaidIt"])

    monkeypatch.setattr(rce, "judge_groundedness", fake_groundedness)
    monkeypatch.setattr(rce, "judge_completeness", fake_completeness)
    monkeypatch.setattr(rce, "_claim_extractor", lambda: FakeExtractor())
    question = {"id": "h1", "question": "What platform?", "answerable": True,
                "gold_article_ids": ["GOLD-ID-SECRET"], "gold_facts": ["PaidIt launched"]}
    run = {"config": "hybrid_k10", "evidence": [{"source": "news", "content": "CBA unveils PaidIt"}],
           "retrieved": [{"article_id": "GOLD-ID-SECRET"}]}
    result = rce.judge_answer(question, run, "CBA launched PaidIt.")
    assert "GOLD-ID-SECRET" not in json.dumps(seen)
    assert result["claims"][0]["supported"] is True and result["facts"][0]["covered"] is True
    assert result["abstention"] is None  # answerable question: no abstention check


def test_report_metrics():
    test_set = [
        {"id": "q1", "answerable": True, "gold_article_ids": ["a", "b"], "gold_facts": ["f1", "f2"]},
        {"id": "q11", "answerable": False, "gold_article_ids": [], "gold_facts": []},
    ]
    runs = [{"question_id": "q1", "config": "c", "retrieved": [{"article_id": "a"}, {"article_id": "x"}]},
            {"question_id": "q11", "config": "c", "retrieved": [{"article_id": "y"}]}]
    answers = [{"question_id": "q1", "config": "c", "answer": "..", "shared_with": None},
               {"question_id": "q11", "config": "c", "answer": "..", "shared_with": None}]
    judgements = [
        {"question_id": "q1", "config": "c", "claims": [{"supported": True}, {"supported": False}],
         "facts": [{"covered": True}, {"covered": False}],
         "whole_answer_groundedness": {"groundedness_pct": 80}, "abstention": None},
        {"question_id": "q11", "config": "c", "claims": [{"supported": True}], "facts": [],
         "whole_answer_groundedness": {"groundedness_pct": 100}, "abstention": {"declined": True}},
    ]
    rows = rce.per_question_rows(test_set, runs, answers, judgements)
    assert (rows[0]["recall"], rows[0]["precision"], rows[0]["groundedness"], rows[0]["completeness"]) == (0.5, 0.5, 0.5, 0.5)
    assert rows[1]["recall"] is None and rows[1]["declined"] is True
    s = rce.summarize(rows)[0]
    assert s["recall"] == 0.5                      # answerable questions only
    assert s["groundedness"] == 0.75               # mean of 0.5 and 1.0 over all answers
    assert s["completeness"] == 0.5 and s["abstention_correct"] == "1/1"
    assert s["unsupported_claims_total"] == 1
