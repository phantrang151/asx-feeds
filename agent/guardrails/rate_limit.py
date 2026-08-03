from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from config import RATE_LIMIT_MAX_REQUESTS, RATE_LIMIT_WINDOW_MINUTES
from db.queries import count_recent_requests, log_ask_request


def enforce_rate_limit(user_id: str) -> None:
    """Raises HTTPException(429) if `user_id` has made >= RATE_LIMIT_MAX_REQUESTS
    /api/ask calls in the trailing RATE_LIMIT_WINDOW_MINUTES; otherwise logs this
    request and returns. DB-backed (api_request_log), not in-memory, so it's correct
    across process restarts/multiple backend instances - unlike the guardrails in
    agent/chat/nodes.py, this runs before the graph is even invoked, so it's a real
    HTTP error rather than a graceful in-graph decline (see app/main.py::ask_endpoint).

    Count-then-insert isn't atomic, so a concurrent burst from the same user could
    slightly exceed the limit - acceptable at this scale, same "demo-grade" tone as
    app/auth.py::require_admin's own docstring.
    """
    since = (datetime.now(timezone.utc) - timedelta(minutes=RATE_LIMIT_WINDOW_MINUTES)).isoformat()
    if count_recent_requests(user_id, since) >= RATE_LIMIT_MAX_REQUESTS:
        raise HTTPException(
            status_code=429,
            detail=(
                f"You've made too many requests - please try again in a bit "
                f"(limit: {RATE_LIMIT_MAX_REQUESTS} per {RATE_LIMIT_WINDOW_MINUTES} minutes)."
            ),
        )
    log_ask_request(user_id)
