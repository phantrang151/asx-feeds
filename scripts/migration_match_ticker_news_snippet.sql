-- Brings the deployed match_ticker_news() in line with schema.sql: return `snippet` alongside
-- `title`. The live function predated the snippet column in its result, so every caller -
-- search_internal_news_tool, search_internal_peer_news_tool (tools/react_tools.py) and the
-- insight pipeline's peer-news step - got headlines only: format_news_content(title, snippet)
-- silently fell back to the title, so the answer model never saw the article summary even though
-- matching (content_embedding = title + snippet) had used it. Found by the retrieval-config eval
-- (agent/eval/runners/run_retrieval_config_eval.py), 2026-10-15.
--
-- Postgres can't change a function's result columns with CREATE OR REPLACE, so it is dropped and
-- recreated - inside one transaction, so no caller ever sees it missing. The NOTIFY makes
-- PostgREST (Supabase's REST layer, which serves client.rpc) reload its schema cache and pick up
-- the new result shape immediately.

begin;

drop function if exists match_ticker_news(vector, text[], integer, double precision, timestamptz);

create function match_ticker_news(
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
  snippet text,
  similarity float
)
language sql stable
as $$
  with peer_news as materialized (
    select id, ticker, title, publisher, source_url, published_at, snippet, content_embedding
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
    peer_news.snippet,
    1 - (peer_news.content_embedding <=> query_embedding) as similarity
  from peer_news
  where 1 - (peer_news.content_embedding <=> query_embedding) >= similarity_threshold
  order by peer_news.content_embedding <=> query_embedding
  limit match_count;
$$;

commit;

notify pgrst, 'reload schema';
