"""
LLM-as-judge scoring functions for generation quality (groundedness, relevance).
Advice-avoidance is NOT reimplemented here - it reuses
agent.guardrails.advice_check.check_advice_avoidance directly, the same function the
live output guardrail runs, so the eval and the live gate can never drift apart.

All judging uses config.JUDGE_MODEL - a different, smaller Groq model than MODEL (the
one that generated the answer being judged), so it isn't grading its own homework.
"""

from langchain_groq import ChatGroq
from pydantic import BaseModel, Field

from agent.shared.groq_retry import call_with_tool_use_retry
from config import JUDGE_MODEL, GROQ_API_KEY


class GroundednessJudgment(BaseModel):
    unsupported_claims: list[str] = Field(
        description="Specific claims in the insight that are NOT supported by the evidence. Empty if fully grounded."
    )
    grounded: bool = Field(description="True if every claim in the insight is supported by the evidence.")


class RelevanceJudgment(BaseModel):
    score: int = Field(description="1-5: does the insight actually address the question asked? 5 = fully addresses it.")
    reasoning: str = Field(description="One short sentence explaining the score.")


def _judge_llm():
    # Constructed lazily (not at import time) so this module stays importable without a
    # live GROQ_API_KEY, matching agent/shared/synthesize.py's own style.
    return ChatGroq(model=JUDGE_MODEL, api_key=GROQ_API_KEY, temperature=0)


def judge_groundedness(insight: str, evidence: list[dict]) -> GroundednessJudgment:
    """RAGAS calls this axis 'faithfulness' - the single most important quality metric
    given the whole app's design goal is 'don't say things the evidence doesn't
    support'. Checks each claim in `insight` against `evidence` verbatim (no access to
    outside/parametric knowledge is implied to the judge - it's only asked to compare
    the two texts)."""
    evidence_text = "\n\n".join(
        f"[{item.get('source', 'unknown')}] {item.get('content')}" for item in evidence
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
    return call_with_tool_use_retry(lambda: judge.invoke(prompt))


def judge_relevance(question: str, insight: str) -> RelevanceJudgment:
    prompt = (
        "You are grading whether a generated answer actually addresses the question "
        "asked, on a 1-5 scale (5 = fully addresses it, 1 = doesn't address it at "
        "all). Score based on relevance to the question only, not factual accuracy.\n\n"
        f"Question:\n{question}\n\n"
        f"Answer:\n{insight}"
    )
    judge = _judge_llm().with_structured_output(RelevanceJudgment)
    return call_with_tool_use_retry(lambda: judge.invoke(prompt))
