-- Lets the front page read the site_stats snapshot straight from Supabase (anon key) instead
-- of through GET /api/public/site-stats. The backend scales to zero, so on a cold start the
-- front-page numbers took ~5s to appear; Supabase answers immediately.
--
-- site_stats holds only the four public counts plus their timestamp, so read access for
-- everyone exposes nothing new. Writes stay service_role only (no insert/update/delete policy).
--
-- Additive and safe to rerun. Apply BEFORE deploying the frontend that reads the table.

drop policy if exists "public read site stats" on site_stats;
create policy "public read site stats" on site_stats for select to anon, authenticated using (true);
grant select on site_stats to anon, authenticated;
