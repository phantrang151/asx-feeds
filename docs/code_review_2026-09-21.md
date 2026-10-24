# TickerThesis Code Review — 2026-09-21

Full-codebase review of `main` (production code), high effort, 8 parallel finder agents (correctness, invariants, cross-file tracing, reuse, simplification/efficiency, altitude). Findings below are deduped and ranked by severity. Not independently re-verified after dedup — see note at bottom.

## Critical

### 1. Token-budget guardrails are dead no-ops
**File:** `agent/guardrails/token_budget.py:34` (also `agent/guardrails/tracer.py:91`)
`TokenBudgetCallback`/`RequestTracer` read `response.llm_output["token_usage"]["total_tokens"]`, a key the installed `langchain-anthropic` version never populates (real usage lives on `message.usage_metadata`).
**Impact:** `total_tokens` stays 0 on every request, so `TOKEN_CEILING_PER_REQUEST` and `TOKEN_CEILING_PER_USER_PER_DAY` can never trip, cost logging always writes 0, the admin efficiency dashboard and cost alerts are permanently empty, and the test suite stays green because `tests/test_token_budget.py` mocks the old (wrong) response shape instead of real `ChatAnthropic` output. Likely a silent regression from an earlier Groq integration.

## High

### 2. `thread_id` not validated as belonging to requesting user
**File:** `api/main.py:136`
`ask_endpoint`'s LangGraph checkpointer is keyed purely on client-supplied `thread_id` with no server-side check that it belongs to `user_id`.
**Impact:** Any authenticated user who obtains another user's `thread_id` (currently a client-generated UUID, so not practically guessable today, but nothing server-side stops it if one leaks/is logged/shared) can resume that user's private chat history via `/api/ask`.

### 3. Semantic memory namespace shared across all users
**File:** `agent/chat/analysis_node.py:93`
The semantic-memory namespace passed to langmem's `manage_memory`/`search_memory` tools is keyed only by ticker, not `(user_id, ticker)` like episodic/procedural memory are.
**Impact:** A fact the model stores while answering User A's ticker question can be retrieved by User B asking about the same ticker later, leaking content derived from User A's conversation into User B's session.

### 4. Empty-body PATCH bypasses common-feed edit block
**File:** `db/queries.py:80`
`update_feed()` falls back to `get_feed()` (ownership check only) when the updates dict is empty, skipping the `feed_type='custom'` filter that the `.update()` path enforces.
**Impact:** `PATCH /api/feeds/{common_feed_id}` with an empty or all-null body returns 200 with the common feed's row instead of the documented 404, letting a user confirm/probe a common feed's data through an endpoint meant to reject edits to it.

### 5. Duplicate feed names silently collapse insight data
**File:** `agent/pipelines/insight_nodes.py:172`
`feed_name` (user-editable, no DB or API uniqueness constraint) is used as the dict key for `items_by_feed`/`feed_embeddings`/`feed_descriptions`/`source_decisions`/`step_by_feed`.
**Impact:** Two custom feeds on the same ticker named identically (allowed by schema and API) cause one feed's classified items to be silently overwritten by the other's; the synthesized insight summarizes the wrong feed twice and drops the other feed's evidence entirely — confirmed reachable via `schema.sql` and `api/main.py`.

## Medium

### 6. Per-feed summaries bypass output guardrail
**File:** `agent/pipelines/insight_nodes.py:302`
Only the final combined `insight_text` is passed through `check_output`/`check_advice_avoidance`; each per-feed `result.summary` is stored and rendered to users (`frontend/pages/alerts.js:85`) without ever passing that check.
**Impact:** If a per-feed summarization call drifts into advice-shaped language, it ships straight to the alerts dashboard's per-feed panel with none of the double-layer (regex+judge) compliance protection the rest of the app relies on for LLM-generated recommendation text.

### 7. Narrow exception catch can 500 `/api/ask`
**File:** `agent/guardrails/citations.py:27`
`_is_reachable`'s docstring promises any exception means "not confirmed reachable, never raised," but the except clause only catches `requests.RequestException`, not `Exception` generally.
**Impact:** A citation URL that triggers a non-`RequestException` failure (e.g. a `UnicodeError`/IDNA encoding failure from a malformed host) propagates uncaught through `filter_reachable_references`, turning a successfully-generated answer into an unhandled 500.

### 8. No null-check/try-catch on expired-session submit
**File:** `frontend/components/TickerForm.js:16`
`handleSubmit` dereferences `session.access_token` with no null check and no try/catch around `fetch`, unlike the other three data-mutating components.
**Impact:** User's Supabase session expires while the tab is open; clicking "Add ticker" throws an unhandled promise rejection with zero user feedback — the button silently does nothing.

### 9. Sample dedup id collision creates audit blind spot
**File:** `monitoring/quality_sampling.py:129`
`sample_feed_combine_quality` uses a feed-combine candidate's first underlying news item id as its dedup id, per the function's own docstring admission.
**Impact:** Two different feeds on the same ticker that both match the same first news article get the same dedup id; once either is sampled, the other is permanently excluded from ever being audited — not a one-time skip but an indefinite monitoring gap.

### 10. Bare except on bucket lookup can crash startup
**File:** `db/storage.py:11`
`ensure_documents_bucket` treats every `get_bucket()` failure (network blip, auth error, transient 5xx) as "bucket doesn't exist" and calls `create_bucket()` unguarded.
**Impact:** If `get_bucket()` fails for a reason other than a missing bucket while the bucket actually exists, the unguarded `create_bucket()` call raises an uncaught "already exists" error at app startup, hiding a real connectivity/auth misconfiguration behind a confusing conflict error.

### 11. Three drifted copies of the ASX ticker regex
**File:** `api/admin.py:57`
`api/admin.py`'s `ASX_TICKER_PATTERN` (`{1,6}` chars) and `frontend/pages/admin.js`'s copy both diverge from the canonical `agent/guardrails/tickers.py` pattern (`{1,10}` chars), found independently by three separate review passes.
**Impact:** A real ASX ticker with a 7-10 character base code that `api/main.py`'s `validate_ticker()` and the chat guardrail accept gets rejected with a 422 by `/api/admin/documents/upload` and `/api/admin/pipeline/debug-planner` purely due to the narrower, unsynced regex.

## Low

### 12. Falsy-zero bug hides real $0 cost as missing
**File:** `monitoring/langsmith_summary.py:68`
`"estimated_cost_usd": round(total_cost, 4) if total_cost else None` treats a genuine `total_cost == 0.0` the same as no cost data. A time window with zero real spend shows "n/a" on the admin cost dashboard instead of "$0.00".

### 13. NULL `published_at` articles permanently unsearchable
**File:** `db/queries.py:722`
`match_ticker_news_for_embedding` wraps a Postgres RPC filtering `WHERE published_at >= news_since`; `NULL >= x` evaluates to `NULL` (not true) in SQL, excluding those rows from every match. `ingestion_steps.py`'s `_parse_published_at` legitimately returns `None` when yfinance omits both date fields (documented, non-rare), so those embedded articles become permanently invisible to search with no caller docstring flagging the exclusion.

### 14. Admin "mark reviewed" routes 500 instead of 404
**File:** `db/queries.py:981`
`mark_quality_sample_reviewed`/`mark_guardrail_sample_reviewed`/`mark_classification_sample_reviewed` do bare `result.data[0]` with no not-found guard, unlike every sibling mutation in the same file (`get_feed`, `update_feed`, `delete_feed`). A double-click or stale/raced `sample_id` causes an unhandled `IndexError` surfaced as a raw 500.

### 15. Falsy-zero bug discards epoch-0 publish date
**File:** `agent/pipelines/ingestion_steps.py:30`
`_parse_published_at` does `if not published: return None`, treating a legitimate Unix timestamp of 0 the same as a missing timestamp.

### 16. News fast-path skips the LLM advice-seeking gate
**File:** `agent/chat/nodes.py:84`
The known-shape "latest/recent news" shortcut routes straight to `search_news` on a narrow regex match, entirely skipping the router LLM call that provides the broader advice-seeking safety net. A query like "is it worth adding TLS.AX to my portfolio, show me the latest news" matches the news shortcut but not the narrow advice-seeking regexes, so it's served without ever reaching the LLM's own judgment (low severity since `search_news` only returns raw headlines).

## Reuse / Efficiency

### 17. 12 near-duplicate monitoring-sample functions
**File:** `db/queries.py:913`
`get_sampled_source_ids`/`insert_quality_samples`/`get_quality_samples`/`mark_quality_sample_reviewed` and their guardrail/classification counterparts are triplicated almost verbatim (~180 lines), differing only in table/column names. Should collapse to 4 parameterized helpers with each concrete function reduced to a 1-line wrapper.

### 18. ChatAnthropic built 7x with no shared factory
**File:** `agent/shared/synthesize.py:96`
Identical `ChatAnthropic(model=..., api_key=ANTHROPIC_API_KEY)` construction repeated across `synthesize.py`, `chat/nodes.py`, `analysis_node.py`, `insight_nodes.py` (x2), `eval/judge.py`, and `advice_check.py`. Any cross-cutting LLM-construction change needs 7 manual edits.

### 19. Independent items processed strictly sequentially
**File:** `agent/pipelines/orchestrator.py:33`
All three ingestion-pipeline phases loop over independent tickers/users/feeds one at a time for blocking LLM/I-O work, with nothing structurally preventing concurrency (each item's try/except already isolates failures). Total pipeline wall-clock scales linearly with ticker/user count x per-item LLM latency. Same pattern repeats in `insight_nodes.py`'s `execute_step_node` (per-feed) and `run_classification_eval.py`'s `classify_rows` (per-row embedding calls, despite an existing `embed_batch()` helper going unused).

---

**Note on process:** This review used 8 parallel finder agents (one per angle: correctness across 3 code areas, missing-invariant audit, cross-file caller/callee tracing, reuse, simplification/efficiency, altitude). The orchestrating agent that was supposed to dedupe and re-verify all 8 reports appears to have stalled/failed to hand back its final report after ~2 hours; the list above was deduped and ranked manually from the 8 raw agent reports instead. Most individual findings were already spot-checked by their source agent (e.g. #1 was verified against the installed `langchain_anthropic` package source, #5 against `schema.sql` and `api/main.py`), but the list as a whole has not been re-verified end-to-end. Recommend spot-checking before acting on lower-confidence items (marked "low"/"borderline" in the raw agent reports).
