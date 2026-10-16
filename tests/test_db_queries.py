from sys import exc_info
from unittest.mock import patch, MagicMock
import pytest
import httpx
from postgrest.exceptions import APIError
import logging
from db.queries import upsert_ticker_news


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
        with pytest.raises(Exception) as exc_info:
            upsert_ticker_news(rows)

    assert "Max attempts reached" in str(exc_info.value)
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

    assert "Non-retriable exception:" in str(exc_info.value)
    assert mock_execute.call_count == 1