from unittest.mock import patch, MagicMock
import pytest
import logging
from requests.exceptions import ConnectionError
from agent.pipelines.orchestrator import run_ingestion_for_all_watchlisted_tickers
from db.queries import get_distinct_watchlisted_tickers
from tools.search import search_news

def fake_search_news(ticker: str, max_results: int = 20):
    if ticker == "TLS.AX":
        return None
    else:
        return []

def test_local_failure_isolated(caplog):
    with patch('agent.pipelines.ingestion_steps.search_news', side_effect=fake_search_news) as mock_search:
        result = run_ingestion_for_all_watchlisted_tickers()

    assert result.get('status') == 'success'
    assert mock_search.call_count == 5 # there are 5 tickers in the systems

#-----------------------------------------------------------------------------#

def fake_5_consecutive_failures(ticker: str, max_results: int = 20):
    if ticker in["TLS.AX",'CBA.AX','NAB.AX','ANZ.AX','WBC.AX']:
        return None
    else:        return []
    
test_tickers = ["TLS.AX",'CBA.AX','NAB.AX','ANZ.AX','WBC.AX','BHP.AX', 'RIO.AX', 'CSL.AX', 'WES.AX', 'WOW.AX']

def test_5_consecutive_failures(caplog):
    with patch('agent.pipelines.ingestion_steps.search_news', side_effect=fake_5_consecutive_failures) as mock_search:
        with patch('agent.pipelines.orchestrator.get_distinct_watchlisted_tickers', return_value=test_tickers):
            with caplog.at_level(logging.ERROR):
                result = run_ingestion_for_all_watchlisted_tickers()    

    assert result.get('status') == 'failed'
    assert result.get('errors') == [{"phase": "fetch_and_classify_common", "error": "System failures"}]
    assert "Pipeline failed during fetch_and_cache phase, and 5 consecutive tickers have failed. Aborting further processing." in caplog.text
    assert mock_search.call_count == 5  # Ensure that the search_news was called only once before the system failure

#-----------------------------------------------------------------------------#
test_tickers_system_error = ["CBA.AX","TLS.AX",'NAB.AX','ANZ.AX','WBC.AX','BHP.AX', 'RIO.AX', 'CSL.AX', 'WES.AX', 'WOW.AX']

def search_news_system_failure(ticker: str, max_results: int = 20):
    if ticker == "TLS.AX":
        raise ConnectionError(f"Yahoo Service not available for ticker {ticker}.")
    else:
        return []

def test_system_failure(caplog):
    with patch('agent.pipelines.ingestion_steps.search_news', side_effect=search_news_system_failure) as mock_search:
        with patch('agent.pipelines.orchestrator.get_distinct_watchlisted_tickers', return_value=test_tickers_system_error):
            with caplog.at_level(logging.ERROR):
                result = run_ingestion_for_all_watchlisted_tickers()    

    assert result.get('status') == 'failed'
    assert {"ticker": "TLS.AX", "phase": "fetch_and_cache", "error": "Yahoo Service not available for ticker TLS.AX."} in result.get('errors')
    assert "Yahoo Service not available for ticker TLS.AX." in caplog.text
    assert "Pipeline failed for TLS.AX during fetch_and_cache" in caplog.text
    assert result.get('common_items_classified') == -1
    assert result.get('feeds_classified') == -1
    assert result.get('insights_generated') == -1
    assert result.get('items_skipped') == -1
    assert mock_search.call_count == 2  # Ensure that the search_news was called only once before the system failure, it should pass the first ticker and failed on the TLS.AX

    
#-----------------------------------------------------------------------------#

def test_phase_1_aborted():
    with patch('agent.pipelines.orchestrator._fetch_and_classify_common', return_value =(-1,set())):
        with patch('agent.pipelines.orchestrator._classify_custom_feeds') as mock_custom:
            with patch('agent.pipelines.orchestrator._synthesize_insights') as mock_synthesis:
                result = run_ingestion_for_all_watchlisted_tickers()

    assert result.get('status') == 'failed'
    assert result.get('errors') == [{"phase": "fetch_and_classify_common", "error": "System failures"}]
    assert result.get('common_items_classified') == -1
    assert result.get('feeds_classified') == -1
    assert result.get('insights_generated') == -1
    assert result.get('items_skipped') == -1
    # Important behavioral assertions
    mock_custom.assert_not_called()
    mock_synthesis.assert_not_called()