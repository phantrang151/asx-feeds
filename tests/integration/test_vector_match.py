"""I7 (docs/test_case_catalog.md, ticker_news half): match_ticker_news_for_embedding's
RPC round-trip - seeds two peer tickers' news with different embeddings and confirms the
closer match is ranked first, and articles outside `tickers` are never returned even if
they'd otherwise be the closest match.

The match_document_chunks_for_embedding half isn't covered here - `documents.uploaded_by`
has a foreign key to auth.users, which needs a seeded auth user first. Left as a
follow-up (see docs/test_case_catalog.md)."""

from datetime import datetime, timezone

from db.queries import upsert_ticker_news, match_ticker_news_for_embedding


def _near(embedding, nudge=0.0001):
    return [v + nudge for v in embedding]


def test_closer_embedding_ranks_first_and_excluded_tickers_never_appear(
    client, test_ticker, embedding, other_embedding, cleanup_ticker
):
    peer_ticker = f"T{test_ticker[1:-3]}P.AX"  # deterministic sibling of test_ticker, cleaned up alongside it
    outside_ticker = f"T{test_ticker[1:-3]}O.AX"

    try:
        upsert_ticker_news([
            {
                "ticker": test_ticker,
                "title": "Close match",
                "publisher": "Test Publisher",
                "source_url": f"https://example.com/{test_ticker}/close",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "content_embedding": _near(embedding),
            },
            {
                "ticker": peer_ticker,
                "title": "Far match",
                "publisher": "Test Publisher",
                "source_url": f"https://example.com/{peer_ticker}/far",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "content_embedding": other_embedding,
            },
            {
                "ticker": outside_ticker,
                "title": "Should never be returned",
                "publisher": "Test Publisher",
                "source_url": f"https://example.com/{outside_ticker}/excluded",
                "published_at": datetime.now(timezone.utc).isoformat(),
                "content_embedding": embedding,  # would rank first if it weren't excluded by `tickers`
            },
        ])

        matches = match_ticker_news_for_embedding([test_ticker, peer_ticker], embedding, match_count=10)

        assert [m["ticker"] for m in matches] == [test_ticker, peer_ticker]
        assert matches[0]["similarity"] > matches[1]["similarity"]
    finally:
        client.table("ticker_news").delete().eq("ticker", peer_ticker).execute()
        client.table("ticker_news").delete().eq("ticker", outside_ticker).execute()


def test_empty_ticker_list_returns_empty_without_a_query(test_ticker, embedding):
    assert match_ticker_news_for_embedding([], embedding) == []
