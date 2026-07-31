from typing_extensions import TypedDict


class NewsArticle(TypedDict):
    title: str
    publisher: str
    link: str
    published: str


class FetchState(TypedDict):
    """State for phases 1 and 1.5: ticker-scoped news caching and common-feed
    classification. Runs once per distinct watchlisted ticker per pipeline run,
    regardless of how many users are watching it."""

    ticker: str
    articles_cached: int
    common_classified_count: int


class ClassifyState(TypedDict):
    """State for phase 2: per-(user, ticker) custom-feed classification. Reads from the
    ticker_news cache populated by phase 1 instead of calling yfinance directly, and
    only classifies feed_type='custom' feeds - common feeds are already handled by
    phase 1.5."""

    user_id: str
    ticker: str
    run_cutoff: str
    classified_count: int
    skipped_count: int
