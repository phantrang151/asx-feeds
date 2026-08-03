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
    # them would fail at runtime. Add each back here once its node exists. 'declined'
    # covers every guardrail short-circuit (invalid ticker, advice-seeking question,
    # recursion/token-budget abort, advice-language-detected output) - router_node and
    # conduct_analysis_node route straight to END with a decline message instead.
    category: Optional[Literal["search_news", "conduct_analysis", "declined"]]
    result: Optional[str]
    references: Optional[list[Reference]]
    # Full, unfiltered evidence conduct_analysis_node gathered (see
    # _extract_tool_evidence) - unlike `references`, not deduped/filtered for the UI.
    # Exposed on State so eval/run_generation_eval.py can judge groundedness against it
    # from outside the node.
    evidence: Optional[list[dict]]


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
    is_advice_seeking: bool = Field(
        description=(
            "True if the user is asking for a recommendation or opinion on whether to "
            "buy, sell, or hold a stock, or whether it's a 'good investment' (e.g. "
            "'should I buy TLS.AX', 'is TPG a good investment'). False for questions "
            "about what happened or why, even if they mention price or profit (e.g. "
            "'why is TLS.AX's profit increasing', 'what happened to TPG's share price')."
        )
    )
