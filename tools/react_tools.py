from langchain_core.tools import tool

from tools.search import search_news as _search_news
from tools.price import get_latest_price as _get_latest_price
from tools.embeddings import embed
from db.client import get_client
from db.queries import match_document_chunks_for_embedding
from db.storage import DOCUMENTS_BUCKET

# How long a signed link to an uploaded report file stays valid. References aren't
# persisted server-side (only kept in the frontend's in-memory chat history), so this
# just needs to outlive a browser session, not be permanent.
_DOCUMENT_LINK_EXPIRY_SECONDS = 24 * 60 * 60


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
def search_news_tool(ticker: str):
    """Get recent news headlines for an ASX ticker. Input is the ticker symbol, e.g. 'TLS.AX'."""
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
