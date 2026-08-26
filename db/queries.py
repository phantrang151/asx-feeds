import statistics
from typing import Optional
from datetime import datetime, timedelta, timezone

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


def delete_feed(feed_id: str, user_id: str) -> Optional[dict]:
    """Deletes one feed, scoped to ownership only (unlike update_feed, common feeds are
    deletable too - the frontend's delete button shows for both feed types). Cascades to
    the feed's feed_items via schema.sql's ON DELETE CASCADE. Returns the deleted row (so
    the caller has its ticker to re-synthesize the cross-feed insight with) or None if it
    didn't exist / wasn't the caller's."""
    client = get_client()
    result = (
        client.table("feeds")
        .delete()
        .eq("id", feed_id)
        .eq("user_id", user_id)
        .select("*")
        .execute()
    )
    return result.data[0] if result.data else None


def delete_ticker_for_user(ticker: str, user_id: str) -> bool:
    """Deletes this user's feeds and watchlist row for a ticker. Feed-item rows cascade
    from feed deletion; shared ticker and common-feed news are intentionally retained."""
    client = get_client()
    feeds = client.table("feeds").select("id").eq("user_id", user_id).eq("ticker", ticker).execute().data
    had_feeds = bool(feeds)
    client.table("feeds").delete().eq("user_id", user_id).eq("ticker", ticker).execute()
    result = (
        client.table("watchlist_stocks")
        .delete()
        .eq("user_id", user_id)
        .eq("ticker", ticker)
        .select("id")
        .execute()
    )
    return had_feeds or bool(result.data)


def set_feed_needs_rematch(feed_id: str, user_id: str) -> Optional[dict]:
    """Flags a custom feed so the next pipeline run wipes its feed_items and re-matches its
    entire ticker_news history under its current description/threshold (see
    classify_and_store). Same ownership+custom-only scoping as update_feed."""
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


def get_custom_feed_items(feed_id: str) -> list[dict]:
    client = get_client()
    return (
        client.table("feed_items")
        .select("*")
        .eq("feed_id", feed_id)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def get_common_feed_items(common_feed_template_id: str, ticker: str) -> list[dict]:
    """A 'common' feed's items - unlike a custom feed, these never land in feed_items
    (see feeds.feed_type in schema.sql), so a caller walking a user's feeds needs this
    instead of get_custom_feed_items() whenever feed_type == 'common'."""
    client = get_client()
    return (
        client.table("common_feed_items")
        .select("*")
        .eq("common_feed_template_id", common_feed_template_id)
        .eq("ticker", ticker)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def insert_ticker_insight(
    user_id: str,
    ticker: str,
    insight_text: str,
    based_on_feed_item_ids: list[str],
    feed_summaries: list[dict],
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
                "feed_summaries": feed_summaries,
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


def get_ticker_insight_pairs() -> list[dict]:
    """Every (user_id, ticker) pair that already has at least one ticker_insights row -
    lets the orchestrator's insight-synthesis phase tell "never generated yet" apart
    from "generated before, nothing new since", since only the latter should be skipped
    when a run adds no fresh evidence."""
    client = get_client()
    return client.table("ticker_insights").select("user_id, ticker").execute().data


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
    insights_generated: int,
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
            "insights_generated": insights_generated,
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
    before classify_and_store re-matches the feed's full ticker_news history."""
    if not feed_ids:
        return
    client = get_client()
    client.table("feed_items").delete().in_("feed_id", feed_ids).execute()


def reset_feed_watermarks(feed_ids: list[str]) -> None:
    """Nulls last_classified_at for these feeds - the second step of a user-requested
    refresh. match_feed_for_embedding reads last_classified_at fresh from the DB on every
    call, so this (not just an in-memory change) is what actually makes
    classify_and_store stop skipping the feed's already-seen articles this run."""
    if not feed_ids:
        return
    client = get_client()
    client.table("feeds").update({"last_classified_at": None}).in_("id", feed_ids).execute()


def clear_feeds_needs_rematch(feed_ids: list[str]) -> None:
    """Clears the refresh flag once classify_and_store has actually re-matched these
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


def insert_document(
    ticker: str,
    title: str,
    source_type: str,
    source_url: Optional[str],
    uploaded_by: str,
) -> dict:
    client = get_client()
    result = (
        client.table("documents")
        .insert(
            {
                "ticker": ticker,
                "title": title,
                "source_type": source_type,
                "source_url": source_url,
                "uploaded_by": uploaded_by,
                "status": "processing",
            }
        )
        .execute()
    )
    return result.data[0]


def update_document_storage_path(document_id: str, storage_path: str) -> None:
    client = get_client()
    client.table("documents").update({"storage_path": storage_path}).eq("id", document_id).execute()


def update_document_status(document_id: str, status: str, error: Optional[str] = None) -> None:
    client = get_client()
    client.table("documents").update({"status": status, "error": error}).eq("id", document_id).execute()


def insert_document_chunks(
    document_id: str, ticker: str, chunks: list[str], embeddings: list[list[float]]
) -> None:
    if not chunks:
        return
    client = get_client()
    rows = [
        {
            "document_id": document_id,
            "ticker": ticker,
            "chunk_index": i,
            "content": chunk,
            "content_embedding": embedding,
        }
        for i, (chunk, embedding) in enumerate(zip(chunks, embeddings))
    ]
    client.table("document_chunks").insert(rows).execute()


def get_documents_for_ticker(ticker: str) -> list[dict]:
    client = get_client()
    return (
        client.table("documents")
        .select("*")
        .eq("ticker", ticker)
        .order("created_at", desc=True)
        .execute()
        .data
    )


def get_document_chunk_counts(ticker: str) -> dict[str, int]:
    """Calls the get_document_chunk_counts() Postgres function (see schema.sql) - one
    aggregate query instead of counting per-document one at a time."""
    client = get_client()
    result = client.rpc("get_document_chunk_counts", {"doc_ticker": ticker}).execute()
    return {row["document_id"]: row["chunk_count"] for row in result.data}


def match_document_chunks_for_embedding(
    ticker: str, embedding: list[float], match_count: int = 5
) -> list[dict]:
    """Calls the match_document_chunks() Postgres function (see schema.sql) - a pgvector
    cosine-similarity search over admin-uploaded report chunks for this ticker, used by
    search_financial_reports_tool. Returns chunks ordered by similarity, highest first."""
    client = get_client()
    result = client.rpc(
        "match_document_chunks",
        {"query_embedding": embedding, "match_ticker": ticker, "match_count": match_count},
    ).execute()
    return result.data


def match_ticker_news_for_embedding(
    tickers: list[str],
    embedding: list[float],
    match_count: int = 10,
    similarity_threshold: float = 0.6,
    news_since: Optional[str] = None,
) -> list[dict]:
    """Calls match_ticker_news() - pgvector cosine-similarity search over ticker_news
    across MULTIPLE tickers (peer tickers), unlike match_document_chunks_for_embedding's
    single-ticker match. Skips the round trip and returns [] if `tickers` is empty."""
    if not tickers:
        return []
    client = get_client()
    rpc_args = {
        "query_embedding": embedding,
        "match_tickers": tickers,
        "match_count": match_count,
        "similarity_threshold": similarity_threshold,
    }
    if news_since is not None:
        rpc_args["news_since"] = news_since
    result = client.rpc(
        "match_ticker_news",
        rpc_args,
    ).execute()
    return result.data


def upsert_companies(rows: list[dict]) -> None:
    """Bulk upsert for scripts/seed_companies.py - safe to re-run, rows are
    {"ticker", "company_name"} pairs keyed on ticker."""
    if not rows:
        return
    client = get_client()
    client.table("companies").upsert(rows, on_conflict="ticker").execute()


def get_company(ticker: str) -> Optional[dict]:
    """Looked up by the chat agent's ticker-validation guardrail
    (agent/guardrails/tickers.py) before trusting an LLM-proposed ticker."""
    client = get_client()
    result = client.table("companies").select("*").eq("ticker", ticker).limit(1).execute()
    return result.data[0] if result.data else None


def insert_watchlist_ticker(user_id: str, ticker: str, company_name: str | None) -> dict:
    """Adds a ticker to one user's watchlist; ownership comes from the verified JWT."""
    client = get_client()
    result = client.table("watchlist_stocks").insert(
        {"user_id": user_id, "ticker": ticker, "company_name": company_name}
    ).execute()
    return result.data[0]


def get_company_sector(ticker: str) -> Optional[dict]:
    """Sector/industry cache lookup for peer-ticker identification (see
    ingestion_steps.py::ensure_company_sector_cached, the write side). Returns None if no
    companies row exists yet OR sector_fetched_at is null (never successfully attempted) -
    callers should treat both cases identically: no peer lookup possible this run."""
    client = get_client()
    result = client.table("companies").select("*").eq("ticker", ticker).limit(1).execute()
    row = result.data[0] if result.data else None
    return row if row and row.get("sector_fetched_at") else None


def upsert_company_sector(
    ticker: str, company_name: str, sector: Optional[str], industry: Optional[str], fetched_at: str
) -> None:
    """Upserts a companies row with freshly-fetched sector/industry, keyed on ticker -
    creates the row if scripts/seed_companies.py never seeded this ticker (true for any
    watchlisted ticker outside the top-200 seed)."""
    client = get_client()
    client.table("companies").upsert(
        {
            "ticker": ticker,
            "company_name": company_name,
            "sector": sector,
            "industry": industry,
            "sector_fetched_at": fetched_at,
        },
        on_conflict="ticker",
    ).execute()


def get_peer_tickers(industry: str, exclude_ticker: str, limit: int = 4) -> list[str]:
    """Other ASX 200 tickers sharing this industry, for peer-news lookup.
    Queried against the companies cache, not a live yfinance scan - a candidate only
    shows up here once ensure_company_sector_cached has run for it too."""
    client = get_client()
    result = (
        client.table("companies")
        .select("ticker")
        .eq("industry", industry)
        .eq("is_asx200", True)
        .neq("ticker", exclude_ticker)
        .limit(limit)
        .execute()
    )
    return [r["ticker"] for r in result.data]


def count_recent_requests(user_id: str, since: str) -> int:
    """Number of /api/ask calls this user has made since `since` (ISO timestamp) -
    what the rate-limit guardrail (agent/guardrails/rate_limit.py) compares against
    config.RATE_LIMIT_MAX_REQUESTS."""
    client = get_client()
    result = (
        client.table("api_request_log")
        .select("id", count="exact")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .execute()
    )
    return result.count or 0


def log_ask_request(user_id: str) -> None:
    """Records one accepted /api/ask call - what count_recent_requests() above counts
    on the next request from this user."""
    client = get_client()
    client.table("api_request_log").insert({"user_id": user_id}).execute()


def sum_recent_token_usage(user_id: str, since: str) -> int:
    """Total tokens this user's /api/ask requests have logged since `since` (ISO
    timestamp) - what the daily token-budget guardrail
    (agent/guardrails/daily_token_budget.py) compares against
    config.TOKEN_CEILING_PER_USER_PER_DAY. Summed in Python rather than a DB-side SUM -
    same demo-grade scale as count_recent_requests() above."""
    client = get_client()
    result = (
        client.table("llm_token_usage_log")
        .select("tokens")
        .eq("user_id", user_id)
        .gte("created_at", since)
        .execute()
    )
    return sum(row["tokens"] for row in result.data) if result.data else 0


def log_token_usage(user_id: str, tokens: int) -> None:
    """Records the total tokens one /api/ask request spent across every Groq call it
    made - what sum_recent_token_usage() above sums on this user's next request."""
    client = get_client()
    client.table("llm_token_usage_log").insert({"user_id": user_id, "tokens": tokens}).execute()


def get_classified_ticker_news_sample(limit: int) -> list[dict]:
    """Recent ticker_news rows already evaluated against common_feed_templates - the
    pool eval/export_labels.py samples from to build a classification-quality labeling
    worksheet (see match_common_feed_template_for_embedding for how each row's
    candidate feed match is computed)."""
    client = get_client()
    return (
        client.table("ticker_news")
        .select("*")
        .not_.is_("common_classified_at", "null")
        .order("created_at", desc=True)
        .limit(limit)
        .execute()
        .data
    )


def insert_eval_run(eval_type: str, summary: dict) -> dict:
    """Logs one eval run - called by eval/score_classification.py (eval_type=
    'classification') and eval/run_generation_eval.py (eval_type='generation') after
    they finish scoring, so the admin page's Evaluation section has something to read.
    `summary` is whatever shape that eval type's own output looks like - see each
    script - not a fixed schema, since the two eval types measure different things."""
    client = get_client()
    result = (
        client.table("eval_runs").insert({"eval_type": eval_type, "summary": summary}).execute()
    )
    return result.data[0]


def get_recent_eval_runs(eval_type: Optional[str] = None, limit: int = 20) -> list[dict]:
    """Recent eval runs, newest first - what the admin page's Evaluation section
    renders. Filtered to one eval_type if given, otherwise both types interleaved."""
    client = get_client()
    query = client.table("eval_runs").select("*")
    if eval_type:
        query = query.eq("eval_type", eval_type)
    return query.order("created_at", desc=True).limit(limit).execute().data


def insert_request_trace(
    user_id: str,
    thread_id: str,
    question: str,
    ticker: Optional[str],
    category: Optional[str],
    status: str,
    decline_reason: Optional[str],
    input_guardrail_regex_matched: Optional[bool],
    input_guardrail_llm_is_advice: Optional[bool],
    output_guardrail_regex_matched: Optional[bool],
    output_guardrail_llm_is_advice: Optional[bool],
    evidence_count: Optional[int],
    step_count: int,
    total_tokens: Optional[int],
    total_duration_ms: int,
    answer: Optional[str] = None,
    evidence: Optional[list[dict]] = None,
) -> dict:
    """One row per /api/ask request - see request_trace in schema.sql. Called once,
    from api/main.py::ask_endpoint's finally block, after graph.invoke() returns (or
    raises) - so this fires on every outcome (completed, declined, or error), not just
    success. `answer`/`evidence` are only meaningful for a completed conduct_analysis
    request - what eval/run_live_sample_eval.py re-judges later; left None otherwise."""
    client = get_client()
    result = (
        client.table("request_trace")
        .insert(
            {
                "user_id": user_id,
                "thread_id": thread_id,
                "question": question,
                "answer": answer,
                "evidence": evidence,
                "ticker": ticker,
                "category": category,
                "status": status,
                "decline_reason": decline_reason,
                "input_guardrail_regex_matched": input_guardrail_regex_matched,
                "input_guardrail_llm_is_advice": input_guardrail_llm_is_advice,
                "output_guardrail_regex_matched": output_guardrail_regex_matched,
                "output_guardrail_llm_is_advice": output_guardrail_llm_is_advice,
                "evidence_count": evidence_count,
                "step_count": step_count,
                "total_tokens": total_tokens,
                "total_duration_ms": total_duration_ms,
            }
        )
        .execute()
    )
    return result.data[0]


def insert_request_trace_steps(request_trace_id: str, steps: list[dict]) -> None:
    """Bulk-inserts every step a RequestTracer recorded (see
    agent/guardrails/tracer.py) for one request, in order - one call, one round trip,
    rather than one insert per step. No-op for a request with no steps (e.g. declined
    before anything traceable ran, like the input regex gate on its own)."""
    if not steps:
        return
    client = get_client()
    rows = [
        {
            "request_trace_id": request_trace_id,
            "step_index": i,
            "step_name": s["step_name"],
            "step_type": s["step_type"],
            "duration_ms": s["duration_ms"],
            "tokens": s.get("tokens"),
            "result": s.get("result"),
        }
        for i, s in enumerate(steps)
    ]
    client.table("request_trace_steps").insert(rows).execute()


def insert_ops_alert(request_trace_id: str, user_id: str, alert_type: str, threshold: float, actual_value: float) -> dict:
    """One row per tripped ALERT_* threshold (see agent/guardrails/alerts.py) -
    persists what was previously only an ephemeral logger.warning when the matching
    hard guardrail aborted a request."""
    client = get_client()
    result = (
        client.table("ops_alerts")
        .insert(
            {
                "request_trace_id": request_trace_id,
                "user_id": user_id,
                "alert_type": alert_type,
                "threshold": threshold,
                "actual_value": actual_value,
            }
        )
        .execute()
    )
    return result.data[0]


def get_recent_ops_alerts(limit: int = 50) -> list[dict]:
    """Recent alerts across every user, newest first - what the admin page's Alerts
    subsection renders. No question/answer content here (see ops_alerts in schema.sql),
    only ids and numbers - stays within the admin's operational-visibility scope."""
    client = get_client()
    return (
        client.table("ops_alerts").select("*").order("created_at", desc=True).limit(limit).execute().data
    )


def get_efficiency_summary(hours: int = 24 * 7, sample_limit: int = 1000) -> dict:
    """Percentile summary (p50/p95/max) of steps/tokens/latency across recent
    request_trace rows, plus the recursion-limit hit rate - what the admin page's
    Efficiency subsection renders, and what config.py's own placeholder comments on
    REACT_RECURSION_LIMIT/TOKEN_CEILING_PER_REQUEST ask for ("check real trace depth...
    a p95/max, not just an average") once there's real traffic. Percentiles computed in
    Python over a bounded recent sample, not a DB-side aggregate - same demo-grade
    tradeoff as sum_recent_token_usage() above."""
    client = get_client()
    since = (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat()
    rows = (
        client.table("request_trace")
        .select("step_count, total_tokens, total_duration_ms, decline_reason")
        .gte("created_at", since)
        .order("created_at", desc=True)
        .limit(sample_limit)
        .execute()
        .data
    )

    def _percentiles(values: list[float]) -> dict:
        if not values:
            return {"p50": None, "p95": None, "max": None}
        values = sorted(values)
        quantiles = statistics.quantiles(values, n=100, method="inclusive") if len(values) > 1 else [values[0]] * 99
        return {"p50": quantiles[49], "p95": quantiles[94], "max": values[-1]}

    # Imported here, not at module level, to avoid db/ importing from agent/ as a
    # standing dependency direction - this is the one place that needs the exact
    # decline copy to detect which guardrail fired.
    from agent.chat.decline_messages import RECURSION_LIMIT_REACHED

    steps = [r["step_count"] for r in rows if r["step_count"] is not None]
    tokens = [r["total_tokens"] for r in rows if r["total_tokens"] is not None]
    durations = [r["total_duration_ms"] for r in rows if r["total_duration_ms"] is not None]
    recursion_hits = sum(1 for r in rows if r["decline_reason"] == RECURSION_LIMIT_REACHED)

    return {
        "window_hours": hours,
        "n": len(rows),
        "steps": _percentiles(steps),
        "tokens": _percentiles(tokens),
        "duration_ms": _percentiles(durations),
        "recursion_limit_hit_rate": round(recursion_hits / len(rows), 4) if rows else None,
    }


def sample_recent_request_traces(n: int, hours: int = 24) -> list[dict]:
    """Random sample of up to `n` completed conduct_analysis requests from the last
    `hours` - what eval/run_live_sample_eval.py judges for groundedness/relevance/
    answer-discovery against REAL traffic, not just eval/run_generation_eval.py's fixed
    fixture set. Random, not most-recent-N: most-recent would just re-judge whatever
    happened to come in right before the audit ran, biasing toward one time-of-day/one
    user's traffic pattern. Sampled in Python from a bounded pull, not a DB-side
    TABLESAMPLE/random() - same demo-grade tradeoff as get_efficiency_summary above."""
    import random

    client = get_client()
    rows = (
        client.table("request_trace")
        .select("id, question, answer, evidence")
        .eq("category", "conduct_analysis")
        .eq("status", "completed")
        .gte("created_at", (datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat())
        .limit(500)
        .execute()
        .data
    )
    return random.sample(rows, min(n, len(rows)))
