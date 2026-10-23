-- Links each request_trace row to the HTTP request id that api/request_id.py's middleware
-- generates per request - the same id returned to the client in the X-Request-ID header,
-- stamped on every log line (tools/logger.py) and attached to the LangSmith run as metadata.
-- One id then joins the response a user saw, the log file, this table and LangSmith.
--
-- Additive only: a new nullable column, so the existing primary key (id) and every foreign key
-- that points at it (request_trace_steps.request_trace_id, ops_alerts.request_trace_id) are
-- untouched, and rows written before this migration simply keep request_id = null. Not unique:
-- it's an observability lookup key, and a constraint violation must never lose a trace row.
-- Apply BEFORE deploying the code that writes the column.

alter table request_trace add column if not exists request_id uuid;

create index if not exists request_trace_request_id_idx on request_trace (request_id);

notify pgrst, 'reload schema';
