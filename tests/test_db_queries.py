from sys import exc_info
from unittest.mock import patch, MagicMock
import pytest
import httpx
from postgrest.exceptions import APIError
import logging
from db.errors import DatabaseUnavailableError
from db.queries import upsert_ticker_news


@pytest.fixture(autouse=True)
def no_retry_sleep():
    """run() backs off between retries (0.5 s, 1 s) - not worth waiting for in unit tests."""
    with patch("db.queries.time.sleep"):
        yield


def test_client_timeout_retry(caplog):     
    rows = [{}]
    mock = MagicMock()
    mock_execute = mock.table.return_value.upsert.return_value.execute
    mock_execute.side_effect = [
        httpx.TimeoutException("Timeout occurred while executing upsert_ticker_news."),
        MagicMock()
    ]
    with patch('db.queries.get_client', return_value=mock) as mock_client:           
        with caplog.at_level(logging.ERROR):
            result = upsert_ticker_news(rows)

    assert result is None
    assert mock_execute.call_count == 2


def test_db_timeout_retry(caplog):
        
    rows = [{}]
    db_error = APIError({
        "code": "PGRST003",
        "message": "Timeout occurred while executing upsert_ticker_news.",
        "details": None,
        "hint": None
    })

    mock = MagicMock()
    mock_execute = mock.table.return_value.upsert.return_value.execute
    mock_execute.side_effect = [
        db_error,
        MagicMock()
    ]
    with patch('db.queries.get_client', return_value=mock) as mock_client:           
        with caplog.at_level(logging.ERROR):
            result = upsert_ticker_news(rows)

    assert result is None
    assert mock_execute.call_count == 2


def test_3_retry(caplog):
        
    rows = [{}]
    db_error = APIError({
        "code": "PGRST003",
        "message": "Timeout occurred while executing upsert_ticker_news.",
        "details": None,
        "hint": None
    })

    client_error = httpx.TimeoutException("Timeout occurred while executing upsert_ticker_news.")

    mock = MagicMock()
    mock_execute = mock.table.return_value.upsert.return_value.execute
    mock_execute.side_effect = [
        db_error,
        client_error,
        db_error
    ]
    with patch('db.queries.get_client', return_value=mock) as mock_client:           
        with pytest.raises(DatabaseUnavailableError) as exc_info:
            upsert_ticker_news(rows)

    # Retries exhausted -> the app's own error, which api/main.py turns into a 503.
    # An upsert is idempotent, so the outcome is known (not completed), not uncertain.
    assert exc_info.value.outcome_uncertain is False
    assert mock_execute.call_count == 3


def test_non_retriable_error(caplog):
        
    rows = [{}]
    unknown_error = Exception("Non-retriable exception")
    
    mock = MagicMock()
    mock_execute = mock.table.return_value.upsert.return_value.execute
    mock_execute.side_effect = unknown_error

    with patch('db.queries.get_client', return_value=mock) as mock_client:           
        with pytest.raises(Exception) as exc_info:
            result = upsert_ticker_news(rows)

    # Non-retriable errors are raised unchanged (no retry, no wrapping), keeping their real
    # type for the API's error handlers / UnhandledExceptionMiddleware.
    assert exc_info.value is unknown_error
    assert mock_execute.call_count == 1