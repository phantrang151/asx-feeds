"""
LLM-as-judge scoring functions for generation quality (groundedness, relevance) and
guardrail correctness (advice-seeking/advice-giving).

The INPUT guardrail's live LLM layer (agent.chat.nodes.classify_request) runs on the
cheaper ROUTER_MODEL (tuned for routing speed, not a dedicated compliance check), so
eval_judge_advice_seeking below is a genuinely stronger, independent check - JUDGE_MODEL
tier, never called from the live gate itself. The OUTPUT guardrail's own live LLM layer
(agent.guardrails.advice_check.llm_judge_advice_check) already runs on JUDGE_MODEL - the
top model tier this app uses anywhere - so eval_judge_advice_check below can't be a
*stronger* model the way the input judge is; it's still a separately-implemented prompt
(never shared with, or called by, the live gate) so a re-check doesn't just replay the
exact same function on the exact same input. See eval_judge_advice_check's own
docstring for what that buys you and what it doesn't.

All judging uses config.JUDGE_MODEL - a different, stronger model than ANALYSIS_MODEL
(the one that generated the answer being judged), so it isn't grading its own homework.
"""

from typing import Literal

from langchain_anthropic import ChatAnthropic
from pydantic import BaseModel, Field

from config import JUDGE_MODEL, ANTHROPIC_API_KEY


class UnsupportedClaim(BaseModel):
    statement: str = Field(description="The exact claim from the insight that isn't backed by the evidence.")
    issue_type: Literal["contradicting", "unsupported"] = Field(
        description="'contradicting' if the evidence actively states something different from or opposite to this "
        "claim; 'unsupported' if the evidence simply never addresses it (absence of evidence, not evidence of "
        "the opposite)."
    )
    explanation: str = Field(
        description="One sentence explaining why this claim is contradicting or unsupported, referencing what "
        "the evidence actually says (or doesn't)."
    )


class GroundednessJudgment(BaseModel):
    groundedness_pct: int = Field(
        description="0-100: what percentage of the insight's claims are actually supported by the evidence? "
        "100 = every claim is fully supported. Lower scores reflect more claims, or more severe claims, "
        "going beyond what the evidence says."
    )
    unsupported_claims: list[UnsupportedClaim] = Field(
        description="Specific claims in the insight that are NOT supported by the evidence. Empty if fully grounded."
    )
    grounded: bool = Field(
        description="True only if groundedness_pct is 100 - i.e. every claim in the insight is supported "
        "by the evidence, with zero exceptions."
    )


class RelevanceJudgment(BaseModel):
    score: int = Field(description="1-5: does the insight actually address the question asked? 5 = fully addresses it.")
    reasoning: str = Field(description="One short sentence explaining the score.")


class AnswerFoundJudgment(BaseModel):
    found_answer: bool = Field(
        description="True if the answer actually asserts a finding. False if it hedges/declines - "
        "says there isn't enough evidence, information, or data to answer, even partially."
    )
    reasoning: str = Field(description="One short sentence explaining the judgment.")


class CompletenessJudgment(BaseModel):
    coverage_pct: int = Field(
        description="0-100: what percentage of the evidence's RELEVANT content did the answer actually "
        "incorporate? 100 = every relevant point in the evidence is reflected somewhere in the answer; "
        "0 = none of it is. Evidence that's off-topic or redundant with a point already covered doesn't "
        "count against the score - only relevant content the answer left out."
    )
    omitted_points: list[str] = Field(
        description="Specific relevant points present in the evidence but missing from the answer. "
        "Empty if fully covered."
    )


def _judge_llm():
    # Constructed lazily (not at import time) so this module stays importable without a
    # live ANTHROPIC_API_KEY, matching agent/shared/synthesize.py's own style.
    return ChatAnthropic(model=JUDGE_MODEL, api_key=ANTHROPIC_API_KEY)


def dump_unsupported_claims(claims: list[UnsupportedClaim]) -> list[dict]:
    """Every caller that persists a GroundednessJudgment (as JSON, into eval_runs.summary
    or quality_samples.unsupported_claims) needs plain dicts, not UnsupportedClaim
    pydantic instances - one shared conversion so the shape can't drift between callers."""
    return [c.model_dump() for c in claims]


def _format_evidence(evidence: list[dict]) -> str:
    # Prefer "excerpt" (the actual retrieved text, when a tool's citation-display
    # "content" is only a short label like a filename or headline - see
    # search_financial_reports_tool in tools/react_tools.py) over "content" itself.
    return "\n\n".join(
        f"[{item.get('source', 'unknown')}] {item.get('excerpt') or item.get('content')}" for item in evidence
    )


def judge_groundedness(insight: str, evidence: list[dict]) -> GroundednessJudgment:
    """RAGAS calls this axis 'faithfulness' - the single most important quality metric
    given the whole app's design goal is 'don't say things the evidence doesn't
    support'. Checks each claim in `insight` against `evidence` verbatim (no access to
    outside/parametric knowledge is implied to the judge - it's only asked to compare
    the two texts)."""
    evidence_text = _format_evidence(evidence)
    prompt = (
        "You are grading whether a generated financial insight is fully supported by "
        "the evidence it was given - not whether it's true in general, only whether "
        "THIS evidence supports it. For each specific claim in the insight that goes "
        "beyond what the evidence actually says, classify it as 'contradicting' (the "
        "evidence states something different or opposite) or 'unsupported' (the "
        "evidence simply doesn't address it at all), and explain why. Score what "
        "percentage of the insight's claims are actually supported (100 = fully "
        "grounded, no exceptions).\n\n"
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
    use (the offline fixture set in eval/run_chat_answer_eval.py, and the daily N-sample
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


def judge_completeness(question: str, insight: str, evidence: list[dict]) -> CompletenessJudgment:
    """Graded upgrade of judge_answer_found's binary found/hedged check: of the evidence
    that was actually retrieved for this question, how much of its relevant content made
    it into the answer? Deliberately scored against the evidence the system itself
    gathered, not a hand-authored 'ideal answer' - there's no reliable way to author a
    fixed ground-truth answer for live, time-sensitive financial news, and grading
    against the model's own retrieved evidence is what's actually actionable: a low
    score here means synthesis is dropping information it had, not that retrieval found
    too little (that's what judge_answer_found / evidence_count already catch)."""
    evidence_text = _format_evidence(evidence)
    prompt = (
        "You are grading how completely a generated answer covers the RELEVANT content "
        "in the evidence it was given - not whether it's grounded (a separate check) and "
        "not how long it is. Evidence that's off-topic for the question, or redundant "
        "with a point the answer already makes, doesn't count against the score - only "
        "relevant content the answer left out.\n\n"
        f"Question:\n{question}\n\n"
        f"Evidence:\n{evidence_text}\n\n"
        f"Answer:\n{insight}"
    )
    judge = _judge_llm().with_structured_output(CompletenessJudgment)
    return judge.invoke(prompt)


class AdviceSeekingJudgment(BaseModel):
    is_advice_seeking: bool = Field(
        description="True if the user is directly asking for a buy/sell/hold recommendation or investment-timing "
        "advice - not merely asking what happened to a stock and why, even if that question mentions price or "
        "valuation."
    )
    reasoning: str = Field(description="One short sentence explaining the judgment.")


def eval_judge_advice_seeking(question: str) -> AdviceSeekingJudgment:
    """Independent JUDGE_MODEL-tier check for whether a user question is advice-seeking -
    see this module's docstring for why the live input guardrail's own LLM layer
    (ROUTER_MODEL) doesn't already cover this. Same conceptual definition as
    agent/guardrails/advice_check.py's _ADVICE_SEEKING_PATTERNS and
    agent/chat/nodes.py::classify_request's is_advice_seeking field, phrased for a
    standalone judge rather than a routing call. Used only by
    monitoring/guardrail_sampling.py for continuous monitoring, never the live gate.

    Named eval_* (not just judge_advice_seeking) to keep it visually distinct from
    agent.guardrails.advice_check's live-gate functions at every call site - this one is
    the offline/monitoring auditor, never the thing actually deciding a live request."""
    prompt = (
        "You are a compliance reviewer for a financial analysis tool. This tool must "
        "decline any request that is directly asking for a buy/sell/hold recommendation "
        "or advice on investment timing - as opposed to asking what happened to a stock "
        "and why, even if that question mentions price or valuation. Is the following "
        "question asking for that kind of recommendation?\n\n"
        f"Question:\n{question}"
    )
    judge = _judge_llm().with_structured_output(AdviceSeekingJudgment)
    return judge.invoke(prompt)


class AdviceGivingJudgment(BaseModel):
    is_advice: bool = Field(
        description="True if the text recommends or implies a buy/sell/hold decision, or states/implies "
        "whether now is a good or bad time to invest."
    )
    reasoning: str = Field(description="One short sentence explaining the judgment.")


def eval_judge_advice_check(text: str) -> AdviceGivingJudgment:
    """Independent second opinion for the OUTPUT guardrail, structurally parallel to
    eval_judge_advice_seeking above - but with one important difference, spelled out here
    so it isn't mistaken for an equally strong check.

    On the INPUT side, the live gate's own LLM layer is ROUTER_MODEL (cheap), so
    eval_judge_advice_seeking is a genuinely stronger, independent tier - a real second
    opinion. On the OUTPUT side, the live gate's own LLM layer
    (agent.guardrails.advice_check.llm_judge_advice_check) already runs on JUDGE_MODEL -
    the strongest tier this app uses anywhere - so this function can't out-rank it the
    same way; both run on the identical model. What it still buys you: a separately
    written prompt/implementation that the live gate never calls and that never changes
    when advice_check.py's own prompt is tuned, so monitoring/guardrail_sampling.py's
    output-side disagreement check isn't just re-invoking the exact same function object
    on the exact same input (which would only ever catch LLM sampling non-determinism).
    It's still the same underlying model, though - it will NOT catch a mistake that's
    systemic to JUDGE_MODEL itself, the way the input side's cheap-vs-strong gap can.
    Used only by monitoring/guardrail_sampling.py, never the live gate."""
    prompt = (
        "You are an independent compliance auditor reviewing text produced by a "
        "financial analysis tool. The tool is only allowed to explain what happened to a "
        "stock and why - it must never recommend buying, selling, or holding, and never "
        "state or imply whether now is a good or bad time to invest. Read the text "
        "carefully, including indirect or implied recommendations (e.g. praising a "
        "stock's prospects in a way that nudges toward buying, or framing a decline as a "
        "buying opportunity), not just explicit 'you should buy/sell' phrasing. Does the "
        "following text cross that line?\n\n"
        f"Text:\n{text}"
    )
    judge = _judge_llm().with_structured_output(AdviceGivingJudgment)
    return judge.invoke(prompt)


class ClassificationJudgment(BaseModel):
    is_correct_match: bool = Field(
        description="True if this news article genuinely belongs to the given feed's topic, based on its "
        "description - not merely thematically adjacent."
    )
    reasoning: str = Field(description="One short sentence explaining the judgment.")


def judge_feed_classification(article_content: str, feed_name: str, feed_description: str) -> ClassificationJudgment:
    """Independent JUDGE_MODEL check of whether a news article was correctly matched to
    a feed. The live classifier (db/queries.py::match_feed_for_embedding /
    match_common_feed_template_for_embedding) only checks embedding similarity against a
    threshold - no semantic verification that the match is actually genuine, so this is
    a real gap, not a duplicate of an existing check (run_classification_eval.py's
    Evaluation panel scores the same live classifier, but only against a hand-labeled
    CSV, never with an LLM). Used only by monitoring/classification_sampling.py -
    deliberately not run at ingestion time, since an LLM call per classified article
    would be far too costly at real pipeline volume. `article_content` should be built
    via agent/shared/news_text.py::format_news_content (title + snippet) by the caller,
    not the bare headline - a headline alone is often too thin for this judge to tell a
    genuine match from a thematically-adjacent false positive."""
    prompt = (
        "You are auditing whether a news article was correctly matched to a topic feed "
        "for a stock-tracking tool. The match was made by embedding similarity, which can "
        "produce false positives - articles that are thematically adjacent but don't "
        "actually belong to the feed's topic. Does this article genuinely belong to the "
        "feed below?\n\n"
        f"Feed: {feed_name}\n"
        f"Feed description: {feed_description}\n\n"
        f"Article: {article_content}"
    )
    judge = _judge_llm().with_structured_output(ClassificationJudgment)
    return judge.invoke(prompt)
