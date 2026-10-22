"""Shared fixtures for the system-level tests in this folder."""
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def ask_client():
    """Yields (TestClient, graph mock, mocks of the DB writes) with /api/ask's external
    dependencies replaced."""
    from contextlib import ExitStack

    from fastapi.testclient import TestClient

    import api.main as main

    with ExitStack() as stack:
        p = lambda name, **kw: stack.enter_context(patch.object(main, name, **kw))  # noqa: E731
        p("get_user_id_from_token", return_value="user-1")
        p("enforce_rate_limit")
        p("enforce_daily_token_budget", return_value=MagicMock(total_tokens=0))
        p("log_token_usage")
        p("sum_recent_token_usage", return_value=0)
        p("evaluate_alerts", return_value=[])
        p("insert_ops_alert")
        p("filter_reachable_references", side_effect=lambda refs: refs)
        insert_trace = p("insert_request_trace", return_value={"id": "trace-1"})
        p("insert_request_trace_steps")
        graph = p("graph")
        yield TestClient(main.app, raise_server_exceptions=False), graph, insert_trace
