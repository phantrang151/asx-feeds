from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import END
from langgraph.types import Command

from .schemas import State, Router
from .prompts import ROUTER_PROMPT
from . import decline_messages
from agent.guardrails.tickers import validate_ticker
from config import MODEL, GROQ_API_KEY
from tools.search import search_news


def _declined(ticker: str, message: str) -> Command:
    """Shared shape for every router-level guardrail short-circuit - routes straight to
    END with a decline message instead of the LLM's chosen category, same
    messages/references/evidence contract every other terminal node returns so
    /api/ask's response shape and the frontend's AnswerBlock stay unaffected."""
    return Command(
        goto=END,
        update={
            "ticker": ticker,
            "category": "declined",
            "result": message,
            "references": [],
            "evidence": [],
            "messages": [AIMessage(content=message)],
        },
    )


def router_node(state: State):
    """Determine the category of the request and the ticker symbol."""
    human_message = state["messages"]

    llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY)
    llm_router = llm.with_structured_output(Router)

    response = llm_router.invoke([SystemMessage(content=ROUTER_PROMPT)] + human_message)

    # Input guardrails, checked before any live tool call is made against the LLM's
    # ticker guess: reject a ticker that doesn't resolve against a real ASX-listed
    # company, then decline anything asking for a buy/sell/hold recommendation rather
    # than an explanation - independent of whichever category the LLM picked, since an
    # advice-seeking question can get routed to either search_news or conduct_analysis.
    if not validate_ticker(response.ticker):
        return _declined(response.ticker, decline_messages.TICKER_NOT_FOUND)
    if response.is_advice_seeking:
        return _declined(response.ticker, decline_messages.ADVICE_SEEKING)

    return Command(
        goto=response.category,
        update={"ticker": response.ticker, "category": response.category},
    )


def search_news_node(state: State):
    """Search for news based on the ticker symbol."""
    ticker = state["ticker"]

    articles = search_news(ticker)
    if not articles:
        answer = f"No recent news found for {ticker}."
        references = []
    else:
        answer = "\n".join(f"- {a['title']} ({a.get('publisher') or 'Unknown'})" for a in articles)
        references = [
            {
                "source": "search_news",
                "content": f"{a['title']} ({a.get('publisher') or 'Unknown'})",
                "url": a.get("link"),
            }
            for a in articles
        ]

    return Command(
        update={"result": answer, "references": references, "messages": [AIMessage(content=answer)]}
    )
