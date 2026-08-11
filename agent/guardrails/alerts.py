from config import (
    TOKEN_CEILING_PER_REQUEST,
    TOKEN_CEILING_PER_USER_PER_DAY,
    REACT_RECURSION_LIMIT,
    ALERT_LATENCY_MS,
)


def evaluate_alerts(request_tokens: "int | None", daily_tokens_after: "int | None", step_count: int, duration_ms: int) -> list[dict]:
    """
    Checks one finished request's metrics against the four ALERT thresholds (see
    config.py) and returns the ops_alerts rows to insert - empty if none tripped.

    Deliberately reuses the existing hard guardrail ceilings for three of the four
    (cost_per_request, cost_per_user_per_day, step_count) rather than a separate,
    earlier warning tier - a request that trips one of these has, by definition,
    already been aborted/blocked by TokenBudgetCallback/DailyTokenBudgetCallback/
    GraphRecursionError, so this only turns that existing block into a queryable row
    instead of adding a new, independent kind of block. latency has no matching
    guardrail at all (nothing today aborts a slow request), so ALERT_LATENCY_MS is a
    pure observability signal, not an echo of an existing block.

    `daily_tokens_after` is the user's trailing-day total AFTER this request (what
    enforce_daily_token_budget would check on the user's NEXT request) - None if this
    request never called an LLM (nothing to sum).
    """
    alerts = []

    if request_tokens is not None and request_tokens >= TOKEN_CEILING_PER_REQUEST:
        alerts.append(
            {"alert_type": "cost_per_request", "threshold": TOKEN_CEILING_PER_REQUEST, "actual_value": request_tokens}
        )

    if daily_tokens_after is not None and daily_tokens_after >= TOKEN_CEILING_PER_USER_PER_DAY:
        alerts.append(
            {
                "alert_type": "cost_per_user_per_day",
                "threshold": TOKEN_CEILING_PER_USER_PER_DAY,
                "actual_value": daily_tokens_after,
            }
        )

    if duration_ms >= ALERT_LATENCY_MS:
        alerts.append({"alert_type": "latency", "threshold": ALERT_LATENCY_MS, "actual_value": duration_ms})

    # step_count (tool calls) isn't directly comparable to REACT_RECURSION_LIMIT (each
    # tool call is ~2 of that limit's LangGraph super-steps - see the matching comment
    # on REACT_RECURSION_LIMIT in config.py), so this alert fires on the ceiling
    # halved rather than on step_count == REACT_RECURSION_LIMIT, which step_count
    # could never actually reach.
    step_ceiling = REACT_RECURSION_LIMIT // 2
    if step_count >= step_ceiling:
        alerts.append({"alert_type": "step_count", "threshold": step_ceiling, "actual_value": step_count})

    return alerts
