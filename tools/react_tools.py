from langchain_core.tools import tool

from tools.search import search_news as _search_news
from tools.price import get_latest_price as _get_latest_price
from tools.financials import get_financial_summary as _get_financial_summary
from tools.embeddings import embed
from db.queries import match_document_chunks_for_embedding

# How much of a chunk's text shows up in the user-facing reference list - the model
# itself still reasons over the full chunk via the tool's plain-text content, this only
# trims the reference *preview* so one bullet point doesn't become a 1000-char wall of
# text in the UI.
_REFERENCE_PREVIEW_LEN = 240


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


@tool
def get_financial_summary_tool(ticker: str) -> str:
    """Get the latest stored financial record (revenue, profit, headcount) for an ASX ticker."""
    return _get_financial_summary(ticker)


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
    references = [
        {
            "content": f"[{m['document_title']}] {m['content'][:_REFERENCE_PREVIEW_LEN]}...",
            "url": None,
        }
        for m in matches
    ]
    return content, references
