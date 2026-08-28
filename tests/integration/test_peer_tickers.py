"""I6 (docs/test_case_catalog.md): get_peer_tickers returns other ASX200-flagged
companies sharing the same industry, excluding the ticker itself, and never returns a
different-industry company."""

import uuid

from db.queries import upsert_companies, get_peer_tickers


def test_returns_same_industry_peers_and_excludes_self(client):
    industry = f"Test Industry {uuid.uuid4().hex[:6]}"  # unique per test run, avoids cross-run collisions
    ticker_a = f"T{uuid.uuid4().hex[:6].upper()}.AX"
    ticker_b = f"T{uuid.uuid4().hex[:6].upper()}.AX"
    ticker_other = f"T{uuid.uuid4().hex[:6].upper()}.AX"

    rows = [
        {"ticker": ticker_a, "company_name": "A", "is_asx200": True, "industry": industry},
        {"ticker": ticker_b, "company_name": "B", "is_asx200": True, "industry": industry},
        {"ticker": ticker_other, "company_name": "Other", "is_asx200": True, "industry": "A Different Industry"},
    ]
    try:
        upsert_companies(rows)

        peers = get_peer_tickers(industry, exclude_ticker=ticker_a)

        assert peers == [ticker_b]
    finally:
        for t in (ticker_a, ticker_b, ticker_other):
            client.table("companies").delete().eq("ticker", t).execute()


def test_excludes_non_asx200_companies(client):
    industry = f"Test Industry {uuid.uuid4().hex[:6]}"
    ticker_a = f"T{uuid.uuid4().hex[:6].upper()}.AX"
    ticker_not_asx200 = f"T{uuid.uuid4().hex[:6].upper()}.AX"

    rows = [
        {"ticker": ticker_a, "company_name": "A", "is_asx200": True, "industry": industry},
        {"ticker": ticker_not_asx200, "company_name": "Not ASX200", "is_asx200": False, "industry": industry},
    ]
    try:
        upsert_companies(rows)

        peers = get_peer_tickers(industry, exclude_ticker=ticker_a)

        assert peers == []
    finally:
        for t in (ticker_a, ticker_not_asx200):
            client.table("companies").delete().eq("ticker", t).execute()
