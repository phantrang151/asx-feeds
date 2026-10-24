"""Tests for the request-id middleware (api/request_id.py) and its logging integration
(tools/logger.py). Uses a tiny app with the same middleware order as api/main.py - a catch-all
500 middleware inside, add_request_id outside - so it runs in milliseconds without importing the
full application (models, DB client)."""

import asyncio
import logging
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient
from starlette.middleware.base import BaseHTTPMiddleware

from api.request_id import REQUEST_ID_HEADER, add_request_id
from tools.logger import RequestIdFilter, request_id_var

test_logger = logging.getLogger("tests.request_id")


class CatchAll(BaseHTTPMiddleware):
    """Stand-in for api/main.py's UnhandledExceptionMiddleware (same behaviour)."""

    async def dispatch(self, request, call_next):
        try:
            return await call_next(request)
        except Exception:
            return JSONResponse(status_code=500, content={"detail": "Internal server error",
                                                          "request_id": request_id_var.get()})


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(CatchAll)
    app.middleware("http")(add_request_id)  # added last -> outermost, as in api/main.py

    @app.get("/sync")
    def sync_route(request: Request):  # sync -> runs in FastAPI's threadpool
        test_logger.info("handling sync")
        return {"ctx": request_id_var.get(), "state": request.state.request_id}

    @app.get("/slow")
    async def slow_route(delay: float):
        await asyncio.sleep(delay)  # overlap concurrent requests
        return {"ctx": request_id_var.get()}

    @app.get("/boom")
    def boom():
        raise RuntimeError("unexpected")

    return app


def test_each_request_gets_a_new_valid_uuid():
    client = TestClient(_app())
    ids = [client.get("/sync").headers[REQUEST_ID_HEADER] for _ in range(5)]
    assert len(set(ids)) == 5
    assert all(uuid.UUID(i).version == 4 for i in ids)


def test_id_is_visible_inside_the_endpoint_and_matches_the_header():
    resp = TestClient(_app()).get("/sync")
    body = resp.json()
    assert body["ctx"] == body["state"] == resp.headers[REQUEST_ID_HEADER]


def test_client_supplied_header_is_ignored():
    resp = TestClient(_app()).get("/sync", headers={REQUEST_ID_HEADER: "evil\ninjected-log-line"})
    assert resp.headers[REQUEST_ID_HEADER] != "evil\ninjected-log-line"
    uuid.UUID(resp.headers[REQUEST_ID_HEADER])


def test_unhandled_error_still_returns_the_id_in_header_and_body():
    resp = TestClient(_app(), raise_server_exceptions=False).get("/boom")
    assert resp.status_code == 500
    assert resp.json()["request_id"] == resp.headers[REQUEST_ID_HEADER]


def test_concurrent_requests_keep_their_own_ids():
    async def run():
        transport = httpx.ASGITransport(app=_app())
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # earlier requests sleep longer, so they finish after later ones started
            delays = [0.05 * (10 - i) for i in range(10)]
            return await asyncio.gather(*(client.get("/slow", params={"delay": d}) for d in delays))

    responses = asyncio.run(run())
    ids = [r.headers[REQUEST_ID_HEADER] for r in responses]
    assert len(set(ids)) == 10
    assert all(r.json()["ctx"] == r.headers[REQUEST_ID_HEADER] for r in responses)


def test_request_id_is_reset_after_the_request():
    TestClient(_app()).get("/sync")
    assert request_id_var.get() == "-"


def test_log_lines_written_during_a_request_carry_its_id():
    records = []

    class Capture(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = Capture()
    handler.addFilter(RequestIdFilter())
    test_logger.addHandler(handler)
    test_logger.setLevel(logging.INFO)
    try:
        resp = TestClient(_app()).get("/sync")
    finally:
        test_logger.removeHandler(handler)
    assert [r.request_id for r in records] == [resp.headers[REQUEST_ID_HEADER]]


def test_log_lines_outside_a_request_get_a_placeholder():
    record = logging.LogRecord("x", logging.INFO, __file__, 1, "msg", None, None)
    RequestIdFilter().filter(record)
    assert record.request_id == "-"


def test_insert_request_trace_stores_the_request_id():
    from unittest.mock import MagicMock, patch

    from db.queries import insert_request_trace

    mock = MagicMock()
    mock.table.return_value.insert.return_value.execute.return_value.data = [{"id": "row-1"}]
    with patch("db.queries.get_client", return_value=mock):
        insert_request_trace(
            request_id="11111111-1111-4111-8111-111111111111", user_id="u", thread_id="t", question="q",
            ticker=None, category=None, status="completed", decline_reason=None,
            input_guardrail_regex_matched=None, input_guardrail_llm_is_advice=None,
            output_guardrail_regex_matched=None, output_guardrail_llm_is_advice=None,
            evidence_count=None, step_count=0, total_tokens=None, total_duration_ms=1,
        )
    row = mock.table.return_value.insert.call_args.args[0]
    assert row["request_id"] == "11111111-1111-4111-8111-111111111111"
    assert "id" not in row  # the primary key is still generated by the database
