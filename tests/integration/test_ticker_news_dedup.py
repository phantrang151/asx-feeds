"""I3 (docs/test_case_catalog.md): proves ticker_news's unique(ticker, source_url)
constraint actually holds, so a re-fetch of the same article never duplicates it - the
protection classify_and_store's watermark gap (I1) doesn't have."""

from datetime import datetime, timezone

from db.queries import upsert_ticker_news


def _article(test_ticker, embedding):
    return {
        "ticker": test_ticker,
        "title": "Same article, fetched twice",
        "publisher": "Test Publisher",
        "source_url": f"https://example.com/{test_ticker}/only-article",
        "published_at": datetime.now(timezone.utc).isoformat(),
        "content_embedding": embedding,
    }


def test_reinserting_same_ticker_and_source_url_does_not_duplicate(client, test_ticker, embedding, cleanup_ticker):
    upsert_ticker_news([_article(test_ticker, embedding)])
    upsert_ticker_news([_article(test_ticker, embedding)])  # same (ticker, source_url) again

    rows = client.table("ticker_news").select("id").eq("ticker", test_ticker).execute().data
    assert len(rows) == 1
