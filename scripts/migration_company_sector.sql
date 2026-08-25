-- Apply this in the Supabase SQL editor when the live companies table predates
-- the sector/industry and ASX 200 peer lookup changes.
alter table companies add column if not exists sector text;
alter table companies add column if not exists industry text;
alter table companies add column if not exists sector_fetched_at timestamptz;
alter table companies add column if not exists is_asx200 boolean not null default false;