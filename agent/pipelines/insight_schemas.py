from typing import Optional
from typing_extensions import TypedDict
from pydantic import BaseModel, Field


class Plan(BaseModel):
    steps: list[str] = Field(
        description="Ordered list of feed names to review to build a cross-feed insight"
    )


class InsightState(TypedDict):
    user_id: str
    ticker: str
    plan: list[str]
    step_results: list[dict]  # [{"step": feed_name, "items": [feed_item, ...]}, ...]
    insight_text: Optional[str]
    based_on_feed_item_ids: list[str]
