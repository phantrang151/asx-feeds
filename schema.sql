-- Run this in the Supabase SQL editor before running scripts/seed_single_user.py.
-- Covers only what's needed for the single-user news pipeline test.
-- The fuller schema (profiles, feed_templates) can be layered on once auth is added.

create extension if not exists vector;
create extension if not exists pgcrypto; -- for gen_random_uuid()

-- Global, ticker-agnostic feed topics (e.g. "Revenue Trend") that every user can opt a
-- feed into instead of writing their own description. Classified once per ticker (see
-- common_feed_items below) instead of once per user, which is the whole point of them.
create table if not exists common_feed_templates (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  description text not null,
  description_embedding vector(384) not null,
  -- Lower than a custom feed's threshold: matching a one-line news headline against a
  -- short topic blurb ("Controversies, scandals, outages...") caps out around 0.25-0.28
  -- cosine similarity even for an obviously on-topic article, since the two texts are
  -- different styles rather than paraphrases of each other. 0.35 here made every common
  -- feed template permanently unmatchable (see common_items_classified in pipeline_runs).
  match_threshold float not null default 0.22,
  created_at timestamptz not null default now()
);

create table if not exists feeds (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  feed_name text not null,
  feed_description text not null,
  description_embedding vector(384) not null,
  -- Custom feed descriptions match against news headlines in the 0.40-0.50 similarity
  -- range whether or not the article is genuinely on-topic (unlike common feed templates,
  -- see above) - 0.4 trims off the weakest, most generic matches without being
  -- unreachable the way the common-feed threshold at this level would be. Lands on a
  -- 10%-step boundary since users can only set this in 10% increments (see the API).
  match_threshold float not null default 0.4,
  digest_enabled boolean not null default true,
  -- null means "never classified" - a fresh feed (new or just re-added) gets a
  -- full-history pass against ticker_news instead of an incremental one.
  last_classified_at timestamptz,
  -- Set by the user's "Refresh" action after editing a custom feed's description or
  -- threshold: the next pipeline run wipes this feed's feed_items and re-matches its
  -- entire ticker_news history under the feed's current settings, then clears this flag.
  needs_rematch boolean not null default false,
  -- 'common' feeds link to a shared common_feed_templates row and are classified once
  -- per ticker (see common_feed_items), not once per user.
  feed_type text not null default 'custom' check (feed_type in ('common', 'custom')),
  common_feed_template_id uuid references common_feed_templates(id),
  created_at timestamptz not null default now()
);

create table if not exists watchlist_stocks (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  company_name text,
  created_at timestamptz not null default now(),
  unique (user_id, ticker)
);

create table if not exists feed_items (
  id uuid primary key default gen_random_uuid(),
  feed_id uuid not null references feeds(id) on delete cascade,
  source_type text not null,       -- 'news' | 'financial'
  content_summary text not null,
  source_url text,
  content_embedding vector(384),
  created_at timestamptz not null default now()
);

-- Shared per-ticker news cache. Populated once per ticker per pipeline run (not once
-- per user watching that ticker) - this is what stops N users on the same ticker from
-- each triggering their own yfinance call for the same headlines.
create table if not exists ticker_news (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  title text not null,
  publisher text,
  source_url text,
  published_at timestamptz,
  content_embedding vector(384) not null,
  -- Set once this row has been evaluated against common_feed_templates, whether or not
  -- it matched - so a below-threshold article isn't re-evaluated on every run.
  common_classified_at timestamptz,
  created_at timestamptz not null default now(),
  unique (ticker, source_url)
);

-- Classification results for common_feed_templates, computed once per (ticker, article,
-- template) and shared by every user whose feed for that ticker is 'common' - instead of
-- once per user's feed the way feed_items works for 'custom' feeds.
create table if not exists common_feed_items (
  id uuid primary key default gen_random_uuid(),
  common_feed_template_id uuid not null references common_feed_templates(id) on delete cascade,
  ticker text not null,
  source_type text not null default 'news',
  content_summary text not null,
  source_url text,
  content_embedding vector(384),
  created_at timestamptz not null default now(),
  unique (common_feed_template_id, ticker, source_url)
);

create index if not exists feeds_embedding_idx
  on feeds using ivfflat (description_embedding vector_cosine_ops);

create index if not exists feed_items_embedding_idx
  on feed_items using ivfflat (content_embedding vector_cosine_ops);

create index if not exists ticker_news_embedding_idx
  on ticker_news using ivfflat (content_embedding vector_cosine_ops);

create index if not exists ticker_news_ticker_idx
  on ticker_news (ticker, created_at);

create index if not exists common_feed_items_embedding_idx
  on common_feed_items using ivfflat (content_embedding vector_cosine_ops);

create table if not exists financial_records (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  period text not null,
  revenue numeric,
  profit numeric,
  headcount int,
  notes text,
  created_at timestamptz not null default now()
);

-- Real ASX-listed companies, seeded from Wikipedia's S&P/ASX 200 table (see
-- scripts/seed_companies.py) - used by the chat agent's ticker-validation guardrail to
-- reject/clarify a hallucinated ticker before it reaches any live tool call. Only covers
-- the ~200 largest listed companies (the official ASX CSV is blocked by a WAF from a
-- server environment) - a ticker NOT in this table isn't necessarily fake, see
-- agent/guardrails/tickers.py's live-yfinance fallback for anything outside the seed.
create table if not exists companies (
  ticker text primary key,          -- Yahoo Finance ASX format, e.g. 'TLS.AX'
  company_name text not null,
  is_asx200 boolean not null default false,
  created_at timestamptz not null default now()
);

-- Sector/industry cache, lazily populated for EVERY watchlisted ticker (not just the
-- top-200 seed above) by ingestion_steps.py's ensure_company_sector_cached during phase
-- 1 of the pipeline - so insight_nodes.py's peer-ticker lookup at synthesis time is
-- DB-only, never a live yfinance call mid-graph-run. sector_fetched_at is stamped even
-- when the fetch found no sector (both left null) - a ticker yfinance genuinely has no
-- classification for shouldn't cost a live API call on every single pipeline run.
alter table companies add column if not exists sector text;
alter table companies add column if not exists industry text;
alter table companies add column if not exists sector_fetched_at timestamptz;
alter table companies add column if not exists is_asx200 boolean not null default false;

-- Admin-uploaded source material (files or pasted links) for a ticker, run through
-- extraction -> chunking -> embedding so a future analysis tool can retrieve report
-- content instead of only the single-row financial_records summary.
create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  title text not null,                 -- original filename, or the pasted URL for links
  source_type text not null check (source_type in ('file', 'link')),
  source_url text,                     -- original pasted link when source_type = 'link'
  storage_path text,                   -- Supabase Storage object path (raw bytes, both types)
  status text not null default 'processing' check (status in ('processing', 'ready', 'failed')),
  error text,
  uploaded_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table if not exists document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  ticker text not null,                -- denormalized for direct filtering, same as feed_items
  chunk_index int not null,
  content text not null,
  content_embedding vector(384) not null,
  created_at timestamptz not null default now()
);

create index if not exists document_chunks_embedding_idx
  on document_chunks using ivfflat (content_embedding vector_cosine_ops);
create index if not exists document_chunks_ticker_idx on document_chunks (ticker);
create index if not exists documents_ticker_idx on documents (ticker, created_at);

-- Per-document chunk counts for the admin document list, same style as match_feeds().
create or replace function get_document_chunk_counts(doc_ticker text)
returns table (document_id uuid, chunk_count bigint)
language sql stable
as $$
  select document_chunks.document_id, count(*) as chunk_count
  from document_chunks
  where document_chunks.ticker = doc_ticker
  group by document_chunks.document_id;
$$;

-- Returns the closest-matching chunks from admin-uploaded reports for a given ticker +
-- query embedding - what the chat agent's search_financial_reports_tool calls, so it can
-- ground answers in actually-uploaded report content instead of only general knowledge.
create or replace function match_document_chunks(
  query_embedding vector(384),
  match_ticker text,
  match_count int default 5
)
returns table (
  id uuid,
  document_id uuid,
  document_title text,
  content text,
  similarity float,
  source_type text,
  source_url text,
  storage_path text
)
language sql stable
as $$
  -- "materialized" forces this ticker filter to run BEFORE the vector ordering below.
  -- Without it, Postgres orders by content_embedding first using the ivfflat index -
  -- an approximate search over the WHOLE table's index lists (default probes=1) - then
  -- filters by ticker, so a ticker's chunks that aren't well-represented in the one
  -- probed list can be almost entirely invisible even with hundreds of rows in the
  -- table. Materializing first limits the ordering step to just this ticker's chunks
  -- (a few hundred to a few thousand rows), which is small enough for an exact sort -
  -- no ANN index involved, no missed matches.
  with ticker_chunks as materialized (
    select id, document_id, content, content_embedding
    from document_chunks
    where ticker = match_ticker
  )
  select
    ticker_chunks.id,
    ticker_chunks.document_id,
    documents.title as document_title,
    ticker_chunks.content,
    1 - (ticker_chunks.content_embedding <=> query_embedding) as similarity,
    documents.source_type,
    documents.source_url,
    documents.storage_path
  from ticker_chunks
  join documents on documents.id = ticker_chunks.document_id
  order by ticker_chunks.content_embedding <=> query_embedding
  limit match_count;
$$;

-- Multi-ticker sibling of match_document_chunks() above: closest-matching ticker_news
-- rows across a SET of tickers (peer tickers in the same sector) for a query embedding.
-- Used by insight_nodes.py's execute_step_node for feeds the LLM decided need
-- peer-ticker news - the feed's own ticker is never included in match_tickers, since
-- that's already covered by items_by_feed. Same materialized-CTE-first shape as
-- match_document_chunks, for the same reason (see its comment above).
create or replace function match_ticker_news(
  query_embedding vector(384),
  match_tickers text[],
  match_count int default 10,
  similarity_threshold float default 0.6,
  news_since timestamptz default now() - interval '6 months'
)
returns table (
  id uuid,
  ticker text,
  title text,
  publisher text,
  source_url text,
  published_at timestamptz,
  similarity float
)
language sql stable
as $$
  with peer_news as materialized (
    select id, ticker, title, publisher, source_url, published_at, content_embedding
    from ticker_news
    where ticker = any(match_tickers)
      and published_at >= news_since
  )
  select
    peer_news.id,
    peer_news.ticker,
    peer_news.title,
    peer_news.publisher,
    peer_news.source_url,
    peer_news.published_at,
    1 - (peer_news.content_embedding <=> query_embedding) as similarity
  from peer_news
  where 1 - (peer_news.content_embedding <=> query_embedding) >= similarity_threshold
  order by peer_news.content_embedding <=> query_embedding
  limit match_count;
$$;

create table if not exists ticker_insights (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  insight_text text not null,
  based_on_feed_item_ids uuid[] not null default '{}',
  -- Per-feed breakdown backing insight_text: [{feed_name, status: "sufficient" |
  -- "insufficient", summary, item_count, item_ids}, ...] - see synthesize_node in
  -- agent/pipelines/insight_nodes.py. '[]' on rows written before this column existed.
  feed_summaries jsonb not null default '[]',
  created_at timestamptz not null default now()
);
-- Safe to re-run against a database created before per-feed sufficiency gating - see the
-- insights_generated migration above for the same pattern.
alter table ticker_insights add column if not exists feed_summaries jsonb not null default '[]';

-- One row per eval run (see eval/score_classification.py, eval/run_generation_eval.py,
-- eval/score_guardrails.py, eval/run_live_sample_eval.py) - what the admin page's
-- Evaluation section reads to show quality metrics over time, same "one row per run"
-- shape as pipeline_runs below. `summary` holds whatever each eval type's own
-- summarize()/score() output looks like (see each script) rather than a fixed schema,
-- since each eval type measures something fundamentally different. 'guardrails' =
-- per-layer TP/FP against a labeled adversarial+quality set (eval/score_guardrails.py).
-- 'live_sample' = the daily N-sample judge audit against real recent traffic
-- (eval/run_live_sample_eval.py), as opposed to 'generation''s fixed fixture set.
-- 'insight_quality' = groundedness/relevance/completeness over a fixed set of
-- (ticker, evidence) pairs, synthesized fresh each run (eval/run_insight_eval.py), the
-- pipeline-side counterpart to 'generation'. 'feed_summary' = groundedness/completeness
-- over a fixed set of (article, feed) pairs, summarized fresh each run
-- (eval/run_feed_summary_eval.py) - the regression-test counterpart to
-- monitoring/quality_sampling.py's continuous custom_feed/common_feed sampling.
-- 'research_order' = the deterministic ordering guard's labeled call-sequence
-- regression check (eval/score_research_order.py) - no LLM calls, unlike 'guardrails'.
create table if not exists eval_runs (
  id uuid primary key default gen_random_uuid(),
  eval_type text not null check (
    eval_type in (
      'classification', 'generation', 'insight_quality', 'feed_summary', 'guardrails',
      'research_order', 'live_sample'
    )
  ),
  summary jsonb not null,
  created_at timestamptz not null default now()
);

-- Safe to re-run against a database created before insight_quality/research_order/
-- feed_summary existed as eval types - drops and recreates the check constraint with
-- the wider set, same pattern as the other "safe to re-run" migrations in this file.
alter table eval_runs drop constraint if exists eval_runs_eval_type_check;
alter table eval_runs add constraint eval_runs_eval_type_check check (
  eval_type in (
    'classification', 'generation', 'insight_quality', 'feed_summary', 'guardrails',
    'research_order', 'live_sample'
  )
);

-- Continuous production quality monitoring - one row per LLM-generated text item
-- sampled and judged, across all four surfaces that write LLM text: custom feed item
-- summaries, common feed item summaries, pipeline insight summaries, and chat answers
-- (see monitoring/quality_sampling.py). Complements eval_runs (fixed test cases /
-- aggregate-only, re-run on prompt change) with per-item, continuously-sampled
-- production output - the admin page's Monitoring section reads this to surface
-- specific bad examples for prompt iteration, not just an aggregate score. Same "one
-- type column + jsonb payload" shape as eval_runs rather than four separate tables per
-- surface, so the admin panel queries one table instead of a UNION of four.
create table if not exists quality_samples (
  id uuid primary key default gen_random_uuid(),
  surface_type text not null check (surface_type in ('custom_feed', 'common_feed', 'insight', 'chat_answer')),
  source_id uuid not null,      -- feed_items.id / common_feed_items.id / ticker_insights.id / request_trace.id
  ticker text,
  question text,                -- real question (chat) or a synthetic framing (feed/insight), fed to judge_completeness
  -- Display-only context for the admin panel's first column - the feed's own
  -- description for custom_feed/common_feed rows (feeds.feed_description /
  -- common_feed_templates.description), null for insight/chat_answer (which show
  -- `question`/reconstructed feed summaries there instead - see
  -- monitoring/quality_sampling.py). Distinct from `question` because `question` is fed
  -- to judge_completeness and changing its wording would change what's being judged.
  context text,
  text text not null,           -- the summary/answer being judged
  evidence jsonb not null default '[]',
  groundedness_pct int,          -- 0-100, mirrors completeness_pct - see judge.py::GroundednessJudgment
  grounded boolean not null,
  unsupported_claims jsonb not null default '[]',
  completeness_pct int,
  omitted_points jsonb not null default '[]',
  -- Flagged whenever grounded is false (zero tolerance on unsupported claims - a
  -- financial-context hallucination can bias a user's decision) OR completeness_pct is
  -- below QUALITY_COMPLETENESS_THRESHOLD_PCT (config.py) - computed once at insert time
  -- so every reader (admin panel, future alerting) applies the same bar.
  flagged boolean not null,
  reviewed_at timestamptz,
  reviewed_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  -- Re-triggering sampling must not re-judge (and re-spend LLM calls on) an item
  -- already sampled - see monitoring/quality_sampling.py's pre-judge exclusion too.
  unique (surface_type, source_id)
);
-- Safe to re-run against a database created before `context`/`groundedness_pct`
-- existed - same pattern as the other "safe to re-run" migrations in this file.
alter table quality_samples add column if not exists context text;
alter table quality_samples add column if not exists groundedness_pct int;
create index if not exists quality_samples_flagged_idx on quality_samples (flagged, created_at);
create index if not exists quality_samples_surface_idx on quality_samples (surface_type, created_at);

-- Continuous production monitoring for the two advice-avoidance guardrails (input:
-- agent/guardrails/advice_check.py::keyword_scan_advice_seeking + agent/chat/nodes.py::
-- classify_request; output: keyword_scan + llm_judge_advice_check) - see
-- monitoring/guardrail_sampling.py. Same "one row per judged item" shape as
-- quality_samples, but a separate table since the judgment shape is genuinely
-- different (a flag + one-sentence reasoning, not groundedness/completeness against
-- evidence).
--
-- Samples recent request_trace rows and re-checks each with BOTH the live production
-- regex layer (re-run fresh, not read from the historical row, so a regex pattern
-- added after the fact still gets credit for catching old text) and an independent
-- evaluation-tier judge (judge_advice_seeking for input - the live input gate's LLM
-- layer only runs the cheap ROUTER_MODEL, so this is the first JUDGE_MODEL-tier check
-- for that side; llm_judge_advice_check re-run fresh for output, which already IS
-- JUDGE_MODEL-tier live). `llm_flagged` is what the live gate's LLM layer actually
-- decided for THIS historical request (null if that layer was never reached, e.g. the
-- regex layer already fail-fast declined it).
--
-- Output-guardrail sampling can only audit PASSED requests - a blocked response's text
-- is never persisted to request_trace.answer by design (status only reaches
-- 'completed', which is what populates answer, when nothing was blocked), so this
-- necessarily catches false negatives (missed violations), not false positives.
create table if not exists guardrail_samples (
  id uuid primary key default gen_random_uuid(),
  guardrail_type text not null check (guardrail_type in ('input', 'output')),
  source_id uuid not null,      -- request_trace.id
  ticker text,
  text text not null,           -- the question (input) or answer (output) being audited
  regex_flagged boolean not null,
  llm_flagged boolean,          -- the live gate's own verdict on this historical request; null if never reached
  eval_flagged boolean not null,
  eval_reasoning text not null,
  -- True when eval_flagged disagrees with what the live gate actually decided
  -- (llm_flagged if that layer ran, else regex_flagged) - the "needs review" signal.
  flagged boolean not null,
  reviewed_at timestamptz,
  reviewed_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  unique (guardrail_type, source_id)
);
create index if not exists guardrail_samples_flagged_idx on guardrail_samples (flagged, created_at);
create index if not exists guardrail_samples_type_idx on guardrail_samples (guardrail_type, created_at);

-- Continuous production monitoring for feed classification correctness (custom feed_items
-- and common_feed_items) - see monitoring/classification_sampling.py. The live classifier
-- (db/queries.py::match_feed_for_embedding / match_common_feed_template_for_embedding)
-- only checks embedding similarity against a threshold, with no semantic verification -
-- this samples real recent classifications and independently judges (judge_feed_classification,
-- JUDGE_MODEL) whether the match is actually genuine, catching false positives the
-- similarity threshold let through. Complements score_classification.py's Evaluation
-- panel (same live classifier, scored against a hand-labeled CSV) rather than
-- replacing it - that's still the source of truth for precision/recall/ROC-AUC; this is
-- the continuous, no-labeling-required companion for real traffic.
create table if not exists classification_samples (
  id uuid primary key default gen_random_uuid(),
  classification_type text not null check (classification_type in ('custom_feed', 'common_feed')),
  source_id uuid not null,      -- feed_items.id / common_feed_items.id
  ticker text,
  article_title text not null,
  feed_name text not null,
  feed_description text not null,
  eval_correct boolean not null,
  eval_reasoning text not null,
  -- = not eval_correct - the "likely misclassification, needs review" signal.
  flagged boolean not null,
  reviewed_at timestamptz,
  reviewed_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  unique (classification_type, source_id)
);
create index if not exists classification_samples_flagged_idx on classification_samples (flagged, created_at);
create index if not exists classification_samples_type_idx on classification_samples (classification_type, created_at);

create table if not exists pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running', -- running | success | partial_failure | failed
  tickers_processed int not null default 0,
  feeds_classified int not null default 0,
  common_items_classified int not null default 0,
  items_skipped int not null default 0,
  insights_generated int not null default 0,
  errors jsonb not null default '[]'::jsonb
);
-- Safe to re-run against a database created before insight_graph was wired into the
-- orchestrator - `create table if not exists` above is a no-op there, so the column
-- needs adding separately.
alter table pipeline_runs add column if not exists insights_generated int not null default 0;

-- One row per accepted /api/ask call, per user - what the rate-limit guardrail
-- (agent/guardrails/rate_limit.py::enforce_rate_limit) counts over a trailing window
-- (config.RATE_LIMIT_WINDOW_MINUTES/MAX_REQUESTS). A log, not a running counter, so the
-- window size can change later without a migration.
create table if not exists api_request_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  created_at timestamptz not null default now()
);
create index if not exists api_request_log_user_time_idx on api_request_log (user_id, created_at);

-- One row per /api/ask request, per user - total tokens that request spent across
-- every Groq call it made (router classification, conduct_analysis's ReAct loop +
-- synthesis, advice-avoidance judge). What the daily token-budget guardrail
-- (agent/guardrails/daily_token_budget.py::enforce_daily_token_budget) sums over a
-- trailing window (config.TOKEN_CEILING_PER_USER_PER_DAY/TOKEN_CEILING_WINDOW_HOURS).
-- A log, not a running counter, same reasoning as api_request_log above - the window
-- size can change later without a migration. Requests that never call an LLM (e.g.
-- declined by a pre-LLM guardrail) aren't logged - zero tokens spent, nothing to add.
create table if not exists llm_token_usage_log (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  tokens int not null,
  created_at timestamptz not null default now()
);
create index if not exists llm_token_usage_log_user_time_idx on llm_token_usage_log (user_id, created_at);

-- One row per /api/ask request - the full observability trace: router decision, both
-- guardrail layers' verdicts, and aggregate timing/token/step counts. Complements
-- llm_token_usage_log above (which stays as-is - the daily-budget guardrail's own
-- lightweight bookkeeping table, summed on the hot path of every request, and
-- shouldn't get slower as this fuller trace grows) and eval_runs (offline judge scores
-- against a fixture set or labeled worksheet, not live traffic). What the admin page's
-- Evaluation section's efficiency/guardrail-trip metrics query against (see
-- agent/guardrails/tracer.py::RequestTracer, which builds one of these per request).
create table if not exists request_trace (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  thread_id text not null,
  question text not null,
  -- Final answer text + the evidence it was synthesized from - stored so
  -- eval/run_live_sample_eval.py can re-judge groundedness/relevance/answer-discovery
  -- against REAL past requests after the fact, not just eval/run_generation_eval.py's
  -- fixed fixture set. Same "already storing user content for debugging" posture as
  -- `question` above - deliberately NOT duplicated onto ops_alerts, which stays
  -- content-free (see that table's own comment).
  answer text,
  evidence jsonb,
  ticker text,
  category text,           -- router's chosen category: search_news | conduct_analysis | declined
  status text not null,    -- completed | declined | error
  decline_reason text,     -- set when status = 'declined'/'error' - which guardrail/limit tripped

  input_guardrail_regex_matched boolean,    -- keyword_scan_advice_seeking hit, pre-router
  input_guardrail_llm_is_advice boolean,    -- router's own is_advice_seeking judgment
  output_guardrail_regex_matched boolean,   -- keyword_scan hit on the final insight
  output_guardrail_llm_is_advice boolean,   -- llm_judge_advice_check verdict (only reached if regex above was clean)

  evidence_count int,       -- len(evidence) conduct_analysis_node gathered - free structural
                             -- proxy for "did the system find anything" (see judge_answer_found
                             -- in eval/judge.py for the fuller offline/sampled version of this)
  step_count int not null default 0,        -- tool calls made in the ReAct loop - what the cost
                             -- guardrail (REACT_RECURSION_LIMIT) bounds; each tool call is ~2 of
                             -- that limit's LangGraph super-steps, so this isn't the same unit as
                             -- REACT_RECURSION_LIMIT itself, just proportional to it
  total_tokens int,                         -- denormalized copy of the sum already tracked in llm_token_usage_log
  total_duration_ms int not null,

  created_at timestamptz not null default now()
);
create index if not exists request_trace_user_time_idx on request_trace (user_id, created_at);
create index if not exists request_trace_category_idx on request_trace (category, created_at);

-- One row per step inside a request_trace - the router call, each individual ReAct
-- tool call, each guardrail check, synthesis. Child table (not a jsonb array on
-- request_trace) because "avg duration per step type" / "which step is slowest" are
-- aggregate, GROUP-BY queries you want indexed, not values pulled out of jsonb every
-- time. Populated in one bulk insert per request from RequestTracer.steps.
create table if not exists request_trace_steps (
  id uuid primary key default gen_random_uuid(),
  request_trace_id uuid not null references request_trace(id) on delete cascade,
  step_index int not null,     -- order within the request
  step_name text not null,     -- 'router' | 'input_guardrail_regex' | 'tool:search_news_tool' | 'output_guardrail_regex' | 'output_guardrail_llm' | 'synthesis' | ...
  step_type text not null,     -- 'guardrail' | 'llm' | 'tool'
  duration_ms int not null,
  tokens int,                  -- null for non-LLM steps (guardrail regex, tool calls)
  result jsonb,                -- flexible per step_type: matched keywords, judge reasoning, error detail
  created_at timestamptz not null default now()
);
create index if not exists request_trace_steps_trace_idx on request_trace_steps (request_trace_id, step_index);

-- Fires when a single request or a user's trailing-day usage crosses an ALERT
-- threshold - reuses the existing hard guardrail ceilings (TOKEN_CEILING_PER_REQUEST,
-- TOKEN_CEILING_PER_USER_PER_DAY, REACT_RECURSION_LIMIT) plus the new
-- ALERT_LATENCY_MS, all in config.py. These fire at the SAME value their matching
-- guardrail trips at (a deliberate choice - see agent/guardrails/alerts.py), turning
-- what was only ever an ephemeral logger.warning into a queryable, persisted row.
-- Carries no question/answer content, only ids and numbers - keeps this within the
-- admin's existing operational-visibility scope (see project_admin_privacy_scope
-- memory) even though request_trace itself stores the question text for debugging.
create table if not exists ops_alerts (
  id uuid primary key default gen_random_uuid(),
  request_trace_id uuid not null references request_trace(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  alert_type text not null check (alert_type in (
    'cost_per_request', 'cost_per_user_per_day', 'latency', 'step_count'
  )),
  threshold numeric not null,     -- the configured limit at the time this fired
  actual_value numeric not null,  -- tokens, milliseconds, or step count - whichever crossed it
  created_at timestamptz not null default now()
);
create index if not exists ops_alerts_type_time_idx on ops_alerts (alert_type, created_at);
create index if not exists ops_alerts_user_time_idx on ops_alerts (user_id, created_at);

-- Admin-only data, never queried directly from the frontend (only via the /api/admin
-- routes, which use the service_role key). RLS is enabled with no policies, so anon and
-- authenticated clients get nothing at all - defense in depth even though the frontend
-- was never going to query this table directly.
alter table pipeline_runs enable row level security;

-- Same posture as pipeline_runs above.
alter table eval_runs enable row level security;

-- Same posture again: admin-only, backend service_role key only.
alter table quality_samples enable row level security;
alter table guardrail_samples enable row level security;
alter table classification_samples enable row level security;

-- Same posture again: only ever written/read by the backend's daily token-budget
-- guardrail via the service_role key, never by the frontend directly.
alter table llm_token_usage_log enable row level security;

-- Same admin-only posture as pipeline_runs above: reachable only through the backend's
-- service_role key (the admin upload endpoints today, and potentially a future
-- analysis-tool query, which would also run backend-side with service_role).
alter table documents enable row level security;
alter table document_chunks enable row level security;

-- Same posture as pipeline_runs/eval_runs above - admin-only, backend service_role key only.
alter table request_trace enable row level security;
alter table request_trace_steps enable row level security;
alter table ops_alerts enable row level security;

-- Same posture again: only ever written/read by the backend's rate-limit guardrail via
-- the service_role key, never by the frontend directly.
alter table api_request_log enable row level security;

-- Row Level Security: the frontend talks to Supabase directly using each user's own
-- session (anon key + their JWT), so RLS is what actually stops user A from seeing or
-- writing user B's data - the Python backend, by contrast, uses the service_role key
-- (see SUPABASE_KEY in .env), which bypasses RLS entirely. Keep that key out of any
-- frontend code.

alter table feeds enable row level security;
create policy "select own feeds" on feeds for select using (auth.uid() = user_id);
create policy "insert own feeds" on feeds for insert with check (auth.uid() = user_id);
create policy "update own feeds" on feeds for update using (auth.uid() = user_id);
create policy "delete own feeds" on feeds for delete using (auth.uid() = user_id);

alter table watchlist_stocks enable row level security;
create policy "select own watchlist" on watchlist_stocks for select using (auth.uid() = user_id);
create policy "insert own watchlist" on watchlist_stocks for insert with check (auth.uid() = user_id);
create policy "delete own watchlist" on watchlist_stocks for delete using (auth.uid() = user_id);

alter table feed_items enable row level security;
-- feed_items has no user_id column of its own - ownership is via its parent feed,
-- so the policy checks that the parent feed belongs to the requesting user.
create policy "select own feed items" on feed_items for select using (
  exists (
    select 1 from feeds
    where feeds.id = feed_items.feed_id
      and feeds.user_id = auth.uid()
  )
);

alter table ticker_insights enable row level security;
create policy "select own insights" on ticker_insights for select using (auth.uid() = user_id);

-- financial_records is intentionally NOT row-level-secured: it holds shared, public
-- company data (see the earlier design discussion), not per-user data.

-- companies is the same posture as financial_records above - shared, public reference
-- data (real ASX ticker/name pairs), not per-user data.

-- ticker_news and common_feed_items are also shared, not user-owned data - unlike
-- financial_records, though, they ARE reachable directly by the frontend (via the
-- user_feed_items view below), so unlike financial_records they get RLS enabled with an
-- explicit read-only "any authenticated user" policy rather than being left wide open.
alter table ticker_news enable row level security;
create policy "select ticker news" on ticker_news for select using (auth.role() = 'authenticated');

alter table common_feed_templates enable row level security;
create policy "select common feed templates" on common_feed_templates for select using (auth.role() = 'authenticated');

alter table common_feed_items enable row level security;
create policy "select common feed items" on common_feed_items for select using (auth.role() = 'authenticated');

-- Returns the closest-matching CUSTOM feed(s) for a given user + ticker + embedding.
-- similarity is 1 - cosine_distance, so higher = more similar (range ~0 to 1).
-- Scoped to feed_type = 'custom' - common feeds are classified once per ticker via
-- common_feed_templates/common_feed_items instead, and must never be matched here too,
-- or every article would re-trigger a per-user LLM call the common-feed path exists to
-- avoid.
create or replace function match_feeds(
  query_embedding vector(384),
  match_user_id uuid,
  match_ticker text,
  match_count int default 3
)
returns table (
  id uuid,
  feed_name text,
  feed_description text,
  match_threshold float,
  last_classified_at timestamptz,
  similarity float
)
language sql stable
as $$
  select
    feeds.id,
    feeds.feed_name,
    feeds.feed_description,
    feeds.match_threshold,
    feeds.last_classified_at,
    1 - (feeds.description_embedding <=> query_embedding) as similarity
  from feeds
  where feeds.user_id = match_user_id
    and feeds.ticker = match_ticker
    and feeds.feed_type = 'custom'
  order by feeds.description_embedding <=> query_embedding
  limit match_count;
$$;

-- Returns the closest-matching common feed template(s) for a given ticker + embedding.
-- Ticker-agnostic (common_feed_templates aren't scoped to a ticker), used once per
-- ticker_news row regardless of how many users have a common feed on that ticker.
create or replace function match_common_feed_templates(
  query_embedding vector(384),
  match_count int default 1
)
returns table (
  id uuid,
  name text,
  description text,
  match_threshold float,
  similarity float
)
language sql stable
as $$
  select
    common_feed_templates.id,
    common_feed_templates.name,
    common_feed_templates.description,
    common_feed_templates.match_threshold,
    1 - (common_feed_templates.description_embedding <=> query_embedding) as similarity
  from common_feed_templates
  order by common_feed_templates.description_embedding <=> query_embedding
  limit match_count;
$$;

-- Unions each user's own custom feed_items with the shared common_feed_items their
-- 'common' feeds link to, so the frontend can query one thing for a user's whole alert
-- feed. security_invoker is required, not optional: without it Postgres evaluates RLS as
-- the view's (privileged) owner rather than the querying user, which would let any
-- authenticated client see every user's feed items through this view. With it, the joins
-- back to `feeds` are filtered by feeds' own "select own feeds" policy, which is what
-- actually scopes the otherwise-broadly-readable common_feed_items down to just this
-- user's own common feeds.
create view user_feed_items with (security_invoker = true) as
  select
    feed_items.id,
    feed_items.content_summary,
    feed_items.source_url,
    feed_items.created_at,
    feeds.feed_name,
    feeds.ticker
  from feed_items
  join feeds on feeds.id = feed_items.feed_id
  where feeds.feed_type = 'custom'
  union all
  select
    common_feed_items.id,
    common_feed_items.content_summary,
    common_feed_items.source_url,
    common_feed_items.created_at,
    feeds.feed_name,
    feeds.ticker
  from common_feed_items
  join feeds
    on feeds.common_feed_template_id = common_feed_items.common_feed_template_id
   and feeds.ticker = common_feed_items.ticker
  where feeds.feed_type = 'common';

grant select on user_feed_items to authenticated;
