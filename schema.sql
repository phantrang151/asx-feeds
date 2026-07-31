-- Run this in the Supabase SQL editor before running scripts/seed_single_user.py.
-- Covers only what's needed for the single-user news pipeline test.
-- The fuller schema (profiles, watchlist_stocks, feed_templates, documents,
-- document_chunks, financial_records) can be layered on once auth is added.

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

create table if not exists ticker_insights (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  insight_text text not null,
  based_on_feed_item_ids uuid[] not null default '{}',
  created_at timestamptz not null default now()
);

create table if not exists pipeline_runs (
  id uuid primary key default gen_random_uuid(),
  started_at timestamptz not null default now(),
  finished_at timestamptz,
  status text not null default 'running', -- running | success | partial_failure | failed
  tickers_processed int not null default 0,
  feeds_classified int not null default 0,
  common_items_classified int not null default 0,
  items_skipped int not null default 0,
  errors jsonb not null default '[]'::jsonb
);

-- Admin-only data, never queried directly from the frontend (only via the /api/admin
-- routes, which use the service_role key). RLS is enabled with no policies, so anon and
-- authenticated clients get nothing at all - defense in depth even though the frontend
-- was never going to query this table directly.
alter table pipeline_runs enable row level security;

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
