"""
One-off migration: extends the already-live ops_alerts table (see schema.sql) to
support 'structured_output_parse_failure' alerts raised by
agent/shared/structured_output.py - these come from the background ingestion
pipeline, not a chat request, so request_trace_id must become nullable, and they
carry context (ticker, schema name, raw args) that needs a new `details` column
rather than the numeric threshold/actual_value pair the original four alert types use.

schema.sql's own `create table if not exists` won't retroactively alter an
already-created table, hence this separate migration. Safe to re-run.

Usage:
    python -m scripts.migrate_ops_alerts_structured_output
"""

import psycopg
from dotenv import load_dotenv

from config import SUPABASE_DB_URL

load_dotenv()

MIGRATION_SQL = """
alter table ops_alerts alter column request_trace_id drop not null;

alter table ops_alerts drop constraint if exists ops_alerts_alert_type_check;
alter table ops_alerts add constraint ops_alerts_alert_type_check check (alert_type in (
    'cost_per_request', 'cost_per_user_per_day', 'latency', 'step_count',
    'structured_output_parse_failure'
));

alter table ops_alerts add column if not exists details jsonb not null default '{}'::jsonb;
"""


def migrate():
    with psycopg.connect(SUPABASE_DB_URL) as conn:
        with conn.cursor() as cur:
            cur.execute(MIGRATION_SQL)
        conn.commit()
    print("ops_alerts migrated: request_trace_id nullable, structured_output_parse_failure allowed, details column added.")


if __name__ == "__main__":
    migrate()
