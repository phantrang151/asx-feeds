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
  similarity float
)
language sql stable
as $$
  select
    document_chunks.id,
    document_chunks.document_id,
    documents.title as document_title,
    document_chunks.content,
    1 - (document_chunks.content_embedding <=> query_embedding) as similarity
  from document_chunks
  join documents on documents.id = document_chunks.document_id
  where document_chunks.ticker = match_ticker
  order by document_chunks.content_embedding <=> query_embedding
  limit match_count;
$$;
