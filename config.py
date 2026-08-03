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

# --- Guardrails / cost controls ---

# Second, distinct Groq model used ONLY as an LLM judge (advice-avoidance check, eval
# groundedness/relevance scoring) - kept separate from MODEL so results aren't "the same
# model grading its own homework". A different model family/size than MODEL, not just a
# different temperature of the same one.
JUDGE_MODEL = "llama-3.1-8b-instant"

# How many /api/ask calls one user can make in RATE_LIMIT_WINDOW_MINUTES before a 429.
# PLACEHOLDER - not derived from real usage data, retune once there's real traffic.
RATE_LIMIT_WINDOW_MINUTES = 60
RATE_LIMIT_MAX_REQUESTS = 20

# LangGraph recursion_limit for the conduct_analysis ReAct sub-agent - each tool call +
# its result is ~2 super-steps, so 15 allows roughly 6-7 tool calls before aborting.
# PLACEHOLDER - check real LangSmith trace depth (see /api/admin/langsmith/summary) once
# there's traffic, and size this comfortably above the observed p95.
REACT_RECURSION_LIMIT = 15

# Hard ceiling on total tokens (prompt+completion, summed across every Groq call in one
# conduct_analysis request) before the ReAct loop is aborted mid-run with a graceful
# decline and no partial answer. PLACEHOLDER - /api/admin/langsmith/summary currently
# only exposes an average, not a p95/max; size this from real traffic once available.
TOKEN_CEILING_PER_REQUEST = 20000

# Per-URL timeout and worker-pool size for the citation-reachability check that runs
# before references are shown as clickable links.
CITATION_CHECK_TIMEOUT_SECONDS = 3
CITATION_CHECK_MAX_WORKERS = 8
