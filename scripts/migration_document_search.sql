-- Incremental migration for an existing Supabase project that already has
-- migration_documents.sql applied. Paste into the Supabase SQL editor and run once.
-- (For a brand-new project, just run the full schema.sql instead.)

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
