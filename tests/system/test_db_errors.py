"""
API-level tests for transient database failures: api/main.py's
@app.exception_handler(DatabaseUnavailableError) and ask_endpoint's bookkeeping. Faked graph and
DB writes (ask_client fixture, tests/system/conftest.py). Marked slow: imports the whole app.
"""
import pytest

from db.errors import DatabaseUnavailableError

pytestmark = pytest.mark.slow


def _ask(client):
    return client.post("/api/ask", json={"question": "What was ANZ's FY2025 profit?", "thread_id": "t-1"},
                       headers={"Authorization": "Bearer fake-token"})


def test_failed_read_returns_503_try_again(ask_client):
    client, graph, insert_trace = ask_client
    graph.invoke.side_effect = DatabaseUnavailableError("match_ticker_news_for_embedding", outcome_uncertain=False)

    resp = _ask(client)

    assert resp.status_code == 503
    body = resp.json()
    assert body["detail"] == "The database is temporarily unavailable. Please try again shortly."
    assert body["request_id"] == resp.headers["X-Request-ID"]
    assert insert_trace.call_args.kwargs["decline_reason"] == "database_unavailable"


def test_failed_plain_insert_returns_503_with_uncertain_outcome_message(ask_client):
    client, graph, _ = ask_client
    graph.invoke.side_effect = DatabaseUnavailableError("create_feed", outcome_uncertain=True)

    resp = _ask(client)

    assert resp.status_code == 503
    assert resp.json()["detail"] == ("We couldn't confirm whether your request was completed. "
                                     "Please check before trying again.")


def test_lost_trace_row_does_not_fail_a_good_answer(ask_client):
    # insert_request_trace is best-effort: returns None when the DB is down. The user still
    # gets the answer, and no steps are written against a missing parent row.
    from langchain_core.messages import AIMessage

    import api.main as main

    client, graph, insert_trace = ask_client
    insert_trace.return_value = None
    graph.invoke.return_value = {"category": "conduct_analysis", "ticker": "ANZ.AX", "references": [],
                                 "messages": [AIMessage(content="ANZ's profit was ...")]}

    resp = _ask(client)

    assert resp.status_code == 200
    assert resp.json()["answer"] == "ANZ's profit was ..."
    main.insert_request_trace_steps.assert_not_called()
