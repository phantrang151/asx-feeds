from functools import lru_cache

from psycopg_pool import ConnectionPool
from psycopg.rows import dict_row
from langgraph.store.postgres import PostgresStore
from langgraph.checkpoint.postgres import PostgresSaver

from config import SUPABASE_DB_URL
from tools.embeddings import embed_batch


@lru_cache(maxsize=1)
def _get_pool() -> ConnectionPool:
    if not SUPABASE_DB_URL:
        raise RuntimeError(
            "SUPABASE_DB_URL must be set in .env - the direct Postgres connection string "
            "(Supabase dashboard > Project Settings > Database > Connection string), not "
            "the SUPABASE_URL/SUPABASE_KEY the REST client in db/client.py uses."
        )
    # autocommit + prepare_threshold=0: Supabase's pooled connection runs pgbouncer in
    # transaction mode, which doesn't support server-side prepared statements - this avoids
    # psycopg trying to use them.
    return ConnectionPool(
        conninfo=SUPABASE_DB_URL,
        max_size=10,
        kwargs={"autocommit": True, "row_factory": dict_row, "prepare_threshold": 0},
    )


@lru_cache(maxsize=1)
def get_store() -> PostgresStore:
    """
    Long-term memory: procedural, episodic, and semantic memory all live here, backed by
    Supabase Postgres instead of InMemoryStore. This is what makes it actually "long-term" -
    it survives process restarts, so a fact stored last week or an episodic example from a
    previous session is still there the next time someone loads the demo.

    .setup() creates the store's own tables on first run (separate from feeds/feed_items/
    etc.) - safe to call every time the process starts, it's a no-op after the first run.
    """
    store = PostgresStore(_get_pool(), index={"dims": 384, "embed": embed_batch})
    store.setup()
    return store


@lru_cache(maxsize=1)
def get_checkpointer() -> PostgresSaver:
    """
    Long-term conversation checkpointing (thread/message history), also moved off
    MemorySaver for the same reason: a conversation thread should survive a restart,
    not just live for the duration of one process.
    """
    checkpointer = PostgresSaver(_get_pool())
    checkpointer.setup()
    return checkpointer
