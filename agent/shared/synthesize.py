from typing import Optional

from langchain_anthropic import ChatAnthropic

from config import ANALYSIS_MODEL, ANTHROPIC_API_KEY

SYNTHESIS_PROMPT = """You are a financial analyst. You are given evidence gathered about a stock -
this may include recent news, financial figures, and price movements.

Look across ALL of the evidence together and produce one short, connected insight, in the style of:
"Profit and stock price have risen over the past 2 years, but this is driven by price increases and
staff reductions rather than organic growth, which may not be sustainable."

Some evidence may be labeled with other companies in the same industry. When that peer evidence is
present, use it as comparative context: assess whether the target company's strategy, performance,
or event appears to follow an industry trend, move against it, or stand out from peers. Make the
comparison explicit when it improves the explanation, but do not treat peer news as evidence that
the target company did something it did not report, and do not force a comparison when the peer
evidence is unrelated or too thin.

Do not just summarize each piece of evidence separately - your job is to find the connection between
them. If there isn't enough evidence to draw a connection, say so plainly rather than guessing.

Describe what happened and why - never recommend buying, selling, or holding the stock, and never
state or imply whether now is a good or bad time to invest."""

# Used instead of SYNTHESIS_PROMPT when the call is answering a specific user question (chat's
# conduct_analysis) rather than generating a proactive feed digest (the Plan-Execute pipeline,
# which has no question - see synthesize_node in agent/pipelines/insight_nodes.py). Without this,
# the LLM was forced into the "what happened and why, profit/price framing" example above even
# when the user asked something the evidence didn't actually cover in that shape (e.g. "list
# Telstra's key strategies" got answered with a profit/valuation narrative because that's the
# only style the prompt offered).
SYNTHESIS_PROMPT_WITH_QUESTION = """You are a financial analyst. You are given evidence gathered
about a stock while researching the user's question below - this may include recent news,
financial figures, and price movements.

Answer the user's question directly, in whatever form it actually calls for (a list, a short
paragraph, a comparison, etc.) - do not force the answer into a "what happened and why" narrative
if that isn't what was asked. Look across the evidence together rather than summarizing each piece
separately, and only use evidence that's actually relevant to the question.

If the gathered evidence doesn't cover what the question asks, say so plainly rather than
answering a different, adjacent question with what you do have.

Never recommend buying, selling, or holding the stock, and never state or imply whether now is a
good or bad time to invest."""


def synthesize_insight(
    ticker: str,
    evidence: list[dict],
    callbacks: Optional[list] = None,
    question: Optional[str] = None,
    draft_answer: Optional[str] = None,
    no_evidence_feeds: Optional[list[str]] = None,
    insufficient_evidence_feeds: Optional[list[str]] = None,
) -> str:
    """
    Takes whatever evidence was gathered - news items, financial figures, price data, in any mix -
    and produces one reasoned, cross-referenced insight. Shared by:
      - conduct_analysis (ReAct): evidence gathered on the fly, one tool call at a time, answering
        a specific user question - pass `question` so the answer actually addresses it, and
        `draft_answer` (the ReAct loop's own final message, before this call replaces it) so
        synthesis can check/refine an existing attempt instead of starting from nothing.
      - synthesize_insight pipeline node (Plan-Execute): evidence gathered via a fixed plan, no
        question or draft - a proactive "what happened and why" digest, not a Q&A turn. Pass
        `no_evidence_feeds`/`insufficient_evidence_feeds` (pipeline-only, ignored whenever
        `question` is set) - feed names from synthesize_node (see
        agent/pipelines/insight_nodes.py), split by WHY a feed didn't make it into `evidence`:
        zero items at all vs. items that came back but were judged too thin/off-topic - so the
        digest names those gaps explicitly, with the right wording for each, instead of just
        going quiet about them or claiming "no evidence" for a feed that actually had some.
    Each `evidence` item is expected to look like {"source": str, "content": str}.

    `callbacks`, if given, is passed straight into this call's config, tagged with
    metadata={"step_name": "synthesis"} for RequestTracer (see
    agent/guardrails/tracer.py) - conduct_analysis_node passes the same
    TokenBudgetCallback instance used for its ReAct loop, so the per-request token
    ceiling covers this call too, not just the tool loop.
    """
    skipped_notes = []
    if no_evidence_feeds:
        skipped_notes.append(f"No evidence was found for: {', '.join(no_evidence_feeds)}.")
    if insufficient_evidence_feeds:
        skipped_notes.append(f"Not enough evidence was found for: {', '.join(insufficient_evidence_feeds)}.")
    skipped_note = (" " + " ".join(skipped_notes)) if skipped_notes else ""

    if not evidence:
        return f"Not enough evidence was gathered for {ticker} to produce an insight.{skipped_note}"

    evidence_text = "\n\n".join(
        f"[{item.get('source', 'unknown')}] {item.get('content')}" for item in evidence
    )

    llm = ChatAnthropic(model=ANALYSIS_MODEL, api_key=ANTHROPIC_API_KEY)
    if question:
        draft_block = (
            f"\n\nA draft answer was already produced by an earlier reasoning pass over this "
            f"same evidence:\n{draft_answer}\n\nUse it as a starting point if it's useful, but "
            f"verify it against the evidence above rather than trusting it - correct, complete, "
            f"or replace it as needed. It may be incomplete or may have drawn conclusions the "
            f"evidence doesn't actually support."
            if draft_answer
            else ""
        )
        prompt = (
            f"{SYNTHESIS_PROMPT_WITH_QUESTION}\n\nTicker: {ticker}\n\n"
            f"User's question: {question}\n\nEvidence:\n{evidence_text}{draft_block}"
        )
    else:
        gap_parts = []
        if no_evidence_feeds:
            gap_parts.append(f"no evidence at all this run: {', '.join(no_evidence_feeds)}")
        if insufficient_evidence_feeds:
            gap_parts.append(
                f"evidence that was found but judged too thin or off-topic to draw a "
                f"conclusion from: {', '.join(insufficient_evidence_feeds)}"
            )
        skipped_block = (
            f"\n\nThe following topics were skipped this run - {'; and '.join(gap_parts)}. "
            f"Explicitly name these as gaps in your insight, keeping the distinction between "
            f"the two clear, rather than silently ignoring them or implying no evidence exists "
            f"for a topic that actually had some."
            if gap_parts
            else ""
        )
        prompt = f"{SYNTHESIS_PROMPT}\n\nTicker: {ticker}\n\nEvidence:\n{evidence_text}{skipped_block}"
    config = {"callbacks": callbacks, "metadata": {"step_name": "synthesis"}} if callbacks else None
    response = llm.invoke(prompt, config=config)
    content = response.content
    if isinstance(content, list):
        content = "".join(
            block.get("text", "") for block in content if isinstance(block, dict) and block.get("type") == "text"
        )
    return content.strip()
