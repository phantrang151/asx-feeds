"""
API-level tests for an LLM whose structured output stays unparseable after repair and a retry
(router, output guardrail): api/main.py's @app.exception_handler(StructuredOutputError). Faked
graph and DB writes (ask_client fixture, tests/system/conftest.py). Marked slow: imports the app.
"""
import pytest

from agent.shared.structured_output import StructuredOutputError

pytestmark = pytest.mark.slow

DETAIL = "We ran into a technical problem while processing your request. Please try again shortly."


def _ask(client):
    return client.post("/api/ask", json={"question": "What was ANZ's FY2025 profit?", "thread_id": "t-1"},
                       headers={"Authorization": "Bearer fake-token"})


def test_unparseable_output_returns_a_technical_problem_message(ask_client):
    client, graph, _ = ask_client
    graph.invoke.side_effect = StructuredOutputError("Router", {"garbage": 1}, attempts=2)

    resp = _ask(client)

    assert resp.status_code == 500
    body = resp.json()
    assert body["detail"] == DETAIL
    assert body["request_id"] == resp.headers["X-Request-ID"]


def test_failure_is_traced_and_the_raw_output_logged(ask_client, caplog):
    client, graph, insert_trace = ask_client
    graph.invoke.side_effect = StructuredOutputError("AdviceJudgment", {"garbage": 1}, attempts=2)

    _ask(client)

    assert insert_trace.call_args.kwargs["status"] == "error"
    assert insert_trace.call_args.kwargs["decline_reason"] == "structured_output_error"
    assert "Unparseable AdviceJudgment output" in caplog.text and "garbage" in caplog.text
