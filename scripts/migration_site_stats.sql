-- Public marketing statistics for the TickerThesis front page (stats/site_stats.py).
--
-- compute_site_stats() calculates the four headline numbers in one query; the weekly job
-- (scripts/run_weekly_job.py) stores its result as a snapshot row in site_stats, and the
-- public endpoint GET /api/public/site-stats serves the latest row - so a front-page visit
-- never runs these counts, and the numbers only move when the pipeline has run.
--
-- Additive only: a new table and a new function. Apply BEFORE deploying the code that uses them.

create table if not exists site_stats (
  id uuid primary key default gen_random_uuid(),
  computed_at timestamptz not null default now(),
  active_researchers int not null,
  feeds_created int not null,
  articles_matched int not null,
  insights_generated int not null
);
create index if not exists site_stats_computed_at_idx on site_stats (computed_at desc);

-- Same posture as pipeline_runs: RLS on with no policies, so only the backend's service_role
-- key reads or writes it. The public endpoint exposes the four numbers, never the table.
alter table site_stats enable row level security;

-- active_researchers: distinct users who asked a question, created a feed or added a ticker
--   in the last 30 days.
-- feeds_created: feeds currently tracked (custom and common) - deleted feeds drop out.
-- articles_matched: distinct news articles (by URL) matched to at least one custom or common
--   feed. A common-feed match is shared by every user on that ticker, so it counts once.
-- insights_generated: insights where at least one feed had sufficient evidence - an insight
--   built only from "not enough evidence" feeds is not counted as evidence-backed.
create or replace function compute_site_stats()
returns table (
  active_researchers int,
  feeds_created int,
  articles_matched int,
  insights_generated int
)
language sql
stable
as $$
  select
    (select count(distinct user_id)::int from (
        select user_id from api_request_log where created_at > now() - interval '30 days'
        union
        select user_id from feeds where created_at > now() - interval '30 days'
        union
        select user_id from watchlist_stocks where created_at > now() - interval '30 days'
    ) recent),
    (select count(*)::int from feeds),
    (select count(*)::int from (
        select source_url from custom_feed_items where source_type = 'news' and source_url is not null
        union
        select source_url from common_feed_items where source_url is not null
    ) matched),
    (select count(*)::int from ticker_insights i
      where exists (select 1 from jsonb_array_elements(i.feed_summaries) s
                    where s->>'status' = 'sufficient'));
$$;

-- Backend only: not callable through PostgREST with the anon or a user's key.
revoke execute on function compute_site_stats() from public, anon, authenticated;
grant execute on function compute_site_stats() to service_role;

notify pgrst, 'reload schema';
