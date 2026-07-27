from langchain_groq import ChatGroq
from langchain_core.messages import AIMessage, SystemMessage
from langgraph.types import Command

from .schemas import State, Router
from .prompts import ROUTER_PROMPT
from config import MODEL, GROQ_API_KEY
from tools.search import search_news


def router_node(state: State):
    """Determine the category of the request and the ticker symbol."""
    human_message = state["messages"]

    llm = ChatGroq(model=MODEL, api_key=GROQ_API_KEY)
    llm_router = llm.with_structured_output(Router)

    response = llm_router.invoke([SystemMessage(content=ROUTER_PROMPT)] + human_message)

    return Command(
        goto=response.category,
        update={"ticker": response.ticker, "category": response.category},
    )


def search_news_node(state: State):
    """Search for news based on the ticker symbol."""
    ticker = state["ticker"]

    news_result = search_news(ticker)

    return Command(
        update={"result": news_result, "messages": [AIMessage(content=str(news_result))]}
    )
