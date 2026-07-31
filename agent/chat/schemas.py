from typing import Annotated, Literal, Optional
from typing_extensions import TypedDict
from langgraph.graph.message import add_messages
from pydantic import BaseModel, Field


class Reference(TypedDict):
    """One piece of evidence a node used to produce its answer - shown to the user
    above the answer itself, so they see what it's based on before the conclusion."""

    source: str
    content: str
    url: Optional[str]


class State(TypedDict):
    """State of the agent, passed through each step of the graph."""

    messages: Annotated[list, add_messages]
    ticker: Optional[str]
    # NOTE: 'search_price' and 'read_report' are still not implemented - routing to
    # them would fail at runtime. Add each back here once its node exists.
    category: Optional[Literal["search_news", "conduct_analysis"]]
    result: Optional[str]
    references: Optional[list[Reference]]


class Router(BaseModel):
    """Decide the type of request based on user input."""

    category: Literal["search_news", "conduct_analysis"] = Field(
        description=(
            "The category of the request. Use 'search_news' for a plain news lookup. "
            "Use 'conduct_analysis' for anything that asks 'why' or requires reasoning "
            "across news, price, and financials together."
        )
    )
    ticker: str = Field(description="The ticker symbol of the stock, if applicable")
