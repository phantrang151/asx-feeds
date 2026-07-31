-- Incremental migration for an existing Supabase project that already has the
-- pre-common-feeds schema.sql applied. Paste into the Supabase SQL editor and run once.
-- (For a brand-new project, just run the full schema.sql instead - this file only
-- covers the delta.)

create table if not exists common_feed_templates (
  id uuid primary key default gen_random_uuid(),
  name text not null unique,
  description text not null,
  description_embedding vector(384) not null,
  -- See schema.sql for why this is lower than a custom feed's threshold.
  match_threshold float not null default 0.22,
  created_at timestamptz not null default now()
);

alter table feeds add column if not exists last_classified_at timestamptz;
alter table feeds add column if not exists feed_type text not null default 'custom' check (feed_type in ('common', 'custom'));
alter table feeds add column if not exists common_feed_template_id uuid references common_feed_templates(id);

create table if not exists ticker_news (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  title text not null,
  publisher text,
  source_url text,
  published_at timestamptz,
  content_embedding vector(384) not null,
  common_classified_at timestamptz,
  created_at timestamptz not null default now(),
  unique (ticker, source_url)
);

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

create index if not exists ticker_news_embedding_idx
  on ticker_news using ivfflat (content_embedding vector_cosine_ops);
create index if not exists ticker_news_ticker_idx
  on ticker_news (ticker, created_at);
create index if not exists common_feed_items_embedding_idx
  on common_feed_items using ivfflat (content_embedding vector_cosine_ops);

alter table pipeline_runs add column if not exists common_items_classified int not null default 0;

alter table ticker_news enable row level security;
create policy "select ticker news" on ticker_news for select using (auth.role() = 'authenticated');

alter table common_feed_templates enable row level security;
create policy "select common feed templates" on common_feed_templates for select using (auth.role() = 'authenticated');

alter table common_feed_items enable row level security;
create policy "select common feed items" on common_feed_items for select using (auth.role() = 'authenticated');

-- match_feeds' RETURNS TABLE shape is changing (new last_classified_at output column),
-- and CREATE OR REPLACE FUNCTION can't change an existing function's return signature -
-- it has to be dropped first.
drop function if exists match_feeds(vector, uuid, text, integer);

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

drop view if exists user_feed_items;
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
