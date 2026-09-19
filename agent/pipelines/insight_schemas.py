from typing import Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class FeedSummary(BaseModel):
    summary: str = Field(description="1-3 sentence summary of what these items say about this topic")
    sufficient: bool = Field(
        description="True if these items give a real, on-topic signal about this specific "
        "feed's subject - even a single genuinely relevant item counts as sufficient, since "
        "one data point can still be worth surfacing as an early signal. False only if the "
        "items are off-topic, too vague, or don't actually address what this feed is meant "
        "to track, regardless of how many there are."
    )


class FeedSourceDecision(BaseModel):
    feed_name: str = Field(description="Must exactly match one of the feed names given in the prompt")
    needs_reports: bool = Field(
        description="True if official financial-report content (uploaded filings, earnings "
        "reports) would materially help this feed's topic - e.g. profit, revenue, margins, "
        "earnings trends. False for feeds about sentiment, competitors, management "
        "commentary, or anything reports don't typically cover."
    )
    needs_peer_news: bool = Field(
        description="True if news about OTHER companies in the same industry would "
        "materially help this feed's topic - e.g. competitive positioning, market share, "
        "industry trends, or strategy judged relative to rivals. False for feeds that are "
        "purely about this company's own numbers or internal matters."
    )


class FeedSourcePlan(BaseModel):
    decisions: list[FeedSourceDecision]


class InsightState(TypedDict):
    user_id: str
    ticker: str
    items_by_feed: dict[str, list[dict]]  # every feed's own items, fetched once by planner_node
    # feed_name -> that feed's own description_embedding (reused for supplementary-source
    # queries in execute_step_node instead of a fresh embed() call)
    feed_embeddings: dict[str, list[float]]
    # feed_name -> that feed's own feed_description, set once by planner_node - passed to
    # summarize_feed_items alongside feed_name so its sufficiency judgment isn't made on
    # the bare feed name alone (the same name can carry a different description per
    # company - see decide_feed_sources, which already does this).
    feed_descriptions: dict[str, str]
    # feed_name -> decide_feed_sources' verdict on needs_reports/needs_peer_news, set once
    # by planner_node
    source_decisions: dict[str, FeedSourceDecision]
    # feed_name -> extra items (report chunks / peer-ticker news) execute_step_node fetched
    # for that feed. Deliberately excluded from item id tracking - see
    # based_on_feed_item_ids below - items here have no "id" key at all.
    supplementary_items_by_feed: dict[str, list[dict]]
    plan: list[str]
    # [{"step": feed_name, "items": [...], "summary": str, "sufficient": bool}, ...]
    step_results: list[dict]
    insight_text: Optional[str]
    # Strictly real custom_feed_items/common_feed_items ids - never document_chunks or another
    # ticker's ticker_news ids, since frontend/pages/alerts.js only resolves ids against
    # the user_feed_items view. See synthesize_node and execute_step_node in
    # insight_nodes.py for how this invariant is kept.
    based_on_feed_item_ids: list[str]
