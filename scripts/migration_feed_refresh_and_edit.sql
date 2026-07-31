-- Incremental migration for an existing Supabase project that already has
-- migration_common_feeds_and_ticker_news.sql applied. Paste into the Supabase SQL editor
-- and run once. (For a brand-new project, just run the full schema.sql instead.)

-- Set by the user's "Refresh" action after editing a custom feed's description or
-- threshold: the next pipeline run wipes this feed's feed_items and re-matches its
-- entire ticker_news history under the feed's current settings, then clears this flag.
alter table feeds add column if not exists needs_rematch boolean not null default false;
