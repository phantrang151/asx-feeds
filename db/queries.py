from typing import Optional

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
    match_threshold: float = 0.35,
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
            }
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


def match_feed_for_embedding(
    user_id: str, ticker: str, embedding: list[float], match_count: int = 3
) -> list[dict]:
    """
    Calls the match_feeds() Postgres function (see schema.sql) to run a
    pgvector cosine-similarity search scoped to this user's feeds for this ticker.
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
