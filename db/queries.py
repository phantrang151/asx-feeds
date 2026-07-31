from typing import Optional
from datetime import datetime, timezone

from db.client import get_client


def get_feeds_for_user(user_id: str, ticker: Optional[str] = None) -> list[dict]:
    client = get_client()
    query = client.table("feeds").select("*").eq("user_id", user_id)
    if ticker:
        query = query.eq("ticker", ticker)
    return query.execute().data


def create_feed(
    user_id: str,
    ticker: str,
    feed_name: str,
    feed_description: str,
    description_embedding: list[float],
    match_threshold: float = 0.4,
    feed_type: str = "custom",
    common_feed_template_id: Optional[str] = None,
) -> dict:
    client = get_client()
    result = (
        client.table("feeds")
        .insert(
            {
                "user_id": user_id,
                "ticker": ticker,
                "feed_name": feed_name,
                "feed_description": feed_description,
                "description_embedding": description_embedding,
                "match_threshold": match_threshold,
                "feed_type": feed_type,
                "common_feed_template_id": common_feed_template_id,
            }
        )
        .execute()
    )
    return result.data[0]


def get_feed(feed_id: str, user_id: str) -> Optional[dict]:
    """Single ownership-scoped feed fetch - used to 404 cleanly on an edit/refresh request
    for a feed that doesn't exist or isn't the caller's."""
    client = get_client()
    result = (
        client.table("feeds").select("*").eq("id", feed_id).eq("user_id", user_id).limit(1).execute()
    )
    return result.data[0] if result.data else None


def update_feed(
    feed_id: str,
    user_id: str,
    feed_name: Optional[str] = None,
    feed_description: Optional[str] = None,
    description_embedding: Optional[list[float]] = None,
    match_threshold: Optional[float] = None,
) -> Optional[dict]:
    """
    Updates only the fields passed in. Scoped to feed_type='custom' as well as ownership -
    common feeds mirror a shared common_feed_templates row and aren't user-editable, so an
    edit request against one is treated the same as one against a feed the caller doesn't
    own: a no-op that returns None for the endpoint to 404 on.
    """
    updates = {
        k: v
        for k, v in {
            "feed_name": feed_name,
            "feed_description": feed_description,
            "description_embedding": description_embedding,
            "match_threshold": match_threshold,
        }.items()
        if v is not None
    }
    if not updates:
        return get_feed(feed_id, user_id)

    client = get_client()
    result = (
        client.table("feeds")
        .update(updates)
        .eq("id", feed_id)
        .eq("user_id", user_id)
        .eq("feed_type", "custom")
        .execute()
    )
    return result.data[0] if result.data else None


def set_feed_needs_rematch(feed_id: str, user_id: str) -> Optional[dict]:
    """Flags a custom feed so the next pipeline run wipes its feed_items and re-matches its
    entire ticker_news history under its current description/threshold (see
    classify_and_store_node). Same ownership+custom-only scoping as update_feed."""
    client = get_client()
    result = (
        client.table("feeds")
        .update({"needs_rematch": True})
        .eq("id", feed_id)
        .eq("user_id", user_id)
        .eq("feed_type", "custom")
        .execute()
    )
    return result.data[0] if result.data else None


def get_common_feed_templates() -> list[dict]:
    client = get_client()
    return client.table("common_feed_templates").select("*").execute().data


def get_common_feed_template(template_id: str) -> Optional[dict]:
    client = get_client()
    result = (
        client.table("common_feed_templates").select("*").eq("id", template_id).limit(1).execute()
    )
    return result.data[0] if result.data else None


def upsert_common_feed_template(
    name: str, description: str, description_embedding: list[float], match_threshold: float = 0.22
) -> dict:
    """Used only by the one-off seed script - common_feed_templates is fixed, curated
    content (Revenue Trend, Business Strategy, Red Flags), not something created via
    the API."""
    client = get_client()
    result = (
        client.table("common_feed_templates")
        .upsert(
            {
                "name": name,
                "description": description,
                "description_embedding": description_embedding,
                "match_threshold": match_threshold,
            },
            on_conflict="name",
        )
        .execute()
    )
    return result.data[0]


def insert_feed_item(
    feed_id: str,
    source_type: str,
    content_summary: str,
    source_url: Optional[str],
    content_embedding: list[float],
) -> dict:
    client = get_client()
    result = (
        client.table("feed_items")
        .insert(
            {
                "feed_id": feed_id,
                "source_type": source_type,
                "content_summary": content_summary,
                "source_url": source_url,
                "content_embedding": content_embedding,
            }
        )
        .execute()
    )
    return result.data[0]


def get_feed_items(feed_id: str) -> list[dict]:
    client = get_client()
    return (
        client.table("feed_items")
        .select("*")
        .eq("feed_id", feed_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def get_latest_financial_record(ticker: str) -> Optional[dict]:
    client = get_client()
    result = (
        client.table("financial_records")
        .select("*")
        .eq("ticker", ticker)
        .order("period", desc=True)
        .limit(1)
        .execute()
    )
    return result.data[0] if result.data else None


def insert_ticker_insight(
    user_id: str, ticker: str, insight_text: str, based_on_feed_item_ids: list[str]
) -> dict:
    client = get_client()
    result = (
        client.table("ticker_insights")
        .insert(
            {
                "user_id": user_id,
                "ticker": ticker,
                "insight_text": insight_text,
                "based_on_feed_item_ids": based_on_feed_item_ids,
            }
        )
        .execute()
    )
    return result.data[0]


def get_all_watchlist_entries() -> list[dict]:
    """Every (user, ticker) pair currently watchlisted by anyone - what phase 2 (custom
    feed classification) of the ingestion pipeline loops over."""
    client = get_client()
    return client.table("watchlist_stocks").select("user_id, ticker").execute().data


def get_distinct_watchlisted_tickers() -> list[str]:
    """Every ticker at least one user is watching, deduplicated - what phase 1 (news
    fetch + cache) loops over, so a ticker watched by 100 users still gets fetched once."""
    client = get_client()
    result = client.table("watchlist_stocks").select("ticker").execute()
    return sorted({row["ticker"] for row in result.data})


def create_pipeline_run() -> str:
    """Logs the start of a pipeline run and returns its id, so progress can be updated
    once the run finishes (or partially finishes)."""
    client = get_client()
    result = client.table("pipeline_runs").insert({"status": "running"}).execute()
    return result.data[0]["id"]


def update_pipeline_run(
    run_id: str,
    status: str,
    tickers_processed: int,
    feeds_classified: int,
    common_items_classified: int,
    items_skipped: int,
    errors: list[dict],
) -> None:
    client = get_client()
    client.table("pipeline_runs").update(
        {
            "status": status,
            "tickers_processed": tickers_processed,
            "feeds_classified": feeds_classified,
            "common_items_classified": common_items_classified,
            "items_skipped": items_skipped,
            "errors": errors,
            "finished_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", run_id).execute()


def get_recent_pipeline_runs(limit: int = 20) -> list[dict]:
    client = get_client()
    return (
        client.table("pipeline_runs")
        .select("*")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )


def match_feed_for_embedding(
    user_id: str, ticker: str, embedding: list[float], match_count: int = 3
) -> list[dict]:
    """
    Calls the match_feeds() Postgres function (see schema.sql) to run a
    pgvector cosine-similarity search scoped to this user's CUSTOM feeds for this ticker
    (common feeds are matched once per ticker via match_common_feed_template_for_embedding
    instead - match_feeds() filters feed_type='custom' server-side).
    Returns feeds ordered by similarity, highest first.
    """
    client = get_client()
    result = client.rpc(
        "match_feeds",
        {
            "query_embedding": embedding,
            "match_user_id": user_id,
            "match_ticker": ticker,
            "match_count": match_count,
        },
    ).execute()
    return result.data


def match_common_feed_template_for_embedding(
    embedding: list[float], match_count: int = 1
) -> list[dict]:
    """Calls the match_common_feed_templates() Postgres function - the single
    ticker-agnostic top match for one ticker_news row's embedding."""
    client = get_client()
    result = client.rpc(
        "match_common_feed_templates",
        {"query_embedding": embedding, "match_count": match_count},
    ).execute()
    return result.data


def upsert_ticker_news(rows: list[dict]) -> None:
    """
    Upserts pre-shaped ticker_news rows (ticker, title, publisher, source_url,
    published_at, content_embedding), silently skipping ones that already exist for a
    (ticker, source_url) pair - this is what stops the same handful of yfinance
    headlines from being re-embedded and re-inserted on every pipeline run. Articles
    with no source_url can't be deduped this way (a unique constraint never treats two
    NULLs as a conflict) and are always inserted as new.
    """
    if not rows:
        return
    client = get_client()
    client.table("ticker_news").upsert(
        rows, on_conflict="ticker,source_url", ignore_duplicates=True
    ).execute()


def get_unclassified_ticker_news(ticker: str) -> list[dict]:
    """ticker_news rows for this ticker not yet evaluated against common_feed_templates -
    what phase 1.5 loops over, regardless of how many users watch this ticker."""
    client = get_client()
    return (
        client.table("ticker_news")
        .select("*")
        .eq("ticker", ticker)
        .is_("common_classified_at", "null")
        .execute()
        .data
    )


def mark_ticker_news_common_classified(ids: list[str], run_cutoff: str) -> None:
    """Marks these ticker_news rows as evaluated against common_feed_templates, whether
    or not they matched one - so a below-threshold article isn't re-evaluated forever."""
    if not ids:
        return
    client = get_client()
    client.table("ticker_news").update({"common_classified_at": run_cutoff}).in_(
        "id", ids
    ).execute()


def get_ticker_news_since(ticker: str, since: Optional[str], until: str) -> list[dict]:
    """ticker_news rows for this ticker created after `since` (or the ticker's full
    cached history if `since` is None) and no later than `until` - the pipeline run's
    single cutoff timestamp, so articles cached by a ticker fetched later in the same
    run can't leak into this classification pass."""
    client = get_client()
    query = client.table("ticker_news").select("*").eq("ticker", ticker).lte("created_at", until)
    if since:
        query = query.gt("created_at", since)
    return query.execute().data


def bulk_update_feed_last_classified_at(feed_ids: list[str], run_cutoff: str) -> None:
    """Advances the classification watermark for every one of these feeds to the same
    run_cutoff, even ones with zero new matching articles this run."""
    if not feed_ids:
        return
    client = get_client()
    client.table("feeds").update({"last_classified_at": run_cutoff}).in_("id", feed_ids).execute()


def delete_feed_items(feed_ids: list[str]) -> None:
    """Wipes every feed_item for these feeds - the first step of a user-requested refresh,
    before classify_and_store_node re-matches the feed's full ticker_news history."""
    if not feed_ids:
        return
    client = get_client()
    client.table("feed_items").delete().in_("feed_id", feed_ids).execute()


def reset_feed_watermarks(feed_ids: list[str]) -> None:
    """Nulls last_classified_at for these feeds - the second step of a user-requested
    refresh. match_feed_for_embedding reads last_classified_at fresh from the DB on every
    call, so this (not just an in-memory change) is what actually makes
    classify_and_store_node stop skipping the feed's already-seen articles this run."""
    if not feed_ids:
        return
    client = get_client()
    client.table("feeds").update({"last_classified_at": None}).in_("id", feed_ids).execute()


def clear_feeds_needs_rematch(feed_ids: list[str]) -> None:
    """Clears the refresh flag once classify_and_store_node has actually re-matched these
    feeds' full history in this run."""
    if not feed_ids:
        return
    client = get_client()
    client.table("feeds").update({"needs_rematch": False}).in_("id", feed_ids).execute()


def insert_common_feed_item(
    common_feed_template_id: str,
    ticker: str,
    content_summary: str,
    source_url: Optional[str],
    content_embedding: list[float],
) -> None:
    client = get_client()
    client.table("common_feed_items").upsert(
        {
            "common_feed_template_id": common_feed_template_id,
            "ticker": ticker,
            "source_type": "news",
            "content_summary": content_summary,
            "source_url": source_url,
            "content_embedding": content_embedding,
        },
        on_conflict="common_feed_template_id,ticker,source_url",
        ignore_duplicates=True,
    ).execute()
