-- Supports "what changed in my thesis" (get_my_thesis_tool) and stops the alerts page
-- downloading every historical insight.
--
-- ticker_insights is append-only: every synthesis inserts a new row, kept as history. Both
-- readers want one user's newest snapshot(s) for a ticker, so:
--   - an index on (user_id, ticker, created_at desc) serves get_my_thesis_tool's
--     latest-vs-previous lookup and the view below;
--   - latest_ticker_insights returns only the newest row per (user, ticker) for the alerts page.
--
-- feed_summaries entries now also carry feed_id (written by synthesize_node); that needs no
-- migration, since the column is jsonb and older entries simply lack the key.
--
-- Additive only: a new index and a new view. Apply BEFORE deploying the frontend change
-- (alerts.js reads the view).

create index if not exists ticker_insights_user_ticker_created_idx
  on ticker_insights (user_id, ticker, created_at desc);

-- security_invoker is required: without it Postgres applies RLS as the view's owner, which
-- would expose every user's insights. With it, ticker_insights' "select own insights" policy
-- applies to the querying user.
create or replace view latest_ticker_insights with (security_invoker = true) as
  select distinct on (user_id, ticker) *
  from ticker_insights
  order by user_id, ticker, created_at desc;

grant select on latest_ticker_insights to authenticated;
