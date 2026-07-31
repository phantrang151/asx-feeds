-- Incremental migration for an existing Supabase project that already has
-- migration_feed_refresh_and_edit.sql applied. Paste into the Supabase SQL editor and
-- run once. (For a brand-new project, just run the full schema.sql instead.)

create table if not exists documents (
  id uuid primary key default gen_random_uuid(),
  ticker text not null,
  title text not null,
  source_type text not null check (source_type in ('file', 'link')),
  source_url text,
  storage_path text,
  status text not null default 'processing' check (status in ('processing', 'ready', 'failed')),
  error text,
  uploaded_by uuid not null references auth.users(id),
  created_at timestamptz not null default now()
);

create table if not exists document_chunks (
  id uuid primary key default gen_random_uuid(),
  document_id uuid not null references documents(id) on delete cascade,
  ticker text not null,
  chunk_index int not null,
  content text not null,
  content_embedding vector(384) not null,
  created_at timestamptz not null default now()
);

create index if not exists document_chunks_embedding_idx
  on document_chunks using ivfflat (content_embedding vector_cosine_ops);
create index if not exists document_chunks_ticker_idx on document_chunks (ticker);
create index if not exists documents_ticker_idx on documents (ticker, created_at);

create or replace function get_document_chunk_counts(doc_ticker text)
returns table (document_id uuid, chunk_count bigint)
language sql stable
as $$
  select document_chunks.document_id, count(*) as chunk_count
  from document_chunks
  where document_chunks.ticker = doc_ticker
  group by document_chunks.document_id;
$$;

alter table documents enable row level security;
alter table document_chunks enable row level security;
