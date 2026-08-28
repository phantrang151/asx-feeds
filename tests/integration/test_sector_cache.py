"""I5 (docs/test_case_catalog.md): ensure_company_sector_cached only calls yfinance
once per ticker, ever - the second call must be a pure DB read, no live fetch. The
yfinance call itself is mocked (no network dependency in this test); the DB round-trip
is real."""

from unittest.mock import patch

from db.queries import get_company_sector
from agent.pipelines.ingestion_steps import ensure_company_sector_cached


def test_second_call_does_not_refetch_live(client, test_ticker, cleanup_ticker):
    with patch(
        "agent.pipelines.ingestion_steps.fetch_sector_industry_live",
        return_value=("Financial Services", "Banks - Diversified"),
    ) as mock_fetch:
        ensure_company_sector_cached(test_ticker)
        ensure_company_sector_cached(test_ticker)

    mock_fetch.assert_called_once_with(test_ticker)

    row = get_company_sector(test_ticker)
    assert row["sector"] == "Financial Services"
    assert row["industry"] == "Banks - Diversified"
