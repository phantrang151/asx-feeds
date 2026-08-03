from groq import BadRequestError as GroqBadRequestError

# Small models doing forced tool-calling (structured output, or the ReAct loop's own tool
# calls) occasionally emit a malformed function call - Groq rejects it as a 400
# 'tool_use_failed' rather than returning a bad result. This is sampling noise (retrying
# the identical request often just succeeds), not a bug to fix by catching/ignoring; give
# up and let it propagate (surfacing as the standard Groq-error 503) after this many
# attempts.
TOOL_USE_FAILED_RETRIES = 2


def call_with_tool_use_retry(fn, retries: int = TOOL_USE_FAILED_RETRIES):
    """Calls `fn()`, retrying up to `retries` times if Groq rejects the call with
    'tool_use_failed'. Shared by every forced-tool-call site (the ReAct loop in
    conduct_analysis_node, and every LLM-judge call using with_structured_output) so they
    all get the same tolerance for this known Groq/small-model flakiness instead of each
    reimplementing it - or, as with the judge calls before this existed, not at all."""
    for attempt in range(retries + 1):
        try:
            return fn()
        except GroqBadRequestError as e:
            is_tool_use_failed = getattr(e, "body", None) and e.body.get("error", {}).get("code") == "tool_use_failed"
            if not is_tool_use_failed or attempt == retries:
                raise
