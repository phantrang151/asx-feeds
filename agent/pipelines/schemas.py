from typing_extensions import TypedDict


class NewsArticle(TypedDict):
    title: str
    publisher: str
    link: str
    published: str


class PipelineState(TypedDict):
    """State for the daily news ingestion pipeline. No message history needed -
    this is a scheduled batch job, not a conversation."""

    user_id: str
    ticker: str
    raw_articles: list[NewsArticle]
    classified_count: int
    skipped_count: int
