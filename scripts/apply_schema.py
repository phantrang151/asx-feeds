"""One-off: applies schema.sql to the database at SUPABASE_DB_URL. Used to set up a
fresh local Supabase CLI stack for integration tests (`supabase start`, then this
script) - also how the CI integration-test job initializes its ephemeral instance.

Safe to run once against a fresh instance. NOT safe to re-run against an
already-initialized one without resetting first (`supabase db reset`) - schema.sql's
`create table`/`alter table` statements are all idempotent, but its `create policy`
statements are not (Postgres has no `create policy if not exists`), so a second run
against the same instance will fail on duplicate policy names.

Usage:
    python -m scripts.apply_schema
"""

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()


def apply_schema():
    db_url = os.environ["SUPABASE_DB_URL"]
    with open("schema.sql", encoding="utf-8") as f:
        sql = f.read()
    with psycopg.connect(db_url) as conn:
        with conn.cursor() as cur:
            cur.execute(sql)
        conn.commit()
    print("schema.sql applied.")


if __name__ == "__main__":
    apply_schema()
