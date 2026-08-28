import os
from datetime import datetime, timedelta, timezone

from langsmith import Client
from langsmith.utils import LangSmithNotFoundError

LANGSMITH_PROJECT = os.getenv("LANGCHAIN_PROJECT", "default")

_EMPTY_SUMMARY = {
    "window_hours": None,
    "run_count": 0,
    "error_count": 0,
    "avg_latency_seconds": None,
    "total_tokens": 0,
    "estimated_cost_usd": None,
}


def get_langsmith_summary(hours: int = 24, start_time: datetime | None = None, end_time: datetime | None = None) -> dict:
    """
    Pulls recent run stats from LangSmith for a lightweight cost/latency/error dashboard.
    Requires LANGCHAIN_TRACING_V2=true and LANGCHAIN_API_KEY set (see .env.example) - with
    those unset, every graph call still works, it just isn't traced, and this will return
    an empty summary rather than fail.

    NOTE: LangSmith's run object fields (especially cost/token accounting) have changed
    across SDK versions - if total_tokens/total_cost come back as None even with real
    traffic, check `pip show langsmith` and LangSmith's current Run schema rather than
    assuming this code is wrong. This is intentionally a thin read layer, not a cache or
    aggregation service - it queries LangSmith fresh on every call.
    """
    client = Client()
    end = end_time or datetime.now(timezone.utc)
    since = start_time or end - timedelta(hours=hours)

    try:
        runs = list(client.list_runs(project_name=LANGSMITH_PROJECT, start_time=since, end_time=end))
    except LangSmithNotFoundError:
        # The project only exists on LangSmith's side once it has received a trace -
        # until then, "not found" means the same thing as "no runs yet".
        return {**_EMPTY_SUMMARY, "window_hours": (end - since).total_seconds() / 3600}

    if not runs:
        return {
            "window_hours": (end - since).total_seconds() / 3600,
            "run_count": 0,
            "error_count": 0,
            "avg_latency_seconds": None,
            "total_tokens": 0,
            "estimated_cost_usd": None,
        }

    latencies = [
        (r.end_time - r.start_time).total_seconds()
        for r in runs
        if r.end_time and r.start_time
    ]
    total_tokens = sum((getattr(r, "total_tokens", None) or 0) for r in runs)
    total_cost = sum((getattr(r, "total_cost", None) or 0) for r in runs)
    error_count = sum(1 for r in runs if r.error)

    return {
        "window_hours": (end - since).total_seconds() / 3600,
        "run_count": len(runs),
        "error_count": error_count,
        "avg_latency_seconds": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "total_tokens": total_tokens,
        "estimated_cost_usd": round(total_cost, 4) if total_cost else None,
    }
