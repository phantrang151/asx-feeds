from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from langchain_core.tools import tool

from tools.search import search_news as _search_news
from tools.price import get_latest_price as _get_latest_price
from tools.embeddings import embed
from db.client import get_client
from db.queries import (
    get_company_sector,
    get_peer_tickers,
    match_document_chunks_for_embedding,
    match_ticker_news_for_embedding,
)
from db.storage import DOCUMENTS_BUCKET

# How long a signed link to an uploaded report file stays valid. References aren't
# persisted server-side (only kept in the frontend's in-memory chat history), so this
# just needs to outlive a browser session, not be permanent.
_DOCUMENT_LINK_EXPIRY_SECONDS = 24 * 60 * 60


@dataclass
class _ResearchGate:
    internal_news_called: bool = False
    target_news_found: bool = False


_research_gate: ContextVar[_ResearchGate | None] = ContextVar("research_gate", default=None)


@contextmanager
def research_gate():
    """Scope ReAct source ordering to one request without sharing state across users."""
    token = _research_gate.set(_ResearchGate())
    try:
        yield
    finally:
        _research_gate.reset(token)


def _require_internal_news(source_name: str) -> str | None:
    gate = _research_gate.get()
    if gate and not gate.internal_news_called:
        return (
            f"{source_name} is blocked until search_internal_news_tool has been called first. "
            "Call search_internal_news_tool for the target ticker before using another research source."
        )
    return None


def _internal_tool_result(content: str) -> tuple[str, list[dict]]:
    """Keep guardrail control messages available to the model, but mark them as non-evidence."""
    return content, [{"content": content, "visibility": "internal", "outcome": "blocked"}]


def _document_url(source_type: str, source_url: str | None, storage_path: str | None) -> str | None:
    """A pasted link cites its own URL directly. An uploaded file has no public URL -
    the documents bucket is private (see db/storage.py) - so it needs a signed URL
    minted on demand instead."""
    if source_type == "link":
        return source_url
    if not storage_path:
        return None
    signed = get_client().storage.from_(DOCUMENTS_BUCKET).create_signed_url(
        storage_path, _DOCUMENT_LINK_EXPIRY_SECONDS
    )
    return signed.get("signedURL")


@tool(response_format="content_and_artifact")
def search_internal_news_tool(ticker: str, query: str):
    """Search the application's cached news for the target ASX company.

    This is the first research source for ReAct analysis questions. Use it before uploaded
    financial reports, external web news, or peer-company news. The results are limited to
    the target ticker and recent cached articles; do not use peer or external sources just
    to increase the amount of evidence.
    """
    gate = _research_gate.get()
    matches = match_ticker_news_for_embedding(
        [ticker], embed(query), match_count=5, similarity_threshold=0.35,
    )
    if gate:
        gate.internal_news_called = True
        gate.target_news_found = bool(matches)
    if not matches:
        return f"No relevant cached news found for {ticker}.", []
    content = "\n".join(f"- {m['title']} ({m.get('publisher') or 'Unknown'})" for m in matches)
    references = [
        {"content": f"{m['title']} ({m.get('publisher') or 'Unknown'})", "url": m.get("source_url")}
        for m in matches
    ]
    return content, references


@tool(response_format="content_and_artifact")
def search_internal_peer_news_tool(ticker: str, query: str):
    """Search cached news for up to four ASX 200 companies in the target company's industry.

    Use this only for an explicit comparison or industry-context question, and only after
    search_internal_news_tool has been used for the target ticker. Never use peer news as a
    substitute for evidence about the target company. Results are limited to recent cached
    articles with at least 0.60 semantic similarity.
    """
    blocked = _require_internal_news("search_internal_peer_news_tool")
    if blocked:
        return _internal_tool_result(blocked)
    gate = _research_gate.get()
    if gate and not gate.target_news_found:
        return "Peer news is blocked because no relevant target-company news was found.", []
    company = get_company_sector(ticker)
    if not company or not company.get("industry"):
        return f"No cached industry classification is available for {ticker}.", []
    peer_tickers = get_peer_tickers(company["industry"], exclude_ticker=ticker, limit=4)
    matches = match_ticker_news_for_embedding(
        peer_tickers, embed(query), match_count=5, similarity_threshold=0.6,
    )
    if not matches:
        return f"No relevant cached peer news found for {ticker}.", []
    content = "\n".join(
        f"- [{m['ticker']}] {m['title']} ({m.get('publisher') or 'Unknown'})" for m in matches
    )
    references = [
        {
            "content": f"[{m['ticker']}] {m['title']} ({m.get('publisher') or 'Unknown'})",
            "url": m.get("source_url"),
        }
        for m in matches
    ]
    return content, references


@tool(response_format="content_and_artifact")
def search_news_tool(ticker: str):
    """Fallback to fresh external Yahoo Finance news for an ASX ticker.

    For ReAct analysis, use search_internal_news_tool first. Use this tool only when cached
    company news is missing, stale, or insufficient for the user's question. This tool is
    also used directly for plain latest-news lookups, where freshness is the priority.
    """
    blocked = _require_internal_news("search_news_tool")
    if blocked:
        return _internal_tool_result(blocked)
    articles = _search_news(ticker)
    if not articles:
        return f"No recent news found for {ticker}.", []
    # content is what the model reads; the artifact is only for _extract_tool_evidence to
    # build user-facing references from, in the shared {"content", "url"} shape every
    # tool's artifact uses - no reason to spend the model's context on URLs it doesn't
    # need to reason about.
    content = "\n".join(f"- {a['title']} ({a['publisher']})" for a in articles)
    references = [
        {"content": f"{a['title']} ({a.get('publisher') or 'Unknown'})", "url": a.get("link")}
        for a in articles
    ]
    return content, references


@tool
def get_latest_price_tool(ticker: str) -> str:
    """Get the latest share price for an ASX ticker. Input is the ticker symbol, e.g. 'TLS.AX'."""
    return _get_latest_price(ticker)


@tool(response_format="content_and_artifact")
def search_financial_reports_tool(ticker: str, query: str):
    """Search previously admin-uploaded financial report documents (annual/half-year
    reports, etc.) for an ASX ticker for content relevant to a query. Prefer this over
    general knowledge whenever an uploaded report might actually answer the question -
    e.g. query='revenue growth drivers' or query='reasons for profit increase'."""
    blocked = _require_internal_news("search_financial_reports_tool")
    if blocked:
        return _internal_tool_result(blocked)
    matches = match_document_chunks_for_embedding(ticker, embed(query), match_count=5)
    if not matches:
        return f"No uploaded financial report content found for {ticker}.", []
    content = "\n\n".join(f"[{m['document_title']}] {m['content']}" for m in matches)
    # One signed URL per document, not per chunk - several chunks routinely come from
    # the same report.
    urls_by_document = {}
    references = []
    for m in matches:
        doc_id = m["document_id"]
        if doc_id not in urls_by_document:
            urls_by_document[doc_id] = _document_url(m["source_type"], m["source_url"], m["storage_path"])
        # "content" stays the short display label (filename) the frontend's citation
        # list renders as link text (see AnswerBlock in AskQuestion.js) - "excerpt" carries
        # the actual chunk text alongside it so judge_groundedness (eval/judge.py) has real
        # evidence to check claims against, not just a filename.
        references.append({"content": m["document_title"], "excerpt": m["content"], "url": urls_by_document[doc_id]})
    return content, references
