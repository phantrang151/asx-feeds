import os
from dotenv import load_dotenv

load_dotenv()

# --- Model tiers (Claude) ---
# Three separate tiers, cheapest to strongest, so each task uses only as much model as
# it needs rather than one model doing everything:
#   - ROUTER_MODEL: the router's request-classification call (router_node) and other
#     short, generic per-item tasks (e.g. the one-sentence feed-relevance summary in
#     agent/pipelines/nodes.py) - high volume, low complexity.
#   - ANALYSIS_MODEL: the actual "daily production" reasoning work - conduct_analysis's
#     ReAct loop, cross-evidence synthesis (agent/shared/synthesize.py), and insight
#     planning (agent/pipelines/insight_nodes.py).
#   - JUDGE_MODEL: the advice-avoidance output guardrail (agent/guardrails/advice_check.py)
#     and the offline eval judges (eval/judge.py) - deliberately the strongest tier AND a
#     different model from ANALYSIS_MODEL, so it isn't grading its own homework; a judge
#     is only as trustworthy as its own reasoning, and grading subtle cases (does this
#     insight cross into advice? is every claim actually backed by the evidence?) needs at
#     least as much capability as generating the text being judged, arguably more.
ROUTER_MODEL = "claude-haiku-4-5"
ANALYSIS_MODEL = "claude-sonnet-5"
JUDGE_MODEL = "claude-opus-5"

EMBEDDING_MODEL = "all-MiniLM-L6-v2"  # 384-dim, matches vector(384) columns in schema.sql

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
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
TEST_USER_ID = "1df40f20-c5e1-4858-a7ad-0400f1afca63"

MATCH_THRESHOLD_DEFAULT = 0.35

# --- Guardrails / cost controls ---

# How many /api/ask calls one user can make in RATE_LIMIT_WINDOW_MINUTES before a 429.
# PLACEHOLDER - not derived from real usage data, retune once there's real traffic.
RATE_LIMIT_WINDOW_MINUTES = 60
RATE_LIMIT_MAX_REQUESTS = 20

# LangGraph recursion_limit for the conduct_analysis ReAct sub-agent - each tool call +
# its result is ~2 super-steps, so 15 allows roughly 6-7 tool calls before aborting.
# PLACEHOLDER - check real LangSmith trace depth (see /api/admin/langsmith/summary) once
# there's traffic, and size this comfortably above the observed p95.
REACT_RECURSION_LIMIT = 15

# Hard ceiling on total tokens (prompt+completion, summed across every Claude call in one
# conduct_analysis request) before the ReAct loop is aborted mid-run with a graceful
# decline and no partial answer. PLACEHOLDER - /api/admin/langsmith/summary currently
# only exposes an average, not a p95/max; size this from real traffic once available.
TOKEN_CEILING_PER_REQUEST = 20000

# Per-URL timeout and worker-pool size for the citation-reachability check that runs
# before references are shown as clickable links.
CITATION_CHECK_TIMEOUT_SECONDS = 3
CITATION_CHECK_MAX_WORKERS = 8

# Per-user ceiling on tokens summed across every Claude call one user's /api/ask requests
# make in a trailing TOKEN_CEILING_WINDOW_HOURS window (not calendar day) - router
# classification, conduct_analysis's ReAct loop + synthesis, AND the advice-avoidance
# judge call, unlike TOKEN_CEILING_PER_REQUEST above which only bounds one request's
# own ReAct loop + synthesis. PLACEHOLDER, carried over from the old Groq-based estimate
# (~$0.12-0.16/user/day at Groq's llama-3.3-70b-versatile pricing) - per-token cost is
# now much higher on Claude (see ROUTER_MODEL/ANALYSIS_MODEL/JUDGE_MODEL above), so this
# needs re-deriving from real traffic, not just re-pricing the same token count.
TOKEN_CEILING_PER_USER_PER_DAY = 200_000
TOKEN_CEILING_WINDOW_HOURS = 24

# --- Alerts (agent/guardrails/alerts.py) ---
# cost_per_request/cost_per_user_per_day/step_count alerts deliberately reuse the hard
# guardrail ceilings above (TOKEN_CEILING_PER_REQUEST, TOKEN_CEILING_PER_USER_PER_DAY,
# REACT_RECURSION_LIMIT) rather than a separate earlier-warning tier - they fire at the
# same moment the guardrail already aborts/blocks the request, turning what's today
# only an ephemeral logger.warning into a queryable, persisted ops_alerts row. Latency
# has no existing guardrail at all (nothing currently times a request end-to-end),
# hence the new constant here.
ALERT_LATENCY_MS = 30_000
