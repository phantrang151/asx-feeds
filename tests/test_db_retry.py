"""Tests for the database retry policy in db/queries.py (run() and is_retriable_exception):
retry transient failures for reads and idempotent writes only; never retry plain INSERTs;
best-effort telemetry logs and continues. No database needed - queries are fakes."""
import ast
import logging
import re
from unittest.mock import MagicMock, patch

import httpx
import pytest
from postgrest.exceptions import APIError

from db.errors import DatabaseUnavailableError
from db.queries import is_retriable_exception, run


@pytest.fixture(autouse=True)
def no_retry_sleep():
    with patch("db.queries.time.sleep"):
        yield


def _api_error(code: str) -> APIError:
    return APIError({"code": code, "message": f"error {code}", "details": None, "hint": None})


def _query(*outcomes):
    """A fake PostgREST query whose execute() raises / returns each outcome in turn."""
    q = MagicMock()
    q.execute.side_effect = list(outcomes)
    return q


@pytest.mark.parametrize("error, expected", [
    (httpx.ReadTimeout("read timed out"), True),
    (httpx.ConnectError("connection refused"), True),
    (_api_error("PGRST003"), True),   # PostgREST pool timeout
    (_api_error("57014"), True),      # statement timeout
    (_api_error("23505"), False),     # unique violation - fails the same way every time
    (_api_error("42501"), False),     # permission denied
    (ValueError("bug"), False),
])
def test_what_counts_as_transient(error, expected):
    assert is_retriable_exception(error) is expected


def test_read_is_retried_until_it_succeeds():
    q = _query(httpx.ReadTimeout("t"), "rows")
    assert run(q, idempotent=True) == "rows"
    assert q.execute.call_count == 2


def test_idempotent_failure_after_all_retries_is_not_uncertain():
    q = _query(*[httpx.ReadTimeout("t")] * 3)
    with pytest.raises(DatabaseUnavailableError) as exc:
        run(q, idempotent=True, operation="get_feed")
    assert q.execute.call_count == 3
    assert exc.value.outcome_uncertain is False and exc.value.operation == "get_feed"


def test_plain_insert_is_never_retried_and_reports_an_uncertain_outcome():
    q = _query(httpx.ReadTimeout("t"), "would-duplicate")
    with pytest.raises(DatabaseUnavailableError) as exc:
        run(q, idempotent=False, operation="create_feed")
    assert q.execute.call_count == 1          # a retry could duplicate a row that did commit
    assert exc.value.outcome_uncertain is True


def test_best_effort_write_logs_and_returns_none(caplog):
    q = _query(httpx.ReadTimeout("t"))
    with caplog.at_level(logging.ERROR, logger="db.queries"):
        assert run(q, essential=False, operation="insert_request_trace") is None
    assert q.execute.call_count == 1
    assert "insert_request_trace" in caplog.text


def test_non_transient_error_is_raised_unchanged_without_retry():
    err = _api_error("23505")
    q = _query(err)
    with pytest.raises(APIError) as exc:
        run(q, idempotent=True)
    assert exc.value is err and q.execute.call_count == 1


def test_no_plain_insert_in_queries_is_marked_idempotent():
    # Guard for future edits: any function that does a plain .insert( (not an upsert) must not
    # opt into retries.
    src = open("db/queries.py", encoding="utf-8").read()
    offenders = []
    for f in ast.parse(src).body:
        if isinstance(f, ast.FunctionDef):
            body = ast.get_source_segment(src, f)
            if re.search(r"\.insert\(", body) and "idempotent=True" in body:
                offenders.append(f.name)
    assert offenders == []
