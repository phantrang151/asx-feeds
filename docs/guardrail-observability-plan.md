# Guardrail Observability Plan

## Current issue

The research-order guardrail correctly blocks calls to sources such as `search_financial_reports_tool` until `search_internal_news_tool` has run. However, the blocked response is currently treated as ordinary tool evidence:

1. `_require_internal_news()` returns a plain text message.
2. `_extract_tool_evidence()` converts tool responses without artifacts into evidence.
3. The evidence is passed through synthesis and can appear in the user's references.

The agent needs to see the control message, but the user should not see it as evidence or a citation.

## Implementation plan

### 1. Mark internal tool results

Update `tools/react_tools.py` so blocked results carry machine-readable metadata:

```json
{
  "content": "This source is unavailable until internal news is searched.",
  "visibility": "internal",
  "outcome": "blocked",
  "reason": "research_order"
}
```

The agent should still receive a concise correction message. The metadata must identify that the result is control information, not research evidence.

### 2. Filter internal results from user output

Update `agent/chat/analysis_node.py` so `_extract_tool_evidence()` and the reference-building path exclude results where:

```python
visibility == "internal"
```

Internal events may remain available to the model and must remain in the audit trace. They must not be passed into the user-facing `references` list.

### 3. Capture complete tool events

Extend `agent/guardrails/tracer.py` so each tool event records:

- tool name
- sanitized tool input or an input hash
- outcome: `succeeded`, `blocked`, `failed`, or `empty`
- blocked reason, when applicable
- result summary
- duration
- ordered step index

The tracer already records names such as `tool:search_financial_reports_tool`, but successful results and tool inputs are not currently captured consistently.

### 4. Persist audit details

Use `request_trace_steps` as the canonical per-request event stream. Extend `result` or add dedicated columns through a migration in `schema.sql` and `scripts/`.

Example result payload:

```json
{
  "outcome": "blocked",
  "visibility": "internal",
  "reason": "internal_news_required",
  "input": {
    "ticker": "CBA.AX",
    "query_hash": "..."
  }
}
```

Keep the full question and final answer in `request_trace`, but avoid duplicating full article text in every step event. Do not log API keys, credentials, or unnecessary sensitive content.

### 5. Record intercepted guardrail events

When a tool is blocked before its underlying search/database function executes, still record an event such as:

```text
tool:search_financial_reports_tool
outcome: blocked
reason: internal_news_required
```

This makes the sequence auditable even though no external source was queried.

### 6. Add evaluation queries

Add admin/evaluation support for:

- blocked financial-report calls before internal news
- external-news calls before internal news
- whether the agent corrected the sequence afterward
- requests with no relevant target-company news
- tool-call sequences by request
- failed, empty, and timed-out tools

Useful metrics include ordering-violation rate, correction rate, blocked-call count, and tool failure rate.

### 7. Support replay and rollback

Treat request traces as append-only audit records. Store enough metadata to reproduce a request safely:

- model name/version
- prompt version
- tool name
- sanitized tool arguments
- database/RPC name where relevant
- timestamp
- outcome
- final answer
- evidence IDs

For semantic-memory writes, add a memory version or change record so an incorrect memory write can be reverted without deleting the request history.

### 8. Add regression tests

Cover these cases:

- A blocked tool message is available to the agent but absent from `references`.
- The blocked attempt is present in `request_trace_steps`.
- The trace records the correct tool name and reason.
- Successful research tools remain valid evidence.
- Failed or empty tools are logged but do not become citations.
- A complete tool sequence can be reconstructed in order.

## Recommended rollout

1. Implement internal-result metadata and user-reference filtering.
2. Add tracer fields and persistence migration.
3. Add blocked/success/failure outcome tests.
4. Add admin sequence and evaluation queries.
5. Add semantic-memory versioning only if replay/rollback is required for memory writes.

The smallest first change is the visibility marker plus filtering. The full observability change should build on the existing `request_trace` and `request_trace_steps` tables rather than introducing a separate logging system.
