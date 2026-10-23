"""
Automated tests for LLM connection failures - an API timeout or a failed connection to the model -
handled app-wide by api/main.py's @app.exception_handler(APIConnectionError) as a 503 "try again".

Two families of Anthropic errors exist: APIStatusError (the model answered with an error status,
e.g. 429 / overloaded - handled by anthropic_error_handler) and APIConnectionError (no answer came
back at all: timeout, network). These tests cover the second family.

The graph is faked to raise the error, so no real LLM, network or DB call is made (ask_client
fixture, tests/system/conftest.py). Marked slow: importing api.main loads the whole app.
"""
import httpx
import pytest
from anthropic import APIConnectionError, APITimeoutError

pytestmark = pytest.mark.slow

_ANTHROPIC_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")
TIMEOUT_DETAIL = "The AI model is taking too long to respond. Please try again shortly."
CONNECTION_DETAIL = "Unable to connect to the AI model. Please try again shortly."


def _ask(client):
    return client.post("/api/ask", json={"question": "What was ANZ's FY2025 profit?", "thread_id": "t-1"},
                       headers={"Authorization": "Bearer fake-token"})


def test_api_timeout_returns_503_with_a_try_again_message(ask_client):
    client, graph, _ = ask_client
    graph.invoke.side_effect = APITimeoutError(request=_ANTHROPIC_REQUEST)

    resp = _ask(client)

    assert resp.status_code == 503
    assert resp.json()["detail"] == TIMEOUT_DETAIL


def test_the_timeout_langchain_actually_raises_is_also_caught(ask_client):
    # ChatAnthropic wraps the SDK error in its own class (verified with a real call): it is an
    # APITimeoutError AND langchain's provider-neutral ModelTimeoutError. Test the real class,
    # so a future change to how LangChain wraps it can't silently bypass the handler.
    from langchain_anthropic.chat_models import AnthropicTimeoutError

    client, graph, _ = ask_client
    graph.invoke.side_effect = AnthropicTimeoutError(request=_ANTHROPIC_REQUEST)

    resp = _ask(client)

    assert resp.status_code == 503
    assert resp.json()["detail"] == TIMEOUT_DETAIL


def test_connection_failure_returns_503_with_a_connection_message(ask_client):
    client, graph, _ = ask_client
    graph.invoke.side_effect = APIConnectionError(request=_ANTHROPIC_REQUEST, message="network is unreachable")

    resp = _ask(client)

    assert resp.status_code == 503
    assert resp.json()["detail"] == CONNECTION_DETAIL


def test_error_response_keeps_the_request_id_header(ask_client):
    # The handler runs inside the middleware stack, so the 503 still carries X-Request-ID
    # (and CORS headers) - the user can quote it when reporting the failure.
    client, graph, _ = ask_client
    graph.invoke.side_effect = APITimeoutError(request=_ANTHROPIC_REQUEST)

    resp = _ask(client)

    assert resp.status_code == 503
    assert resp.headers["X-Request-ID"]


def test_failed_request_is_still_traced(ask_client):
    # ask_endpoint's `except Exception: ... raise` records the trace before the handler answers.
    client, graph, insert_trace = ask_client
    graph.invoke.side_effect = APITimeoutError(request=_ANTHROPIC_REQUEST)

    resp = _ask(client)

    trace = insert_trace.call_args.kwargs
    assert trace["status"] == "error"
    assert trace["request_id"] == resp.headers["X-Request-ID"]


def test_handler_covers_every_endpoint_not_just_ask(ask_client):
    # The point of an app-wide handler: a timeout in any endpoint gets the same 503.
    # A throwaway route stands in for "some other endpoint that calls the LLM".
    import api.main as main

    client, _, _ = ask_client

    def other_endpoint():
        raise APITimeoutError(request=_ANTHROPIC_REQUEST)

    main.app.add_api_route("/__test_other_llm_endpoint", other_endpoint, methods=["GET"])
    try:
        resp = client.get("/__test_other_llm_endpoint")
    finally:
        main.app.router.routes = [r for r in main.app.router.routes
                                  if getattr(r, "path", None) != "/__test_other_llm_endpoint"]

    assert resp.status_code == 503
    assert resp.json()["detail"] == TIMEOUT_DETAIL
