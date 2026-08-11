import time
from contextlib import contextmanager
from typing import Optional
from uuid import UUID

from langchain_core.callbacks.base import BaseCallbackHandler


class RequestTracer(BaseCallbackHandler):
    """
    Records one entry per meaningful step of a single /api/ask request - timing,
    tokens, and a short result summary - for the request_trace_steps table (see
    schema.sql). Two capture paths, since not every step is an LLM/tool call
    LangChain fires events for:

      1. Automatic, via the callback hooks below: attach a RequestTracer instance as
         one of the `callbacks` on any .invoke() config (router, synthesis, the
         output-guardrail judge, and the ReAct loop's own internal reasoning + tool
         calls) and every LLM/tool call LangChain makes inside it is captured with no
         other code change. Pass config={"metadata": {"step_name": "..."}} alongside
         it to give a specific call site (router, synthesis, output_guardrail_llm) a
         precise name - calls with no step_name metadata (the ReAct loop's own
         internal reasoning turns) fall back to a generic default per call type; tool
         calls always use their real tool name regardless.

      2. Manual, via the `step()` context manager below - for the two guardrail
         layers that are plain regex/Python, not an LLM or tool call LangChain has
         any event for.

    Must be a FRESH instance per request (never module-level/shared) - same reasoning
    as TokenBudgetCallback in agent/guardrails/token_budget.py: concurrent requests
    would otherwise corrupt each other's step lists.
    """

    def __init__(self):
        self.steps: list[dict] = []
        self._start_times: dict[UUID, float] = {}
        self._names: dict[UUID, str] = {}

    # --- Manual path (regex guardrails) ---

    @contextmanager
    def step(self, name: str, step_type: str):
        start = time.monotonic()
        try:
            yield
        finally:
            self.steps.append(
                {
                    "step_name": name,
                    "step_type": step_type,
                    "duration_ms": round((time.monotonic() - start) * 1000),
                    "tokens": None,
                    "result": None,
                }
            )

    # --- Automatic path (LLM/tool calls) ---

    def _start(self, run_id: UUID, metadata: Optional[dict], default_name: str) -> None:
        self._start_times[run_id] = time.monotonic()
        self._names[run_id] = (metadata or {}).get("step_name", default_name)

    def _finish(self, run_id: UUID, step_type: str, tokens: Optional[int] = None, result: Optional[dict] = None) -> None:
        start = self._start_times.pop(run_id, None)
        name = self._names.pop(run_id, step_type)
        if start is None:
            # No matching _start (e.g. a run_id we never saw on_*_start for) - nothing
            # reliable to record rather than guess a duration.
            return
        self.steps.append(
            {
                "step_name": name,
                "step_type": step_type,
                "duration_ms": round((time.monotonic() - start) * 1000),
                "tokens": tokens,
                "result": result,
            }
        )

    def on_llm_start(self, serialized, prompts, *, run_id: UUID, metadata: Optional[dict] = None, **kwargs) -> None:
        self._start(run_id, metadata, "llm")

    def on_chat_model_start(self, serialized, messages, *, run_id: UUID, metadata: Optional[dict] = None, **kwargs) -> None:
        # Chat models (ChatAnthropic included) fire this instead of on_llm_start in recent
        # langchain-core - both are overridden defensively so a step is captured
        # either way, regardless of exactly which hook a given langchain-core version
        # actually calls for a chat model.
        self._start(run_id, metadata, "llm")

    def on_llm_end(self, response, *, run_id: UUID, **kwargs) -> None:
        usage = (response.llm_output or {}).get("token_usage") or {}
        self._finish(run_id, "llm", tokens=usage.get("total_tokens"))

    def on_llm_error(self, error, *, run_id: UUID, **kwargs) -> None:
        self._finish(run_id, "llm", result={"error": str(error)})

    def on_tool_start(self, serialized, input_str, *, run_id: UUID, metadata: Optional[dict] = None, **kwargs) -> None:
        # Deliberately ignores metadata["step_name"] (unlike on_llm_start/
        # on_chat_model_start below) - a config-level step_name is set on the WHOLE
        # ReAct sub-agent invocation to label its internal reasoning LLM calls (see
        # conduct_analysis_node's sub_config), and that same metadata would otherwise
        # leak onto every tool call inside it too, hiding the real tool name behind a
        # generic label. The actual tool name is always more informative anyway.
        self._start_times[run_id] = time.monotonic()
        self._names[run_id] = f"tool:{serialized.get('name', 'unknown')}"

    def on_tool_end(self, output, *, run_id: UUID, **kwargs) -> None:
        self._finish(run_id, "tool")

    def on_tool_error(self, error, *, run_id: UUID, **kwargs) -> None:
        self._finish(run_id, "tool", result={"error": str(error)})

    @property
    def step_count(self) -> int:
        """Tool calls made in the ReAct loop - what request_trace.step_count records
        and what the cost guardrail (config.REACT_RECURSION_LIMIT) bounds. Not
        len(self.steps): that also counts the router/synthesis/guardrail LLM calls
        and the two regex guardrail checks, which aren't part of what
        REACT_RECURSION_LIMIT is limiting."""
        return sum(1 for s in self.steps if s["step_type"] == "tool")
