"""Fixtures for integration tests - these hit a REAL Postgres+PostgREST instance via
db/queries.py (never mocked) and must NEVER run against a live/production Supabase
project, since they write and delete real rows.

Setup: `supabase start` (Supabase CLI - spins up a local Postgres+PostgREST+pgvector
stack via Docker), then apply schema.sql to it, then point SUPABASE_URL/SUPABASE_KEY at
the local instance before running pytest. See docs/test_case_catalog.md's "Remaining
tasks" for the full setup story. `_require_local_supabase` below refuses to run rather
than risk touching a real project if that isn't done.
"""

import uuid
import os

import pytest

from db.client import get_client

pytestmark = pytest.mark.integration


@pytest.fixture(scope="session", autouse=True)
def _require_local_supabase():
    url = os.environ.get("SUPABASE_URL", "")
    if "127.0.0.1" not in url and "localhost" not in url:
        pytest.skip(
            "Integration tests require SUPABASE_URL to point at the local Supabase CLI "
            "stack (`supabase start`) - skipping rather than risk touching a real project."
        )


@pytest.fixture
def test_ticker():
    """A unique, disposable ticker per test - never collides across tests or parallel runs."""
    return f"T{uuid.uuid4().hex[:6].upper()}.AX"


@pytest.fixture
def test_user_id():
    return str(uuid.uuid4())


@pytest.fixture
def embedding():
    """A fixed 384-dim vector. Integration tests check row counts/shape and
    match/no-match behavior at known similarity (identical vectors -> similarity 1.0),
    not real semantic quality - any valid vector works as long as it's reused
    consistently within one test to force a match."""
    return [0.01] * 384


@pytest.fixture
def other_embedding():
    """A second fixed vector, orthogonal enough to `embedding` that cosine similarity
    against it is low - used to prove a non-match/no-false-match case."""
    vec = [0.01] * 384
    vec[0] = -0.9
    return vec


@pytest.fixture
def client():
    return get_client()


@pytest.fixture
def cleanup_ticker(client, test_ticker):
    """Deletes every row this test may have created for test_ticker, across every table
    a test could touch - runs after the test regardless of pass/fail. Tests use a fresh
    random ticker each time so this never needs to worry about cross-test collisions,
    only about not leaking rows into local reruns of the suite."""
    yield
    client.table("ticker_news").delete().eq("ticker", test_ticker).execute()
    client.table("common_feed_items").delete().eq("ticker", test_ticker).execute()
    client.table("watchlist_stocks").delete().eq("ticker", test_ticker).execute()
    client.table("companies").delete().eq("ticker", test_ticker).execute()
