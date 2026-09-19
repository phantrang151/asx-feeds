# Test Case Catalog

21 unit, integration, and system test cases for the backend - each tied to a specific
finding from the architecture audit (coupling, testing, error handling, observability,
state/data integrity) or a currently-untested piece of real logic, not generic coverage.

Design only - no test code written yet. See "Sequencing" at the bottom before starting
implementation.

**Correctness vs. quality:** these cases catch *correctness* regressions - crashes,
duplicate rows, wrong status codes. Prompt-enhancement work is validated separately,
against the eval fixtures in `agent/eval/*` (groundedness, completeness, relevance) -
same before/after discipline, different axis.

**Implementation status:** U1-U6 and I8 are implemented (`tests/`) and wired into CI
(`.github/workflows/test.yml`, runs on every push/PR, no secrets required). U7, I1-I7,
and all of S1-S6 are still design-only - each needs either a small refactor (U7) or a
decision on test-database strategy (everything else) before it can be written. See
"Remaining tasks" at the bottom.

## Layer 1: Unit (pure logic, no I/O)

Fast, deterministic, safe to run on every commit.

| ID | Case | Target | Assert | Priority |
|---|---|---|---|---|
| U1 | Confusion-matrix arithmetic | `agent/eval/confusion_matrix.py::score_binary` | Known tp/fp/tn/fn rows -> exact TPR/FPR; all-bad and all-clean sets -> the "no positives"/"no negatives" branch returns `None`, not a divide-by-zero. | Med |
| U2 | Threshold boundary | `agent/eval/runners/run_classification_eval.py::predict_label` | `similarity == threshold` counts as a match (the `>=` boundary); missing `candidate_similarity` -> `"none"`. | Med |
| U3 | Precision/recall/false-skip arithmetic | `agent/eval/runners/run_classification_eval.py::score` | A hand-built 5-row set including one skipped row and one wrong-feed row -> exact expected precision/recall/false_skip_rate. | Med |
| U4 | PR/Average-Precision correctness | `agent/eval/runners/run_classification_eval.py::compute_pr_auc` | Perfect-separation set -> `auc == 1.0`, correct best threshold; the imperfect set already hand-verified this session -> `auc == 0.5`. Values already known-good - just needs locking in. Switched from ROC-AUC to PR-AUC since real news is heavily skewed toward "none of the 3 templates," which dilutes ROC's FPR term and overstates threshold quality. | High |
| U5 | Timestamp normalization | `agent/pipelines/ingestion_steps.py::_parse_published_at` | ISO string passes through unchanged; Unix int converts to ISO; falsy input -> `None`. | Low |
| U6 | Guard state edge cases | `agent/guardrails/research_order.py::ResearchOrderGuard` | Calling `record_internal_news_result` twice with different `found` values -> last write wins; calling `authorize` again after an allow -> still allowed. | Low |
| U7 | Plan-inclusion decision | `agent/pipelines/insight_nodes.py`'s planner_node floor logic | 0 own items + `needs_reports=True` -> included; 0 items + both flags `False` -> excluded. **Needs extracting into a standalone function first** - currently entangled with the DB fetch inside `planner_node`. | Med |

## Layer 2: Integration (real DB / RPC boundary)

Against a test Supabase project. No LLM cost unless noted.

| ID | Case | Target | Assert | Priority |
|---|---|---|---|---|
| I1 | Re-run duplication | `agent/pipelines/ingestion_steps.py::classify_and_store` | Seed one feed + a few `ticker_news` rows, run once, capture `custom_feed_items` count; run again with no new news -> count must be **unchanged**. Proves the audit's top finding - expect this to fail until the watermark-per-article fix lands. | High |
| I2 | Concurrent classify race | `classify_and_store` | Two overlapping calls against the same feed -> documents the missing lock; same root cause as I1, concurrency angle. | High |
| I3 | News cache dedup | `db/queries.py::upsert_ticker_news` | Insert the same `(ticker, source_url)` twice -> exactly one row. Proves the existing unique constraint actually holds. | Med |
| I4 | eval_type constraint coverage | `db/queries.py::insert_eval_run` | Loop all 6 real `eval_type` strings through `insert_eval_run` -> none violate the DB check constraint. Would have caught this session's real constraint bug immediately, instead of via manual smoke test. | High |
| I5 | Sector-cache idempotency | `ingestion_steps.py::ensure_company_sector_cached` | Call twice with `fetch_sector_industry_live` mocked -> the live-fetch mock is called exactly once. | Med |
| I6 | Peer-ticker matching | `db/queries.py::get_peer_tickers` | Seed two same-sector companies plus one different-sector -> correct set returned, self excluded. | Med |
| I7 | Vector-match round trip | `match_ticker_news_for_embedding`, `match_document_chunks_for_embedding` | Seed a row with a known embedding, query with a near-identical vector -> returned above the similarity threshold. | Med |
| I8 | Guardrail eval as regression gate | `agent/eval/runners/run_research_order_eval.py::score_research_order` | Wrap the existing fixture run in a pytest assertion: `true_positive_rate == 1.0`, `false_positive_rate == 0.0`. No LLM cost - deterministic guard. Bridges directly into CI/CD. | High |

## Layer 3: System (full workflow, over HTTP)

FastAPI `TestClient`. LLM-touching cases marked slow/costly.

| ID | Case | Target | Assert | Priority |
|---|---|---|---|---|
| S1 | Input guardrail decline | `POST /api/ask` | Advice-seeking question ("should I buy TLS.AX") -> `200` decline-shaped response, and a `request_trace` row written with `decline_reason` set. | High |
| S2 | Plain news-lookup path | `POST /api/ask` | "What's the latest news on Telstra" -> `category == "search_news"`, correct response shape. | Med |
| S3 | Analysis path, grounded answer | `POST /api/ask` | A real "why" question -> response has `references` populated and no advice language. Real LLM call - mark slow, run less often. | Med |
| S4 | Admin auth gating, every route | all `/api/admin/*` | Loop every registered admin route: no token -> `401`; valid non-admin token -> `403`. Regression-proofs any future route that forgets the dependency. | High |
| S5 | Full user journey | ticker -> feed -> pipeline -> insight | `POST /api/tickers`, `POST /api/feeds`, `POST /api/admin/pipeline/trigger` -> a `ticker_insights` row exists for the right user/ticker. Closest thing to a true end-to-end smoke test - exercises nearly the whole system. | High |
| S6 | Rate/budget enforcement | `POST /api/ask` | Exceed the configured daily token budget or request rate -> `429`. | Med |

## Sequencing

**I4 and I8 cost nothing to run** (no LLM, no flaky network) and are the fastest wins -
write those first, wire them into CI immediately, and they're already regression gates
on day one.

**I1 and I2 should be written before the fix, not after** - as failing/characterization
tests that document the current gap, so the eventual fix has a target to turn green
rather than a bug report with no test attached.

S3 and any LLM-touching case are the ones worth gating behind a `slow`/`costly` marker
so the fast suite (unit + most integration) can run on every push, with the expensive
tier reserved for pre-merge or nightly.

## Remaining tasks

1. **Decide the test-database strategy** - blocks I1-I7 and S1, S2, S4, S5, S6. Two
   options: a dedicated test Supabase project (its URL/keys stored as GitHub secrets,
   `schema.sql` applied once), or a local Postgres+pgvector service container spun up
   fresh inside the CI job (self-contained, free, but needs `schema.sql` applied at job
   start every run). Neither is implemented - this is a real decision, not a default.
2. **Write I1-I7 and S1-S6** once the DB strategy above is picked - these are actual
   pytest files with fixtures/`conftest.py` for seeding and tearing down test data.
3. **Extract the plan-inclusion decision into a standalone function** in
   `agent/pipelines/insight_nodes.py::planner_node` before U7 can be written - currently
   entangled with the DB fetch.
4. **Decide whether `deploy-backend.yml` should require tests passing first.** Right now
   `test.yml` runs independently and reports pass/fail on the commit/PR, but nothing
   stops a deploy from proceeding if tests fail - wiring that gate is either a
   `needs:`/workflow dependency, or a branch-protection rule on `main` (repo settings,
   not a file change).
5. **Gate S3 (and any other LLM-touching case) behind the `slow` marker** once written,
   and decide its cadence (pre-merge vs. nightly) - already scaffolded in `pytest.ini`,
   just needs cases to mark.
