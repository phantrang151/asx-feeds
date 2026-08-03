from typing import Optional

from langchain_groq import ChatGroq

from config import MODEL, GROQ_API_KEY

SYNTHESIS_PROMPT = """You are a financial analyst. You are given evidence gathered about a stock -
this may include recent news, financial figures, and price movements.

Look across ALL of the evidence together and produce one short, connected insight, in the style of:
"Profit and stock price have risen over the past 2 years, but this is driven by price increases and
staff reductions rather than organic growth, which may not be sustainable."

Do not just summarize each piece of evidence separately - your job is to find the connection between
them. If there isn't enough evidence to draw a connection, say so plainly rather than guessing.

Describe what happened and why - never recommend buying, selling, or holding the stock, and never
state or imply whether now is a good or bad time to invest."""


def synthesize_insight(ticker: str, evidence: list[dict], callbacks: Optional[list] = None) -> str:
    """
    Takes whatever evidence was gathered - news items, financial figures, price data, in any mix -
    and produces one reasoned, cross-referenced insight. Shared by:
      - conduct_analysis (ReAct): evidence gathered on the fly, one tool call at a time
      - synthesize_insight pipeline node (Plan-Execute): evidence gathered via a fixed plan
    Each `evidence` item is expected to look like {"source": str, "content": str}.

    `callbacks`, if given, is passed straight into this call's config - conduct_analysis_node
    passes the same TokenBudgetCallback instance used for its ReAct loop, so the per-request
    token ceiling covers this call too, not just the tool loop.
    """
    if not evidence:
        return f"Not enough evidence was gathered for {ticker} to produce an insight."

    evidence_text = "\n\n".join(
        f"[{item.get('source', 'unknown')}] {item.get('content')}" for item in evidence
    )

    llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY)
    prompt = f"{SYNTHESIS_PROMPT}\n\nTicker: {ticker}\n\nEvidence:\n{evidence_text}"
    response = llm.invoke(prompt, config={"callbacks": callbacks} if callbacks else None)
    return response.content.strip()
