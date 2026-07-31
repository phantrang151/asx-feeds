import os
from dotenv import load_dotenv

load_dotenv()

MODEL = "llama-3.3-70b-versatile"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384-dim, matches vector(384) columns in schema.sql

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
# NOTE: now that RLS is enabled (see schema.sql), this must be the service_role key, not
# the anon key - service_role bypasses RLS, which the pipeline scripts need since they
# write on behalf of a fixed test user rather than through a logged-in session. The
# frontend uses the anon key instead (see frontend/.env.local.example) precisely so RLS
# DOES apply there.
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
# Used by app/main.py to verify the Supabase-issued JWT the frontend sends on each
# request, so the API can trust which user_id it's acting on behalf of. Found in
# Supabase dashboard > Project Settings > API > JWT Secret.
SUPABASE_JWT_SECRET = os.getenv("SUPABASE_JWT_SECRET")
# Direct Postgres connection string (Supabase dashboard > Project Settings > Database >
# Connection string) - needed for PostgresStore/PostgresSaver, which manage their own
# tables via a raw psycopg connection. Different from SUPABASE_URL/SUPABASE_KEY above,
# which are for the REST client used in db/client.py.
SUPABASE_DB_URL = os.getenv("SUPABASE_DB_URL")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
# Comma-separated allowlist of emails permitted to hit /api/admin/* routes.
# See app/auth.py:require_admin for why this is demo-grade, not real RBAC.
ADMIN_EMAILS = os.getenv("ADMIN_EMAILS")

# Single-user testing mode: no auth yet, everything is scoped to this fixed id.
# Swap this out for the real authenticated user id once auth is wired up.
TEST_USER_ID = "00000000-0000-0000-0000-000000000001"

MATCH_THRESHOLD_DEFAULT = 0.35
