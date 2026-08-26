"""
LLM-as-judge scoring functions for generation quality (groundedness, relevance).
Advice-avoidance is NOT reimplemented here - it reuses
agent.guardrails.advice_check.check_advice_avoidance directly, the same function the
live output guardrail runs, so the eval and the live gate can never drift apart.

All judging uses config.JUDGE_MODEL - a different, stronger model than ANALYSIS_MODEL
(the one that generated the answer being judged), so it isn't grading its own homework.
"""

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from config import JUDGE_MODEL, ANTHROPIC_API_KEY


class GroundednessJudgment(BaseModel):
    unsupported_claims: list[str] = Field(
        description="Specific claims in the insight that are NOT supported by the evidence. Empty if fully grounded."
    )
    grounded: bool = Field(description="True if every claim in the insight is supported by the evidence.")


class RelevanceJudgment(BaseModel):
    score: int = Field(description="1-5: does the insight actually address the question asked? 5 = fully addresses it.")
    reasoning: str = Field(description="One short sentence explaining the score.")


class AnswerFoundJudgment(BaseModel):
    found_answer: bool = Field(
        description="True if the answer actually asserts a finding. False if it hedges/declines - "
        "says there isn't enough evidence, information, or data to answer, even partially."
    )
    reasoning: str = Field(description="One short sentence explaining the judgment.")


def _judge_llm():
    # Constructed lazily (not at import time) so this module stays importable without a
    # live ANTHROPIC_API_KEY, matching agent/shared/synthesize.py's own style.
    return ChatAnthropic(model=JUDGE_MODEL, api_key=ANTHROPIC_API_KEY)


def judge_groundedness(insight: str, evidence: list[dict]) -> GroundednessJudgment:
    """RAGAS calls this axis 'faithfulness' - the single most important quality metric
    given the whole app's design goal is 'don't say things the evidence doesn't
    support'. Checks each claim in `insight` against `evidence` verbatim (no access to
    outside/parametric knowledge is implied to the judge - it's only asked to compare
    the two texts)."""
    # Prefer "excerpt" (the actual retrieved text, when a tool's citation-display
    # "content" is only a short label like a filename or headline - see
    # search_financial_reports_tool in tools/react_tools.py) over "content" itself.
    evidence_text = "\n\n".join(
        f"[{item.get('source', 'unknown')}] {item.get('excerpt') or item.get('content')}" for item in evidence
    )
    prompt = (
        "You are grading whether a generated financial insight is fully supported by "
        "the evidence it was given - not whether it's true in general, only whether "
        "THIS evidence supports it. List any specific claims in the insight that go "
        "beyond what the evidence actually says.\n\n"
        f"Evidence:\n{evidence_text}\n\n"
        f"Insight:\n{insight}"
    )
    judge = _judge_llm().with_structured_output(GroundednessJudgment)
    return judge.invoke(prompt)


def judge_relevance(question: str, insight: str) -> RelevanceJudgment:
    prompt = (
        "You are grading whether a generated answer actually addresses the question "
        "asked, on a 1-5 scale (5 = fully addresses it, 1 = doesn't address it at "
        "all). Score based on relevance to the question only, not factual accuracy.\n\n"
        f"Question:\n{question}\n\n"
        f"Answer:\n{insight}"
    )
    judge = _judge_llm().with_structured_output(RelevanceJudgment)
    return judge.invoke(prompt)


def judge_answer_found(question: str, insight: str) -> AnswerFoundJudgment:
    """RAGAS calls this axis roughly 'context recall' - the answer-discovery-rate
    metric: does the system actually assert a finding, or does it hedge/decline ("not
    enough evidence") on a question a real answer exists for? Complements the free,
    structural evidence_count == 0 signal already on every live request_trace row (see
    schema.sql) - that catches genuine retrieval failures (tools returned nothing) for
    free on every request; this judge catches the rarer, subtler case where tools DID
    return usable evidence but synthesis still hedged anyway. Reserved for low-volume
    use (the offline fixture set in eval/run_generation_eval.py, and the daily N-sample
    live audit in eval/run_live_sample_eval.py) - deliberately not run on every live
    request, same reasoning as judge_groundedness/judge_relevance above."""
    prompt = (
        "You are grading whether a generated financial answer actually asserts a "
        "finding, or instead hedges/declines to answer (e.g. 'not enough evidence was "
        "gathered', 'I don't have enough information'). This question is known to be "
        "genuinely answerable - judge only whether THIS answer found and stated an "
        "answer, not whether that answer is correct or complete.\n\n"
        f"Question:\n{question}\n\n"
        f"Answer:\n{insight}"
    )
    judge = _judge_llm().with_structured_output(AnswerFoundJudgment)
    return judge.invoke(prompt)
