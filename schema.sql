-- Run this in the Supabase SQL editor before running scripts/seed_single_user.py.
-- Covers only what's needed for the single-user news pipeline test.
-- The fuller schema (profiles, watchlist_stocks, feed_templates, documents,
-- document_chunks, financial_records) can be layered on once auth is added.

create extension if not exists vector;
create extension if not exists pgcrypto; -- for gen_random_uuid()

create table if not exists feeds (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  ticker text not null,
  feed_name text not null,
  feed_description text not null,
  description_embedding vector(384) not null,
  match_threshold float not null default 0.35,
  digest_enabled boolean not null default true,
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

create index if not exists feeds_embedding_idx
  on feeds using ivfflat (description_embedding vector_cosine_ops);

create index if not exists feed_items_embedding_idx
  on feed_items using ivfflat (content_embedding vector_cosine_ops);

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

-- Returns the closest-matching feed(s) for a given user + ticker + embedding.
-- similarity is 1 - cosine_distance, so higher = more similar (range ~0 to 1).
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
  similarity float
)
language sql stable
as $$
  select
    feeds.id,
    feeds.feed_name,
    feeds.feed_description,
    feeds.match_threshold,
    1 - (feeds.description_embedding <=> query_embedding) as similarity
  from feeds
  where feeds.user_id = match_user_id
    and feeds.ticker = match_ticker
  order by feeds.description_embedding <=> query_embedding
  limit match_count;
$$;
