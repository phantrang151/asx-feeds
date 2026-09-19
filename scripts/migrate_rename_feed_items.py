"""
One-off migration: renames feed_items to custom_feed_items, so it reads symmetrically
with common_feed_items (schema.sql). Postgres carries the table's FK, indexes, RLS
policies, and the user_feed_items view's dependency across a RENAME automatically -
only the index name is renamed separately for consistency, since RENAME TABLE doesn't
touch index names on its own.

schema.sql's own `create table if not exists` won't retroactively rename an
already-created table, hence this separate migration. Safe to re-run.

Usage:
    python -m scripts.migrate_rename_feed_items
"""

import psycopg
from dotenv import load_dotenv

from config import SUPABASE_DB_URL

load_dotenv()

MIGRATION_SQL = """
alter table if exists feed_items rename to custom_feed_items;
alter index if exists feed_items_embedding_idx rename to custom_feed_items_embedding_idx;
"""


def migrate():
    with psycopg.connect(SUPABASE_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        conn.commit()
    print("feed_items renamed to custom_feed_items (table + index).")


if __name__ == "__main__":
    migrate()
